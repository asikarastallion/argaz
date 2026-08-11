"""Run-to-run comparison: the classifier, and its refusals.

WHY THE REFUSALS GET MORE TESTS THAN THE ARITHMETIC
---------------------------------------------------
Subtracting two numbers is not where this goes wrong. What goes wrong is
subtracting two numbers that were never about the same thing — a different
firmware, an edited procedure, a parameter file somebody changed — and
reporting the difference as though the aircraft had got worse.

So most of what is asserted here is that the comparison *declines*, and says
why. The exit codes matter for the same reason: CI has to be able to tell "this
build got worse" from "these runs do not line up", and a pipeline that merged
them would eventually report a mis-specified baseline as a regression.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

import json

import pytest

from argazui import regression

pytestmark = pytest.mark.tier1


# Every identity field, present and known. `differences()` treats an ABSENT
# field as a difference — a statement that nothing here can show the two runs
# match — so a fixture that omits one makes every comparison `incomparable` and
# these tests would pass for the wrong reason.
FINGERPRINT = {
    "model": {"config_hash": "sha256:model"},
    "procedure_hash": "sha256:proc",
    "ardupilot": {"commit": "abc123", "firmware_commit": "abc123",
                  "dirty": False, "dirty_digest": "clean"},
    "argaz": {"commit": "def456", "dirty": False, "dirty_digest": "clean"},
    "gazebo": {"version": "Gazebo Sim, version 8.9.0"},
}


def metric(key, value, procedure="", better=regression.metricslib.LOWER,
           unit="deg", detail="", clock=regression.metricslib.CLOCK_VEHICLE,
           window=regression.metricslib.WINDOW_LOG):
    # `clock` and `window` are part of what makes two numbers the same
    # quantity; a comparison across either is refused. Defaulted here so the
    # tests below stay about thresholds and direction.
    return {"key": key, "value": value, "procedure": procedure, "unit": unit,
            "better": better, "detail": detail, "scope": "run",
            "clock": clock, "window": window}


def run(run_id="20260809T000000Z_iris", *, model="iris",
        procedures=("copter_takeoff",), metrics=None, fingerprint=None,
        started="2026-08-09T00:00:00Z"):
    return {"run_id": run_id, "dir": f"runs/{run_id}", "schema": 3,
            "status": "passed", "started_utc": started, "model_id": model,
            "procedures": sorted(procedures), "metrics": metrics or [],
            "fingerprint": fingerprint if fingerprint is not None else FINGERPRINT}


def compare(before, after, **kwargs):
    return regression.compare(before, after, **kwargs)


def verdict_for(comparison, key, procedure=""):
    return next(row for row in comparison["metrics"]
                if row["key"] == key and row["procedure"] == procedure)["verdict"]


# ------------------------------------------------------------- classification
def test_a_metric_past_its_tolerance_in_the_wrong_direction_is_a_regression():
    before = run(metrics=[metric("tracking_error_roll_max", 10.0)])
    after = run(metrics=[metric("tracking_error_roll_max", 18.0)])
    comparison = compare(before, after)
    assert comparison["verdict"] == regression.REGRESSED
    assert verdict_for(comparison, "tracking_error_roll_max") == regression.DEGRADED
    assert comparison["degraded"] == ["tracking_error_roll_max"]


def test_the_same_move_the_other_way_is_an_improvement():
    comparison = compare(run(metrics=[metric("tracking_error_roll_max", 18.0)]),
                         run(metrics=[metric("tracking_error_roll_max", 10.0)]))
    assert comparison["verdict"] == regression.PASSED
    assert verdict_for(comparison, "tracking_error_roll_max") == regression.IMPROVED


def test_direction_is_read_from_the_metric_and_not_assumed():
    """A comparator that hard-codes "smaller is better" is wrong on the first
    metric where it is not."""
    before = run(metrics=[metric("made_up_height", 10.0,
                                 better=regression.metricslib.HIGHER, unit="m")])
    after = run(metrics=[metric("made_up_height", 4.0,
                                better=regression.metricslib.HIGHER, unit="m")])
    assert verdict_for(compare(before, after), "made_up_height") == regression.DEGRADED


def test_a_change_inside_the_relative_tolerance_is_unchanged():
    comparison = compare(run(metrics=[metric("peak_angular_rate", 100.0,
                                             unit="deg/s")]),
                         run(metrics=[metric("peak_angular_rate", 105.0,
                                             unit="deg/s")]))
    assert verdict_for(comparison, "peak_angular_rate") == regression.UNCHANGED
    assert comparison["verdict"] == regression.PASSED


def test_the_absolute_floor_stops_noise_near_zero_from_reading_as_a_regression():
    """0.02° to 0.04° is +100% and means nothing; both numbers are noise.

    Without the floor, CI would go red for quantities that are identical in
    engineering terms, and a red build nobody believes is worse than none.
    """
    comparison = compare(run(metrics=[metric("tracking_error_roll_rms", 0.02)]),
                         run(metrics=[metric("tracking_error_roll_rms", 0.04)]))
    row = next(r for r in comparison["metrics"] if r["key"] == "tracking_error_roll_rms")
    assert row["relative"] == pytest.approx(1.0)      # +100%, and reported
    assert row["verdict"] == regression.UNCHANGED     # and still not a regression


def test_a_baseline_of_zero_has_no_percentage_and_is_judged_on_the_floor_alone():
    comparison = compare(run(metrics=[metric("time_outside_attitude_envelope",
                                             0.0, unit="s")]),
                         run(metrics=[metric("time_outside_attitude_envelope",
                                             4.0, unit="s")]))
    row = next(r for r in comparison["metrics"]
               if r["key"] == "time_outside_attitude_envelope")
    assert row["relative"] is None
    assert row["verdict"] == regression.DEGRADED


def test_a_metric_measured_on_only_one_side_is_incomparable_with_a_reason():
    before = run(metrics=[metric("time_to_target_alt", None, procedure="t",
                                 unit="s", detail="never reached in this log")])
    after = run(metrics=[metric("time_to_target_alt", 12.0, procedure="t", unit="s")])
    comparison = compare(before, after)
    row = next(r for r in comparison["metrics"] if r["key"] == "time_to_target_alt")
    assert row["verdict"] == regression.INCOMPARABLE
    assert "never reached" in row["reason"]
    # An incomparable metric is not a regression: nothing got worse, something
    # could not be measured.
    assert comparison["verdict"] == regression.PASSED


def test_a_metric_only_the_current_run_has_is_reported_rather_than_dropped():
    """A metric added since the baseline was flown is listed, not hidden.

    Dropping it would make the comparison quietly narrower than it looks —
    the reader would see a clean table and no sign that a quantity now being
    measured has nothing to be measured against.
    """
    comparison = compare(run(metrics=[metric("tracking_error_roll_max", 10.0)]),
                         run(metrics=[metric("tracking_error_roll_max", 10.0),
                                      metric("peak_angular_rate", 40.0)]))
    row = next(r for r in comparison["metrics"] if r["key"] == "peak_angular_rate")
    assert row["verdict"] == regression.INCOMPARABLE
    assert "baseline" in row["reason"]


# -------------------------------------------------------------- compatibility
def test_two_different_models_are_never_compared():
    comparison = compare(run(model="iris", metrics=[metric("peak_angular_rate", 10.0)]),
                         run(model="skywalker", metrics=[metric("peak_angular_rate", 90.0)]))
    assert comparison["verdict"] == regression.NOT_COMPARABLE
    assert any(b["field"] == "model" for b in comparison["compatibility"]["blocking"])
    assert all(row["verdict"] == regression.INCOMPARABLE
               for row in comparison["metrics"])


def test_a_different_set_of_procedures_is_never_compared():
    comparison = compare(
        run(procedures=("copter_takeoff",), metrics=[metric("peak_angular_rate", 10.0)]),
        run(procedures=("copter_takeoff", "copter_land"),
            metrics=[metric("peak_angular_rate", 10.0)]))
    assert comparison["verdict"] == regression.NOT_COMPARABLE
    assert any(b["field"] == "procedures" for b in comparison["compatibility"]["blocking"])


def test_a_run_without_metrics_says_how_to_produce_them():
    comparison = compare(run(metrics=[]), run(metrics=[]))
    reasons = " ".join(b["reason"] for b in comparison["compatibility"]["blocking"])
    assert "argazui report" in reasons


@pytest.mark.parametrize("field,path", [
    ("procedure", ("procedure_hash",)),
    ("model", ("model", "config_hash")),
    ("ardupilot", ("ardupilot", "commit")),
])
def test_configuration_drift_blocks_the_comparison_until_it_is_acknowledged(field, path):
    """A firmware change measures the change as much as it measures the aircraft."""
    drifted = json.loads(json.dumps(FINGERPRINT))
    node = drifted
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = "something-else"

    before = run(metrics=[metric("tracking_error_roll_max", 10.0)])
    after = run(metrics=[metric("tracking_error_roll_max", 30.0)],
                fingerprint=drifted)

    comparison = compare(before, after)
    assert comparison["verdict"] == regression.NOT_COMPARABLE
    assert comparison["compatibility"]["configuration_drift"]

    # Asked for out loud, it compares — and still reports what changed.
    forced = compare(before, after, ignore_config_drift=True)
    assert forced["verdict"] == regression.REGRESSED
    assert forced["compatibility"]["drift_ignored"] is True
    assert forced["compatibility"]["configuration_drift"]


def test_an_unknown_identity_field_is_treated_as_a_difference():
    """Not a claim that they differ — a statement that nothing shows they match.

    This is the case that would otherwise pass silently: a run recorded before
    fingerprints existed has no procedure hash at all, and comparing against it
    would look exactly like comparing two identical configurations.
    """
    comparison = compare(
        run(metrics=[metric("peak_angular_rate", 10.0)], fingerprint={}),
        run(metrics=[metric("peak_angular_rate", 10.0)]))
    assert comparison["verdict"] == regression.NOT_COMPARABLE
    assert all(d["reason"] == "unknown on at least one side"
               for d in comparison["compatibility"]["configuration_drift"])


# ------------------------------------------------------------------ thresholds
def test_thresholds_come_from_the_configuration_when_it_states_them():
    table = regression.thresholds({
        "default_tolerance": 0.5,
        "tolerance": {"peak_angular_rate": 0.9},
        "floor": {"peak_angular_rate": 7.0},
    })
    assert table["metrics"]["peak_angular_rate"] == {"tolerance": 0.9, "floor": 7.0}
    assert table["metrics"]["time_to_target_alt"]["tolerance"] == 0.5


def test_a_wider_tolerance_actually_changes_the_verdict():
    before = run(metrics=[metric("peak_angular_rate", 100.0, unit="deg/s")])
    after = run(metrics=[metric("peak_angular_rate", 130.0, unit="deg/s")])
    assert compare(before, after)["verdict"] == regression.REGRESSED
    relaxed = compare(before, after, config={"default_tolerance": 0.5})
    assert relaxed["verdict"] == regression.PASSED


# ------------------------------------------------------ reading and rendering
def test_a_directory_that_is_not_a_run_is_refused_by_name(tmp_path):
    with pytest.raises(regression.RunNotReadable, match="no result.json"):
        regression.load_run(tmp_path)


def test_a_run_is_loaded_from_its_result_json(tmp_path):
    directory = tmp_path / "20260809T101500Z_iris"
    directory.mkdir()
    (directory / "result.json").write_text(json.dumps({
        "schema": 3, "run_id": directory.name, "status": "passed",
        "started_utc": "2026-08-09T10:15:00Z", "model": {"id": "iris"},
        "procedures": [{"procedure": "copter_land"}, {"procedure": "copter_takeoff"}],
        "metrics": [metric("peak_angular_rate", 12.0)],
        "fingerprint": FINGERPRINT,
    }), encoding="utf-8")

    loaded = regression.load_run(directory)
    assert loaded["model_id"] == "iris"
    assert loaded["procedures"] == ["copter_land", "copter_takeoff"]
    assert loaded["metrics"][0]["value"] == 12.0


def test_the_rendered_comparison_states_the_verdict_and_the_baseline():
    comparison = compare(
        run("20260801T000000Z_iris", metrics=[metric("tracking_error_roll_max", 10.0)]),
        run("20260809T000000Z_iris", metrics=[metric("tracking_error_roll_max", 30.0)]))
    text = regression.render(comparison)
    assert "REGRESSION" in text
    assert "20260801T000000Z_iris" in text and "20260809T000000Z_iris" in text
    assert "measurements, not acceptance criteria" in text
    assert "**DEGRADED**" in text


def test_writing_leaves_both_documents_beside_the_run(tmp_path):
    comparison = compare(run(metrics=[metric("peak_angular_rate", 10.0)]),
                         run(metrics=[metric("peak_angular_rate", 10.0)]))
    as_json, as_text = regression.write(tmp_path, comparison)
    assert json.loads(as_json.read_text())["verdict"] == regression.PASSED
    assert as_text.read_text().startswith("# Regression comparison")


def test_the_newest_earlier_run_of_the_same_model_is_the_default_baseline(tmp_path):
    def write(name, model, started, metrics_list):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "result.json").write_text(json.dumps({
            "schema": 3, "run_id": name, "status": "passed",
            "started_utc": started, "model": {"id": model},
            "procedures": [{"procedure": "copter_takeoff"}],
            "metrics": metrics_list, "fingerprint": FINGERPRINT}), encoding="utf-8")
        return directory

    write("20260801T000000Z_iris", "iris", "2026-08-01T00:00:00Z",
          [metric("peak_angular_rate", 10.0)])
    write("20260805T000000Z_iris", "iris", "2026-08-05T00:00:00Z",
          [metric("peak_angular_rate", 11.0)])
    write("20260807T000000Z_skywalker", "skywalker", "2026-08-07T00:00:00Z",
          [metric("peak_angular_rate", 99.0)])
    current = regression.load_run(
        write("20260809T000000Z_iris", "iris", "2026-08-09T00:00:00Z",
              [metric("peak_angular_rate", 12.0)]))

    baseline = regression.previous_run_for(current, root=tmp_path)
    assert baseline["run_id"] == "20260805T000000Z_iris", (
        "the default baseline is not the newest earlier run of the same model")


def test_there_is_no_baseline_when_nothing_earlier_exists(tmp_path):
    directory = tmp_path / "20260809T000000Z_iris"
    directory.mkdir()
    (directory / "result.json").write_text(json.dumps({
        "schema": 3, "run_id": directory.name, "status": "passed",
        "started_utc": "2026-08-09T00:00:00Z", "model": {"id": "iris"},
        "procedures": [], "metrics": [metric("peak_angular_rate", 1.0)],
        "fingerprint": FINGERPRINT}), encoding="utf-8")
    assert regression.previous_run_for(regression.load_run(directory),
                                       root=tmp_path) is None
