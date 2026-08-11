"""Every failure gets one category, and the category has to be the right one.

WHY THESE ARE WORTH TESTING
---------------------------
The classification is read by `docs/status.md`, by the run listing, by the
flight report and by every campaign summary. If it puts a refused ARM under
`acceptance`, four different readers are told the aircraft misbehaved when the
aircraft was never armed — which is the exact class of untruth this project
exists to remove, pointed at the diagnosis instead of at the verdict.

Needs no vehicle; the `tier1` marker only says which CI job runs it.
"""
from __future__ import annotations

import pytest

from argazui import failures

pytestmark = pytest.mark.tier1


def procedure_result(**overrides) -> dict:
    """A passing procedure result, for a test to break one field of."""
    base = {
        "ok": True, "outcome": "passed", "procedure": "copter_takeoff",
        "role": "takeoff", "steps": [], "expect": [], "faults": [],
        "params_changed": {}, "text": "",
    }
    base.update(overrides)
    return base


def step(**overrides) -> dict:
    base = {"index": 0, "kind": "set_mode", "label": "Switch to GUIDED",
            "status": "passed", "text": "", "seconds": 0.1}
    base.update(overrides)
    return base


def criterion(**overrides) -> dict:
    base = {"label": "reached altitude", "condition": {}, "passed": True,
            "text": "", "kind": "eventually", "duration": None}
    base.update(overrides)
    return base


# ------------------------------------------------------------------ nothing
def test_a_passing_procedure_has_no_failure():
    """None, not a category called "none" — see failures.py."""
    assert failures.classify_procedure(procedure_result()) is None


def test_a_passing_run_has_no_failure():
    run = {"status": "passed", "procedures": [{"procedure": "copter_takeoff",
                                               "role": "takeoff",
                                               "result": procedure_result()}],
           "artefacts": {"dataflash": "00000001.BIN", "dataflash_check":
                         {"complete": True, "error": ""}}}
    assert failures.classify_run(run) is None


# ------------------------------------------------------------- the categories
def test_a_refused_arm_is_vehicle_readiness_not_acceptance():
    """The distinction the whole taxonomy exists for.

    An aircraft that never armed has not misbehaved in the air; it has not been
    in the air. Reporting that as an acceptance failure would say the opposite
    of what happened.
    """
    result = procedure_result(
        outcome="failed", ok=False,
        steps=[step(index=1, kind="arm", label="Arm the motors",
                    status="failed",
                    text="ARM: REJECTED (MAV_RESULT_FAILED) — autopilot: "
                         "PreArm: AHRS: waiting for home")],
        expect=[criterion(passed=False, text="not evaluated")])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.VEHICLE_READINESS
    assert failure.code == failures.CODE_ARM_REFUSED
    assert "waiting for home" in failure.detail


def test_a_prearm_complaint_on_a_non_arm_step_is_still_readiness():
    """The autopilot's own wording decides, not the step type alone."""
    result = procedure_result(
        outcome="failed", ok=False,
        steps=[step(status="failed", text="PreArm: Compass not calibrated")])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.VEHICLE_READINESS


def test_a_refused_mode_is_a_procedure_failure():
    result = procedure_result(
        outcome="failed", ok=False,
        steps=[step(status="failed",
                    text="mode GUIDED: REJECTED (MAV_RESULT_TEMPORARILY_REJECTED)")])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.PROCEDURE
    assert failure.code == failures.CODE_STEP_FAILED


@pytest.mark.parametrize("text", [
    # The exact wording i18n.py produces, in both languages: a classifier that
    # only knew the English form would file every Turkish session's timeout
    # under the generic code.
    "the expected state did not arrive within 60s — last seen: alt=3.2m",
    "beklenen duruma 60 sn icinde ulasilmadi — son gorulen: alt=3.2m",
    "'arm' timed out",
    "the procedure exceeded its overall timeout of 240s",
])
def test_a_timed_out_step_gets_its_own_code(text):
    result = procedure_result(
        outcome="failed", ok=False,
        steps=[step(kind="wait_for", status="failed", text=text)])
    assert failures.classify_procedure(result).code == failures.CODE_STEP_TIMEOUT


