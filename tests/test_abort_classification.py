"""A broken simulator must not be reported as a broken aircraft.

WHAT THIS FILE EXISTS TO STOP COMING BACK
-----------------------------------------
`failures.py` opens by saying that `acceptance` "is the only one that means the
aircraft did something wrong", and that conflating the categories "is how a
broken harness comes to be reported as a broken aircraft". The v1.6 audit then
showed it doing exactly that: five distinct non-aircraft aborts all classified
`acceptance` / `criterion-not-judged`.

    fault mechanism absent on this firmware  -> acceptance
    operator cancelled the run               -> acceptance
    the procedure's overall timeout          -> acceptance
    fault start condition never held         -> acceptance
    unresolvable placeholder in the document -> acceptance

The mechanism was structural rather than a mistaken branch. An abort leaves
skipped steps and criteria marked "not evaluated" behind; `classify_procedure`
looked at that residue, found a criterion that had not passed, and named it.
The cause was not in the document at all — so the runner records it now
(`result["abort"]`) and the classifier dispatches on it before anything else.

Every test below builds a result document the way the runner does and asserts
the category. The `_aborted` helper deliberately includes the residue — skipped
steps, unevaluated criteria — because a document WITHOUT it would pass these
tests for the wrong reason.
"""
from __future__ import annotations

import pytest

from argazui import failures, procrunner

pytestmark = pytest.mark.tier1


def _aborted(kind: str, text: str = "something went wrong") -> dict:
    """The document a real abort leaves: no failed step, nothing judged."""
    return {
        "outcome": "failed",
        "procedure": "copter_gps_loss",
        "text": text,
        "abort": {"kind": kind, "text": text},
        "params_changed": {},
        "faults": [],
        "steps": [
            {"index": 0, "kind": "set_mode", "status": "skipped",
             "label": "Switch to GUIDED", "text": ""},
            {"index": 1, "kind": "arm", "status": "skipped",
             "label": "Arm", "text": ""},
        ],
        "expect": [
            {"label": "reached altitude", "passed": False, "evaluated": False,
             "text": "not evaluated — the procedure stopped earlier"},
        ],
    }


# ------------------------------------------------------- the five regressions
@pytest.mark.parametrize("kind, category, code", [
    (procrunner.ABORT_FAULT_UNAVAILABLE,
     failures.ENVIRONMENT, failures.CODE_FAULT_UNAVAILABLE),
    (procrunner.ABORT_FAULT_REFUSED,
     failures.ENVIRONMENT, failures.CODE_FAULT_NOT_APPLIED),
    (procrunner.ABORT_OVERRIDE,
     failures.ENVIRONMENT, failures.CODE_OVERRIDE_FAILED),
    (procrunner.ABORT_NO_VEHICLE,
     failures.ENVIRONMENT, failures.CODE_NO_VEHICLE),
    (procrunner.ABORT_CONFIG,
     failures.ENVIRONMENT, failures.CODE_CONFIG_ERROR),
    (procrunner.ABORT_TIMEOUT,
     failures.PROCEDURE, failures.CODE_PROCEDURE_TIMEOUT),
    (procrunner.ABORT_FAULT_START,
     failures.PROCEDURE, failures.CODE_FAULT_START_MISSED),
    (procrunner.ABORT_CANCELLED,
     failures.INFRASTRUCTURE, failures.CODE_CANCELLED),
])
def test_an_abort_is_classified_by_its_stated_reason(kind, category, code):
    failure = failures.classify_procedure(_aborted(kind))
    assert failure is not None
    assert failure.category == category, (
        f"{kind} classified {failure.category}, expected {category}")
    assert failure.code == code


@pytest.mark.parametrize("kind", [k for k in procrunner.ABORT_KINDS
                                  if k != procrunner.ABORT_STEP])
def test_no_abort_reason_is_ever_an_acceptance_failure(kind):
    """The single most important assertion in this file.

    `acceptance` means the aircraft did something the procedure said it must
    not. None of these did — the aircraft was never asked.
    """
    failure = failures.classify_procedure(_aborted(kind))
    assert failure is not None
    assert failure.category != failures.ACCEPTANCE, (
        f"'{kind}' is reported as an aircraft acceptance failure")


def test_every_abort_kind_the_runner_can_raise_has_a_category():
    """A kind added to the runner and not to the table would go silent."""
    unmapped = [k for k in procrunner.ABORT_KINDS
                if k != procrunner.ABORT_STEP
                and k not in failures.ABORT_CATEGORIES]
    assert not unmapped, f"abort kinds with no classification: {unmapped}"


def test_the_table_names_no_kind_the_runner_cannot_raise():
    stray = set(failures.ABORT_CATEGORIES) - set(procrunner.ABORT_KINDS)
    assert not stray, f"classified kinds the runner never produces: {sorted(stray)}"


