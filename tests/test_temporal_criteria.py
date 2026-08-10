"""The temporal acceptance criteria: within, for, never.

WHY THESE ARE UNIT TESTS AND NOT ONLY FLIGHTS
---------------------------------------------
A criterion that decides whether an aircraft passed has to be pinned down
exactly: known state in, known verdict out. The real flights in
`test_tier1_procedures.py` exercise the same evaluator against SITL, but they
can only show it agreeing with a healthy aircraft. What matters just as much is
that it *refuses* — that a lapse fails a `for`, that a single excursion fails a
`never`, and that a stream which never arrived is reported as unmeasured rather
than as good behaviour.

Every case below is one a plausible implementation gets wrong. The vehicle-clock
case in particular is the reason `_Window` exists at all: under SITL speedup a
wall-clock second is not a second of flight, so a `for: 5s` judged on
`time.time()` would demand five times the flight it says it does — or a fifth
of it, depending on which way the speedup goes.

They need no vehicle and take milliseconds; the `tier1` marker only says which
CI job runs them.
"""
from __future__ import annotations

import time

import pytest

from argazui import procedures as procs
from argazui.mavlink_link import StabilityWatch, VehicleState
from argazui.procrunner import ProcedureRunner, _Window

pytestmark = pytest.mark.tier1


class FakeLink:
    """A vehicle whose state and clock this test drives directly.

    `submit` stands in for the link's worker thread: the runner hands it a job
    that would keep the message pump running, and here that means advancing the
    vehicle's clock by one sampling interval of simulated time and letting the
    test change what the vehicle is doing.
    """

    def __init__(self, speedup: float = 1.0, script=None, clock: float = 100.0,
                 advance: bool = True) -> None:
        self.state = VehicleState(connected=True, attitude_known=True,
                                  prearm_known=True, vehicle_clock_s=clock)
        self.stability = StabilityWatch()
        self.speedup = speedup
        self.ticks = 0
        self._script = script or (lambda link, tick: None)
        self._advance = advance

    def submit(self, fn, timeout: float = 0.0, label: str = "") -> dict:
        from argazui.procrunner import TEMPORAL_SAMPLE_S

        self.ticks += 1
        if self._advance:
            # One sampling interval of WALL time is `speedup` seconds of
            # VEHICLE time — the relationship the criteria are measured on.
            self.state.vehicle_clock_s += TEMPORAL_SAMPLE_S * self.speedup
        self._script(self, self.ticks)
        return {"ok": True, "text": ""}


def evaluate(link: FakeLink, condition: dict, **temporal):
    """Runs one `expect:` entry through the real evaluator."""
    expectation = procs.Expectation(condition=condition, **temporal)
    return ProcedureRunner(link)._evaluate(expectation, condition)


# --------------------------------------------------------------------- within
def test_within_passes_and_states_how_long_it_took():
    def script(link, tick):
        if tick >= 5:
            link.state.alt = 20.0

    result = evaluate(FakeLink(script=script), {"alt_above": 15}, within=10.0)
    assert result.passed, result.text
    assert result.kind == "within" and result.duration == 10.0
    assert result.clock == "vehicle"
    # 5 ticks of 0.2 vehicle seconds each.
    assert result.observed == pytest.approx(1.0, abs=0.05), result.text
    assert "alt=20.0m" in result.text


def test_within_fails_at_the_deadline_and_says_what_it_last_saw():
    link = FakeLink()
    link.state.alt = 3.2
    result = evaluate(link, {"alt_above": 15}, within=2.0)
    assert not result.passed
    assert "alt=3.2m" in result.text, result.text
    assert "2s" in result.text, result.text
    assert result.observed >= 2.0, result.text


def test_within_is_measured_on_the_vehicles_clock_not_ours():
    """The whole reason `_Window` exists.

    At speedup 10 the condition becomes true after 10 seconds of FLIGHT, and a
    `within: 12s` must therefore pass — even though the polling loop that
    watched it ran for a fraction of that in wall-clock terms.
    """
    def script(link, tick):
        if link.state.vehicle_clock_s >= 110.0:
            link.state.alt = 30.0

    result = evaluate(FakeLink(speedup=10.0, script=script),
                      {"alt_above": 15}, within=12.0)
    assert result.passed, result.text
    assert result.observed == pytest.approx(10.0, abs=0.5), result.text


def test_within_and_timeout_cannot_both_be_stated():
    with pytest.raises(procs.ProcedureError, match="two names for the same"):
        procs._parse_expect({"condition": {"armed": True}, "within": "5s",
                             "timeout": 10}, "x", schema=2)


