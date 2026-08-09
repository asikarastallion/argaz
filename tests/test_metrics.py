"""The metric computations: known evidence in, known numbers out.

WHY THESE ARE PINNED DOWN
-------------------------
A metric is compared against a baseline and can fail CI through
`regression.py`. A quantity that is computed slightly differently after a
refactor would move every comparison against every stored baseline at once, and
nothing else in this project would notice — the number would simply be
different, and still look like a number.

So each metric is asserted against evidence built by hand here, including the
cases where it must refuse to produce a number at all.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

import pytest

from argazui import metrics

pytestmark = pytest.mark.tier1


def altitude(profile):
    """[(t, alt), ...] from a list of (t, alt) pairs — named for readability."""
    return list(profile)


def attitude(rows):
    """[(t, DesRoll, Roll, DesPitch, Pitch), ...]"""
    return list(rows)


def compute(**kwargs):
    base = {
        "altitude": [], "attitude": [], "attitude_stats": {},
        "gyro_peak_dps": None, "armed_intervals": [], "context": {},
    }
    base.update(kwargs)
    return {(m["key"], m["procedure"]): m for m in metrics.compute(**base)}


# ------------------------------------------------------------ time to target
def test_time_to_target_is_measured_from_arming():
    """From the moment the aircraft could move, not from the log's first byte.

    A log that begins before arming — which is what LOG_DISARMED=1 produces —
    would otherwise charge the climb for however long the vehicle sat on the
    ground waiting for a pre-arm check.
    """
    out = compute(
        altitude=altitude([(0, 0), (10, 0), (12, 5), (14, 19), (16, 21)]),
        armed_intervals=[{"armed_at": 10.0, "disarmed_at": 30.0, "seconds": 20.0}],
        context={"targets": [{"procedure": "copter_takeoff", "alt_m": 20.0}]})
    metric = out[("time_to_target_alt", "copter_takeoff")]
    assert metric["value"] == pytest.approx(6.0)
    assert metric["unit"] == "s"
    assert metric["scope"] == "procedure"


def test_a_target_that_was_never_reached_is_null_with_a_reason():
    """Not zero, and not omitted. The flight failed to climb; say that."""
    out = compute(
        altitude=altitude([(0, 0), (5, 3), (10, 4)]),
        armed_intervals=[{"armed_at": 0.0, "disarmed_at": 10.0, "seconds": 10.0}],
        context={"targets": [{"procedure": "vtol_takeoff", "alt_m": 20.0}]})
    metric = out[("time_to_target_alt", "vtol_takeoff")]
    assert metric["value"] is None
    assert "never reached" in metric["detail"]


def test_no_declared_target_produces_a_stated_absence():
    out = compute(altitude=altitude([(0, 0), (5, 30)]))
    metric = out[("time_to_target_alt", "")]
    assert metric["value"] is None
    assert "no procedure" in metric["detail"]


# --------------------------------------------------------- envelope excursion
ENVELOPE = {"procedure": "copter_takeoff", "roll": [-20, 20], "pitch": [-20, 20]}


def test_time_outside_the_envelope_is_weighted_by_the_logs_own_clock():
    """Seconds, not samples.

    ATT is not logged at a fixed rate across firmwares or vehicles, so counting
    samples outside a band would make the same flight score differently on two
    autopilots.
    """
    rows = attitude([(0.0, 0, 0, 0, 0), (0.5, 0, 45, 0, 0), (1.0, 0, 45, 0, 0),
                     (1.5, 0, 0, 0, 0)])
    out = compute(attitude=rows, context={"envelope": ENVELOPE})
    metric = out[("time_outside_attitude_envelope", "")]
    # Each sample carries the interval that ENDS at it: 0.5 s at 45°, then
    # another 0.5 s still at 45°.
    assert metric["value"] == pytest.approx(1.0)
    assert "roll [-20,20]" in metric["detail"]


def test_a_gap_in_the_log_cannot_manufacture_time_outside_the_envelope():
    rows = attitude([(0.0, 0, 45, 0, 0), (60.0, 0, 45, 0, 0)])
    out = compute(attitude=rows, context={"envelope": ENVELOPE})
    assert out[("time_outside_attitude_envelope", "")]["value"] == pytest.approx(
        metrics.MAX_SAMPLE_GAP_S)


def test_no_declared_envelope_means_no_number():
    out = compute(attitude=attitude([(0.0, 0, 45, 0, 0), (1.0, 0, 45, 0, 0)]))
    metric = out[("time_outside_attitude_envelope", "")]
    assert metric["value"] is None
    assert "declared" in metric["detail"]


# ------------------------------------------------------------------ the rest
def test_tracking_errors_and_peak_rate_are_carried_through_with_their_units():
    out = compute(
        attitude_stats={"roll_max": 15.0, "roll_rms": 1.2,
                        "pitch_max": 8.8, "pitch_rms": 1.1},
        gyro_peak_dps=99.5)
    assert out[("tracking_error_roll_max", "")]["value"] == 15.0
    assert out[("tracking_error_roll_max", "")]["unit"] == "deg"
    assert out[("tracking_error_pitch_rms", "")]["value"] == 1.1
    assert out[("peak_angular_rate", "")]["value"] == 99.5
    assert out[("peak_angular_rate", "")]["unit"] == "deg/s"


def test_a_log_with_no_gyro_says_so_rather_than_reporting_zero():
    """Zero is the answer a perfectly still aircraft gives. Silence is not that."""
    metric = compute(gyro_peak_dps=None)[("peak_angular_rate", "")]
    assert metric["value"] is None
    assert "no IMU records" in metric["detail"]


def test_mode_latency_is_the_slowest_change_per_procedure():
    out = compute(context={"mode_transitions": [
        {"procedure": "copter_takeoff", "label": "GUIDED", "seconds": 0.4},
        {"procedure": "copter_takeoff", "label": "ALT_HOLD", "seconds": 1.9},
        {"procedure": "copter_land", "label": "LAND", "seconds": 0.2},
    ]})
    assert out[("mode_transition_latency_max", "copter_takeoff")]["value"] == 1.9
    assert out[("mode_transition_latency_max", "copter_land")]["value"] == 0.2
    assert "ALT_HOLD" in out[("mode_transition_latency_max", "copter_takeoff")]["detail"]


def test_every_metric_declares_a_direction_and_a_source():
    """`better` is what a comparator classifies on; a blank one is a silent bug."""
    for key, spec in metrics.CATALOGUE.items():
        assert spec["better"] in (metrics.LOWER, metrics.HIGHER), key
        assert spec["source"], key
        assert spec["unit"], key
        assert set(spec["label"]) >= {"en", "tr"}, f"{key} has no Turkish label"


# ---------------------------------------------------------------- the context
def test_the_context_is_read_out_of_a_runs_own_result():
    """The log knows what the aircraft did, not what it was told to do."""
    result = {
        "procedures": [
            {"procedure": "copter_takeoff", "role": "takeoff",
             "values": {"alt": 15},
             "result": {
                 "steps": [
                     {"kind": "set_mode", "status": "passed", "label": "GUIDED",
                      "seconds": 0.3},
                     {"kind": "arm", "status": "passed", "label": "arm",
                      "seconds": 4.0},
                     {"kind": "set_mode", "status": "failed", "label": "AUTO",
                      "seconds": 9.9},
                 ],
                 "expect": [
                     {"condition": {"alt_above": 13.5}},
                     {"condition": {"attitude_stable": {"roll": [-20, 20],
                                                        "max_rate": 60}}},
                 ]}},
        ]}
    context = metrics.context_from_result(result)
    assert context["targets"] == [{"procedure": "copter_takeoff", "alt_m": 15.0}]
    # A failed mode change is not a mode-change latency measurement: the step
    # ran out of time rather than confirming anything.
    assert [t["label"] for t in context["mode_transitions"]] == ["GUIDED"]
    assert context["envelope"]["roll"] == [-20, 20]
    assert context["envelope"]["procedure"] == "copter_takeoff"


def test_a_hand_flown_run_yields_an_empty_context_rather_than_guesses():
    context = metrics.context_from_result({"procedures": []})
    assert context == {"targets": [], "mode_transitions": [], "envelope": {}}
