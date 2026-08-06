"""The status table is the project's central claim, so it gets its own tests.

`docs/status.md` is what replaced a hand-written list of ticks. If its
generator quietly maps the wrong outcome to the wrong word, the table is
exactly the thing it was built to remove — and nothing else in the suite would
notice, because every other test is about flying.

The bug these were written after is the one in `test_a_failure_is_never_shown_
as_untested`: a model that never reached pre-arm ran no procedure, so its run
record said `no-procedure`, and that overwrote a real `failed` verdict. Tier 2
had flown swan_k1_hwing and watched it fail; the table said "not yet
verified". No vehicle was involved in that mistake, and no flight would have
caught it.

Needs no SITL and no Gazebo; the `tier1` marker only says which CI job runs it.
"""
from __future__ import annotations

import json

import pytest

from argazui import status

pytestmark = pytest.mark.tier1

REGISTRY = {"models": [
    {"id": "flyer", "vehicle_class": "VTOL", "method": "gz_plus_sitl_paramfile"},
    {"id": "grounded", "vehicle_class": "Plane", "method": "gz_plus_sitl_frame"},
    {"id": "never_run", "vehicle_class": "Copter", "method": "ros2_launch"},
]}


def write_suite(root, tests: list[dict], environment="tier2-image") -> None:
    (root / "suite.json").write_text(json.dumps({
        "schema": 1, "generated_utc": "2026-08-03T00:00:00Z",
        "environment": environment, "exit_status": 0, "counts": {},
        "tests": tests}), encoding="utf-8")


def write_run(root, model_id: str, *, status_value="passed", flaky=None,
              procedures=("vtol_takeoff",), advisories=0) -> None:
    d = root / f"20260803T000000Z_{model_id}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(json.dumps({
        "schema": 2, "run_id": d.name, "status": status_value,
        "model": {"id": model_id}, "advisory_count": advisories,
        "flaky": flaky or [], "started_utc": "2026-08-03T00:00:00Z",
        "build": {"text": "ArduPlane V4.8.0-dev @ abc123"},
        "procedures": [{"procedure": p} for p in procedures]}), encoding="utf-8")


def node(model_id: str) -> str:
    return f"tests/test_tier2_models.py::test_model_takes_off_changes_mode_and_lands[{model_id}]"


def row_for(data: dict, model_id: str) -> status.Row:
    return next(r for r in data["rows"] if r.model_id == model_id)


def test_a_failure_is_never_shown_as_untested(tmp_path):
    """The regression this file exists for.

    A model that fails pre-arm runs no procedure, so its run record carries
    `no-procedure`. That must not turn a failure into "not yet verified".
    """
    write_suite(tmp_path, [{"nodeid": node("grounded"), "outcome": "failed",
                            "markers": ["tier2"], "reason": "never passed pre-arm"}])
    write_run(tmp_path, "grounded", status_value="no-procedure", procedures=())

    data = status.collect([tmp_path], registry=REGISTRY)
    row = row_for(data, "grounded")
    assert row.result == status.FAILED, (
        f"a model tier 2 flew and watched fail is reported as {row.result}")
    assert row.tier == "tier 2", "the tier that found the failure is not named"


def test_a_skip_is_untested_and_never_passed(tmp_path):
    write_suite(tmp_path, [{"nodeid": node("never_run"), "outcome": "skipped",
                            "markers": ["tier2"],
                            "reason": "Skipped: needs a ros2 workspace"}])
    data = status.collect([tmp_path], registry=REGISTRY)
    row = row_for(data, "never_run")
    assert row.result == status.UNTESTED
    assert "ros2" in row.reason
    assert row.tier == "", "a skipped model must not claim a tier verified it"


def test_a_model_tier2_never_touched_stays_untested(tmp_path):
    """Tier 1 can be as green as it likes; it says nothing about a model.

    This is the distinction the whole version rests on, so it is asserted
    rather than trusted: a suite full of passing tier-1 tests must leave every
    model row `untested`.
    """
    write_suite(tmp_path, [
        {"nodeid": "tests/test_tier1_procedures.py::test_x[sitl_quad]",
         "outcome": "passed", "markers": ["tier1"]},
        {"nodeid": "tests/e2e/test_page.py::test_y", "outcome": "passed",
         "markers": ["tier1", "e2e"]},
    ], environment="tier1-image")

    data = status.collect([tmp_path], registry=REGISTRY)
    assert {r.result for r in data["rows"]} == {status.UNTESTED}
    assert all(r.tier == "" for r in data["rows"])
    assert data["tier1"]["total"] == 2, data["tier1"]


def test_a_retried_pass_is_flaky_not_passed(tmp_path):
    write_suite(tmp_path, [{"nodeid": node("flyer"), "outcome": "passed",
                            "markers": ["tier2"]}])
    write_run(tmp_path, "flyer", flaky=["vtol_takeoff"])
    assert row_for(status.collect([tmp_path], registry=REGISTRY), "flyer").result \
        == status.FLAKY


