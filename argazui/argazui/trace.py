"""Identifiers, and the chain that links an intention to the evidence for it.

WHAT THIS LAYER IS FOR
----------------------
Every release up to now made the *facts* better: measured criteria, temporal
shapes, metrics, fingerprints, campaigns, a failure category. What none of them
made possible is following one claim backwards. A reviewer holding
`docs/status.md` and asked *"which criterion is that, which run showed it, and
what file proves it"* had to read three documents and join them by eye.

So every link in the chain gets a name:

    test intent   test_id        the pytest node, or "flown by hand"
      -> procedure    procedure_id   the YAML file's own id
      -> step         step_id        derived from position
      -> criterion    criterion_id   DECLARED in the procedure
      -> metric       metric_id      key@procedure
      -> run          run_id         the run directory
      -> artefact     the evidence manifest's paths
      -> verdict      the run's status and failure category

THERE IS NO DATABASE, AND THAT IS THE DESIGN
--------------------------------------------
Nothing here stores anything of its own. A chain is *computed* from a run's
`result.json` every time it is asked for, exactly as a campaign document is
recomputed from its runs. A traceability record that could drift from the run
it describes would be worse than none: it would be a second source for the one
thing this project exists to keep single.

WHY CRITERIA ARE DECLARED AND STEPS ARE DERIVED
-----------------------------------------------
A step identifier is only ever read *inside* the run that produced it — the
report lists the steps, the failure classification names the one that failed.
Position is a perfectly good name for that, and `<procedure>#s3` costs nothing
to maintain.

A criterion identifier is quoted *outside* its own run: in the coverage report,
in the "what was not tested" list, in a comparison of two runs months apart.
Those need a name that survives someone inserting a criterion above it, so a
criterion declares its own — `id: alt-held` — and a procedure that omits one
gets a derived id that is explicitly marked as such, because an identifier
whose stability the reader cannot see is worse than one they can.
"""
from __future__ import annotations

import re
from typing import Any, Optional

SCHEMA = 1

# A declared identifier: lower-case, no separators that would collide with the
# `procedure#local` form this module composes. Deliberately narrow — an id is
# quoted in tables, URLs and shell commands, and one that needs escaping in any
# of them is an id that will be got wrong somewhere.
DECLARED_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")

# Separates a procedure from the part local to it. `#` cannot appear in a
# declared id, so a composed identifier can always be split back apart.
SEP = "#"

# What a run says when nothing but a person produced it. Not None and not an
# empty string: "flown by hand" is a real answer to "what was the intent", and
# it is the answer that says no test asserts this.
BY_HAND = "manual"


class TraceError(ValueError):
    """A declared identifier is malformed. Carries the file for the message."""


def check_declared(value: Any, where: str) -> str:
    """Validates an author-declared id. Returns it unchanged."""
    if not isinstance(value, str) or not DECLARED_ID.match(value):
        raise TraceError(
            f"{where}: an id must be lower-case letters, digits, '_' or '-', "
            f"1-48 characters, and may not contain '{SEP}' — got {value!r}")
    return value


def step_id(procedure: str, index: int, declared: Optional[str] = None) -> str:
    """`plane_takeoff#s3`, or `plane_takeoff#arm` when the file declares one."""
    return f"{procedure}{SEP}{declared or f's{index + 1}'}"


def criterion_id(procedure: str, index: int, declared: Optional[str] = None) -> str:
    """`copter_takeoff#alt-held`, or `copter_takeoff#c2` when none is declared."""
    return f"{procedure}{SEP}{declared or f'c{index + 1}'}"


def fault_id(procedure: str, declared: str) -> str:
    """A fault always declares its id — the schema requires it."""
    return f"{procedure}{SEP}{declared}"


def metric_id(key: str, procedure: str = "") -> str:
    """`peak_angular_rate`, or `time_to_target_alt@copter_takeoff`.

    Unchanged from the identity `metrics.py` has used since v1.3; it is named
    here so the chain can refer to it by the same word as everything else.
    """
    return f"{key}@{procedure}" if procedure else key