def test_a_criterion_that_did_not_hold_is_acceptance():
    """The only category that is a verdict about the aircraft."""
    result = procedure_result(
        outcome="failed", ok=False,
        steps=[step()],
        expect=[criterion(),
                criterion(label="held for 5s", passed=False,
                          text="held for only 1.2s of the 5s required")])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.ACCEPTANCE
    assert failure.code == failures.CODE_CRITERION_FAILED
    assert failure.source == "expect[1]", "the failing criterion must be named"


@pytest.mark.parametrize("text", [
    "not judged — 'angular_rate_above' rests on attitude telemetry that never arrived",
    "not evaluated — the procedure stopped earlier",
    "degerlendirilmedi — prosedur daha once durdu",
])
def test_a_criterion_that_was_never_judged_says_so(text):
    """"Nothing was measured" is not "something was wrong", in either language.

    The run record stores the message in whichever language the flight was
    flown in, so the classifier has to recognise both or a Turkish session
    would report every unevaluated criterion as a real failure.

    The CATEGORY changed in the v1.6 corrective release, and the change is the
    point of the test rather than an incidental update. `acceptance` is
    documented as the only category that means the aircraft did something
    wrong; a criterion whose telemetry never arrived says nothing about the
    aircraft at all, so it is a hole in the EVIDENCE. Filing it under
    `acceptance` was the same conflation this module exists to prevent, one
    level further down. The code is unchanged, so anything counting
    `criterion-not-judged` still finds it.
    """
    result = procedure_result(
        outcome="failed", ok=False,
        expect=[criterion(passed=False, text=text)])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_CRITERION_NOT_JUDGED


def test_a_runner_error_is_infrastructure_and_outranks_everything():
    """It says nothing about the aircraft, so it must not be reported as if it did."""
    result = procedure_result(
        outcome="error", ok=False,
        steps=[step(kind="arm", status="failed", text="PreArm: something")],
        expect=[criterion(passed=False, text="did not hold")],
        text="the procedure could not be evaluated: AttributeError")
    failure = failures.classify_procedure(result)
    assert failure.category == failures.INFRASTRUCTURE
    assert failure.code == failures.CODE_RUNNER_ERROR


def test_an_override_that_would_not_apply_outranks_the_steps_it_broke():
    """The vehicle is not in the configuration the procedure requires.

    Everything after that point was measured on an aircraft the procedure did
    not set up, so naming a later step would name a symptom.
    """
    result = procedure_result(
        outcome="failed", ok=False,
        params_changed={"TKOFF_ALT": {"set_to": 50, "applied": False}},
        steps=[step(status="failed", text="mode TAKEOFF: REJECTED")])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.ENVIRONMENT
    assert failure.code == failures.CODE_OVERRIDE_FAILED


def test_a_fault_that_could_not_be_injected_is_an_environment_failure():
    """Fail closed: the scenario did not happen, so nothing else matters."""
    result = procedure_result(
        outcome="failed", ok=False,
        faults=[{"id": "gps_off", "applied": False,
                 "text": "this ArduPilot exposes none of SIM_GPS1_ENABLE"}])
    failure = failures.classify_procedure(result)
    assert failure.category == failures.ENVIRONMENT
    assert failure.code == failures.CODE_FAULT_NOT_APPLIED


def test_a_fault_that_could_not_be_cleared_is_reported_separately():
    """The simulator is still degraded — a different problem from a failed one."""
    result = procedure_result(
        outcome="failed", ok=False,
        faults=[{"id": "gps_off", "applied": True, "cleared": False}])
    assert failures.classify_procedure(result).code == failures.CODE_FAULT_NOT_CLEARED