# ------------------------------------------------- real failures still land right
def test_a_genuine_acceptance_violation_is_still_acceptance():
    """The fix must not make everything non-acceptance.

    This is the counterweight: a flow that ran to the end and a criterion that
    was measured and did not hold is the one case that IS a verdict about the
    aircraft, and it has to keep being reported as one.
    """
    failure = failures.classify_procedure({
        "outcome": "failed", "procedure": "copter_takeoff",
        "text": "failed", "params_changed": {}, "faults": [], "abort": None,
        "steps": [{"index": 0, "kind": "set_mode", "status": "passed",
                   "label": "GUIDED", "text": "mode -> GUIDED"}],
        "expect": [{"label": "held a nose-up hover instead of tumbling",
                    "passed": False, "evaluated": True,
                    "text": "pitch outside [55,115]° for 56.6s"}],
    })
    assert failure is not None
    assert failure.category == failures.ACCEPTANCE
    assert failure.code == failures.CODE_CRITERION_FAILED
    assert "tumbling" in failure.detail


def test_a_criterion_nobody_could_measure_is_evidence_not_acceptance():
    """The F-01 verdict has to land in the right category too.

    A criterion refused because its telemetry never arrived says nothing about
    the aircraft. It is a hole in the evidence, and filing it under
    `acceptance` would be the same conflation one level down.
    """
    failure = failures.classify_procedure({
        "outcome": "failed", "procedure": "copter_land",
        "text": "failed", "params_changed": {}, "faults": [], "abort": None,
        "steps": [{"index": 0, "kind": "set_mode", "status": "passed",
                   "label": "LAND", "text": "mode -> LAND"}],
        "expect": [{"label": "on the ground", "passed": False,
                    "evaluated": False,
                    "text": "no measurement — this condition rests on "
                            "GLOBAL_POSITION_INT (altitude), which has not arrived."}],
    })
    assert failure is not None
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_CRITERION_NOT_JUDGED


def test_a_measured_failure_outranks_an_unmeasured_one():
    """When a run has both, the aircraft result is the one worth naming."""
    failure = failures.classify_procedure({
        "outcome": "failed", "procedure": "copter_takeoff",
        "text": "failed", "params_changed": {}, "faults": [], "abort": None,
        "steps": [{"index": 0, "kind": "arm", "status": "passed",
                   "label": "Arm", "text": ""}],
        "expect": [
            {"label": "unmeasurable", "passed": False, "evaluated": False,
             "text": "no measurement"},
            {"label": "real violation", "passed": False, "evaluated": True,
             "text": "alt=2.1m, wanted above 18"},
        ],
    })
    assert failure.category == failures.ACCEPTANCE
    assert "real violation" in failure.detail


def test_a_failed_step_is_still_a_procedure_or_readiness_failure():
    """`ABORT_STEP` deliberately falls through to the step loop, which knows more."""
    readiness = failures.classify_procedure({
        "outcome": "failed", "procedure": "copter_takeoff", "text": "arm refused",
        "abort": {"kind": procrunner.ABORT_STEP, "text": "arm refused"},
        "params_changed": {}, "faults": [],
        "steps": [{"index": 0, "kind": "arm", "status": "failed",
                   "label": "Arm", "text": "PreArm: GPS horizontal speed error"}],
        "expect": [{"label": "c", "passed": False, "evaluated": False, "text": ""}],
    })
    assert readiness.category == failures.VEHICLE_READINESS
    assert readiness.code == failures.CODE_ARM_REFUSED


def test_a_runner_error_still_outranks_everything():
    failure = failures.classify_procedure({
        "outcome": "error", "procedure": "p", "text": "TypeError: boom",
        "abort": {"kind": procrunner.ABORT_CANCELLED, "text": "cancelled"},
        "params_changed": {}, "faults": [], "steps": [], "expect": [],
    })
    assert failure.category == failures.INFRASTRUCTURE
    assert failure.code == failures.CODE_RUNNER_ERROR


def test_a_passing_procedure_is_never_classified():
    assert failures.classify_procedure(
        {"outcome": "passed", "procedure": "p"}) is None


# ---------------------------------------------------- old runs keep classifying
def test_a_run_recorded_before_the_abort_field_still_classifies():
    """Archived documents have no `abort` key and no `evaluated` flag.

    They fall back to the prose rules, which is what they were written under.
    Refusing to read them would reclassify every run in the repository.
    """
    failure = failures.classify_procedure({
        "outcome": "failed", "procedure": "copter_takeoff", "text": "failed",
        "params_changed": {}, "faults": [],
        "steps": [{"index": 0, "kind": "set_mode", "status": "passed",
                   "label": "m", "text": ""}],
        "expect": [{"label": "alt", "passed": False,
                    "text": "alt=2.1m, wanted above 18"}],
    })
    assert failure.category == failures.ACCEPTANCE
    assert failure.code == failures.CODE_CRITERION_FAILED


def test_an_old_not_judged_criterion_reads_as_evidence():
    failure = failures.classify_procedure({
        "outcome": "failed", "procedure": "p", "text": "failed",
        "params_changed": {}, "faults": [],
        "steps": [{"index": 0, "kind": "set_mode", "status": "passed",
                   "label": "m", "text": ""}],
        "expect": [{"label": "rate", "passed": False,
                    "text": "not judged — 'angular_rate_above' rests on "
                            "attitude telemetry that never arrived."}],
    })
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_CRITERION_NOT_JUDGED