def test_a_pass_with_no_procedure_asserts_nothing_so_it_is_untested(tmp_path):
    """Flown by hand with nothing asserted is not a verified model."""
    write_suite(tmp_path, [{"nodeid": node("flyer"), "outcome": "passed",
                            "markers": ["tier2"]}])
    write_run(tmp_path, "flyer", status_value="no-procedure", procedures=())
    row = row_for(status.collect([tmp_path], registry=REGISTRY), "flyer")
    assert row.result == status.UNTESTED
    assert "no procedure" in row.reason


def test_a_pass_carries_its_evidence(tmp_path):
    write_suite(tmp_path, [{"nodeid": node("flyer"), "outcome": "passed",
                            "markers": ["tier2"]}])
    write_run(tmp_path, "flyer", procedures=("vtol_takeoff", "vtol_land"),
              advisories=3)
    row = row_for(status.collect([tmp_path], registry=REGISTRY), "flyer")
    assert row.result == status.PASSED
    assert row.procedures == ["vtol_takeoff", "vtol_land"]
    assert row.advisories == 3
    assert row.firmware.startswith("ArduPlane")
    assert row.tier == "tier 2"


def test_the_rendered_file_says_it_is_generated_and_never_invents_a_result(tmp_path):
    write_suite(tmp_path, [
        {"nodeid": node("flyer"), "outcome": "passed", "markers": ["tier2"]},
        {"nodeid": node("grounded"), "outcome": "failed", "markers": ["tier2"]},
    ])
    write_run(tmp_path, "flyer")
    write_run(tmp_path, "grounded", status_value="failed")

    text = status.render(status.collect([tmp_path], registry=REGISTRY),
                         workflow="tier2.yml")
    assert "DO NOT EDIT BY HAND" in text
    assert "tier2.yml" in text
    assert "untested" in text and "machine output" in text
    # Only the four permitted words may appear as a result.
    import re
    cells = re.findall(r"\| \*{0,2}(\w[\w-]*)\*{0,2}(?:<br>)?", text)
    forbidden = {"ok", "supported", "working", "yes", "no", "broken", "error"}
    assert not (set(cells) & forbidden), sorted(set(cells) & forbidden)


def test_the_readme_summary_is_generated_between_its_markers(tmp_path):
    """README carries one machine-written sentence, and only one.

    The rest of that file is prose a person maintains. Replacing the whole
    README would put the generator in charge of text it has no business
    writing; leaving the support claim by hand is what produced eleven
    unearned ticks in v1.0.
    """
    write_suite(tmp_path, [
        {"nodeid": node("flyer"), "outcome": "passed", "markers": ["tier2"]},
        {"nodeid": node("grounded"), "outcome": "failed", "markers": ["tier2"]},
    ])
    write_run(tmp_path, "flyer")
    write_run(tmp_path, "grounded", status_value="failed")

    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Project\n\nprose above\n\n{status.SUMMARY_START}\nplaceholder\n"
        f"{status.SUMMARY_END}\n\nprose below\n", encoding="utf-8")

    data = status.collect([tmp_path], registry=REGISTRY)
    assert status.update_readme(readme, data) is True

    text = readme.read_text()
    assert "prose above" in text and "prose below" in text, (
        "the generator rewrote text it does not own")
    assert "placeholder" not in text
    assert "**1** passed" in text and "**1** failed" in text
    assert "docs/status.md" in text

    # Idempotent: a second run with the same data must not churn the file.
    data2 = status.collect([tmp_path], registry=REGISTRY)
    data2["generated_utc"] = data["generated_utc"]
    assert status.update_readme(readme, data2) is False


def test_a_readme_without_markers_is_left_alone(tmp_path):
    write_suite(tmp_path, [])
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n\nno markers here\n", encoding="utf-8")
    data = status.collect([tmp_path], registry=REGISTRY)
    assert status.update_readme(readme, data) is False
    assert readme.read_text() == "# Project\n\nno markers here\n"


# ------------------------------------------------- a fleet run is not a model
# v1.3 flies registered models in fleets under Gazebo. `hexapod_copter` now
# appears in fleet artefacts, fleet suite records and fleet run directories —
# so the risk of a fleet result leaking into the model table is real and new.
#
# The rule is unchanged and absolute: a model row comes from a `tier2`-marked
# test and from nothing else. A fleet run proves the fleet ENGINE works; it is
# not evidence that any airframe is supported.

def fleet_node(model_id: str) -> str:
    """A fleet test whose id mentions a model, as they legitimately do."""
    return (f"tests/test_fleet_gazebo.py::"
            f"test_three_vehicles_fly_with_rtf_and_separation_recorded"
            f"[{model_id}]")


def test_a_fleet_suite_record_cannot_create_a_model_row(tmp_path):
    """Even when the fleet test's id names the model."""
    write_suite(tmp_path, [
        {"nodeid": fleet_node("flyer"), "outcome": "passed",
         "markers": ["fleet_gazebo"], "reason": "", "duration": 300.0},
        {"nodeid": fleet_node("grounded"), "outcome": "passed",
         "markers": ["fleet_sitl"], "reason": "", "duration": 90.0},
    ])
    data = status.collect([tmp_path], registry=REGISTRY)
    for model_id in ("flyer", "grounded", "never_run"):
        row = row_for(data, model_id)
        assert row.result == status.UNTESTED, (
            f"a fleet run marked the {model_id} row {row.result!r}; a fleet "
            f"result is not a model result")
        assert row.tier == ""