# --------------------------------------------------------------------- runs
def test_a_run_whose_procedures_passed_can_still_fail_on_its_evidence():
    """A flight nobody can prove happened is worth what one that did not is."""
    run = {"status": "passed",
           "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                           "result": procedure_result()}],
           "artefacts": {"dataflash": "00000001.BIN",
                         "dataflash_check": {"complete": False,
                                             "error": "no timestamped tail"}}}
    failure = failures.classify_run(run)
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_TRUNCATED_DATAFLASH


def test_a_missing_log_after_a_procedure_ran_is_an_evidence_failure():
    run = {"status": "passed",
           "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                           "result": procedure_result()}],
           "artefacts": {"dataflash": None,
                         "dataflash_absent_reason": "the vehicle armed but no "
                                                    ".BIN newer than the run "
                                                    "start was found"}}
    assert failures.classify_run(run).code == failures.CODE_NO_DATAFLASH


def test_a_session_that_flew_nothing_is_missing_nothing():
    """Started and stopped without a procedure asserts nothing, so nothing is absent."""
    run = {"status": "no-procedure", "procedures": [],
           "artefacts": {"dataflash": None,
                         "dataflash_absent_reason": "the vehicle never armed"}}
    assert failures.classify_run(run) is None


def test_only_the_last_attempt_of_a_procedure_is_classified():
    """The suite is allowed one retry, and it is paid for with `flaky`.

    Classifying the failed first attempt would report a failure the retry went
    on to clear, on a run the status table calls flaky rather than failed.
    """
    run = {"status": "passed",
           "procedures": [
               {"procedure": "copter_takeoff", "role": "takeoff", "attempt": 1,
                "result": procedure_result(outcome="failed", ok=False,
                                           steps=[step(status="failed",
                                                       text="mode refused")])},
               {"procedure": "copter_takeoff", "role": "takeoff", "attempt": 2,
                "result": procedure_result()}],
           "artefacts": {"dataflash": "00000001.BIN",
                         "dataflash_check": {"complete": True, "error": ""}}}
    assert failures.classify_run(run) is None


# ------------------------------------------------------------- comparisons
def test_a_regression_is_classified_as_a_regression():
    comparison = {"verdict": "regressed",
                  "degraded": ["peak_angular_rate"],
                  "compatibility": {"blocking": [], "configuration_drift": []}}
    failure = failures.classify_comparison(comparison)
    assert failure.category == failures.REGRESSION
    assert "peak_angular_rate" in failure.detail


def test_incomparable_runs_are_evidence_and_not_regression():
    """Two runs that do not line up have not shown that anything got worse.

    Reporting them as a regression is the mis-specified-baseline bug that
    `argazui compare` gives its own exit code to avoid.
    """
    comparison = {"verdict": "incomparable", "degraded": [],
                  "compatibility": {
                      "blocking": [{"field": "model",
                                    "reason": "the two runs flew different aircraft"}],
                      "configuration_drift": []}}
    failure = failures.classify_comparison(comparison)
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_NOT_COMPARABLE


def test_a_clean_comparison_is_not_a_failure():
    assert failures.classify_comparison({"verdict": "passed"}) is None


# ------------------------------------------------------------------ taxonomy
def test_the_taxonomy_is_closed_and_documented_in_both_languages():
    """A category with no explanation is a label, not a diagnosis."""
    assert set(failures.CATALOGUE) == set(failures.CATEGORIES)
    for category, spec in failures.CATALOGUE.items():
        for field in ("label", "what", "look_at"):
            for lang in ("en", "tr"):
                assert spec[field].get(lang), f"{category}.{field} has no {lang}"


def test_an_unknown_category_cannot_be_constructed():
    with pytest.raises(ValueError):
        failures.Failure("aircraft_is_haunted", "spooky")


def test_summarise_counts_by_category():
    tally = failures.summarise([
        failures.Failure(failures.ACCEPTANCE, "criterion-failed"),
        failures.Failure(failures.ACCEPTANCE, "criterion-failed"),
        failures.Failure(failures.ENVIRONMENT, "fault-not-applied"),
        None,
    ])
    assert tally == {failures.ACCEPTANCE: 2, failures.ENVIRONMENT: 1}
