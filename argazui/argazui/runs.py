"""Run artefacts — one directory per simulation session.

WHAT A "RUN" IS
---------------
A run is one START ... STOP of one model. It gets `runs/<UTC>_<model_id>/`
containing everything needed to explain afterwards what happened:

    scenario.yaml         the procedure files that were executed, verbatim
    result.json           step-by-step pass/fail plus the acceptance criteria
    console.log           what the simulation terminal showed
    mavlink_events.jsonl  mode/arm/ack/statustext plus a 1 Hz state sample
    <NNNNNNNN>.BIN        the autopilot's own dataflash log
    params_full.txt       every parameter, taken from that log
    params_diff.txt       the ones that differ from the firmware default
    report.md / .json     the post-flight report (flightlog.py)
    versions.txt          ArduPilot SHA, Gazebo, ArgazUI, interpreter

WHY IT IS NOT `argazui/run/<model_id>/`
---------------------------------------
That directory still exists and still is SITL's working directory — it is what
keeps eeprom and logs out of the ArduPilot tree. But it is *reused* by the next
launch of the same model, so nothing in it survives. Artefacts are copied out
of it into a timestamped run directory at the end of the session; the working
directory itself is never made into the archive.

CAPTURE IS APPEND-AS-YOU-GO
---------------------------
`console.log` and `mavlink_events.jsonl` are written while the run happens, not
buffered until the end. If ArgazUI is killed mid-flight the directory still
holds everything up to that moment, which is exactly when it is most wanted.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import paths
from .flightlog import analyse, newest_log
from .i18n import t

RESULT_SCHEMA = 1

# CSI / OSC / two-character escapes. The terminal stream is full of colour and
# cursor movement from MAVProxy's console; a log file wants the text only.
_ANSI = re.compile(
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"          # CSI  ... final byte
    rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC  ... BEL or ST
    rb"|\x1b[@-Z\\-_]"                      # two-character escapes
)


def utc_stamp(when: Optional[datetime] = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def _iso(when: Optional[datetime] = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_terminal_text(data: bytes) -> str:
    text = _ANSI.sub(b"", data).decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _command_output(args: list[str], cwd: Optional[Path] = None,
                    timeout: float = 10.0) -> str:
    try:
        result = subprocess.run(args, cwd=str(cwd) if cwd else None,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(unavailable: {exc})"
    if result.returncode != 0:
        return f"(exit {result.returncode})"
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()),
                "(no output)")


def collect_versions() -> dict[str, str]:
    """Everything needed to say which software produced a run.

    A missing component is recorded as unavailable rather than omitted: a
    report that silently drops the Gazebo version reads the same whether
    Gazebo was absent or simply not asked.
    """
    from . import __version__

    ardupilot = paths.ARDUPILOT
    if (ardupilot / ".git").exists():
        sha = _command_output(["git", "-C", str(ardupilot), "rev-parse", "HEAD"])
        described = _command_output(
            ["git", "-C", str(ardupilot), "describe", "--tags", "--always", "--dirty"])
    else:
        sha = described = "(not a git checkout)"

    try:
        from pymavlink import __version__ as pymavlink_version
    except Exception:
        pymavlink_version = "(unavailable)"

    return {
        "argazui": __version__,
        "ardupilot_sha": sha,
        "ardupilot_describe": described,
        "ardupilot_root": str(ardupilot),
        "gz_sim": _command_output(["gz", "sim", "--version"]),
        "ros_distro": os.environ.get("ROS_DISTRO", "(not set in the server environment)"),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "pymavlink": pymavlink_version,
        "host": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }


class RunRecorder:
    """Collects the artefacts of one simulation session.

    Deliberately independent of FastAPI and of the terminal sessions: it takes
    bytes and dictionaries and writes files. The regression suite of phase 4
    drives the same class without a browser in sight.
    """

    def __init__(self, model: dict, root: Optional[Path] = None,
                 launch_commands: Optional[list[str]] = None,
                 work_dir: Optional[Path] = None,
                 on_log: Optional[Callable[[str], None]] = None) -> None:
        self.model = model
        self.started = datetime.now(timezone.utc)
        self.started_monotonic = self.started.timestamp()
        self.on_log = on_log or (lambda text: None)
        root = Path(root) if root else paths.RUNS_DIR
        self.run_id = f"{utc_stamp(self.started)}_{model.get('id', 'unknown')}"
        self.dir = root / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.work_dir = Path(work_dir) if work_dir else (paths.RUN_DIR / model.get("id", ""))

        self._lock = threading.Lock()
        self._console = (self.dir / "console.log").open("a", encoding="utf-8")
        self._events = (self.dir / "mavlink_events.jsonl").open("a", encoding="utf-8")
        self._procedures: list[dict] = []
        self._scenarios: list[str] = []
        self._finished = False
        self._last_state: Optional[tuple] = None

        header = [
            f"# ArgazUI run {self.run_id}",
            f"# started {_iso(self.started)}",
            f"# model   {model.get('name')} ({model.get('id')}) "
            f"[{model.get('vehicle_class')} / {model.get('method')}]",
            "",
        ]
        if launch_commands:
            header += ["# launch commands typed into the simulation terminal:"]
            header += [f"#   {line}" for line in launch_commands]
            header += [""]
        self._console.write("\n".join(header))
        self._console.flush()

    # ------------------------------------------------------------------ capture
    def console(self, data: bytes) -> None:
        """Terminal output. Called from the pty reader thread."""
        if self._finished:
            return
        text = clean_terminal_text(data)
        with self._lock:
            try:
                self._console.write(text)
                self._console.flush()
            except (ValueError, OSError):
                pass

    def event(self, payload: dict) -> None:
        """One MAVLink-derived event. Called from the link's worker thread."""
        if self._finished:
            return
        now = datetime.now(timezone.utc)
        record = {"t": round(now.timestamp() - self.started_monotonic, 2),
                  "utc": _iso(now), **payload}
        with self._lock:
            try:
                self._events.write(json.dumps(record, ensure_ascii=False) + "\n")
                self._events.flush()
            except (ValueError, OSError, TypeError):
                pass

    def add_procedure(self, procedure, result: dict, values: Optional[dict] = None) -> None:
        """Records one procedure execution and the YAML that drove it.

        The YAML is stored verbatim. That is the point of the single-source
        rule: the file in `scenario.yaml` is byte-for-byte the file the button
        ran, so a run can be reproduced without guessing which revision of the
        procedure was in effect.
        """
        entry = {
            "procedure": procedure.id,
            "name": procedure.label("en"),
            "role": procedure.role,
            "file": procedure.path.name,
            "sources": procedure.sources,
            "started_utc": _iso(),
            "values": values or result.get("values") or {},
            "result": result,
        }
        with self._lock:
            self._procedures.append(entry)
            self._scenarios.append(
                f"# ---------------------------------------------------------------\n"
                f"# executed {entry['started_utc']} — {procedure.id} ({procedure.role})\n"
                f"# inputs: {json.dumps(entry['values'], ensure_ascii=False)}\n"
                f"# outcome: {'PASSED' if result.get('ok') else 'FAILED'}\n"
                f"# source file: {procedure.path.name}\n"
                f"# ---------------------------------------------------------------\n"
                f"{procedure.raw_text.rstrip()}\n")
        self.event({"kind": "procedure", "procedure": procedure.id,
                    "role": procedure.role, "ok": bool(result.get("ok")),
                    "text": result.get("text", "")})

    # ------------------------------------------------------------------ finish
    def finish(self, report: bool = True) -> dict:
        """Closes the capture files and writes the run's own records.

        Call this *after* the simulator has exited, so the dataflash log has
        been flushed and closed. The post-flight report is generated on a
        background thread because parsing a long log takes seconds and STOP
        should not wait for it.
        """
        if self._finished:
            return self.summary()
        self._finished = True
        finished = datetime.now(timezone.utc)

        with self._lock:
            for handle in (self._console, self._events):
                try:
                    handle.close()
                except (ValueError, OSError):
                    pass

        (self.dir / "versions.txt").write_text(
            "\n".join(f"{key} = {value}" for key, value in collect_versions().items()) + "\n",
            encoding="utf-8")

        if self._scenarios:
            body = ("# Procedures executed during this run, in order and verbatim.\n"
                    "# This is the same YAML the TAKEOFF/LAND buttons and the\n"
                    "# regression suite execute — see argazui/procedures/SCHEMA.md.\n\n"
                    + "\n---\n".join(self._scenarios))
        else:
            body = ("# No procedure ran during this session. The model was started and\n"
                    "# stopped, so there is a console log, a dataflash log and a\n"
                    "# parameter set, but nothing to pass or fail.\n")
        (self.dir / "scenario.yaml").write_text(body, encoding="utf-8")

        dataflash = self._copy_dataflash()
        result = self._result(finished, dataflash)
        (self.dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        if report and dataflash:
            threading.Thread(target=self._make_report, args=(dataflash, result),
                             name=f"report-{self.run_id}", daemon=True).start()
        elif report:
            self.on_log(t("run_no_report", id=self.run_id))
        return result

    def _copy_dataflash(self) -> Optional[Path]:
        """Copies the newest `.BIN` the simulator wrote during this run.

        The `newer_than` filter is what stops a stopped-and-restarted model
        from archiving the previous session's log: the working directory is
        shared between launches and keeps every log it has ever written.
        """
        source = newest_log(self.work_dir, newer_than=self.started_monotonic - 5)
        if source is None:
            return None
        target = self.dir / source.name
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            self.on_log(f"run {self.run_id}: could not copy {source}: {exc}")
            return None
        return target

    def _result(self, finished: datetime, dataflash: Optional[Path]) -> dict:
        outcomes = [entry["result"].get("ok") for entry in self._procedures]
        if not outcomes:
            ok, status = None, "no-procedure"
        elif all(outcomes):
            ok, status = True, "passed"
        else:
            ok, status = False, "failed"

        from . import __version__
        return {
            "schema": RESULT_SCHEMA,
            "run_id": self.run_id,
            "argazui_version": __version__,
            "started_utc": _iso(self.started),
            "finished_utc": _iso(finished),
            "seconds": round(finished.timestamp() - self.started_monotonic, 1),
            "ok": ok,
            "status": status,
            "model": {key: self.model.get(key) for key in
                      ("id", "name", "vehicle_class", "method", "vehicle", "frame",
                       "param_file", "world", "env", "has_ros2")},
            "work_dir": str(self.work_dir),
            "procedures": self._procedures,
            "artefacts": {
                "console_log": "console.log",
                "mavlink_events": "mavlink_events.jsonl",
                "scenario": "scenario.yaml",
                "versions": "versions.txt",
                "dataflash": dataflash.name if dataflash else None,
            },
        }

    def _make_report(self, dataflash: Path, result: dict) -> None:
        meta = {
            "run_id": self.run_id,
            "argazui_version": result["argazui_version"],
            "model_id": self.model.get("id"),
            "model_name": self.model.get("name"),
            "procedures": [entry["procedure"] for entry in self._procedures],
            "status": result["status"],
        }
        try:
            analyse(dataflash, self.dir, meta=meta)
        except Exception as exc:                     # a bad log must not be fatal
            (self.dir / "report.md").write_text(
                f"# Flight report — {self.run_id}\n\n"
                f"The dataflash log `{dataflash.name}` could not be analysed:\n\n"
                f"```\n{exc}\n```\n\n"
                f"The log itself is still in this directory and can be opened with "
                f"`MAVExplorer.py {dataflash.name}`.\n", encoding="utf-8")
            self.on_log(t("run_failed", err=exc))
            return
        self.on_log(t("run_report_ready", id=self.run_id))

    def summary(self) -> dict:
        path = self.dir / "result.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"run_id": self.run_id, "status": "running"}


# --------------------------------------------------------------------------- browsing
def _badge(result: dict) -> str:
    return result.get("status") or ("passed" if result.get("ok") else "failed")


def list_runs(root: Optional[Path] = None, limit: int = 200) -> list[dict]:
    """Every run directory, newest first, described from its own result.json.

    A directory without a `result.json` is a session that is still running or
    one that ArgazUI was killed during. It is listed as `incomplete` rather
    than hidden, because a crashed run is precisely the one worth opening.
    """
    root = Path(root) if root else paths.RUNS_DIR
    if not root.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        out.append(describe_run(entry))
        if len(out) >= limit:
            break
    return out


def describe_run(directory: Path) -> dict:
    """The listing row for one run directory."""
    directory = Path(directory)
    result: dict = {}
    path = directory / "result.json"
    if path.is_file():
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result = {}

    dataflash = result.get("artefacts", {}).get("dataflash")
    if not dataflash:
        found = sorted(directory.glob("*.BIN"))
        dataflash = found[0].name if found else None

    procedures = [
        {"id": entry.get("procedure"), "role": entry.get("role"),
         "ok": bool((entry.get("result") or {}).get("ok"))}
        for entry in result.get("procedures", [])
    ]
    warnings = None
    report = directory / "report.json"
    if report.is_file():
        try:
            warnings = len(json.loads(report.read_text(encoding="utf-8")).get("warnings", []))
        except (OSError, json.JSONDecodeError, AttributeError):
            warnings = None

    return {
        "run_id": result.get("run_id") or directory.name,
        "dir": str(directory),
        "status": _badge(result) if result else "incomplete",
        "ok": result.get("ok"),
        "started_utc": result.get("started_utc"),
        "finished_utc": result.get("finished_utc"),
        "seconds": result.get("seconds"),
        "model": result.get("model") or {"id": directory.name.split("_", 1)[-1]},
        "procedures": procedures,
        "dataflash": dataflash,
        "has_report": (directory / "report.md").is_file(),
        "report_warnings": warnings,
        "mavexplorer": f"MAVExplorer.py {directory / dataflash}" if dataflash else None,
    }


def run_dir(run_id: str, root: Optional[Path] = None) -> Optional[Path]:
    """Resolves a run id to its directory, refusing anything outside `root`.

    The id arrives from a URL, so it is treated as untrusted: the resolved
    path must be a direct child of the runs root or it is rejected.
    """
    root = (Path(root) if root else paths.RUNS_DIR).resolve()
    if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        return None
    candidate = (root / run_id).resolve()
    if candidate.parent != root or not candidate.is_dir():
        return None
    return candidate


def run_file(run_id: str, relative: str, root: Optional[Path] = None) -> Optional[Path]:
    """Resolves a file inside a run directory, refusing escapes."""
    base = run_dir(run_id, root)
    if base is None:
        return None
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def regenerate_report(run_id: str, root: Optional[Path] = None) -> dict:
    """Re-runs the post-flight analysis for an existing run."""
    base = run_dir(run_id, root)
    if base is None:
        return {"ok": False, "text": f"unknown run '{run_id}'"}
    logs = sorted(base.glob("*.BIN"))
    if not logs:
        return {"ok": False, "text": f"run '{run_id}' has no dataflash log to analyse"}
    result: dict[str, Any] = {}
    path = base / "result.json"
    if path.is_file():
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result = {}
    meta = {
        "run_id": result.get("run_id", base.name),
        "argazui_version": result.get("argazui_version", ""),
        "model_id": (result.get("model") or {}).get("id"),
        "model_name": (result.get("model") or {}).get("name"),
        "procedures": [entry.get("procedure") for entry in result.get("procedures", [])],
        "status": result.get("status"),
    }
    analyse(logs[0], base, meta=meta)
    return {"ok": True, "text": f"report regenerated for {base.name}"}
