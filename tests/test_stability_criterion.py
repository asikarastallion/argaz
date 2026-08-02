"""The attitude criterion itself: does it actually reject a bad flight?

WHY THIS FILE EXISTS ALONGSIDE THE REAL FLIGHTS
-----------------------------------------------
`attitude_stable` was written because three green tailsitter runs turned out
to have been tumbles. A criterion added for that reason has to be held to the
same standard it imposes: it must be shown to *fail* something, not just to
sit there while healthy aircraft pass.

The real flights already show both sides — the tailsitter frame fails on it
and three other frames pass — but that evidence depends on SITL's mood and on
how loaded the machine is. These checks pin the evaluator down exactly:
known samples in, known verdict out. They need no vehicle and take
milliseconds; the `tier1` marker only says which CI job runs them.

Every case here is one that a plausible implementation gets wrong. The
vehicle-clock case in particular is a real defect this criterion shipped with
for an afternoon: weighted by arrival time, a hundred buffered messages
covering ten seconds of flight all landed within a few milliseconds and the
envelope reported 2.6 seconds of a 15-second climb.
"""
from __future__ import annotations

import pytest

from argazui.mavlink_link import StabilityWatch
from argazui.procrunner import ProcedureRunner

pytestmark = pytest.mark.tier1

HOVER = {"roll": [-20, 20], "pitch": [-20, 20], "max_rate": 60, "tolerance": 2}


class _FakeLink:
    """Only what `_check_stability` touches: a watch to read."""

    def __init__(self, watch: StabilityWatch) -> None:
        self.stability = watch


def evaluate(watch: StabilityWatch, limits: dict) -> tuple[bool, str]:
    return ProcedureRunner(_FakeLink(watch))._check_stability(limits)


def fill(seconds: float, roll: float, pitch: float, rate: float,
         hz: float = 10.0, start: float = 100.0) -> StabilityWatch:
    """A watch holding one steady attitude, on the vehicle's clock."""
    watch = StabilityWatch()
    watch.reset()
    for i in range(int(seconds * hz) + 1):
        watch.add(start + i / hz, roll, pitch, (rate, 0.0, 0.0))
    return watch


def test_a_steady_hover_passes():
    ok, text = evaluate(fill(30, roll=1.0, pitch=-0.5, rate=2.0), HOVER)
    assert ok, text
    assert "0.0s" in text


def test_a_tumble_fails_on_rate():
    """The tailsitter case, reduced to its essentials."""
    ok, text = evaluate(fill(30, roll=1.0, pitch=0.0, rate=300.0), HOVER)
    assert not ok
    assert "turn rate above 60" in text


def test_a_sustained_lean_fails_on_the_band():
    ok, text = evaluate(fill(30, roll=45.0, pitch=0.0, rate=2.0), HOVER)
    assert not ok
    assert "roll outside [-20,20]" in text


def test_a_brief_excursion_inside_the_tolerance_passes():
    """A mode change or a gust must not fail a healthy flight.

    Also the case that decides whether the criterion is usable at all: a limit
    with no forgiveness would reject every real takeoff.
    """
    watch = fill(30, roll=1.0, pitch=0.0, rate=2.0)
    for i in range(1, 16):                   # 1.5 s at 10 Hz, tolerance is 2 s
        watch.add(130.0 + i / 10.0, 45.0, 0.0, (2.0, 0.0, 0.0))
    ok, text = evaluate(watch, HOVER)
    assert ok, text
    assert "1.5s" in text, text


def test_an_excursion_past_the_tolerance_fails():
    watch = fill(30, roll=1.0, pitch=0.0, rate=2.0)
    for i in range(1, 31):                   # 3.0 s, past the 2 s budget
        watch.add(130.0 + i / 10.0, 45.0, 0.0, (2.0, 0.0, 0.0))
    ok, text = evaluate(watch, HOVER)
    assert not ok, text
    assert "for 3.0s" in text, text


def test_too_little_data_fails_rather_than_passes():
    """The whole ethos in one assertion.

    An empty or nearly-empty envelope is the state a broken telemetry stream
    produces. Reporting it as stable would be the same unearned tick this
    version exists to remove, so it fails and says which of the two it is.
    """
    ok, text = evaluate(fill(1.0, roll=0.0, pitch=0.0, rate=0.0), HOVER)
    assert not ok
    assert "unmeasured" in text

    ok, text = evaluate(StabilityWatch(), HOVER)
    assert not ok, "an envelope with no samples at all was accepted"


def test_time_is_counted_on_the_vehicles_clock_not_on_arrival():
    """Buffered telemetry must still account for the flight time it covers.

    Two hundred samples spanning twenty seconds of vehicle time arrive here in
    one burst, exactly as they do when a receive buffer drains. Weighted by
    arrival they would be worth almost nothing and the criterion would report
    "unmeasured" for a perfectly well-observed flight.
    """
    watch = StabilityWatch()
    watch.reset()
    for i in range(200):
        watch.add(500.0 + i * 0.1, 0.0, 0.0, (1.0, 0.0, 0.0))
    assert watch.seconds == pytest.approx(19.9, abs=0.2), watch.report()
    ok, _ = evaluate(watch, HOVER)
    assert ok


def test_a_telemetry_gap_is_not_counted_as_good_behaviour():
    """A dropout can neither manufacture nor excuse time outside a band."""
    watch = StabilityWatch()
    watch.reset()
    watch.add(1000.0, 0.0, 0.0, (1.0, 0.0, 0.0))
    watch.add(1060.0, 0.0, 0.0, (1.0, 0.0, 0.0))     # a 60 s hole
    assert watch.seconds <= StabilityWatch.MAX_GAP, watch.report()