def split(identifier: str) -> tuple[str, str]:
    """`copter_takeoff#c2` -> ("copter_takeoff", "c2")."""
    procedure, _, local = (identifier or "").partition(SEP)
    return procedure, local


def is_derived(identifier: str) -> bool:
    """Was this id generated from a position rather than declared?

    Reported alongside every derived id. A reader comparing two runs months
    apart needs to know which identifiers would have survived an edit and which
    are only as stable as the order of the file.
    """
    _, local = split(identifier)
    return bool(re.match(r"^[sc]\d+$", local))


# --------------------------------------------------------------------- chain
def chain(result: dict) -> dict:
    """The full traceability chain for one stored run.

    Computed from `result.json` alone, so it is exactly as true as the run
    record and cannot outlive it.
    """
    run_id = result.get("run_id") or ""
    procedures: list[dict] = []

    # Only the LAST attempt of each procedure, for the same reason
    # `aggregate_status` reads only the last: a retry is paid for with `flaky`,
    # not by having two chains for one intent.
    last: dict[tuple, dict] = {}
    for entry in result.get("procedures") or []:
        last[(entry.get("procedure"), entry.get("role"))] = entry

    metric_index = _metrics_by_procedure(result)

    for entry in last.values():
        outcome = entry.get("result") or {}
        pid = entry.get("procedure") or ""
        procedures.append({
            "procedure_id": pid,
            "role": entry.get("role"),
            "file": entry.get("file"),
            "attempt": entry.get("attempt", 1),
            "verdict": outcome.get("outcome"),
            "failure": outcome.get("failure"),
            "steps": [
                {"step_id": step.get("step_id") or step_id(pid, step.get("index", 0)),
                 "index": step.get("index"),
                 "kind": step.get("kind"),
                 "label": step.get("label"),
                 "status": step.get("status"),
                 "derived_id": not step.get("step_id")}
                for step in outcome.get("steps") or []
            ],
            "criteria": [
                {"criterion_id": (criterion.get("criterion_id")
                                  or criterion_id(pid, index)),
                 "label": criterion.get("label"),
                 "kind": criterion.get("kind", "eventually"),
                 "duration": criterion.get("duration"),
                 "passed": bool(criterion.get("passed")),
                 "evaluated": _was_evaluated(criterion),
                 "observed": criterion.get("observed"),
                 "clock": criterion.get("clock"),
                 "derived_id": not criterion.get("criterion_id"),
                 "metrics": []}
                for index, criterion in enumerate(outcome.get("expect") or [])
            ],
            "faults": [
                {"fault_id": fault_id(pid, fault.get("id") or "?"),
                 "fault": fault.get("fault"),
                 "target": fault.get("target"),
                 "applied": fault.get("applied"),
                 "cleared": fault.get("cleared"),
                 "passed": fault.get("passed"),
                 "judged": not fault.get("evidence_missing")}
                for fault in outcome.get("faults") or []
            ],
            "metric_ids": metric_index.get(pid, []),
        })

    return {
        "schema": SCHEMA,
        "run_id": run_id,
        # The intent this run served. `manual` is a real answer and says
        # plainly that no test asserts anything about it.
        "test_id": result.get("test_id") or BY_HAND,
        "model_id": (result.get("model") or {}).get("id"),
        "campaign_id": (result.get("campaign") or {}).get("id"),
        "verdict": result.get("status"),
        "failure": result.get("failure"),
        "procedures": procedures,
        "metrics": [
            {"metric_id": metric.get("identity")
                          or metric_id(metric.get("key", ""),
                                       metric.get("procedure", "")),
             "key": metric.get("key"),
             "procedure_id": metric.get("procedure") or None,
             "value": metric.get("value"),
             "unit": metric.get("unit"),
             "measured": metric.get("value") is not None,
             "detail": metric.get("detail", "")}
            for metric in result.get("metrics") or []
        ],
        "evidence": [item.get("path") for item in
                     ((result.get("evidence") or {}).get("artefacts") or [])
                     if item.get("exists")],
    }