# ------------------------------------------------------------------------ for
def test_for_passes_when_the_condition_is_held():
    result = evaluate(_armed_and_high(), {"alt_above": 15, "armed": True},
                      hold_for=3.0)
    assert result.passed, result.text
    assert result.observed >= 3.0
    assert "3s" in result.text


def test_for_fails_on_a_lapse_and_reports_how_long_it_held():
    """A restarting hold window would let a flickering condition pass.

    That is the opposite of what "continuously" means, and the failure text
    would stop describing what the aircraft actually did.
    """
    def script(link, tick):
        if link.state.vehicle_clock_s >= 102.0:
            link.state.alt = 1.0            # sank back after two seconds

    link = _armed_and_high(script=script)
    result = evaluate(link, {"alt_above": 15, "armed": True}, hold_for=5.0)
    assert not result.passed
    assert "2" in result.text, result.text
    assert "alt=1.0m" in result.text, result.text


def test_for_fails_when_the_condition_never_becomes_true_at_all():
    link = FakeLink()
    link.state.alt = 0.0
    result = evaluate(link, {"alt_above": 15}, hold_for=5.0, timeout=0.5)
    assert not result.passed
    assert "never became true" in result.text, result.text


def test_for_refuses_to_pass_without_the_telemetry_it_rests_on():
    """Silence is not success.

    An attitude criterion evaluated against a `VehicleState` that never
    received an ATTITUDE message reads 0.0 for every angle and every rate — a
    perfect flight, measured on nothing.
    """
    link = _armed_and_high()
    link.state.attitude_known = False
    result = evaluate(link, {"roll_within": [-20, 20]}, hold_for=3.0)
    assert not result.passed
    assert "never arrived" in result.text, result.text


# ---------------------------------------------------------------------- never
def test_never_passes_when_the_bound_is_not_crossed():
    link = _armed_and_high()
    link.state.roll_rate = 12.0
    result = evaluate(link, {"angular_rate_above": 90}, never=3.0)
    assert result.passed, result.text
    assert "rate=12°/s" in result.text, result.text
    assert result.observed >= 3.0


def test_never_fails_on_a_single_observed_excursion():
    def script(link, tick):
        if tick == 4:
            link.state.yaw_rate = 300.0

    result = evaluate(_armed_and_high(script=script),
                      {"angular_rate_above": 90}, never=5.0)
    assert not result.passed
    assert "rate=300°/s" in result.text, result.text
    assert result.observed < 5.0, result.text


def test_never_refuses_to_pass_without_the_telemetry_it_rests_on():
    link = _armed_and_high()
    link.state.attitude_known = False
    result = evaluate(link, {"angular_rate_above": 90}, never=3.0)
    assert not result.passed
    assert "not the same as nothing being wrong" in result.text, result.text


def test_a_window_too_short_to_sample_is_not_judged():
    """Two readings cannot describe a duration."""
    link = _armed_and_high(speedup=1000.0)      # one tick swallows the window
    result = evaluate(link, {"angular_rate_above": 90}, never=3.0)
    assert not result.passed
    assert "not judged" in result.text, result.text


# ---------------------------------------------------------------- the fallback
def test_a_stalled_vehicle_clock_falls_back_to_the_wall_clock_and_says_so(monkeypatch):
    """A criterion waiting on a dead telemetry stream is a hang, not a verdict."""
    monkeypatch.setattr("argazui.procrunner.WALL_BACKSTOP_MARGIN", 0.3)
    monkeypatch.setattr("argazui.procrunner.WALL_BACKSTOP_FACTOR", 0.1)

    link = FakeLink(advance=False)              # the clock never moves
    link.state.vehicle_clock_s = 0.0
    link.state.alt = 0.0
    result = evaluate(link, {"alt_above": 15}, within=2.0)

    assert not result.passed
    assert result.clock == "wall"
    assert "wall clock" in result.text, result.text


