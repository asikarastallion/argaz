"""Silence is not success: a criterion cannot pass on telemetry that never came.

WHAT THIS FILE EXISTS TO STOP COMING BACK
-----------------------------------------
The v1.6 audit demonstrated that `alt_below: 1` and `armed: false` both
evaluated PASS against a `VehicleState` that had never received a single
MAVLink message — because 0.0 and False are what a float and a bool start as,
and nothing distinguished "the aircraft is on the ground" from "nothing has
told us where the aircraft is".

Those two conditions are, between them, the ENTIRE acceptance block of all four
shipped landing procedures. A landing therefore reported a valid PASS from
fields nothing had written to, and the recorded measurement — `alt=0.0m` — was
byte-identical to the one a genuine landing leaves.

Two mechanisms were missing and both are tested here:

  1. `CONDITION_EVIDENCE` covered attitude and pre-arm only, so altitude, climb
     rate, ground speed, arm state and mode had no backing signal named at all.
  2. The guard that consults it was called from `_expect_for` and
     `_expect_never` and from neither of the other two shapes, so `within` and
     the schema-1 `eventually` never asked.

The tests below are written against `ProcedureRunner._evaluate` — the real
evaluator, on the real `VehicleState` — rather than against a helper, because
the defect lived in the wiring between them and a test of either half alone
would have passed throughout.

WHAT IS NOT TESTED HERE
-----------------------
That the guard is not over-eager. That matters just as much — a fix which made
everything unevaluable would "close" the finding and destroy the tool — so
`test_a_measured_criterion_still_passes` and
`test_a_measured_criterion_still_fails` are in this file too, and
`tests/test_tier1_procedures.py` flies the whole thing against real SITL.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argazui import procrunner
from argazui.mavlink_link import StabilityWatch, VehicleState
from argazui.procedures import Expectation
from argazui.procrunner import ProcedureRunner

pytestmark = pytest.mark.tier1


class FakeLink:
    """A link whose state is whatever the test says it is.

    Deliberately not a mock of `MavlinkLink`: it holds a REAL `VehicleState`
    and a REAL `StabilityWatch`, because the thing under test is what those two
    objects say about themselves when nothing has written to them. A mock would
    have to reproduce their defaults, which is the exact fact in question.
    """

    def __init__(self) -> None:
        self.state = VehicleState()
        self.stability = StabilityWatch()
        self.speedup = 1.0
        self.submitted = 0

    def submit(self, fn, timeout=0.0, label=""):
        self.submitted += 1
        return {"ok": True, "text": ""}

    def clear_link_fault(self):
        pass


def _runner() -> tuple[ProcedureRunner, FakeLink]:
    link = FakeLink()
    return ProcedureRunner(link), link


def _judge(runner: ProcedureRunner, exp: Expectation):
    return runner._evaluate(exp, exp.condition, "test#c1")


# --------------------------------------------------------------- empty state
def test_an_untouched_vehicle_state_knows_nothing():
    """The premise. If this ever fails the rest of the file proves nothing."""
    state = VehicleState()
    assert state.known() == {"heartbeat": False, "position": False,
                             "vfr": False, "attitude": False, "prearm": False}
    # The values that used to be read as measurements.
    assert state.alt == 0.0 and state.armed is False and state.climb == 0.0


@pytest.mark.parametrize("condition", [
    {"alt_below": 1.0},              # "on the ground" — every landing procedure
    {"alt_above": 5.0},
    {"armed": False},                # "disarmed after landing" — likewise
    {"armed": True},
    {"mode": "LAND"},
    {"mode_in": ["LAND", "RTL"]},
    {"climb_rate_below": 5.0},
    {"climb_rate_above": -5.0},
    {"groundspeed_above": -1.0},
    {"prearm_ok": False},
    {"pitch_within": [-10.0, 10.0]},
    {"roll_within": [-180.0, 180.0]},
    {"angular_rate_below": 90.0},
])
def test_no_condition_passes_without_its_telemetry(condition):
    """Every condition, in the shape most likely to pass on a default value.

    Each entry above is chosen so that the DEFAULT value satisfies it: 0.0 is
    below 1, False equals False, 0°/s is below 90. Before the corrective
    release most of these returned PASS.
    """
    runner, _ = _runner()
    result = _judge(runner, Expectation(condition=condition, timeout=0.2))
    assert result.passed is False, f"{condition} passed with no telemetry"
    assert result.evaluated is False, (
        f"{condition} was reported as judged when nothing was measured")


@pytest.mark.parametrize("shape", ["eventually", "within", "for", "never"])
def test_every_temporal_shape_refuses_unmeasured_data(shape):
    """The guard has to be on all four, which is precisely what it was not."""
    runner, _ = _runner()
    kwargs = {"eventually": {"timeout": 0.2},
              "within": {"within": 0.2},
              "for": {"hold_for": 0.2, "timeout": 0.2},
              "never": {"never": 0.2}}[shape]
    exp = Expectation(condition={"alt_below": 1.0}, **kwargs)
    assert exp.kind == shape
    result = _judge(runner, exp)
    assert result.passed is False, f"'{shape}' passed with no telemetry"
    assert result.evaluated is False, f"'{shape}' claimed to have judged it"


def test_the_refusal_names_the_signal_that_never_arrived():
    """A reader has to be told WHICH stream was missing, not just that one was."""
    runner, _ = _runner()
    result = _judge(runner, Expectation(condition={"alt_below": 1.0}, timeout=0.2))
    assert "GLOBAL_POSITION_INT" in result.text
    assert result.text != ""


def test_a_partially_known_vehicle_still_refuses_the_unknown_half():
    """Heartbeats arriving do not make an altitude criterion measurable.

    This is the shape the real bug took: HEARTBEAT is what `state.connected`
    needs, so the link looked healthy and the landing criteria looked satisfied
    while GLOBAL_POSITION_INT was never requested successfully.
    """
    runner, link = _runner()
    link.state.heartbeat_known = True
    link.state.armed = False

    armed = _judge(runner, Expectation(condition={"armed": False}, timeout=0.2))
    assert armed.passed is True and armed.evaluated is True

    altitude = _judge(runner, Expectation(condition={"alt_below": 3.0},
                                          timeout=0.2))
    assert altitude.passed is False and altitude.evaluated is False


def test_a_compound_condition_needs_every_signal_it_names():
    """`{alt_above, armed, mode}` is one criterion and needs all three."""
    runner, link = _runner()
    link.state.heartbeat_known = True
    link.state.armed, link.state.mode = True, "GUIDED"
    result = _judge(runner, Expectation(
        condition={"alt_above": 5.0, "armed": True, "mode": "GUIDED"},
        timeout=0.2))
    assert result.passed is False and result.evaluated is False


# ------------------------------------------------------- the guard is not blunt
def test_a_measured_criterion_still_passes():
    """The fix must not close the finding by refusing everything."""
    runner, link = _runner()
    link.state.position_known = True
    link.state.alt = 0.4
    result = _judge(runner, Expectation(condition={"alt_below": 3.0}, timeout=1.0))
    assert result.passed is True and result.evaluated is True
    assert "alt=0.4m" in result.text


def test_a_measured_criterion_still_fails():
    """A real violation is still a real, EVALUATED failure about the aircraft."""
    runner, link = _runner()
    link.state.position_known = True
    link.state.alt = 42.0
    result = _judge(runner, Expectation(condition={"alt_below": 3.0}, timeout=0.3))
    assert result.passed is False
    assert result.evaluated is True, (
        "a measured violation must stay a verdict, not become 'not judged'")
    assert "alt=42.0m" in result.text


@pytest.mark.parametrize("alt, passes", [
    (2.999, True),      # just below
    (3.0, False),       # exactly equal — `alt_below` is a strict `<`
    (3.001, False),     # just above
])
def test_boundary_behaviour_is_unchanged_by_the_guard(alt, passes):
    runner, link = _runner()
    link.state.position_known = True
    link.state.alt = alt
    result = _judge(runner, Expectation(condition={"alt_below": 3.0}, timeout=0.3))
    assert result.passed is passes
    assert result.evaluated is True


def test_the_result_is_deterministic_for_the_same_state():
    runner, link = _runner()
    link.state.position_known = True
    link.state.alt = 1.0
    first = _judge(runner, Expectation(condition={"alt_below": 3.0}, timeout=0.3))
    second = _judge(runner, Expectation(condition={"alt_below": 3.0}, timeout=0.3))
    assert (first.passed, first.evaluated) == (second.passed, second.evaluated)


# ------------------------------------------------------------- attitude envelope
def test_an_attitude_envelope_with_no_samples_is_not_judged():
    """`attitude_stable` has its own minimum, and it is not a failure either."""
    runner, link = _runner()
    link.state.attitude_known = True          # ATTITUDE arrived...
    result = _judge(runner, Expectation(
        condition={"attitude_stable": {"max_rate": 90.0}}, timeout=0.3))
    # ...but not enough of it to describe a stretch of flight.
    assert result.passed is False
    assert result.evaluated is False


def test_an_attitude_envelope_with_enough_samples_is_judged():
    runner, link = _runner()
    link.state.attitude_known = True
    for i in range(200):
        # 0.1 s apart on the vehicle's clock: 20 s of measured attitude, well
        # past DEFAULT_STABILITY_MIN_SECONDS, all of it inside the band.
        link.stability.add(i * 0.1, 0.0, 0.0, (1.0, 1.0, 1.0))
    result = _judge(runner, Expectation(
        condition={"attitude_stable": {"max_rate": 90.0}}, timeout=0.3))
    assert result.evaluated is True and result.passed is True


def test_an_attitude_envelope_that_was_violated_still_fails():
    runner, link = _runner()
    link.state.attitude_known = True
    for i in range(200):
        link.stability.add(i * 0.1, 0.0, 0.0, (1882.0, 0.0, 0.0))
    result = _judge(runner, Expectation(
        condition={"attitude_stable": {"max_rate": 90.0}}, timeout=0.3))
    assert result.evaluated is True, "a measured tumble is a verdict"
    assert result.passed is False


# ------------------------------------------------------------------- coverage
def test_every_condition_the_schema_offers_names_its_evidence():
    """A condition added later must not inherit the old silent-pass behaviour.

    `param` is the one deliberate exception: it reads the value live and
    returns None when the vehicle does not answer, so it already fails closed
    without a knowledge flag.
    """
    from argazui import procedures

    declared = set(procedures.CONDITION_KEYS + procedures.CONDITION_KEYS_V2)
    covered = set(procrunner.CONDITION_EVIDENCE) | {"param"}
    assert not declared - covered, (
        f"conditions with no backing signal declared: {sorted(declared - covered)}")


def test_every_named_signal_exists_on_the_vehicle_state():
    """A typo in the table would silently disable the guard for that condition."""
    state = VehicleState()
    for condition, flag in procrunner.CONDITION_EVIDENCE.items():
        assert hasattr(state, flag), f"{condition} names a flag that does not exist: {flag}"
        assert getattr(state, flag) is False, f"{flag} does not start unknown"
        assert flag in procrunner.EVIDENCE_LABEL, f"{flag} has no readable name"


# ------------------------------------------------------------- whole procedure
# The unit tests above judge one criterion at a time. The defect, though, was
# only dangerous because of what happened to the criterion AFTERWARDS: it
# became a passing run, a green row in docs/status.md and a covered item in the
# coverage report. These drive a complete `ProcedureRunner.run()` and follow
# the verdict all the way out.
class _ChattyLink(FakeLink):
    """A link that answers every step, so a procedure can run to its criteria."""

    def __init__(self, **known) -> None:
        super().__init__()
        self.state.connected = True
        self.state.heartbeat_known = True
        for flag, value in known.items():
            setattr(self.state, flag, value)


def _landing_procedure(timeout: float = 0.4):
    """The real `copter_land` document, parsed by the real parser.

    Only the criterion DEADLINES are shortened. The conditions, the ids and the
    shapes are the shipped ones, because those are what is under test — and a
    criterion that has to wait out its real 30 s deadline four times over would
    make this file take two minutes to say something it can say in one second.
    """
    from argazui import procedures as procs

    source = (Path(__file__).resolve().parent.parent
              / "argazui" / "procedures" / "copter_land.yaml")
    procedure = procs.parse(source.read_text(encoding="utf-8"), source)
    for expectation in procedure.expect:
        expectation.timeout = timeout
    return procedure


def test_a_landing_with_no_position_telemetry_does_not_pass(monkeypatch):
    """The exact flight the audit demonstrated, end to end.

    `copter_land` declares two criteria and nothing else: `{armed: false}` and
    `{alt_below: 3.0}`. With heartbeats arriving and GLOBAL_POSITION_INT never
    requested successfully — a state `mavlink_link._request_streams` documents
    ArduCopter reaching — both used to evaluate true against fields nothing had
    written to, and the run was recorded `passed`.
    """
    from argazui import failures, procrunner

    link = _ChattyLink(vfr_known=True, armed=False)
    link.state.climb = -1.0                      # descending, genuinely measured
    # Steps are all satisfied by the fake link, so the flow reaches its
    # criteria — which is the only way to reproduce the original defect.
    monkeypatch.setattr(procrunner.ProcedureRunner, "_run_step",
                        lambda self, step, values, changed: {"ok": True, "text": ""})

    result = procrunner.ProcedureRunner(link).run(_landing_procedure())

    assert result["outcome"] != "passed", "a landing passed with no altitude data"
    by_id = {c["criterion_id"]: c for c in result["expect"]}
    ground = by_id["copter_land#on-ground"]
    assert ground["passed"] is False
    assert ground["evaluated"] is False, "reported as judged when nothing was measured"

    # And it lands in the right category: nothing was measured, so this is a
    # hole in the evidence and NOT a verdict about the aircraft.
    failure = failures.classify_procedure(result)
    assert failure.category == failures.EVIDENCE
    assert failure.code == failures.CODE_CRITERION_NOT_JUDGED


def test_the_same_landing_with_position_telemetry_passes(monkeypatch):
    """The counterweight. The guard must not have broken landing."""
    from argazui import procrunner

    link = _ChattyLink(vfr_known=True, position_known=True, armed=False)
    link.state.climb, link.state.alt = -1.0, 0.2
    monkeypatch.setattr(procrunner.ProcedureRunner, "_run_step",
                        lambda self, step, values, changed: {"ok": True, "text": ""})

    result = procrunner.ProcedureRunner(link).run(_landing_procedure())
    assert result["outcome"] == "passed", result["text"]
    assert all(c["evaluated"] for c in result["expect"])


def test_the_same_landing_still_fails_when_the_aircraft_is_in_the_air(monkeypatch):
    """A measured violation stays a verdict about the aircraft."""
    from argazui import failures, procrunner

    link = _ChattyLink(vfr_known=True, position_known=True, armed=False)
    link.state.climb, link.state.alt = -1.0, 42.0
    monkeypatch.setattr(procrunner.ProcedureRunner, "_run_step",
                        lambda self, step, values, changed: {"ok": True, "text": ""})

    result = procrunner.ProcedureRunner(link).run(_landing_procedure())
    assert result["outcome"] == "failed"
    ground = {c["criterion_id"]: c for c in result["expect"]}["copter_land#on-ground"]
    assert ground["passed"] is False and ground["evaluated"] is True
    failure = failures.classify_procedure(result)
    assert failure.category == failures.ACCEPTANCE


def test_a_procedure_refuses_to_run_without_a_vehicle():
    """F-14: a simulation that never came up is an environment failure.

    Every step would otherwise time out in turn and the run would be reported
    as a `procedure` failure — a statement about a flow that never had an
    aircraft under it.
    """
    from argazui import failures, procrunner

    link = FakeLink()                    # no heartbeat has ever arrived
    result = procrunner.ProcedureRunner(link).run(_landing_procedure())

    assert result["outcome"] == "failed"
    assert result["abort"]["kind"] == procrunner.ABORT_NO_VEHICLE
    failure = failures.classify_procedure(result)
    assert failure.category == failures.ENVIRONMENT
    assert failure.code == failures.CODE_NO_VEHICLE
    assert link.submitted == 0, "it should not have tried to fly anything"


def test_an_unjudged_criterion_is_not_counted_as_covered(monkeypatch):
    """The verdict has to stay honest all the way into the coverage report.

    A criterion that produced no information about the aircraft must not
    inflate a coverage figure, and the status table must not publish it as an
    aircraft failure.
    """
    from argazui import coverage, procrunner, status, trace

    link = _ChattyLink(vfr_known=True, armed=False)
    link.state.climb = -1.0
    monkeypatch.setattr(procrunner.ProcedureRunner, "_run_step",
                        lambda self, step, values, changed: {"ok": True, "text": ""})
    result = procrunner.ProcedureRunner(link).run(_landing_procedure())

    run = {"run_id": "r", "status": "failed", "model": {"id": "sitl_quad"},
           "procedures": [{"procedure": "copter_land", "role": "land",
                           "name": "Copter landing", "result": result}]}

    ground = {c["criterion_id"]: c for c in result["expect"]}["copter_land#on-ground"]
    assert trace._was_evaluated(ground) is False

    _, evaluated, _, _ = coverage._exercised([run])
    assert "copter_land#on-ground" not in evaluated

    claims = {c.subject: c for c in status.claims_of(run)}
    on_ground = claims["on the ground"]
    assert on_ground.result == status.CLAIM_UNEVALUATED, (
        "the status table published an unmeasured criterion as an aircraft failure")
