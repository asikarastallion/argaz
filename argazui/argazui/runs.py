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
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import paths
from .flightlog import analyse, newest_log
from .i18n import t
from .versions import environment

# 2 (v1.1 phase 4): `status` is now one of the values in STATUSES and is about
# acceptance criteria only, and `advisory_count` was added alongside it. In
# schema 1 the single `ok` flag was doing both jobs.
RESULT_SCHEMA = 2

# What a run's acceptance verdict can be. Health findings live in
# `advisory_count` and never appear here.
STATUS_PASSED = "passed"        # every procedure met every acceptance criterion
STATUS_FAILED = "failed"        # at least one criterion did not hold
STATUS_ERROR = "error"          # a procedure could not be evaluated at all
STATUS_NO_PROCEDURE = "no-procedure"   # flown by hand; nothing was asserted
STATUSES = (STATUS_PASSED, STATUS_FAILED, STATUS_ERROR, STATUS_NO_PROCEDURE)

# A run directory is named <UTC stamp>_<model id>. Matching on the name is how
# the listing tells a run apart from anything else that shares the runs root —
# the regression suite's runs/tests/ sub-directory, most obviously.
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z_.+")

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


def _write_versions(directory: Path, firmware: str = "") -> dict[str, str]:
    """Writes versions.txt using the one canonical version record.

    Called twice: once at `finish()`, when the firmware string is not yet
    known, and again after the dataflash log has been parsed. The second pass
    is what makes the file's `ardupilot =` line comparable across runs — see
    versions.py for why there is exactly one such line.
    """
    record = environment(firmware)
    (directory / "versions.txt").write_text(
        "\n".join(f"{key} = {value}" for key, value in record.items()) + "\n",
        encoding="utf-8")
    return record


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
        self._flaky: list[dict] = []
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

    def mark_flaky(self, procedure_id: str, reason: str) -> None:
        """Records that a procedure only succeeded on a retry.

        The regression suite is allowed exactly one retry for SITL timing, and
        it must cost something: a run with a retry is reported as `flaky` in
        docs/status.md, never as `passed`. Retrying quietly until green is the
        behaviour this project exists to prevent, so the retry is recorded
        here rather than swallowed in the test.
        """
        with self._lock:
            self._flaky.append({"procedure": procedure_id, "reason": reason,
                                "utc": _iso()})

    def add_procedure(self, procedure, result: dict, values: Optional[dict] = None,
                      attempt: int = 1) -> None:
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
            "attempt": attempt,
            "values": values or result.get("values") or {},
            "result": result,
        }
        with self._lock:
            self._procedures.append(entry)
            self._scenarios.append(
                f"# ---------------------------------------------------------------\n"
                f"# executed {entry['started_utc']} — {procedure.id} ({procedure.role})\n"
                f"# inputs: {json.dumps(entry['values'], ensure_ascii=False)}\n"
                f"# outcome: {str(result.get('outcome', 'unknown')).upper()}\n"
                f"# source file: {procedure.path.name}\n"
                f"# ---------------------------------------------------------------\n"
                f"{procedure.raw_text.rstrip()}\n")
        self.event({"kind": "procedure", "procedure": procedure.id,
                    "role": procedure.role, "outcome": result.get("outcome"),
                    "text": result.get("text", "")})

    def overrides(self) -> list[dict]:
        """Every parameter the run's procedures changed, in order.

        Flattened out of the procedure results so the report can lead with it
        without knowing how procedures are structured.
        """
        out: list[dict] = []
        for entry in self._procedures:
            for name, record in (entry["result"].get("params_changed") or {}).items():
                out.append({"param": name, "procedure": entry["procedure"], **record})
        return out

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

        # First pass, without the firmware string — the log has not been read
        # yet. `_make_report` rewrites it once the firmware is known.
        _write_versions(self.dir)

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
        """The run's own record.

        `status` answers one question only: did the procedures meet their
        acceptance criteria? Health findings are counted separately in
        `advisory_count`, which stays None until the flight report has been
        produced — "not computed yet" and "nothing flagged" are different
        answers and must not look the same.
        """
        status = aggregate_status(self._procedures)

        from . import __version__
        return {
            "schema": RESULT_SCHEMA,
            "run_id": self.run_id,
            "argazui_version": __version__,
            "started_utc": _iso(self.started),
            "finished_utc": _iso(finished),
            "seconds": round(finished.timestamp() - self.started_monotonic, 1),
            "status": status,
            "advisory_count": None,
            "flaky": list(self._flaky),
            "ok": status == STATUS_PASSED and not self._flaky,
            "model": {key: self.model.get(key) for key in
                      ("id", "name", "vehicle_class", "method", "vehicle", "frame",
                       "param_file", "world", "env", "has_ros2")},
            "build": {},                 # filled in once the log has been read
            "work_dir": str(self.work_dir),
            "overrides": self.overrides(),
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
            "overrides": result.get("overrides") or [],
        }
        try:
            report = analyse(dataflash, self.dir, meta=meta)
        except Exception as exc:                     # a bad log must not be fatal
            (self.dir / "report.md").write_text(
                f"# Flight report — {self.run_id}\n\n"
                f"The dataflash log `{dataflash.name}` could not be analysed:\n\n"
                f"```\n{exc}\n```\n\n"
                f"The log itself is still in this directory and can be opened with "
                f"`MAVExplorer.py {dataflash.name}`.\n", encoding="utf-8")
            self.on_log(t("run_failed", err=exc))
            return
        # The advisory count and the build record only exist once the log has
        # been read, so result.json is completed here rather than guessed at
        # earlier. The status is untouched: advisories never change a verdict.
        attach_report(self.dir, report)
        _write_versions(self.dir, report["log"].get("firmware", ""))
        self.on_log(t("run_report_ready", id=self.run_id,
                      advisories=report["advisory_count"]))

    def summary(self) -> dict:
        path = self.dir / "result.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"run_id": self.run_id, "status": "running"}


