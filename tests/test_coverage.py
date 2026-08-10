"""Coverage arithmetic, and the two places it must refuse to flatter itself.

THE TWO
-------
1. A criterion the procedure never reached is **not** covered. Counting it
   because it appears in a `result.json` would let a run that aborted at step
   two report full criterion coverage.
2. A criterion recorded before identifiers existed is **not** attributed by
   position. The procedure may have been edited since, and a coverage figure
   inflated by a guess is the exact shape of the unearned claim this project
   was rebuilt to remove.

Everything else here is counting, but counting is what a coverage report is,
and a coverage report that counts wrongly is worse than none: it is a number
people stop checking.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

import json

import pytest

from argazui import coverage

pytestmark = pytest.mark.tier1

REGISTRY = {"models": [
    {"id": "iris", "name": "Iris", "vehicle_class": "Copter"},
    {"id": "zephyr", "name": "Zephyr", "vehicle_class": "Plane"},
]}


def write_run(root, name: str, *, procedures=None, suite=None) -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({
        "run_id": name, "status": "passed",
        "procedures": procedures or [],
    }), encoding="utf-8")
    if suite is not None:
        (root / "suite.json").write_text(json.dumps(suite), encoding="utf-8")


def procedure(pid: str, criteria: list[dict], faults=None) -> dict:
    return {"procedure": pid, "role": "takeoff",
            "result": {"outcome": "passed", "steps": [],
                       "expect": criteria, "faults": faults or []}}


def criterion(identifier: str, *, passed=True, text="") -> dict:
    return {"label": identifier, "passed": passed, "text": text,
            "criterion_id": identifier}


def tier2_suite(*models, outcome="passed") -> dict:
    return {"tests": [
        {"nodeid": f"tests/test_tier2_models.py::test_x[{model}]",
         "markers": ["tier2"], "outcome": outcome}
        for model in models]}


# ------------------------------------------------------------- declarations
def test_the_five_dimensions_are_declared_and_labelled():
    assert coverage.DIMENSIONS == ("models", "procedures", "criteria", "faults",
                                   "experiments")
    for name in coverage.DIMENSIONS:
        for lang in ("en", "tr"):
            assert coverage.LABELS[name].get(lang)
            assert coverage.WHAT[name].get(lang)


def test_every_shipped_procedure_and_criterion_is_declared():
    procedures = coverage.declared_procedures()
    criteria = coverage.declared_criteria()
    assert len(procedures) >= 13
    assert len(criteria) >= 30
    # Every declared criterion names the procedure it belongs to, and every one
    # of them declares its own id — that is what makes the list quotable.
    assert all(item["procedure"] for item in criteria)
    assert all(item["declared_id"] for item in criteria)


def test_fault_coverage_counts_mechanisms_and_scenario_faults_separately():
    """They answer different questions.

    A kind with no scenario behind it is a mechanism nobody has pointed at an
    aircraft; a declared fault no run injected is a scenario nobody has flown.
    """
    declared = coverage.declared_faults()
    scopes = {item["scope"] for item in declared}
    assert scopes == {"mechanism", "scenario"}
    assert any(item["id"] == "gps_loss" for item in declared)
    assert any(item["id"] == "copter_gps_loss#gps_off_in_hover"
               for item in declared)


# ------------------------------------------------------------------ counting
def test_uncovered_items_are_named_not_just_counted(tmp_path):
    """A percentage with no list under it is an invitation to stop reading."""
    write_run(tmp_path, "20260810T120000Z_iris", suite=tier2_suite("iris"))
    document = coverage.collect([tmp_path], registry=REGISTRY)

    models = coverage.by_dimension(document, coverage.MODELS)
    assert models["covered"] == 1 and models["declared"] == 2
    assert models["uncovered"] == ["zephyr"]
    assert models["fraction"] == 0.5


def test_a_skipped_tier2_test_is_not_coverage(tmp_path):
    """A skip is the absence of coverage, not a quiet form of it."""
    write_run(tmp_path, "20260810T120000Z_iris",
              suite=tier2_suite("iris", outcome="skipped"))
    document = coverage.collect([tmp_path], registry=REGISTRY)
    assert coverage.by_dimension(document, coverage.MODELS)["covered"] == 0


def test_tier1_runs_do_not_count_as_model_coverage(tmp_path):
    """Tier 1 flies SITL's generic frames and says nothing about an airframe.

    Reading a tier-1 run as model coverage is exactly the conflation
    docs/status.md exists to prevent, pointed at a different table.
    """
    write_run(tmp_path, "20260810T120000Z_iris", suite={"tests": [
        {"nodeid": "tests/test_tier1_procedures.py::test_x[iris]",
         "markers": ["tier1"], "outcome": "passed"}]})
    document = coverage.collect([tmp_path], registry=REGISTRY)
    assert coverage.by_dimension(document, coverage.MODELS)["covered"] == 0


def test_a_procedure_is_covered_when_a_run_executed_it(tmp_path):
    write_run(tmp_path, "20260810T120000Z_iris",
              procedures=[procedure("copter_takeoff", [])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.PROCEDURES)
    assert "copter_takeoff" not in dimension["uncovered"]
    assert "copter_land" in dimension["uncovered"]


def test_an_evaluated_criterion_is_covered(tmp_path):
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        procedure("copter_takeoff", [criterion("copter_takeoff#alt-reached")])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.CRITERIA)
    assert "copter_takeoff#alt-reached" not in dimension["uncovered"]
    assert "copter_takeoff#alt-held" in dimension["uncovered"]


@pytest.mark.parametrize("text", [
    "not evaluated — the procedure stopped earlier",
    "not judged — 'angular_rate_above' rests on attitude telemetry that never "
    "arrived",
    "degerlendirilmedi — prosedur daha once durdu",
])
def test_a_criterion_that_was_never_reached_is_not_covered(tmp_path, text):
    """The first refusal. A run that aborted at step two covers nothing."""
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        procedure("copter_takeoff",
                  [criterion("copter_takeoff#alt-reached", passed=False,
                             text=text)])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.CRITERIA)
    assert "copter_takeoff#alt-reached" in dimension["uncovered"]


def test_a_failed_criterion_is_still_covered(tmp_path):
    """Covered means "some run exercised this and produced a result".

    A failing criterion produced a result about the aircraft — arguably the
    most informative kind — so counting only passes would make coverage a
    second, worse pass rate.
    """
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        procedure("copter_takeoff",
                  [criterion("copter_takeoff#alt-reached", passed=False,
                             text="did not become true within 20s")])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.CRITERIA)
    assert "copter_takeoff#alt-reached" not in dimension["uncovered"]


def test_a_criterion_with_no_identifier_is_counted_not_guessed(tmp_path):
    """The second refusal, and the one that matters on an upgrade.

    A run recorded before criterion identifiers existed cannot be attributed by
    position — the procedure may have been edited since. It is reported so a 0%
    first reading has a stated reason rather than looking like a project that
    tests nothing.
    """
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        {"procedure": "copter_takeoff", "role": "takeoff",
         "result": {"outcome": "passed", "steps": [], "faults": [],
                    "expect": [{"label": "old", "passed": True, "text": ""}]}}])
    document = coverage.collect([tmp_path], registry=REGISTRY)

    assert document["unattributable_criteria"] == 1
    assert coverage.by_dimension(document, coverage.CRITERIA)["covered"] == 0
    text = coverage.render(document)
    assert "could not be attributed" in text
    assert "not matched by position" in text


def test_an_uninjected_fault_covers_nothing(tmp_path):
    """Fail closed, applied to coverage: a fault that never happened proves
    nothing, and the scenario it belongs to was not flown."""
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        procedure("copter_gps_loss", [], faults=[
            {"id": "gps_off_in_hover", "fault": "gps_loss", "applied": False}])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.FAULTS)
    assert "gps_loss" in dimension["uncovered"]
    assert "copter_gps_loss#gps_off_in_hover" in dimension["uncovered"]


def test_an_injected_fault_covers_its_mechanism_and_its_scenario(tmp_path):
    write_run(tmp_path, "20260810T120000Z_iris", procedures=[
        procedure("copter_gps_loss", [], faults=[
            {"id": "gps_off_in_hover", "fault": "gps_loss", "applied": True,
             "passed": True}])])
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.FAULTS)
    assert "gps_loss" not in dimension["uncovered"]
    assert "copter_gps_loss#gps_off_in_hover" not in dimension["uncovered"]
    assert "mavlink_interrupt" in dimension["uncovered"]


# ---------------------------------------------------------------- experiments
def write_experiment_run(root, name: str, *, experiment: str, arm: str) -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({
        "run_id": name, "status": "passed", "procedures": [],
        "experiment": {"schema": 1, "id": experiment, "arm": arm,
                       "run": f"20260810T120000Z_{experiment}", "index": 1,
                       "of": 3},
    }), encoding="utf-8")


def test_every_shipped_experiment_and_arm_is_declared():
    declared = coverage.declared_experiments()
    assert declared, "no experiment is declared, so this dimension measures nothing"
    scopes = {item["scope"] for item in declared}
    assert scopes == {"experiment", "arm"}, (
        "an arm must be listed on its own — an experiment half of whose arms "
        "were flown has answered nothing")


def test_an_experiment_is_covered_by_the_runs_that_carry_its_stamp(tmp_path):
    write_experiment_run(tmp_path, "20260810T120100Z_iris",
                         experiment="copter_gps_loss_vs_nominal", arm="nominal")
    document = coverage.collect([tmp_path], registry=REGISTRY)
    dimension = coverage.by_dimension(document, coverage.EXPERIMENTS)
    assert "copter_gps_loss_vs_nominal" not in dimension["uncovered"]
    assert "copter_gps_loss_vs_nominal#nominal" not in dimension["uncovered"]
    # The other side of the comparison was never flown, and that is the entry
    # that matters: a delta with one arm missing is not a delta.
    assert "copter_gps_loss_vs_nominal#gps_loss" in dimension["uncovered"]


def test_an_empty_dimension_reports_no_fraction_rather_than_full():
    """A dimension with nothing in it is empty, not fully covered — and the two
    read identically as a percentage."""
    assert coverage._pct(0, 0) is None
    assert coverage._pct(0, 4) == 0.0
    assert coverage._pct(4, 4) == 1.0


def test_coverage_of_an_empty_runs_root_is_zero_and_lists_everything(tmp_path):
    document = coverage.collect([tmp_path], registry=REGISTRY)
    assert document["runs_read"] == 0
    for dimension in document["dimensions"]:
        assert dimension["covered"] == 0
        assert len(dimension["uncovered"]) == dimension["declared"]


# ------------------------------------------------------------------ document
def test_the_report_refuses_to_be_a_test_count(tmp_path):
    text = coverage.render(coverage.collect([tmp_path], registry=REGISTRY))
    assert "This is not a test count" in text
    assert "not covered" in text


def test_the_report_says_what_covered_does_not_mean(tmp_path):
    text = coverage.render(coverage.collect([tmp_path], registry=REGISTRY))
    tail = text[text.index("## What a covered item does and does not mean"):]
    assert "does not mean the result was a pass" in tail
    assert "more than once" in tail


def test_generate_writes_the_document(tmp_path):
    out = tmp_path / "docs" / "coverage.md"
    text = coverage.generate([tmp_path], out)
    assert out.is_file()
    assert out.read_text(encoding="utf-8") == text
    assert "DO NOT EDIT BY HAND" in text
