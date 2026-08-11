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

from . import evidence as evidencelib
from . import failures as failurelib
from . import fingerprint as fp
from . import metrics as metricslib
from . import paths
from .flightlog import (analyse, newest_log, refresh_evidence,
                        verify_dataflash)
from .i18n import t
from .versions import environment

# 2 (v1.1 phase 4): `status` is now one of the values in STATUSES and is about
#   acceptance criteria only, and `advisory_count` was added alongside it. In
#   schema 1 the single `ok` flag was doing both jobs.
# 3 (v1.3): `fingerprint` and `metrics` were added. Nothing that existed in
#   schema 2 moved or changed meaning, so a reader of the older shape still
#   works — the version moves because the document now carries more, and a
#   comparison layer has to be able to tell which shape it is looking at.
# 4 (v1.4): `failure` — the classified reason a run did not pass — and
#   `campaign`, the repeatability campaign this run belongs to. Both are null
#   on an ordinary passing run, and again nothing that existed moved.
# 5 (v1.5): `test_id` — the intent this run served — and `evidence`, the
#   manifest of what the run was expected to leave behind and what it did.
#   Steps and criteria inside `procedures` also gained `step_id` and
#   `criterion_id`. Nothing that existed moved.
# 6 (v1.6): `experiment` — the experiment and arm this run belongs to, beside
#   the campaign stamp rather than instead of it, because an experiment's arm
#   IS a campaign and every tool that already reads campaigns must keep
#   finding it. Null on an ordinary run, and nothing that existed moved.
RESULT_SCHEMA = 6

# What a run's acceptance verdict can be. Health findings live in
# `advisory_count` and never appear here.
STATUS_PASSED = "passed"        # every procedure met every acceptance criterion
STATUS_FAILED = "failed"        # at least one criterion did not hold
STATUS_ERROR = "error"          # a procedure could not be evaluated at all
STATUS_NO_PROCEDURE = "no-procedure"   # flown by hand; nothing was asserted
STATUSES = (STATUS_PASSED, STATUS_FAILED, STATUS_ERROR, STATUS_NO_PROCEDURE)

# What a run records about the model it flew, and therefore what the
# environment fingerprint hashes.
#
# WHY THE RECORDED SUBSET AND NOT THE WHOLE REGISTRY ENTRY
# --------------------------------------------------------
# The hash has to be reproducible from the archived run, because `argazui
# report` regenerates a report months later and its answer must line up with
# the one the flight produced. It can only see what result.json stored, so that
# is what is hashed. Every field that changes the aircraft is here: which
# binary, which frame, which parameter files, which world.
MODEL_RECORD_KEYS = ("id", "name", "vehicle_class", "method", "vehicle", "frame",
                     "param_file", "world", "env", "has_ros2")

# Opens and closes the per-execution header in `scenario.yaml`. A constant
# rather than a literal in two places: `_recorded_procedures` reads the body
# back from after the closing fence, and the two must agree exactly or a
# regenerated report hashes different text from the flight that produced it.
SCENARIO_FENCE = "# ---------------------------------------------------------------"

# A run directory is named <UTC stamp>_<model id>. Matching on the name is how
# the listing tells a run apart from anything else that shares the runs root —
# the regression suite's runs/tests/ sub-directory, most obviously.
RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z_.+")