# --------------------------------------------------------------------------- browsing
def attach_report(directory: Path, report: dict) -> None:
    """Folds the report's advisory count and build record back into result.json.

    Kept separate from `RunRecorder` so `argazui report` can do the same thing
    when it regenerates an old run: the two paths must not drift, or a
    regenerated run would disagree with a freshly flown one.
    """
    path = Path(directory) / "result.json"
    if not path.is_file():
        return
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    result["advisory_count"] = report.get("advisory_count", 0)
    result["advisories"] = report.get("advisories", [])
    result["build"] = report.get("build", {})
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def aggregate_status(procedures: list[dict]) -> str:
    """The run's acceptance verdict, from the LAST attempt of each procedure.

    Only the last attempt counts because the suite is allowed one retry for
    SITL timing. That leniency is paid for elsewhere and visibly: the retry is
    recorded in `flaky`, every attempt stays in `procedures`, and the status
    table reports the run as `flaky` rather than `passed`. Without the `flaky`
    record this rule would be a way to hide failures, which is why the two
    always ship together.
    """
    last: dict[tuple, str] = {}
    for entry in procedures:
        key = (entry.get("procedure"), entry.get("role"))
        last[key] = _outcome_of(entry)
    outcomes = list(last.values())
    if not outcomes:
        return STATUS_NO_PROCEDURE
    if any(o == STATUS_ERROR for o in outcomes):
        return STATUS_ERROR
    if all(o == STATUS_PASSED for o in outcomes):
        return STATUS_PASSED
    return STATUS_FAILED


def overrides_of(result: dict) -> list[dict]:
    """The parameters a stored run changed.

    Prefers the top-level list written by schema 2, and falls back to
    flattening the procedure results. The fallback is what lets a run recorded
    before this field existed still show its overrides when its report is
    regenerated, instead of claiming the flight changed nothing.
    """
    declared = result.get("overrides")
    if declared:
        return declared
    out: list[dict] = []
    for entry in result.get("procedures", []):
        changed = (entry.get("result") or {}).get("params_changed") or {}
        for name, record in changed.items():
            out.append({"param": name, "procedure": entry.get("procedure"), **record})
    return out


def _outcome_of(entry: dict) -> str:
    """A procedure's outcome, tolerating runs recorded before the field existed."""
    result = entry.get("result") or {}
    outcome = result.get("outcome")
    if outcome:
        return outcome
    return STATUS_PASSED if result.get("ok") else STATUS_FAILED


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
        # Only directories that are actually named like a run. The regression
        # suite writes into runs/tests/, and that sub-directory must not be
        # listed as a mysterious "incomplete" flight of its own.
        if not entry.is_dir() or not RUN_ID_PATTERN.match(entry.name):
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
         "outcome": _outcome_of(entry)}
        for entry in result.get("procedures", [])
    ]
    # None means "the report has not been produced yet", which is not the same
    # answer as zero. The UI shows the two differently.
    advisories = result.get("advisory_count")

    return {
        "run_id": result.get("run_id") or directory.name,
        "dir": str(directory),
        "status": result.get("status", "incomplete") if result else "incomplete",
        "started_utc": result.get("started_utc"),
        "finished_utc": result.get("finished_utc"),
        "seconds": result.get("seconds"),
        "model": result.get("model") or {"id": directory.name.split("_", 1)[-1]},
        "procedures": procedures,
        "dataflash": dataflash,
        "has_report": (directory / "report.md").is_file(),
        "flaky": result.get("flaky") or [],
        "advisory_count": advisories,
        "overrides": overrides_of(result),
        "build": result.get("build") or {},
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
        "overrides": overrides_of(result),
    }
    report = analyse(logs[0], base, meta=meta)
    # Same completion path as a freshly flown run, so a regenerated run and a
    # new one cannot end up describing themselves differently.
    attach_report(base, report)
    _write_versions(base, report["log"].get("firmware", ""))
    return {"ok": True, "text": f"report regenerated for {base.name}",
            "advisory_count": report["advisory_count"]}