def test_a_fleet_suite_record_cannot_overturn_a_real_tier2_failure(tmp_path):
    """The dangerous direction: a green fleet run hiding a red model."""
    write_suite(tmp_path, [
        {"nodeid": node("flyer"), "outcome": "failed", "markers": ["tier2"],
         "reason": "attitude criterion not met", "duration": 90.0},
        {"nodeid": fleet_node("flyer"), "outcome": "passed",
         "markers": ["fleet_gazebo"], "reason": "", "duration": 300.0},
    ])
    write_run(tmp_path, "flyer", status_value="failed")
    row = row_for(status.collect([tmp_path], registry=REGISTRY), "flyer")
    assert row.result == status.FAILED, (
        "a passing fleet run overwrote a failing tier-2 verdict")


def test_a_fleet_run_directory_cannot_create_a_model_row(tmp_path):
    """Fleet artefacts live beside model runs and must stay inert."""
    directory = tmp_path / "20260805T220837Z_fleet_hexapod_trio"
    (directory / "world").mkdir(parents=True)
    (directory / "fleet.json").write_text(json.dumps({
        "schema": 1, "fleet": {"name": "hexapod_trio",
                               "vehicles": [{"id": "v1", "model": "flyer"}]},
        "environment": {"argazui": "1.3.0"}}), encoding="utf-8")
    (directory / "separation.csv").write_text("t_s,pair,distance_m\n1,v1-v2,9.9\n",
                                              encoding="utf-8")
    (directory / "fleet_report.md").write_text("# Fleet run\n\nPASSED\n",
                                               encoding="utf-8")

    data = status.collect([tmp_path], registry=REGISTRY)
    assert row_for(data, "flyer").result == status.UNTESTED
    assert all(r.result == status.UNTESTED for r in data["rows"])


def test_the_fleet_markers_are_not_counted_as_tier1_either(tmp_path):
    """Tier-1's own summary must not absorb fleet tests."""
    write_suite(tmp_path, [
        {"nodeid": fleet_node("flyer"), "outcome": "passed",
         "markers": ["fleet_gazebo"], "reason": "", "duration": 300.0},
    ])
    data = status.collect([tmp_path], registry=REGISTRY)
    assert data["tier1"].get("total", 0) == 0, (
        "a fleet test was counted in the tier-1 summary")


def test_each_tier_records_to_its_own_path(monkeypatch):
    """A tier-1 run must not be able to delete a tier-2 result.

    One shared `suite.json` silently erased the tier-2 record mid-development,
    which reverted `argazui fleet validate` to "untested" for a model that had
    genuinely flown. The evidence was gone, not the capability.
    """
    import sys
    import support

    seen = {}
    for marker in ("tier1", "tier2", "fleet_sitl", "fleet_gazebo"):
        monkeypatch.setattr(sys, "argv", ["pytest", "-m", marker])
        seen[marker] = support._tier_of_this_run()
    assert seen == {m: m for m in seen}, seen
    assert len(set(seen.values())) == 4, "two tiers share a record path"

    monkeypatch.setattr(sys, "argv", ["pytest"])
    assert support._tier_of_this_run() == "mixed"


def test_the_collector_still_finds_records_under_their_new_paths(tmp_path):
    """Per-tier directories must not hide the records from `status.collect`."""
    tier2 = tmp_path / "tests" / "tier2"
    tier2.mkdir(parents=True)
    write_suite(tier2, [
        {"nodeid": node("flyer"), "outcome": "passed", "markers": ["tier2"],
         "reason": "", "duration": 90.0}])
    write_run(tmp_path, "flyer")
    row = row_for(status.collect([tmp_path], registry=REGISTRY), "flyer")
    assert row.result == status.PASSED, (
        "status.collect no longer finds a tier-2 record filed under its tier")


def test_every_marker_the_generator_reads_is_actually_recorded():
    """A marker the recorder does not know about vanishes from every summary.

    The fleet tiers ran green and still rendered as "no suite record",
    because `pytest_runtest_logreport` filtered markers against a hard-coded
    list written before those tiers existed. Silent, and it made a real result
    invisible.
    """
    from pathlib import Path as _Path

    # Read the file rather than importing it. Two `conftest.py` are reachable
    # as top-level modules here (tests/ and tests/e2e/), and which one wins
    # depends on collection order — the same hazard tests/support.py was
    # split out to avoid.
    source = (_Path(__file__).resolve().parent / "conftest.py").read_text(
        encoding="utf-8")
    for marker in ("tier1", "tier2", "fleet_sitl", "fleet_gazebo"):
        assert f'"{marker}"' in source, (
            f"{marker} is read by the status generator but never recorded")
