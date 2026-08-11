"""A number of seconds is not a measurement until it names its clock and window.

TWO FINDINGS, BOTH ABOUT WHAT A METRIC SILENTLY ASSUMED
-------------------------------------------------------
F-04. `mode_transition_latency_max` was the only metric derived from a recorded
STEP rather than from the dataflash log, and the step was timed with
`time.time()`. Every other metric with unit `s` is on the log's clock. Under
SITL speedup the two differ by the speedup factor, so comparing two runs flown
at different speedups reported a `regression` — a degradation caused by a
command-line argument and attributed to the aircraft.

F-05. `time_outside_attitude_envelope` was computed over every record in the
log, including the aircraft parked on the runway, while the `attitude_stable`
acceptance criterion that shares its name and its bands is scoped to one
procedure. A tailsitter with a [55,115]° pitch band is outside it for every
second it sits still, so the two could report 0.0 s and 40 s for one flight and
both be right, with nothing saying they answered different questions.

Both are now stated per metric — `clock` and `window` travel with the value —
and the regression layer refuses to subtract two numbers that do not share
them.
"""
from __future__ import annotations

import pytest

from argazui import metrics, regression

pytestmark = pytest.mark.tier1


def _context(seconds=None, vehicle_seconds=None):
    """A run record with one passing set_mode step, timed however the test says."""
    step = {"kind": "set_mode", "status": "passed", "label": "Switch to GUIDED",
            "seconds": seconds}
    if vehicle_seconds is not None:
        step["vehicle_seconds"] = vehicle_seconds
    return metrics.context_from_result(
        {"procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                         "result": {"steps": [step], "expect": []}}]})


def _by_key(rows, key):
    return next(r for r in rows if r["key"] == key)


# ------------------------------------------------------------------- catalogue
def test_every_metric_declares_a_clock_and_a_window():
    """A metric added later must not inherit the old implicit assumption."""
    for key, spec in metrics.CATALOGUE.items():
        assert spec.get("clock") in (metrics.CLOCK_VEHICLE, metrics.CLOCK_WALL), key
        assert spec.get("window") in (metrics.WINDOW_PROCEDURE,
                                      metrics.WINDOW_ARMED,
                                      metrics.WINDOW_LOG), key


def test_no_metric_in_the_catalogue_describes_host_time():
    """Every published metric is about the aircraft, so every one is on its clock."""
    wall = [k for k, s in metrics.CATALOGUE.items()
            if s["clock"] != metrics.CLOCK_VEHICLE]
    assert not wall, f"metrics declared on the host clock: {wall}"


def test_the_published_catalogue_carries_both_fields():
    for row in metrics.catalogue("en"):
        assert row["clock"] and row["window"], row["key"]


# ------------------------------------------------------------------- F-04
def test_a_mode_transition_is_measured_on_the_vehicle_clock():
    context = _context(seconds=2.0, vehicle_seconds=10.0)
    rows = metrics.compute(altitude=[], attitude=[], attitude_stats={},
                           gyro_peak_dps=None, armed_intervals=[],
                           context=context)
    row = _by_key(rows, "mode_transition_latency_max")
    assert row["value"] == 10.0, "the host figure was used instead of the vehicle's"
    assert row["clock"] == metrics.CLOCK_VEHICLE


def test_speedup_no_longer_moves_the_mode_transition_metric():
    """The regression false positive, asserted directly.

    Same flight, same 10 s of vehicle time, run once at speedup 1 and once at
    speedup 5 — so the host saw 10 s and then 2 s. The metric must not move.
    """
    slow = metrics.compute(altitude=[], attitude=[], attitude_stats={},
                           gyro_peak_dps=None, armed_intervals=[],
                           context=_context(seconds=10.0, vehicle_seconds=10.0))
    fast = metrics.compute(altitude=[], attitude=[], attitude_stats={},
                           gyro_peak_dps=None, armed_intervals=[],
                           context=_context(seconds=2.0, vehicle_seconds=10.0))
    assert (_by_key(slow, "mode_transition_latency_max")["value"]
            == _by_key(fast, "mode_transition_latency_max")["value"] == 10.0)


def test_a_step_with_no_vehicle_clock_falls_back_and_says_so():
    """Honest degradation: the wall figure is usable, mislabelling it is not."""
    rows = metrics.compute(altitude=[], attitude=[], attitude_stats={},
                           gyro_peak_dps=None, armed_intervals=[],
                           context=_context(seconds=2.0))
    row = _by_key(rows, "mode_transition_latency_max")
    assert row["value"] == 2.0
    assert row["clock"] == metrics.CLOCK_WALL
    assert "HOST clock" in row["detail"]


def test_two_runs_on_different_clocks_are_not_compared():
    """The last line of defence, in the layer that would have subtracted them."""
    def run(clock, value):
        return {"run_id": f"r-{clock}", "dir": f"/tmp/{clock}", "schema": 6,
                "status": "passed", "started_utc": "2026-01-01T00:00:00Z",
                "model_id": "m", "procedures": ["copter_takeoff"],
                "metrics": [{"key": "mode_transition_latency_max",
                             "procedure": "copter_takeoff", "value": value,
                             "unit": "s", "better": "lower", "clock": clock,
                             "window": "procedure"}],
                "fingerprint": {}}

    comparison = regression.compare(run(metrics.CLOCK_WALL, 2.0),
                                    run(metrics.CLOCK_VEHICLE, 10.0),
                                    ignore_config_drift=True)
    row = comparison["metrics"][0]
    assert row["verdict"] == regression.INCOMPARABLE
    assert "different clocks" in row["reason"]
    assert comparison["verdict"] != regression.REGRESSED, (
        "a clock change was reported as the aircraft getting worse")


def test_two_runs_on_the_same_clock_are_still_compared():
    def run(name, value):
        return {"run_id": name, "dir": f"/tmp/{name}", "schema": 6,
                "status": "passed", "started_utc": "2026-01-01T00:00:00Z",
                "model_id": "m", "procedures": ["copter_takeoff"],
                "metrics": [{"key": "mode_transition_latency_max",
                             "procedure": "copter_takeoff", "value": value,
                             "unit": "s", "better": "lower",
                             "clock": metrics.CLOCK_VEHICLE,
                             "window": "procedure"}],
                "fingerprint": {}}

    comparison = regression.compare(run("base", 1.0), run("cur", 5.0),
                                    ignore_config_drift=True)
    assert comparison["metrics"][0]["verdict"] == regression.DEGRADED
    assert comparison["verdict"] == regression.REGRESSED


# ------------------------------------------------------------------- F-05
# (t, DesRoll, Roll, DesPitch, Pitch). 0.1 s apart, so each sample weighs 0.1 s.
def _attitude(count=100, roll=0.0, start=0.0):
    return [(start + i * 0.1, 0.0, roll, 0.0, 0.0) for i in range(count)]


def test_the_envelope_metric_covers_the_armed_interval_only():
    """Ten seconds parked outside the band, ten seconds flying inside it."""
    on_ground = _attitude(count=100, roll=90.0, start=0.0)     # 0-10 s, outside
    flying = _attitude(count=100, roll=0.0, start=10.0)        # 10-20 s, inside
    rows = metrics.compute(
        altitude=[], attitude=on_ground + flying, attitude_stats={},
        gyro_peak_dps=None,
        armed_intervals=[{"armed_at": 10.0, "disarmed_at": 20.0}],
        context={"envelope": {"procedure": "p", "roll": [-45.0, 45.0]}})
    row = _by_key(rows, "time_outside_attitude_envelope")
    assert row["value"] == pytest.approx(0.0, abs=0.2), (
        "ground time was counted as an envelope excursion")
    assert row["window"] == metrics.WINDOW_ARMED


def test_a_real_excursion_in_flight_is_still_measured():
    """Scoping must not become a way of not seeing anything."""
    rows = metrics.compute(
        altitude=[], attitude=_attitude(count=100, roll=90.0, start=10.0),
        attitude_stats={}, gyro_peak_dps=None,
        armed_intervals=[{"armed_at": 10.0, "disarmed_at": 20.0}],
        context={"envelope": {"procedure": "p", "roll": [-45.0, 45.0]}})
    row = _by_key(rows, "time_outside_attitude_envelope")
    assert row["value"] > 9.0, row


def test_a_log_with_no_arming_says_it_covered_everything():
    rows = metrics.compute(
        altitude=[], attitude=_attitude(count=100, roll=90.0),
        attitude_stats={}, gyro_peak_dps=None, armed_intervals=[],
        context={"envelope": {"procedure": "p", "roll": [-45.0, 45.0]}})
    row = _by_key(rows, "time_outside_attitude_envelope")
    assert row["window"] == metrics.WINDOW_LOG
    assert "WHOLE log" in row["detail"]


def test_the_envelope_metric_names_the_criterion_it_can_be_confused_with():
    rows = metrics.compute(
        altitude=[], attitude=_attitude(), attitude_stats={},
        gyro_peak_dps=None,
        armed_intervals=[{"armed_at": 0.0, "disarmed_at": 10.0}],
        context={"envelope": {"procedure": "p", "roll": [-45.0, 45.0]}})
    detail = _by_key(rows, "time_outside_attitude_envelope")["detail"]
    assert "attitude_stable" in detail and "not identical" in detail


def test_two_runs_over_different_windows_are_not_compared():
    def run(name, window, value):
        return {"run_id": name, "dir": f"/tmp/{name}", "schema": 6,
                "status": "passed", "started_utc": "2026-01-01T00:00:00Z",
                "model_id": "m", "procedures": ["p"],
                "metrics": [{"key": "time_outside_attitude_envelope",
                             "procedure": "", "value": value, "unit": "s",
                             "better": "lower", "clock": metrics.CLOCK_VEHICLE,
                             "window": window}],
                "fingerprint": {}}

    comparison = regression.compare(run("b", metrics.WINDOW_LOG, 40.0),
                                    run("c", metrics.WINDOW_ARMED, 0.2),
                                    ignore_config_drift=True)
    row = comparison["metrics"][0]
    assert row["verdict"] == regression.INCOMPARABLE
    assert "different windows" in row["reason"]


def test_within_armed_keeps_only_the_flight():
    samples = [(0.0, 0, 0, 0, 0), (5.0, 0, 0, 0, 0), (15.0, 0, 0, 0, 0)]
    kept = metrics.within_armed(
        samples, [{"armed_at": 4.0, "disarmed_at": 6.0}])
    assert [s[0] for s in kept] == [5.0]


def test_within_armed_returns_everything_when_nothing_armed():
    samples = [(0.0, 0, 0, 0, 0), (5.0, 0, 0, 0, 0)]
    assert metrics.within_armed(samples, []) == samples