def test_a_clock_that_freezes_mid_window_is_detected(monkeypatch):
    """The case v1.3 could not see, and v1.4's link fault makes routine.

    `time_boot_ms` keeps its last value when telemetry stops — it does not go
    backwards and it does not go to zero. A window that only checked for those
    two measured `now - start` = 0 for its whole duration and then reported
    `clock: "vehicle"`: a dead stream described as a healthy measurement of no
    seconds at all.
    """
    monkeypatch.setattr("argazui.procrunner.STALL_AFTER_WALL_S", 0.15)

    def freeze(link, tick):
        if tick >= 2:
            link._advance = False     # the stream dies part way through

    link = FakeLink(script=freeze, speedup=5.0)
    window = _Window(link, budget=10.0)
    assert not window.stalled, "a healthy clock must not read as stalled"

    for _ in range(6):
        window.tick()
        time.sleep(0.05)

    assert window.stalled, "a frozen clock was still believed"
    assert window.clock == "wall"
    # And the duration is not zero: wall seconds converted with the speedup the
    # window opened with, so the number still means vehicle time.
    assert window.elapsed > 0.5, window.elapsed
    assert window.note(), "the fallback has to be stated in the result text"


def test_the_fallback_is_sticky_once_it_has_been_used(monkeypatch):
    """A duration whose unit changed half way through is not a measurement."""
    monkeypatch.setattr("argazui.procrunner.STALL_AFTER_WALL_S", 0.1)

    link = FakeLink(advance=False)
    window = _Window(link, budget=10.0)
    time.sleep(0.15)
    assert window.stalled

    link.state.vehicle_clock_s += 50.0        # telemetry comes back
    assert window.stalled, "the window switched clocks mid-measurement"
    assert window.clock == "wall"


def test_the_wall_backstop_is_sized_from_the_measured_speedup():
    """It has to scale, or it is either useless or a second timeout.

    At speedup 10 a 60-second vehicle window is six wall seconds of flight; a
    fixed ceiling would either fire during a healthy run at speedup 1 or never
    fire at all at speedup 10.
    """
    slow = _Window(FakeLink(speedup=1.0), 60.0)
    fast = _Window(FakeLink(speedup=10.0), 60.0)
    assert fast.wall_limit < slow.wall_limit
    assert slow.clock == "vehicle" and not slow.note()


# ------------------------------------------------------------------ the schema
def test_temporal_keys_need_schema_2():
    with pytest.raises(procs.ProcedureError, match="schema 2"):
        procs._parse_expect({"condition": {"armed": True}, "for": "5s"},
                            "x", schema=1)


def test_only_one_temporal_key_per_criterion():
    with pytest.raises(procs.ProcedureError, match="at most one"):
        procs._parse_expect({"condition": {"armed": True}, "for": "5s",
                             "never": "5s"}, "x", schema=2)


def test_attitude_stable_cannot_also_carry_a_temporal_key():
    """It is already an answer about the whole procedure.

    Asking an accumulated envelope to hold "for 5 s" has no reading that stays
    deterministic, so it is refused with a pointer at the instantaneous
    conditions that do have one.
    """
    with pytest.raises(procs.ProcedureError, match="already accumulated"):
        procs._parse_expect(
            {"condition": {"attitude_stable": {"max_rate": 60}}, "for": "5s"},
            "x", schema=2)


@pytest.mark.parametrize("bad", [5, "5", "5m", "0s", "-3s", True, None])
def test_a_duration_without_a_usable_unit_is_rejected(bad):
    """`for: 5` is ambiguous in a file that writes metres and PWM as numbers."""
    with pytest.raises(procs.ProcedureError):
        procs.parse_duration(bad, "x")


@pytest.mark.parametrize("text,seconds", [
    ("10s", 10.0), ("500ms", 0.5), ("2min", 120.0), (" 1.5 s ", 1.5), ("3SEC", 3.0),
])
def test_durations_that_state_their_unit_are_accepted(text, seconds):
    assert procs.parse_duration(text, "x") == pytest.approx(seconds)


def test_a_reversed_attitude_band_is_rejected():
    """A band that rejects everything reads as a broken aircraft."""
    with pytest.raises(procs.ProcedureError, match="must be below"):
        procs._check_condition({"roll_within": [20, -20]}, "x", schema=2)


def test_the_shipped_copter_takeoff_uses_all_three_shapes():
    """The primitives are not a facility nobody uses.

    A capability with no procedure behind it is a claim, and this project's
    whole subject is the difference between a claim and evidence.
    """
    procedure = procs.load_all()["copter_takeoff"]
    assert procedure.schema == 2
    assert {e.kind for e in procedure.expect} >= {"within", "for", "never"}


# --------------------------------------------------------------------- helpers
def _armed_and_high(script=None, speedup: float = 1.0) -> FakeLink:
    link = FakeLink(script=script, speedup=speedup)
    link.state.armed = True
    link.state.alt = 20.0
    link.state.mode = "GUIDED"
    return link
