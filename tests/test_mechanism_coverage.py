"""F-18/F-19 — the matrix says what is proven, and refuses to say more.

WHAT THIS FILE HAS TO PROVE, FROM §9 AND §19 OF THE v1.7 BRIEF
--------------------------------------------------------------
    * every mechanism has a state, and the states are distinguishable
    * `Verified` is never claimed without an actual recorded flight
    * a mechanism nothing can invoke is not reported as merely uncovered
    * a mechanism that cannot be run here is UNSUPPORTED with a reason, and is
      not faked into looking exercised
    * the two mechanisms the audit named as orphaned are now executable

THE ONE RULE
------------
Nothing may reach EXERCISED or VERIFIED except through a run directory on disk
that recorded it. Most of the tests below are therefore about what the matrix
REFUSES to claim, which is the useful half.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argazui import faults, mechanisms, procedures as procs

pytestmark = pytest.mark.tier1


def _run(directory: Path, run_id: str, procedure: str,
         expect=None, faults_recorded=None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({
        "schema": 6, "run_id": run_id, "status": "passed",
        "model": {"id": "quad"},
        "procedures": [{
            "procedure": procedure, "role": "takeoff",
            "result": {"outcome": "passed", "steps": [],
                       "expect": expect or [],
                       "faults": faults_recorded or []},
        }],
    }, indent=2), encoding="utf-8")


# ----------------------------------------------------------- the declaration
def test_every_declared_mechanism_gets_exactly_one_state(tmp_path):
    document = mechanisms.collect([tmp_path])
    assert document["mechanisms"], "nothing is declared at all"
    for row in document["mechanisms"]:
        assert row["state"] in mechanisms.STATES, row
    assert sum(document["counts"].values()) == len(document["mechanisms"])


def test_every_fault_kind_the_code_implements_is_in_the_matrix(tmp_path):
    """A mechanism that fell out of the matrix would be invisible rather than
    uncovered, which is the failure this report exists to prevent."""
    document = mechanisms.collect([tmp_path])
    listed = {row["id"] for row in document["mechanisms"]
              if row["kind"] == mechanisms.KIND_FAULT}
    assert listed == set(faults.KINDS)


def test_every_shipped_procedure_is_in_the_matrix(tmp_path):
    document = mechanisms.collect([tmp_path])
    listed = {row["id"] for row in document["mechanisms"]
              if row["kind"] == mechanisms.KIND_PROCEDURE}
    assert listed == set(procs.load_all())


# --------------------------------------------- nothing is verified for free
def test_nothing_is_verified_without_a_recorded_run(tmp_path):
    """The rule, asserted against an empty evidence tree.

    Every mechanism this project declares exists in source. If existing in
    source were enough, this assertion would fail — and that is exactly the
    claim the audit found being made by a coverage figure.
    """
    document = mechanisms.collect([tmp_path])
    verified = [r["id"] for r in document["mechanisms"] if r["verified"]]
    exercised = [r["id"] for r in document["mechanisms"] if r["exercised"]]
    assert verified == [], f"verified with no evidence at all: {verified}"
    assert exercised == [], f"exercised with no evidence at all: {exercised}"


def test_a_declared_fault_that_no_scenario_names_is_not_executable(tmp_path,
                                                                   monkeypatch):
    """DEFINED is a different answer from NOT_EXERCISED.

    A mechanism nobody can invoke needs a scenario written; one that a scenario
    names needs a flight. Reporting both as "uncovered" loses which.
    """
    empty = tmp_path / "procedures"
    empty.mkdir()
    document = mechanisms.collect([tmp_path], procedures_dir=empty)
    for row in document["mechanisms"]:
        if row["kind"] != mechanisms.KIND_FAULT:
            continue
        assert row["state"] == mechanisms.DEFINED
        assert row["executable"] is False
        assert "no scenario" in row["reason"]


def test_the_two_orphaned_mechanisms_are_now_executable():
    """F-19, closed at the declaration level.

    `gps_degradation` and `mavlink_degradation` were in `faults.KINDS` with
    unit tests and no scenario, so nothing could point either at an aircraft.
    Two scenario files make them reachable; flying them is what
    `test_tier1_degradation_faults.py` does.
    """
    document = mechanisms.collect([Path("/nonexistent")])
    by_id = {row["id"]: row for row in document["mechanisms"]}
    for kind in ("gps_degradation", "mavlink_degradation"):
        row = by_id[kind]
        assert row["executable"] is True, (
            f"{kind} is still named by no scenario")
        assert row["scenarios"], f"{kind} names no scenario"
        assert row["state"] == mechanisms.NOT_EXERCISED, (
            f"{kind} claims {row['state']} with no run directory behind it")


# ------------------------------------------------- exercised versus verified
def test_an_injected_fault_that_nobody_judged_is_exercised_not_verified(tmp_path):
    """"The mechanism worked" and "the aircraft handled it" are two claims.

    This is the same distinction `FaultResult` enforces with four separate
    fields, and losing it in the matrix would put back exactly the unearned
    tick the fields exist to prevent.
    """
    _run(tmp_path / "run1", "run1", "copter_gps_loss", faults_recorded=[{
        "id": "gps_off_in_hover", "fault": "gps_loss", "applied": True,
        "passed": False, "evidence_missing": True,
    }])
    row = {r["id"]: r for r in mechanisms.collect([tmp_path])["mechanisms"]}
    assert row["gps_loss"]["exercised"] is True
    assert row["gps_loss"]["verified"] is False
    assert row["gps_loss"]["state"] == mechanisms.EXERCISED


def test_a_judged_fault_is_verified_and_names_the_run(tmp_path):
    _run(tmp_path / "run1", "run1", "copter_gps_loss", faults_recorded=[{
        "id": "gps_off_in_hover", "fault": "gps_loss", "applied": True,
        "passed": True, "evidence_missing": False,
    }])
    row = {r["id"]: r for r in mechanisms.collect([tmp_path])["mechanisms"]}
    assert row["gps_loss"]["state"] == mechanisms.VERIFIED
    assert "run1" in row["gps_loss"]["evidence"], (
        "a VERIFIED cell with no run behind it cannot be checked by anybody")


def test_a_declared_fault_that_was_never_injected_covers_nothing(tmp_path):
    """Fail-closed, the same rule coverage.py applies.

    A scenario that ran without its fault is a nominal flight under an
    off-nominal name, and counting it would make the matrix reward running the
    file rather than injecting the fault.
    """
    _run(tmp_path / "run1", "run1", "copter_gps_loss", faults_recorded=[{
        "id": "gps_off_in_hover", "fault": "gps_loss", "applied": False,
        "passed": False,
    }])
    row = {r["id"]: r for r in mechanisms.collect([tmp_path])["mechanisms"]}
    assert row["gps_loss"]["exercised"] is False
    assert row["gps_loss"]["state"] == mechanisms.NOT_EXERCISED


def test_a_procedure_whose_criteria_were_all_unjudged_is_not_verified(tmp_path):
    """`evaluated: false` is the third state v1.6.1 added, and it counts here.

    A criterion refused for missing evidence is not a verdict about anything,
    so a procedure whose every criterion was refused has been exercised and
    has verified nothing.
    """
    _run(tmp_path / "run1", "run1", "copter_land", expect=[{
        "criterion_id": "copter_land#on-ground", "label": "on the ground",
        "passed": False, "evaluated": False,
        "text": "not judged — 'alt_below' rests on GLOBAL_POSITION_INT",
    }])
    row = {r["id"]: r for r in mechanisms.collect([tmp_path])["mechanisms"]}
    assert row["copter_land"]["exercised"] is True
    assert row["copter_land"]["verified"] is False
    assert row["copter_land"]["state"] == mechanisms.EXERCISED


def test_a_measured_failure_still_counts_as_verified(tmp_path):
    """VERIFIED means judged, not passed.

    A procedure whose criterion was measured and did NOT hold has verified
    exactly as much as one that passed: the mechanism ran and produced a
    verdict about the aircraft. Requiring a pass would make the matrix reward
    green rather than evidence.
    """
    _run(tmp_path / "run1", "run1", "copter_land", expect=[{
        "criterion_id": "copter_land#on-ground", "label": "on the ground",
        "passed": False, "evaluated": True, "text": "alt=12.0m",
    }])
    row = {r["id"]: r for r in mechanisms.collect([tmp_path])["mechanisms"]}
    assert row["copter_land"]["state"] == mechanisms.VERIFIED


# ------------------------------------------------------------- unsupported
def test_a_mechanism_that_cannot_run_here_says_so_rather_than_being_faked():
    """UNSUPPORTED with a reason, and never quietly promoted.

    The two mission procedures declare an `upload_mission` step that no tier in
    this suite exercises. That is a fact about the suite, not about the
    procedures, and stating it is more useful than a red cell — and far more
    useful than inventing a flight.
    """
    document = mechanisms.collect([Path("/nonexistent")])
    unsupported = [r for r in document["mechanisms"]
                   if r["state"] == mechanisms.UNSUPPORTED]
    assert unsupported, "nothing is reported as unsupported"
    for row in unsupported:
        assert row["reason"], f"{row['id']} is unsupported with no reason"
        assert row["verified"] is False
        assert row["exercised"] is False


def test_the_unproven_are_named_in_the_rendered_report():
    """Publishing the list is the deliverable; the percentage is the summary."""
    document = mechanisms.collect([Path("/nonexistent")])
    text = mechanisms.render(document)
    assert "### Declared and unproven" in text
    for row in document["mechanisms"]:
        if row["state"] in (mechanisms.NOT_EXERCISED, mechanisms.DEFINED,
                            mechanisms.UNSUPPORTED):
            assert f"`{row['id']}`" in text, row["id"]


def test_the_rendered_matrix_has_the_columns_the_brief_names():
    document = mechanisms.collect([Path("/nonexistent")])
    text = mechanisms.render(document)
    for column in ("Mechanism", "Defined", "Executable", "Exercised",
                   "Verified", "Evidence"):
        assert column in text, column


def test_the_matrix_is_recomputed_and_never_accumulated(tmp_path):
    """A deleted run takes its claim with it.

    No accumulator and no cache, exactly as coverage.py and campaign.py work —
    which is what makes it impossible for the matrix to drift from the evidence
    under it.
    """
    _run(tmp_path / "run1", "run1", "copter_land", expect=[
        {"criterion_id": "copter_land#on-ground", "passed": True,
         "evaluated": True, "label": "on the ground", "text": "alt=0.1m"}])
    before = {r["id"]: r["state"] for r in
              mechanisms.collect([tmp_path])["mechanisms"]}
    assert before["copter_land"] == mechanisms.VERIFIED

    (tmp_path / "run1" / "result.json").unlink()
    after = {r["id"]: r["state"] for r in
             mechanisms.collect([tmp_path])["mechanisms"]}
    assert after["copter_land"] == mechanisms.NOT_EXERCISED
