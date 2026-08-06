"""The RC override keepalive, and why it cannot be a constant.

ArduPilot drops a held stick `RC_OVERRIDE_TIME` after the last override
message — counted in VEHICLE seconds. Two things make a fixed interval wrong:

  * the timeout is a parameter, and a model's parameter file may move it;
  * under SITL speedup a vehicle second is shorter than a real one, so the
    wall-clock budget shrinks by the same factor.

At speedup 10 the shipped 3-second timeout arrives after 0.3 s of real time.
The old constant was 0.25 s: one late packet and a VTOL loses its throttle
mid-climb, which reads as a broken takeoff procedure rather than a timing bug.

Needs no vehicle; `tier1` only says which CI job runs it.
"""
from __future__ import annotations

import time

import pytest

from argazui import mavlink_link as link_mod
from argazui.mavlink_link import MavlinkLink, keepalive_interval

pytestmark = pytest.mark.tier1

DEFAULT = link_mod.RC_OVERRIDE_TIME_DEFAULT      # 3.0 s, ArduPilot's own


def test_the_interval_always_fits_several_refreshes_into_the_budget():
    """The property that matters, asserted across the whole usable range."""
    for override_time in (0.5, 1.0, 3.0, 10.0, 120.0):
        for speedup in (1.0, 2.0, 5.0, 10.0, 20.0):
            interval = keepalive_interval(override_time, speedup)
            budget = override_time / speedup
            # Always true, with no exception: an interval longer than the
            # budget sends the refresh after the stick has already dropped.
            assert interval <= budget + 1e-9, (
                f"RC_OVERRIDE_TIME={override_time} speedup={speedup}: a single "
                f"refresh does not fit — {interval}s into {budget}s")
            # The full margin holds wherever the floor is not binding.
            if budget / link_mod.RC_KEEPALIVE_REFRESHES >= link_mod.RC_KEEPALIVE_MIN:
                assert interval * link_mod.RC_KEEPALIVE_REFRESHES <= budget + 1e-9, (
                    f"RC_OVERRIDE_TIME={override_time} speedup={speedup}: "
                    f"{interval:.3f}s leaves fewer than "
                    f"{link_mod.RC_KEEPALIVE_REFRESHES} refreshes in {budget:.3f}s")


def test_speedup_shortens_the_interval():
    assert keepalive_interval(DEFAULT, 10.0) < keepalive_interval(DEFAULT, 1.0)
    assert keepalive_interval(DEFAULT, 5.0) == pytest.approx(0.15)


def test_the_old_constant_would_have_been_too_slow_at_speedup_10():
    """The concrete regression, stated as a number.

    A 0.25 s interval against a 0.3 s budget leaves room for one refresh, so a
    single dropped packet loses the stick.
    """
    budget = DEFAULT / 10.0
    assert 0.25 * link_mod.RC_KEEPALIVE_REFRESHES > budget
    assert keepalive_interval(DEFAULT, 10.0) * link_mod.RC_KEEPALIVE_REFRESHES <= budget


def test_a_vehicle_that_changed_the_parameter_is_obeyed():
    """Not every airframe keeps ArduPilot's default."""
    assert keepalive_interval(1.0, 1.0) < keepalive_interval(3.0, 1.0)
    assert keepalive_interval(0.5, 5.0) < keepalive_interval(3.0, 5.0)


def test_the_two_special_values_are_not_treated_as_numbers():
    """0 disables overrides; -1 means they never expire.

    Dividing either would produce a nonsense interval — 0 gives the floor and
    -1 a negative one — so both take the slowest sensible rate instead.
    """
    assert keepalive_interval(0.0, 5.0) == link_mod.RC_KEEPALIVE_MAX
    assert keepalive_interval(-1.0, 5.0) == link_mod.RC_KEEPALIVE_MAX


def test_it_is_clamped_at_both_ends():
    # Floor: at speedup 30 the budget is 0.1 s and a quarter of it is below
    # the floor, so the floor applies — it still fits inside the budget.
    assert keepalive_interval(DEFAULT, 30.0) == link_mod.RC_KEEPALIVE_MIN
    # Ceiling: a very long timeout must not turn into a very lazy keepalive.
    assert keepalive_interval(3600.0, 1.0) == link_mod.RC_KEEPALIVE_MAX


def test_the_budget_beats_the_floor_when_they_disagree():
    """A floor longer than the whole budget would guarantee the dropout.

    At speedup 1000 the stick expires 3 ms of real time after it was sent.
    Nothing can hold it there — but sending at the floor's 50 ms would mean
    every refresh arrives after expiry, which is worse than useless.
    """
    interval = keepalive_interval(DEFAULT, 1000.0)
    assert interval == pytest.approx(DEFAULT / 1000.0)
    assert interval < link_mod.RC_KEEPALIVE_MIN


def test_an_unread_parameter_falls_back_to_ardupilots_default():
    assert keepalive_interval(None, 1.0) == keepalive_interval(DEFAULT, 1.0)