def _eeprom_wiped(launch_commands: list) -> Optional[bool]:
    """Did this run boot SITL from a wiped simulated eeprom?

    Read back out of the launch commands rather than passed in, so it states
    what was actually typed into the terminal instead of what somebody meant
    to type. None when no `sim_vehicle.py` line is present at all — a
    ros2_launch model, or a session that never launched anything.
    """
    for line in launch_commands or []:
        if "sim_vehicle.py" not in line:
            continue
        return " -w " in f" {line} "
    return None

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
                 on_log: Optional[Callable[[str], None]] = None,
                 campaign: Optional[dict] = None,
                 test_id: Optional[str] = None,
                 experiment: Optional[dict] = None) -> None:
        self.model = model
        # The shell lines that brought the simulation up, verbatim. Recorded in
        # `result.json` as well as in the console header because they are the
        # only statement of the INITIAL CONDITION a run started from — whether
        # the simulated eeprom was wiped is a `-w` in this list and nothing
        # else, and a campaign claiming N identical repetitions has to be able
        # to show it. See session.build_launch_commands.
        self.launch_commands = list(launch_commands or [])
        # What this run was FOR. A pytest node id when a test drove it, and
        # None when a person pressed START — which is recorded as `manual`
        # rather than left blank, because "flown by hand" is a real answer and
        # it is the one that says no test asserts anything about this.
        self.test_id = test_id
        # The repeatability campaign this run is one iteration of, or None.
        # Stamped into result.json rather than kept in an index file: a
        # campaign is found by reading its runs, so a run that was moved or
        # copied still says what it belonged to.
        self.campaign = dict(campaign) if campaign else None
        # The experiment and arm this run belongs to, or None. Beside the
        # campaign stamp and not instead of it: an experiment's arm IS a
        # repeatability campaign, and a run that dropped its campaign id to
        # carry an experiment one would vanish from every campaign tool.
        self.experiment = dict(experiment) if experiment else None
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
        # The verbatim YAML of each distinct procedure that ran, for the
        # fingerprint to hash. Hashing the file on disk instead would be
        # wrong twice over: it may have been edited since, and a retry would
        # otherwise contribute the same text twice.
        self._procedure_sources: dict[str, dict] = {}
        self._scenarios: list[str] = []
        self._flaky: list[dict] = []
        self._dataflash_check: Optional[dict] = None
        self._dataflash_absent: str = ""
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
            self._procedure_sources[procedure.id] = {
                "id": procedure.id, "schema": getattr(procedure, "schema", 1),
                "file": procedure.path.name, "text": procedure.raw_text,
                "faults": [f.as_dict("en")
                           for f in getattr(procedure, "failures", [])]}
            self._scenarios.append(
                f"{SCENARIO_FENCE}\n"
                f"# executed {entry['started_utc']} — {procedure.id} ({procedure.role})\n"
                f"# inputs: {json.dumps(entry['values'], ensure_ascii=False)}\n"
                f"# outcome: {str(result.get('outcome', 'unknown')).upper()}\n"
                f"# source file: {procedure.path.name}\n"
                f"{SCENARIO_FENCE}\n"
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
    def finish(self, report: bool = True, wait: bool = False,
               report_timeout: float = 120.0) -> dict:
        """Closes the capture files and writes the run's own records.

        Call this *after* the simulator has exited, so the dataflash log has
        been flushed and closed. The post-flight report is generated on a
        background thread because parsing a long log takes seconds and STOP
        should not wait for it.

        `wait=True` blocks until that thread finishes. Anything that exits
        right after calling this — a test session, a CLI — must pass it, or
        the report is killed with the process before it is written.
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
        # yet. `_make_report` rewrites both of these once the firmware is known.
        _write_versions(self.dir)
        self._capture_fingerprint()

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
        self._write_result(result)
        # The manifest is taken AFTER result.json is on disk, because
        # result.json is one of the artefacts it describes. It is captured
        # again once the flight report has run — the report is what produces
        # half the optional entries — for the same reason versions.txt and the
        # fingerprint are written twice.
        result = self._capture_evidence(result)

        if report and dataflash:
            thread = threading.Thread(target=self._make_report,
                                      args=(dataflash, result),
                                      name=f"report-{self.run_id}", daemon=True)
            thread.start()
            if wait:
                # A daemon thread dies with the process. That is right for the
                # server — STOP must not block while a long log is parsed —
                # and wrong for anything that exits straight afterwards: the
                # LAST run of a test session lost its report every time,
                # leaving a run directory with a dataflash log but no
                # report.json, and an empty firmware cell in docs/status.md.
                # Callers that are about to exit ask to wait.
                thread.join(timeout=report_timeout)
                if thread.is_alive():
                    self.on_log(t("run_report_slow", id=self.run_id,
                                  seconds=f"{report_timeout:g}"))
        elif report:
            self.on_log(t("run_no_report", id=self.run_id))
        return result

    def _write_result(self, result: dict) -> None:
        (self.dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

    def _capture_evidence(self, result: dict) -> dict:
        """Writes evidence.json and folds its verdict back into the run record.

        The full manifest lives in its own file; the run record carries only
        the pointer and the one line a reader needs first — whether every
        required artefact is actually there.
        """
        try:
            manifest = evidencelib.capture(self.dir, result)
            evidencelib.write(self.dir, manifest)
        except OSError as exc:
            self.on_log(t("run_evidence_failed", err=exc))
            return result
        result["evidence"] = evidence_summary(manifest)
        # A run whose procedures all passed can still fail on its evidence, and
        # that verdict is only knowable once the directory has been looked at.
        failure = failurelib.classify_run(result, manifest)
        result["failure"] = failure.as_dict() if failure else None
        self._write_result(result)
        return result

    def model_record(self) -> dict:
        """What this run archives about the model it flew."""
        return {key: self.model.get(key) for key in MODEL_RECORD_KEYS}

    def _capture_fingerprint(self, firmware: str = "") -> dict:
        """Records what produced this run, beside the run's own result.

        Called twice for the same reason `versions.txt` is: the firmware string
        only exists once the dataflash log has been parsed, and a fingerprint
        that claimed to know it before then would be stating something it had
        not read.
        """
        manifest = fp.capture(model=self.model_record(),
                              procedures=list(self._procedure_sources.values()),
                              firmware=firmware,
                              scenario=declared_faults(
                                  list(self._procedure_sources.values())))
        try:
            fp.write(self.dir, manifest)
        except OSError as exc:
            # Never lose a run over its own bookkeeping — but never claim the
            # manifest is there when it is not.
            self.on_log(t("run_fingerprint_failed", err=exc))
        return manifest

    def _copy_dataflash(self) -> Optional[Path]:
        """Copies the newest `.BIN` the simulator wrote during this run.

        The `newer_than` filter is what stops a stopped-and-restarted model
        from archiving the previous session's log: the working directory is
        shared between launches and keeps every log it has ever written.
        """
        source = newest_log(self.work_dir, newer_than=self.started_monotonic - 5)
        if source is None:
            self._dataflash_absent = self._why_no_dataflash()
            return None
        target = self.dir / source.name
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            self._dataflash_absent = f"could not copy {source}: {exc}"
            self.on_log(t("run_bin_copy_failed", path=str(source), err=exc))
            return None
        self._dataflash_check = verify_dataflash(target)
        if not self._dataflash_check["complete"]:
            self.on_log(t("run_bin_truncated", name=target.name,
                          detail=self._dataflash_check["error"] or "no timestamped tail"))
        return target

    def _why_no_dataflash(self) -> str:
        """States the reason, because "missing" alone reads like a defect.

        The usual reason is not a fault at all: ArduPilot ships LOG_DISARMED=0,
        so a session where the vehicle never armed produces no log file. That
        is different from a log that was expected and lost, and the run record
        has to distinguish them.
        """
        if not self._ever_armed():
            return ("the vehicle never armed, and ArduPilot's default "
                    "LOG_DISARMED=0 means it writes no dataflash log until it "
                    "does — nothing was lost")
        return (f"the vehicle armed but no .BIN newer than the run start was "
                f"found under {self.work_dir}")

    def _ever_armed(self) -> bool:
        """Did the vehicle arm at any point in this run?

        Every line is parsed and its `kind` field examined. A substring search
        would be cheaper and wrong: a STATUSTEXT carrying the autopilot's own
        refusal — `{"kind": "statustext", "text": "Arm: not armed"}` — contains
        the word, and would make this claim the opposite of the truth. The
        answer feeds the explanation for a missing dataflash log, so it is part
        of the accuracy chain rather than a cosmetic detail.
        """
        path = self.dir / "mavlink_events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        for line in lines:
            if not line.strip():
                continue
            try:
                if json.loads(line).get("kind") == "armed":
                    return True
            except json.JSONDecodeError:
                continue
        return False

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
        record = {
            "schema": RESULT_SCHEMA,
            "run_id": self.run_id,
            "argazui_version": __version__,
            "started_utc": _iso(self.started),
            "finished_utc": _iso(finished),
            "seconds": round(finished.timestamp() - self.started_monotonic, 1),
            "status": status,
            "campaign": self.campaign,
            "experiment": self.experiment,
            "test_id": self.test_id,
            "advisory_count": None,
            # Both stay None until the flight report has been produced. "not
            # computed yet" and "nothing to report" are different answers and
            # must not look the same to whatever reads this next.
            "metrics": None,
            "fingerprint": fp.read(self.dir),
            "flaky": list(self._flaky),
            "ok": status == STATUS_PASSED and not self._flaky,
            "model": self.model_record(),
            "build": {},                 # filled in once the log has been read
            "work_dir": str(self.work_dir),
            # What the run started FROM, in the two terms that can differ
            # between two runs of the same model in the same checkout.
            "initial_state": {
                "launch_commands": list(self.launch_commands),
                # `sim_vehicle.py -w`: the simulated eeprom was wiped, so the
                # vehicle booted from its declared parameter files rather than
                # from whatever the previous run of this model left behind.
                # None where ArgazUI did not compose the SITL command line at
                # all (a ros2_launch model), because "not wiped" and "not ours
                # to wipe" are different answers.
                "eeprom_wiped": _eeprom_wiped(self.launch_commands),
            },
            "overrides": self.overrides(),
            "procedures": self._procedures,
            "artefacts": {
                "console_log": "console.log",
                "mavlink_events": "mavlink_events.jsonl",
                "scenario": "scenario.yaml",
                "versions": "versions.txt",
                "dataflash": dataflash.name if dataflash else None,
                "fingerprint": fp.FILENAME,
                # Proof that the log is whole, or a stated reason there is none.
                "dataflash_check": self._dataflash_check,
                "dataflash_absent_reason": self._dataflash_absent or None,
            },
        }
        # Classified from the finished document, so the answer covers the
        # evidence as well as the flying: a run whose procedures all passed and
        # whose dataflash log is missing has still failed, on `evidence`.
        failure = failurelib.classify_run(record)
        record["failure"] = failure.as_dict() if failure else None
        return record

    def _make_report(self, dataflash: Path, result: dict) -> None:
        sources = list(self._procedure_sources.values())
        # The recorded subset, not the live dict: a report regenerated from
        # this directory can only see what was archived, and both must hash to
        # the same thing or the two runs refuse to be compared with each other.
        # See MODEL_RECORD_KEYS.
        meta = report_meta(result, self.dir, sources, declared_faults(sources))
        meta["model_id"] = self.model.get("id")
        meta["model_name"] = self.model.get("name")
        meta["fingerprint_context"]["model"] = self.model_record()
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
        # The advisory count, the metrics and the build record only exist once
        # the log has been read, so result.json is completed here rather than
        # guessed at earlier. The status is untouched: neither advisories nor
        # metrics ever change a verdict.
        attach_report(self.dir, report)
        _write_versions(self.dir, report["log"].get("firmware", ""))
        if report.get("fingerprint"):
            fp.write(self.dir, report["fingerprint"])
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


def evidence_summary(manifest: dict) -> dict:
    """The part of the manifest a run record carries.

    A pointer plus the verdict, not the whole list. The full manifest is in
    `evidence.json`, and copying it into `result.json` would mean the run
    record contained a hash of itself taken before its own last write.
    """
    return {"schema": manifest.get("schema"),
            "file": evidencelib.FILENAME,
            "complete": manifest.get("complete"),
            "counts": manifest.get("counts"),
            "missing_required": manifest.get("missing_required") or [],
            "absent_unexplained": manifest.get("absent_unexplained") or []}


def report_meta(result: dict, directory: Path, procedure_sources: list,
                scenario: list) -> dict:
    """What the flight report needs that a dataflash log cannot know.

    One builder for both paths — a freshly flown run and a regenerated one —
    because the report is a verification document and two versions of it that
    disagreed about which steps ran would be worse than one that was late.
    """
    manifest = evidencelib.read(directory)
    comparison: dict = {}
    path = directory / "regression.json"
    if path.is_file():
        try:
            comparison = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            comparison = {}

    steps: list[dict] = []
    criteria: list[dict] = []
    last: dict = {}
    for entry in result.get("procedures") or []:
        last[(entry.get("procedure"), entry.get("role"))] = entry
    for entry in last.values():
        outcome = entry.get("result") or {}
        steps += list(outcome.get("steps") or [])
        criteria += list(outcome.get("expect") or [])

    return {
        "run_id": result.get("run_id", directory.name),
        "argazui_version": result.get("argazui_version", ""),
        "model_id": (result.get("model") or {}).get("id"),
        "model_name": (result.get("model") or {}).get("name"),
        "procedures": [entry.get("procedure") for entry in
                       result.get("procedures") or [] if entry.get("procedure")],
        "status": result.get("status"),
        "test_id": result.get("test_id"),
        "campaign_id": (result.get("campaign") or {}).get("id"),
        "overrides": overrides_of(result),
        "faults": injected_faults(result),
        "failure": result.get("failure"),
        "steps": steps,
        "criteria": criteria,
        # Hash-free: the report is one of the artefacts the manifest
        # covers, so the digests stay in evidence.json alone.
        "evidence": evidencelib.for_report(manifest),
        "regression": comparison,
        "fingerprint_context": {
            "model": result.get("model") or {},
            "procedures": procedure_sources,
            "scenario": scenario,
        },
        "metrics_context": metricslib.context_from_result(result),
    }


def injected_faults(result: dict) -> list[dict]:
    """Every fault a stored run actually injected, flattened across procedures.

    Distinct from `declared_faults`, which is what the procedures *asked* for.
    A scenario whose fault could not be applied has one and not the other, and
    that difference is the whole point of the fail-closed rule.
    """
    out: list[dict] = []
    for entry in result.get("procedures") or []:
        for fault in (entry.get("result") or {}).get("faults") or []:
            out.append({"procedure": entry.get("procedure"), **fault})
    return out


def declared_faults(procedure_sources: list[dict]) -> list[dict]:
    """The faults the executed procedures declared, for the fingerprint.

    Prefers the list the recorder captured from the parsed procedure objects
    and falls back to parsing the archived YAML, so a report regenerated months
    later describes the same scenario the flight ran. Failure to parse yields
    an empty list rather than an exception: this section is descriptive, and
    losing a run's report over its own manifest would be the wrong trade.
    """
    out: list[dict] = []
    for entry in sorted(procedure_sources, key=lambda p: (p.get("id") or "")):
        faults = entry.get("faults")
        if faults is None:
            faults = _faults_from_text(entry.get("id") or "", entry.get("text") or "")
        for fault in faults or []:
            out.append({"procedure": entry.get("id"), **fault})
    return out


def _faults_from_text(procedure_id: str, text: str) -> list[dict]:
    from . import procedures as procs
    if not text or "failures:" not in text:
        return []
    try:
        parsed = procs.parse(text, Path(f"{procedure_id}.yaml"))
    except Exception:
        return []
    return [f.as_dict("en") for f in parsed.failures]


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
    # Copied into result.json rather than only left in report.json so that the
    # regression layer reads one document per run. report.json also carries the
    # series it plots, which is megabytes nobody comparing two runs needs.
    result["metrics"] = report.get("metrics") or []
    result["metrics_schema"] = report.get("metrics_schema")
    if report.get("fingerprint"):
        result["fingerprint"] = report["fingerprint"]
    # A run recorded before v1.3 and re-analysed now genuinely becomes a
    # current-schema document: it carries the fields that schema defines.
    # Leaving the old number on it would make the version say less than the
    # file does.
    result.setdefault("campaign", None)
    result.setdefault("experiment", None)
    result.setdefault("test_id", None)
    result["schema"] = RESULT_SCHEMA
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")

    # Re-taken now, not at STOP: the report is what produces report.json,
    # report.md, the parameter dumps and the plots, so a manifest captured
    # before it describes a run that had not finished being written.
    directory = Path(directory)
    manifest = _refresh_evidence(directory, result)
    result["evidence"] = evidence_summary(manifest) if manifest else None
    failure = failurelib.classify_run(result, manifest)
    result["failure"] = failure.as_dict() if failure else None
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _refresh_evidence(directory: Path, result: dict) -> dict:
    """Manifest, report section 7, manifest again — in that order.

    The second capture is not belt and braces. The first one is what fills in
    the report's evidence section, and writing that section changes the report,
    so the digests the first capture took of it are already out of date by the
    time they are written. The second covers the final files. Nothing embedded
    in the report carries a hash, so both captures embed the same content.
    """
    try:
        manifest = evidencelib.capture(directory, result)
        evidencelib.write(directory, manifest)
    except OSError:
        return evidencelib.read(directory)
    if refresh_evidence(directory, evidencelib.for_report(manifest)):
        try:
            manifest = evidencelib.capture(directory, result)
            evidencelib.write(directory, manifest)
        except OSError:
            pass
    return manifest


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
         "outcome": _outcome_of(entry),
         # Faults are listed on the row so a scenario run is distinguishable
         # from a nominal one without opening the directory.
         "faults": [{"id": f.get("id"), "fault": f.get("fault"),
                     "applied": f.get("applied"), "passed": f.get("passed")}
                    for f in ((entry.get("result") or {}).get("faults") or [])]}
        for entry in result.get("procedures", [])
    ]
    # None means "the report has not been produced yet", which is not the same
    # answer as zero. The UI shows the two differently.
    advisories = result.get("advisory_count")

    # Metrics are listed but the report's plot series are not: this is the row
    # a browser renders, and it must not carry megabytes to say one number.
    run_metrics = result.get("metrics")
    manifest = result.get("fingerprint") or fp.read(directory)

    # Classified on the way out rather than only read: a run recorded before
    # v1.4 has no `failure` key, and answering "unclassified" for it when the
    # document says exactly why it failed would be a worse answer than the one
    # available.
    failure = result.get("failure")
    if failure is None and result:
        classified = failurelib.classify_run(result, evidencelib.read(directory))
        failure = classified.as_dict() if classified else None

    return {
        "run_id": result.get("run_id") or directory.name,
        "dir": str(directory),
        "status": result.get("status", "incomplete") if result else "incomplete",
        "failure": failure,
        "campaign": result.get("campaign"),
        "experiment": result.get("experiment"),
        "test_id": result.get("test_id"),
        # The verdict on the run's own evidence, not the whole manifest: the
        # panel needs one line, and `evidence.json` is one fetch away.
        "evidence": result.get("evidence"),
        "metrics": run_metrics,
        "fingerprint": manifest,
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
    # The YAML is read back out of the run's own scenario.yaml, so a
    # regenerated report hashes what the flight actually executed and not
    # whatever the procedure file says today.
    recorded = _recorded_procedures(base, result)
    meta = report_meta(result, base, recorded, declared_faults(recorded))
    report = analyse(logs[0], base, meta=meta)
    # Same completion path as a freshly flown run, so a regenerated run and a
    # new one cannot end up describing themselves differently.
    attach_report(base, report)
    _write_versions(base, report["log"].get("firmware", ""))
    if report.get("fingerprint"):
        fp.write(base, report["fingerprint"])
    return {"ok": True, "text": f"report regenerated for {base.name}",
            "advisory_count": report["advisory_count"],
            "metrics": len(metricslib.measured(report.get("metrics") or []))}


def _recorded_procedures(directory: Path, result: dict) -> list[dict]:
    """The procedures a stored run executed, verbatim, from its scenario.yaml.

    `scenario.yaml` is a fenced header block per execution — `# ----`, four
    comment lines, `# ----` — followed by the procedure file itself, with
    executions separated by `---`. The body is taken from after the closing
    fence rather than by dropping every `#` line: procedures begin with their
    own comment block explaining where the flow comes from, and stripping those
    would produce text that hashes differently from the flight's, which is
    exactly the mismatch that stops a regenerated report from being comparable
    with the run it was regenerated from.
    """
    ids = list(dict.fromkeys(entry.get("procedure") for entry in
                             result.get("procedures") or [] if entry.get("procedure")))
    fallback = [{"id": pid, "schema": None, "file": "", "text": ""} for pid in ids]
    try:
        text = (directory / "scenario.yaml").read_text(encoding="utf-8")
    except OSError:
        return fallback

    def _field(body: str, name: str) -> str:
        prefix = f"{name}:"
        return next((line.split(":", 1)[1].strip() for line in body.splitlines()
                     if line.startswith(prefix)), "")

    out: list[dict] = []
    for block in text.split("\n---\n"):
        lines = block.splitlines()
        fences = [i for i, line in enumerate(lines) if line.startswith(SCENARIO_FENCE)]
        if len(fences) < 2:
            continue                       # not an execution block
        body = "\n".join(lines[fences[1] + 1:]).strip()
        pid = _field(body, "id")
        if pid and pid not in {entry["id"] for entry in out}:
            declared = _field(body, "schema")
            out.append({"id": pid,
                        "schema": int(declared) if declared.isdigit() else None,
                        "file": f"{pid}.yaml", "text": body})
    return out or fallback
