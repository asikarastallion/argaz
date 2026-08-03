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