def _metrics_by_procedure(result: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for metric in result.get("metrics") or []:
        procedure = metric.get("procedure") or ""
        if not procedure:
            continue
        out.setdefault(procedure, []).append(
            metric.get("identity") or metric_id(metric.get("key", ""), procedure))
    return out


def _was_evaluated(criterion: dict) -> bool:
    """Did this criterion actually get judged, or was it never reached?

    A criterion the procedure stopped short of says nothing about the aircraft,
    and counting it as covered would inflate every coverage figure with claims
    nobody tested.
    """
    if criterion.get("passed"):
        return True
    text = (criterion.get("text") or "").lower()
    return not ("not evaluated" in text or "not judged" in text
                or "degerlendirilmedi" in text)


# ----------------------------------------------------------------- integrity
def integrity(result: dict, chain_document: Optional[dict] = None) -> list[dict]:
    """Problems with a run's traceability. Empty means every link resolves.

    This is the check that makes the chain worth having. An identifier scheme
    nobody verifies degrades silently: a criterion loses its id, a metric names
    a procedure the run never flew, an evidence reference points at a file that
    was pruned — and every one of those still renders a table that looks right.
    """
    document = chain_document or chain(result)
    problems: list[dict] = []

    def flag(kind: str, subject: str, detail: str) -> None:
        problems.append({"problem": kind, "subject": subject, "detail": detail})

    procedure_ids = {p["procedure_id"] for p in document["procedures"]}
    seen_criteria: set = set()
    seen_steps: set = set()

    for procedure in document["procedures"]:
        if not procedure["procedure_id"]:
            flag("missing-id", "procedure", "a recorded procedure has no id")
        for step in procedure["steps"]:
            if step["step_id"] in seen_steps:
                flag("duplicate-id", step["step_id"],
                     "two steps in this run share an identifier")
            seen_steps.add(step["step_id"])
        for criterion in procedure["criteria"]:
            identifier = criterion["criterion_id"]
            if identifier in seen_criteria:
                flag("duplicate-id", identifier,
                     "two criteria in this run share an identifier")
            seen_criteria.add(identifier)
            owner, local = split(identifier)
            if owner != procedure["procedure_id"]:
                flag("dangling-link", identifier,
                     f"the criterion's id names procedure '{owner}' but it was "
                     f"recorded under '{procedure['procedure_id']}'")
            if not local:
                flag("missing-id", identifier, "the criterion id has no local part")

    for metric in document["metrics"]:
        procedure = metric["procedure_id"]
        if procedure and procedure not in procedure_ids:
            flag("dangling-link", metric["metric_id"],
                 f"the metric is scoped to procedure '{procedure}', which this "
                 f"run did not execute")

    # Evidence the chain names must actually be in the manifest as present.
    manifest = (result.get("evidence") or {}).get("artefacts") or []
    present = {item.get("path") for item in manifest if item.get("exists")}
    for path in document["evidence"]:
        if path not in present:
            flag("missing-evidence", path,
                 "the chain refers to an artefact the manifest does not list "
                 "as present")

    if document["verdict"] is None:
        flag("missing-verdict", document["run_id"],
             "the run record carries no status, so nothing it contains can be "
             "attached to a result")
    return problems


def derived_ids(document: dict) -> list[str]:
    """Every identifier in a chain that came from a position, not a declaration.

    Reported rather than hidden: these are the ids that would change if someone
    inserted a line above them, and a reader comparing two runs needs to know
    which of the names they are matching on are that kind.
    """
    out: list[str] = []
    for procedure in document.get("procedures") or []:
        out += [s["step_id"] for s in procedure["steps"] if s["derived_id"]]
        out += [c["criterion_id"] for c in procedure["criteria"] if c["derived_id"]]
    return out
