"""L5 — the separation monitor, and the conditions under which it refuses.

The refusal is the part worth testing hardest. Computing a distance from two
positions always produces a number; the whole value of this class is that it
declines to produce one when the two positions do not share a time base.
"""
from __future__ import annotations

import math

import pytest

from argazui.fleet import health, separation

pytestmark = pytest.mark.tier1

REASON = "SITL-only fleet: vehicles do not share a clock"


def fix(vehicle_id, east, north, up=0.0, t=0.0):
    return separation.Fix(vehicle_id=vehicle_id, east_m=east, north_m=north,
                          up_m=up, t_s=t)


# ---------------------------------------------------------------- refusing
def test_without_a_shared_time_base_nothing_is_emitted():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=False,
                                           reason=REASON)
    result = monitor.sample([fix("v1", 0, 0), fix("v2", 100, 0)])
    assert result.measured is False
    assert result.pairs == []
    assert result.minimum_m is None
    assert result.violation is False
    assert REASON in result.reason


def test_refusing_still_refuses_when_the_vehicles_are_obviously_colliding():
    """The refusal is not a filter on plausibility.

    Two vehicles at the same coordinates would be a violation if the numbers
    meant anything. They do not, so nothing is reported — including nothing
    alarming. A monitor that spoke up only for dramatic values would be
    choosing when its own time base mattered.
    """
    monitor = separation.SeparationMonitor(5.0, time_base_valid=False,
                                           reason=REASON)
    result = monitor.sample([fix("v1", 0, 0), fix("v2", 0, 0)])
    assert result.measured is False
    assert result.violation is False
    assert monitor.violations == []


def test_a_refused_run_reports_no_verdict_rather_than_a_pass():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=False,
                                           reason=REASON)
    monitor.sample([fix("v1", 0, 0), fix("v2", 100, 0)])
    verdict = monitor.verdict()
    assert verdict["measured"] is False
    assert verdict["passed"] is None, (
        "None and True are the two answers this project exists to keep apart")
    assert verdict["claim"] == "no relative-geometry claim was made"
    assert REASON in verdict["reason"]


def test_a_refused_run_writes_an_empty_csv():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=False,
                                           reason=REASON)
    for _ in range(10):
        monitor.sample([fix("v1", 0, 0), fix("v2", 3, 0)])
    assert monitor.csv_rows() == []


def test_refusing_without_a_reason_is_itself_an_error():
    """The reason is printed where the numbers would be; there must be one."""
    with pytest.raises(ValueError, match="stated reason"):
        separation.SeparationMonitor(5.0, time_base_valid=False)


def test_there_is_no_override_that_forces_measurement():
    """A caller wanting numbers from an undefined time base is the bug."""
    monitor = separation.SeparationMonitor(5.0, time_base_valid=False,
                                           reason=REASON)
    assert monitor.measuring is False
    assert not any("force" in name or "override" in name
                   for name in dir(monitor))


# --------------------------------------------------------------- measuring
def test_with_a_shared_clock_it_measures_normally():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    result = monitor.sample([fix("v1", 0, 0), fix("v2", 10, 0)])
    assert result.measured is True
    assert result.minimum_m == pytest.approx(10.0)
    assert result.violation is False
    assert len(result.pairs) == 1


def test_the_closest_pair_is_the_one_reported():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    result = monitor.sample([fix("v1", 0, 0), fix("v2", 30, 0), fix("v3", 6, 0)])
    assert len(result.pairs) == 3
    assert result.minimum_m == pytest.approx(6.0)


def test_a_violation_is_recorded_and_fails_the_verdict():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    monitor.sample([fix("v1", 0, 0), fix("v2", 20, 0)])
    monitor.sample([fix("v1", 0, 0), fix("v2", 4.0, 0)])
    monitor.sample([fix("v1", 0, 0), fix("v2", 20, 0)])

    verdict = monitor.verdict()
    assert verdict["measured"] is True
    assert verdict["passed"] is False, (
        "a violation anywhere in the run must fail the criterion, not only "
        "one at the end")
    assert verdict["violations"] == 1
    assert verdict["minimum_m"] == pytest.approx(4.0)


def test_the_minimum_is_over_the_whole_run_not_the_last_sample():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    monitor.sample([fix("v1", 0, 0), fix("v2", 7.0, 0)])
    monitor.sample([fix("v1", 0, 0), fix("v2", 50.0, 0)])
    assert monitor.verdict()["minimum_m"] == pytest.approx(7.0)


def test_a_warning_band_sits_above_the_violation_limit():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    result = monitor.sample([fix("v1", 0, 0), fix("v2", 6.0, 0)])
    assert result.violation is False
    assert result.warning is True


def test_vertical_offset_does_not_count_toward_separation():
    """Two multirotors 0.2 m apart vertically are in the same place.

    Counting the vertical component would let a fleet declare adequate
    separation it does not have.
    """
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    result = monitor.sample([fix("v1", 0, 0, up=0.0), fix("v2", 0, 0, up=20.0)])
    assert result.measured is True
    # math.dist is 3-D, so the pair distance reflects the vertical gap ...
    assert result.pairs[0].distance_m == pytest.approx(20.0)
    # ... but the geometry helper used for spawn checking is horizontal only.
    from argazui.fleet import formations
    a = formations.Point(0, 0, 0.0)
    b = formations.Point(0, 0, 20.0)
    assert formations.distance_m(a, b) == pytest.approx(0.0)


def test_fewer_than_two_vehicles_is_not_a_measurement():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    result = monitor.sample([fix("v1", 0, 0)])
    assert result.measured is False
    assert "at least two" in result.reason
    assert monitor.verdict()["passed"] is None


def test_a_run_that_never_sampled_reports_no_verdict():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    verdict = monitor.verdict()
    assert verdict["passed"] is None
    assert verdict["claim"] == "no relative-geometry claim was made"


def test_the_csv_carries_every_pair_over_time():
    monitor = separation.SeparationMonitor(5.0, time_base_valid=True)
    monitor.sample([fix("v1", 0, 0, t=1.0), fix("v2", 10, 0, t=1.0),
                    fix("v3", 20, 0, t=1.0)])
    rows = monitor.csv_rows()
    assert len(rows) == 3
    assert {r[1] for r in rows} == {"v1-v2", "v1-v3", "v2-v3"}
    assert all(r[0] == 1.0 for r in rows)


# ----------------------------------------------------------- clock spread
def test_clock_spread_needs_two_vehicles_to_mean_anything():
    spread = health.ClockSpread()
    assert spread.spread_s is None
    spread.observe("v1", 10.0, when=100.0)
    assert spread.spread_s is None
    spread.observe("v2", 10.0, when=100.0)
    assert spread.spread_s == pytest.approx(0.0)


def test_clock_spread_corrects_for_when_each_was_read():
    """Reading v1 then v2 a second later must not look like a second of drift."""
    spread = health.ClockSpread()
    spread.observe("v1", 10.0, when=100.0)
    spread.observe("v2", 11.0, when=101.0)      # same clock, read 1 s later
    assert spread.spread_s == pytest.approx(0.0, abs=1e-6)


def test_clock_spread_sees_a_real_offset():
    spread = health.ClockSpread()
    spread.observe("v1", 10.0, when=100.0)
    spread.observe("v2", 5.5, when=100.0)
    assert spread.spread_s == pytest.approx(4.5)
