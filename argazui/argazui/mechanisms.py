"""The mechanism coverage matrix: declared, executable, exercised, verified.

WHY A PERCENTAGE WAS NOT ENOUGH
-------------------------------
`coverage.py` already refuses the three usual cheats — it does not count tests,
it does not count a skip, and it does not attribute a criterion result by
position. What it reports is a fraction per dimension and a list of names that
are not in it, and that is the right summary. It is not enough to answer the
question v1.7 asks:

    is the mechanism this project SAYS it has actually executable, and has
    anything ever executed it?

"Covered" is one bit, and there are at least five distinguishable answers. A
fault kind that exists in `faults.KINDS` with unit tests and no scenario is not
the same as one with a scenario that no run has flown, and neither is the same
as one flown and judged by criteria. Reporting all three as "uncovered" loses
the distinction that says what to do next.

THE STATES, AND WHY EACH LINE IS DIFFERENT WORK
-----------------------------------------------
    DEFINED        the code or a document declares it
    EXECUTABLE     something can actually invoke it — a scenario points at it,
                   or a procedure declares it
    EXERCISED      a recorded run invoked it against a vehicle
    VERIFIED       a recorded run invoked it AND a criterion judged the result
    NOT_EXERCISED  definable and executable, and nothing has run it
    UNSUPPORTED    declared and known not to be executable here, with a reason

VERIFIED IS THE ONLY ONE THAT MEANS ANYTHING ABOUT AN AIRCRAFT, and it is
deliberately hard to reach: a fault that was injected and left unjudged is
`EXERCISED`, not `VERIFIED`, because "the mechanism worked" and "the aircraft
handled it" are two different claims — the same distinction `FaultResult`
enforces with four separate fields.

NO NEW STORAGE, NO NEW EVIDENCE
-------------------------------
Everything here is recomputed from the run directories on every call, exactly
as `coverage.py` and `campaign.py` do. There is no accumulator and no cache, so
a matrix cannot drift from the evidence under it, and a run directory that is
deleted takes its claim with it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import faults as faultlib
from . import procedures as procs
from . import trace

SCHEMA = 1

# ------------------------------------------------------------------- states
DEFINED = "DEFINED"
EXECUTABLE = "EXECUTABLE"
EXERCISED = "EXERCISED"
VERIFIED = "VERIFIED"
NOT_EXERCISED = "NOT_EXERCISED"
UNSUPPORTED = "UNSUPPORTED"

STATES = (VERIFIED, EXERCISED, EXECUTABLE, NOT_EXERCISED, DEFINED, UNSUPPORTED)

# Ordered best-first, for a table that puts what is proven at the top.
STATE_ORDER = {name: index for index, name in enumerate(STATES)}

# ------------------------------------------------------------------- kinds
KIND_FAULT = "fault"
KIND_PROCEDURE = "procedure"

# MECHANISMS THIS INSTALLATION CANNOT EXERCISE, AND WHY
# -----------------------------------------------------
# A mechanism that cannot be run here is marked UNSUPPORTED with the reason,
# and is NOT counted against coverage — a dimension that punished a project for
# an absent dependency would push somebody to fake the evidence, which is the
# failure mode this whole module exists to make visible.
#
# Faking it is the one thing that is not allowed. Nothing may be moved into
# EXERCISED or VERIFIED except by a run directory on disk that recorded it.
#
# WHY A TABLE HERE AND NOT A FIELD IN THE YAML
# ---------------------------------------------
# The reason a mechanism has not been flown is a fact about THIS SUITE, not
# about the procedure. `tailsitter_land` is a perfectly good landing procedure;
# what is missing is a tailsitter this suite can fly it on. Putting that
# sentence in the procedure file would make the document describe the harness
# that reads it, and would have to be edited in every checkout that acquired a
# better frame.
#
# An entry here is a promise that somebody looked. A mechanism with no entry
# reports the generic "declared, executable, and no recorded run has executed
# it", which is the honest answer for one nobody has examined yet.
NOT_EXERCISED_REASONS: dict[str, str] = {
    "tailsitter_land": (
        "needs a tailsitter airframe. The only one in this suite is SITL's "
        "generic `plane-tailsitter`, which ArduPilot's own test suite lists as "
        "unstable in hover and unflyable in cruise — `tailsitter_takeoff` "
        "already fails on it deliberately, at 1882°/s. Flying a landing "
        "procedure on an aircraft that is tumbling would produce a verdict "
        "about the frame and record it against the procedure. Tier 2's "
        "`skycat_tvbs` is the real tailsitter, and it does not currently reach "
        "a hover to land from"),
}


def _procedure_support(proc) -> Optional[str]:
    """A reason this procedure cannot be flown here, or None.

    `upload_mission` is the honest case. The step type exists, is parsed and is
    implemented, and no tier-1 SITL frame in this suite is flown through a
    mission — so the two mission procedures are declared, executable in
    principle, and unexercised for a reason that is about this suite rather
    than about them. Saying that is more useful than a red cell.
    """
    kinds = {step.kind for step in proc.steps}
    if "upload_mission" in kinds:
        return ("declares an `upload_mission` step; no tier in this suite flies "
                "a mission, so nothing here has ever executed it")
    return None


# -------------------------------------------------------------- declarations
def declared(procedures_dir: Optional[Path] = None) -> list[dict]:
    """Every mechanism this installation declares, before any evidence.

    Two families, because they are declared in two different places and a
    reader needs to know which: fault kinds come from `faults.KINDS`, which is
    code, and procedures come from the YAML directory, which is content.
    """
    out: list[dict] = []

    for kind in faultlib.KINDS:
        out.append({
            "id": kind,
            "kind": KIND_FAULT,
            "what": faultlib.label_for(kind),
            "declared_in": "argazui/argazui/faults.py (KINDS)",
            "scenarios": [],
        })

    loaded = procs.load_all(procedures_dir)
    for pid, proc in sorted(loaded.items()):
        out.append({
            "id": pid,
            "kind": KIND_PROCEDURE,
            "what": proc.label("en"),
            "declared_in": f"argazui/procedures/{pid}.yaml",
            "role": proc.role,
            "criteria": len(proc.expect),
            "unsupported_reason": _procedure_support(proc),
        })

    # Which scenarios point at which fault mechanism. This is what turns
    # DEFINED into EXECUTABLE: a mechanism nobody can invoke is a code path.
    by_id = {entry["id"]: entry for entry in out if entry["kind"] == KIND_FAULT}
    for pid, proc in sorted(loaded.items()):
        for fault in proc.failures:
            entry = by_id.get(fault.kind)
            if entry is not None:
                entry["scenarios"].append(trace.fault_id(pid, fault.id))
    return out


# ------------------------------------------------------------------ evidence
def _runs_under(roots: list[Path]) -> list[dict]:
    out: list[dict] = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("result.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def _evidence(runs: list[dict]) -> dict:
    """What the run directories on disk actually show, per mechanism id.

    Returns {id: {"exercised": [run ids], "verified": [run ids]}}. The run ids
    are kept rather than counted: a matrix cell claiming VERIFIED with no way
    to open the flight behind it is the unearned tick this project exists to
    remove.
    """
    found: dict[str, dict] = {}

    def note(identifier: str, level: str, run_id: str) -> None:
        entry = found.setdefault(identifier, {"exercised": [], "verified": []})
        if run_id not in entry[level]:
            entry[level].append(run_id)

    for result in runs:
        run_id = result.get("run_id") or ""
        for procedure in result.get("procedures") or []:
            pid = procedure.get("procedure")
            outcome = procedure.get("result") or {}
            if not pid:
                continue

            # A procedure is EXERCISED when a run executed it at all, and
            # VERIFIED when at least one of its criteria was actually judged.
            # `_was_evaluated` is the single implementation of that question,
            # added by v1.6.1 precisely so three modules stop disagreeing.
            note(pid, "exercised", run_id)
            if any(trace._was_evaluated(c) for c in outcome.get("expect") or []):
                note(pid, "verified", run_id)

            for fault in outcome.get("faults") or []:
                if not fault.get("applied"):
                    # Fail-closed, the same rule coverage.py applies: a fault
                    # that was declared and never injected exercised nothing.
                    continue
                kind = fault.get("fault")
                if not kind:
                    continue
                note(kind, "exercised", run_id)
                # VERIFIED needs a judged verdict, not a successful injection.
                # `evidence_missing` is the runner's own statement that the
                # criteria rested on telemetry that never arrived, and a
                # verdict built on that is not a verdict.
                if fault.get("passed") is not None and not fault.get("evidence_missing"):
                    note(kind, "verified", run_id)
    return found


# ------------------------------------------------------------------ the matrix
def collect(runs_roots: Optional[list[Path]] = None,
            procedures_dir: Optional[Path] = None) -> dict:
    """The whole matrix, recomputed from disk."""
    from . import paths

    roots = [Path(r) for r in (runs_roots or [paths.RUNS_DIR])]
    runs = _runs_under(roots)
    evidence = _evidence(runs)
    rows: list[dict] = []

    for entry in declared(procedures_dir):
        seen = evidence.get(entry["id"], {})
        exercised = list(seen.get("exercised") or [])
        verified = list(seen.get("verified") or [])

        if entry["kind"] == KIND_FAULT:
            executable = bool(entry["scenarios"])
            why_not = ("" if executable else
                       "declared in faults.KINDS and named by no scenario, so "
                       "nothing can point it at an aircraft")
        else:
            executable = entry.get("unsupported_reason") is None
            why_not = entry.get("unsupported_reason") or ""

        if verified:
            state = VERIFIED
        elif exercised:
            state = EXERCISED
        elif not executable and entry["kind"] == KIND_PROCEDURE:
            state = UNSUPPORTED
        elif not executable:
            state = DEFINED
        else:
            state = NOT_EXERCISED
            # A stated reason where somebody has looked, and the generic one
            # where nobody has. The two are different facts and the report
            # says which it is holding.
            why_not = NOT_EXERCISED_REASONS.get(entry["id"], "")

        rows.append({
            "id": entry["id"],
            "kind": entry["kind"],
            "what": entry["what"],
            "declared_in": entry["declared_in"],
            "state": state,
            "defined": True,
            "executable": executable,
            "exercised": bool(exercised),
            "verified": bool(verified),
            # The run ids, so every claim in this table can be opened.
            "evidence": sorted(verified or exercised)[:5],
            "scenarios": entry.get("scenarios") or [],
            "reason": why_not,
        })

    rows.sort(key=lambda r: (r["kind"], STATE_ORDER[r["state"]], r["id"]))
    counts = {state: sum(1 for r in rows if r["state"] == state)
              for state in STATES}
    return {
        "schema": SCHEMA,
        "roots": [str(r) for r in roots],
        "runs_read": len(runs),
        "counts": counts,
        "mechanisms": rows,
    }


def by_state(document: dict, state: str) -> list[dict]:
    return [row for row in document["mechanisms"] if row["state"] == state]


# ------------------------------------------------------------------ rendering
def render(document: dict) -> str:
    """The matrix as a document a person reads. Same facts, no new ones."""
    out: list[str] = []
    add = out.append

    add("## Mechanism coverage")
    add("")
    add("What this installation DECLARES it can do, against what a run "
        "directory on disk shows it has actually done. `Verified` is the only "
        "column that says anything about an aircraft, and it requires a "
        "recorded flight in which a criterion judged the result — a mechanism "
        "that was invoked and left unjudged is `Exercised`, not `Verified`.")
    add("")
    add(f"Read from {document['runs_read']} run(s) under "
        + ", ".join(f"`{r}`" for r in document["roots"]) + ".")
    add("")
    add("| Mechanism | Kind | Defined | Executable | Exercised | Verified | "
        "Evidence | State |")
    add("|---|---|:-:|:-:|:-:|:-:|---|---|")
    for row in document["mechanisms"]:
        mark = lambda flag: "yes" if flag else "—"        # noqa: E731
        evidence = (", ".join(f"`{r}`" for r in row["evidence"][:2])
                    if row["evidence"] else "—")
        add(f"| `{row['id']}` | {row['kind']} | {mark(row['defined'])} "
            f"| {mark(row['executable'])} | {mark(row['exercised'])} "
            f"| {mark(row['verified'])} | {evidence} | **{row['state']}** |")
    add("")
    counts = ", ".join(f"{state} {document['counts'][state]}"
                       for state in STATES if document["counts"][state])
    add(f"Counts: {counts or 'nothing declared'}.")
    add("")

    unproven = [row for row in document["mechanisms"]
                if row["state"] in (NOT_EXERCISED, DEFINED, UNSUPPORTED)]
    if unproven:
        add("### Declared and unproven")
        add("")
        add("Named rather than left to be discovered. None of these is a "
            "defect on its own; each is a claim this project has not earned "
            "yet, and publishing the list is the point.")
        add("")
        for row in unproven:
            add(f"* **`{row['id']}`** ({row['state']}) — "
                + (row["reason"] or "declared, executable, and no recorded run "
                                    "has executed it"))
        add("")
    return "\n".join(out)