def test_speedup_is_measured_from_the_vehicles_own_clock(monkeypatch):
    """Nothing tells a ground station the speedup, so it is derived.

    The vehicle timestamps its telemetry; the ratio of that clock to ours is
    the answer. Fed 20 vehicle-seconds across 4 wall-seconds, the link must
    conclude 5x rather than keep believing 1x.
    """
    link = MavlinkLink(port=14550)
    assert link.speedup == 1.0, "an unmeasured link must not claim a speedup"

    fake_now = [1000.0]
    monkeypatch.setattr(link_mod.time, "time", lambda: fake_now[0])
    monkeypatch.setattr(MavlinkLink, "SPEEDUP_WINDOW", 4.0)

    link._note_vehicle_clock(100.0)          # reference point
    fake_now[0] += 4.0                        # 4 s of wall clock
    link._note_vehicle_clock(120.0)          # 20 s of vehicle time

    assert link.speedup == pytest.approx(5.0)
    assert link.keepalive_interval() == pytest.approx(0.15)


def test_a_backwards_or_stalled_vehicle_clock_is_ignored(monkeypatch):
    """A reboot resets time_boot_ms; that is not a negative speedup."""
    link = MavlinkLink(port=14550)
    fake_now = [1000.0]
    monkeypatch.setattr(link_mod.time, "time", lambda: fake_now[0])
    monkeypatch.setattr(MavlinkLink, "SPEEDUP_WINDOW", 4.0)

    link._note_vehicle_clock(100.0)
    fake_now[0] += 10.0
    link._note_vehicle_clock(50.0)            # the vehicle rebooted
    assert link.speedup == 1.0, "a backwards clock changed the measurement"

    link._note_vehicle_clock(0.0)             # no timestamp at all
    assert link.speedup == 1.0


# =========================================================== the mode settle
# v1.3 phase 3 diagnosed a race in the SINGLE-VEHICLE path: ArduPlane accepts a
# mode command issued in the ~100 ms window after RC input becomes valid, then
# overwrites it from the flight-mode switch with no NAK and no STATUSTEXT.
# Measured over seven full-suite runs, the e2e flight test failed three times
# on exactly this.
#
# The fix is a readiness condition, not a longer timeout: the vehicle is not
# ready for a mode command until its mode has stopped moving on its own.
# Counted in VEHICLE time, per docs/thresholds.md — every timer this is about
# (the switch re-read, DISARM_DELAY, failsafes) runs on the aircraft's clock,
# and under speedup a wall second is not a second of flight.

def test_a_vehicle_whose_mode_just_changed_is_not_settled():
    from argazui.mavlink_link import MavlinkLink, MODE_SETTLE_S

    link = MavlinkLink(connection="udpin:127.0.0.1:1")
    link._note_mode_change(vehicle_s=10.0)
    link.state.vehicle_clock_s = 10.0 + MODE_SETTLE_S * 0.5
    assert link.state.mode_settled is False, (
        "a vehicle whose mode moved half a settle-window ago is not ready for "
        "a mode command")


def test_a_vehicle_whose_mode_has_been_still_is_settled():
    from argazui.mavlink_link import MavlinkLink, MODE_SETTLE_S

    link = MavlinkLink(connection="udpin:127.0.0.1:1")
    link._note_mode_change(vehicle_s=10.0)
    link.state.vehicle_clock_s = 10.0 + MODE_SETTLE_S * 2
    assert link.state.mode_settled is True


def test_the_settle_window_is_counted_on_the_vehicles_clock():
    """At speedup 5 the window must still be MODE_SETTLE_S of FLIGHT."""
    from argazui.mavlink_link import MavlinkLink, MODE_SETTLE_S

    link = MavlinkLink(connection="udpin:127.0.0.1:1")
    link._note_mode_change(vehicle_s=100.0)
    # Only a fifth of the window has passed in vehicle time, however much
    # wall clock the host burned.
    link.state.vehicle_clock_s = 100.0 + MODE_SETTLE_S / 5
    assert link.state.mode_settled is False
    link.state.vehicle_clock_s = 100.0 + MODE_SETTLE_S + 0.01
    assert link.state.mode_settled is True


def test_a_vehicle_that_has_never_reported_a_mode_is_not_settled():
    """Absence of data is not evidence of stillness."""
    from argazui.mavlink_link import MavlinkLink

    link = MavlinkLink(connection="udpin:127.0.0.1:1")
    assert link.state.mode_settled is False


def test_the_settle_state_reaches_the_interface():
    from argazui.mavlink_link import MavlinkLink, MODE_SETTLE_S

    link = MavlinkLink(connection="udpin:127.0.0.1:1")
    link._note_mode_change(vehicle_s=1.0)
    link.state.vehicle_clock_s = 1.0 + MODE_SETTLE_S * 3
    document = link.state.as_dict()
    assert document["mode_settled"] is True, (
        "the page cannot gate its command buttons on a field it is not sent")
