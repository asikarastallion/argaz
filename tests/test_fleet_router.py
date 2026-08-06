"""L4 — group commands, the five outcomes, targets, policies, event ordering.

REVERTED IS THE REASON THIS FILE EXISTS
---------------------------------------
Phase 3 caught ArduPlane accepting a mode change and abandoning it 140 ms
later, with no NAK and no STATUSTEXT. Reported as ACCEPTED that is a lie;
reported as DENIED it is a different lie. These tests pin the third answer.

The fake link here is deliberate and narrow: it stands in for pymavlink so the
*classifier* can be driven through all five outcomes on demand, including the
two that a real autopilot only produces under conditions that are hard to
arrange. The same classifier is then exercised against real SITL in
`test_fleet_sitl_router.py`, where the outcomes are induced rather than
simulated.
"""
from __future__ import annotations

import threading
import time

import pytest

from argazui.fleet import eventbus, outcomes, router
from argazui.fleet import spec as fleetspec

pytestmark = pytest.mark.tier1


# ----------------------------------------------------------------- fake link
class FakeState:
    def __init__(self):
        self.mode = "MANUAL"
        self.armed = False
        self.alt = 0.0
        self.connected = True
        self.sysid = 1

    def as_dict(self):
        return {"mode": self.mode, "armed": self.armed, "alt": self.alt}


class FakeLink:
    """A link whose behaviour is scripted per command.

    `behaviour` is one of:
        "accept"    ack, and the state sticks
        "revert"    ack, the state changes, then flips back after `revert_after`
        "deny"      NAK with the autopilot's reason text
        "timeout"   the command never comes back
        "dead"      the link is not running at all
    """

    def __init__(self, behaviour="accept", reason="", revert_after=0.2,
                 delay=0.0, running=True):
        self.behaviour = behaviour
        self.reason = reason
        self.revert_after = revert_after
        self.delay = delay
        self._running = running
        self.state = FakeState()
        self.sent = []
        # MavlinkLink measures this from the vehicle's own timestamps; 1.0
        # until it knows better.
        self._speedup = 1.0

    @property
    def speedup(self):
        return self._speedup

    def is_running(self):
        return self._running

    def stop(self):
        self._running = False

    def submit(self, fn, timeout, label="step"):
        self.sent.append(label)
        if self.delay:
            time.sleep(self.delay)
        return fn(self)

    # -- the bits of MavlinkLink the router drives ------------------------
    def _do_mode(self, args):
        want = args[0].upper()
        if self.behaviour == "deny":
            return {"ok": False, "text": self.reason or "PreArm: Need 3D Fix"}
        if self.behaviour == "timeout":
            return {"ok": False, "text": "timeout waiting for MODE"}
        previous = self.state.mode
        self.state.mode = want
        if self.behaviour == "revert":
            def _flip():
                time.sleep(self.revert_after)
                self.state.mode = previous
            threading.Thread(target=_flip, daemon=True).start()
        return {"ok": True, "text": f"mode -> {want}"}

    def _do_arm(self, args, arm=True, recover=True):
        if self.behaviour == "deny":
            return {"ok": False, "text": self.reason or "PreArm: Need 3D Fix"}
        if self.behaviour == "timeout":
            return {"ok": False, "text": "timeout waiting for ARM"}
        self.state.armed = arm
        if self.behaviour == "revert":
            def _flip():
                time.sleep(self.revert_after)
                self.state.armed = not arm
            threading.Thread(target=_flip, daemon=True).start()
        return {"ok": True, "text": "armed" if arm else "disarmed"}


def make_spec(tmp_path, count=3, roles=None) -> fleetspec.FleetSpec:
    roles = roles or {}
    body = """
[fleet]
name = "t"
formation = "line"
spacing_m = 10.0
min_separation_m = 5.0

[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0

[fleet.policy]
group_command = "parallel_ack"
start_delay_s = 0.05
"""
    for index in range(count):
        vid = f"v{index + 1}"
        body += f"""
[[vehicle]]
id = "{vid}"
frame = "quad"
vehicle = "ArduCopter"
sysid = {index + 1}
"""
        if roles.get(vid):
            body += f'role = "{roles[vid]}"\n'
    path = tmp_path / "t.toml"
    path.write_text(body, encoding="utf-8")
    spec = fleetspec.load(path)
    fleetspec.resolve_spawns(spec)
    return spec


def make_router(tmp_path, behaviours, hold_s=0.6, **kwargs):
    spec = make_spec(tmp_path, count=len(behaviours), **kwargs)
    links = {f"v{i + 1}": FakeLink(**b) if isinstance(b, dict)
             else FakeLink(behaviour=b)
             for i, b in enumerate(behaviours)}
    bus = eventbus.EventBus()
    return router.FleetRouter(spec, links, bus=bus, hold_s=hold_s), links, bus


# ------------------------------------------------------------- five outcomes
def test_a_command_that_sticks_is_accepted(tmp_path):
    rt, _, _ = make_router(tmp_path, ["accept"])
    result = rt.set_mode("GUIDED")
    entry = result.results[0]
    assert entry.outcome == outcomes.ACCEPTED
    assert entry.confirmed is True
    assert entry.t_ms >= 0
    assert result.verdict == outcomes.PASSED


def test_a_command_that_is_acked_then_abandoned_is_reverted(tmp_path):
    """The case phase 3 found in the wild.

    The autopilot said yes. The vehicle did not stay. Calling this ACCEPTED
    would reintroduce the exact untruth v1.1 removed.
    """
    rt, _, _ = make_router(tmp_path,
                           [{"behaviour": "revert", "revert_after": 0.15}],
                           hold_s=0.8)
    result = rt.set_mode("GUIDED")
    entry = result.results[0]

    assert entry.outcome == outcomes.REVERTED
    assert entry.ack == "ACCEPTED", "the acknowledgement itself was not recorded"
    assert entry.confirmed is False
    assert "did not hold" in entry.observed
    assert "MANUAL" in entry.observed, "the state it fell back to is not named"
    assert result.verdict == outcomes.FAILED


def test_a_rejection_carries_the_autopilots_own_words(tmp_path):
    rt, _, _ = make_router(
        tmp_path, [{"behaviour": "deny", "reason": "PreArm: Need 3D Fix"}])
    result = rt.arm()
    entry = result.results[0]
    assert entry.outcome == outcomes.DENIED
    assert entry.reason == "PreArm: Need 3D Fix"
    assert entry.confirmed is None


def test_no_acknowledgement_is_a_timeout_not_a_denial(tmp_path):
    rt, _, _ = make_router(tmp_path, ["timeout"])
    result = rt.set_mode("GUIDED")
    entry = result.results[0]
    assert entry.outcome == outcomes.TIMEOUT
    assert entry.ack == ""


def test_a_dead_link_is_its_own_outcome(tmp_path):
    rt, links, _ = make_router(tmp_path, ["accept"])
    links["v1"].stop()
    result = rt.set_mode("GUIDED")
    entry = result.results[0]
    assert entry.outcome == outcomes.NO_LINK
    assert result.verdict == outcomes.FAILED


def test_the_five_outcomes_are_all_distinct():
    assert len(set(outcomes.OUTCOMES)) == 5
    assert outcomes.REVERTED not in (outcomes.ACCEPTED, outcomes.DENIED)
    assert outcomes.SUCCESSFUL == (outcomes.ACCEPTED,), (
        "only ACCEPTED means the vehicle is doing what was asked")


def test_a_state_that_flickers_and_returns_still_did_not_hold(tmp_path):
    """Sampling only the end of the window would call this ACCEPTED."""
    rt, links, _ = make_router(tmp_path, ["accept"], hold_s=0.8)
    link = links["v1"]

    def flicker():
        time.sleep(0.15)
        link.state.mode = "MANUAL"
        time.sleep(0.1)
        link.state.mode = "GUIDED"
    threading.Thread(target=flicker, daemon=True).start()

    result = rt.set_mode("GUIDED")
    assert result.results[0].outcome == outcomes.REVERTED


# ------------------------------------------------------------ the ACK matrix
def test_the_matrix_reports_a_partial_failure_per_vehicle(tmp_path):
    rt, _, _ = make_router(
        tmp_path,
        ["accept",
         {"behaviour": "deny", "reason": "PreArm: Need 3D Fix"},
         {"behaviour": "revert", "revert_after": 0.15}],
        hold_s=0.6)
    result = rt.arm()

    assert result.verdict == outcomes.PARTIAL
    assert result.by_outcome(outcomes.ACCEPTED) == ["v1"]
    assert result.by_outcome(outcomes.DENIED) == ["v2"]
    assert result.by_outcome(outcomes.REVERTED) == ["v3"]

    document = result.as_dict()
    assert document["verdict"] == "PARTIAL"
    assert [r["vehicle"] for r in document["results"]] == ["v1", "v2", "v3"]
    assert document["results"][1]["reason"] == "PreArm: Need 3D Fix"


def test_the_matrix_rows_keep_the_target_order_not_the_finish_order(tmp_path):
    """A matrix whose rows moved between runs would be unreadable."""
    rt, _, _ = make_router(
        tmp_path,
        [{"behaviour": "accept", "delay": 0.3},
         {"behaviour": "accept", "delay": 0.0},
         {"behaviour": "accept", "delay": 0.15}],
        hold_s=0.2)
    result = rt.arm()
    assert [r.vehicle for r in result.results] == ["v1", "v2", "v3"]


def test_every_vehicle_appears_exactly_once(tmp_path):
    rt, _, _ = make_router(tmp_path, ["accept", "deny", "timeout"], hold_s=0.2)
    result = rt.arm()
    assert len(result.results) == 3
    assert len({r.vehicle for r in result.results}) == 3


def test_a_verdict_of_empty_is_not_a_pass(tmp_path):
    """Commanding nobody is not the same as everybody obeying."""
    rt, _, _ = make_router(tmp_path, ["accept"], roles={"v1": "leader"})
    result = rt.arm(target="role:follower")
    assert result.results == []
    assert result.verdict == outcomes.EMPTY
    assert outcomes.EMPTY != outcomes.PASSED


# ----------------------------------------------------------------- targeting
def test_targets_resolve_explicitly(tmp_path):
    spec = make_spec(tmp_path, count=3, roles={"v1": "leader", "v2": "wing"})
    assert router.resolve_target("all", spec) == ["v1", "v2", "v3"]
    assert router.resolve_target(None, spec) == ["v1", "v2", "v3"]
    assert router.resolve_target(["v1", "v3"], spec) == ["v1", "v3"]
    assert router.resolve_target("v2", spec) == ["v2"]
    assert router.resolve_target("role:leader", spec) == ["v1"]
    assert router.resolve_target("selected", spec, connected=["v2"]) == ["v2"]


def test_an_unknown_target_is_refused_not_silently_dropped(tmp_path):
    """Commanding three of four vehicles without saying so is the failure
    the explicit-target rule exists to prevent."""
    spec = make_spec(tmp_path, count=2)
    with pytest.raises(ValueError, match="unknown vehicle"):
        router.resolve_target(["v1", "v9"], spec)


def test_a_command_only_reaches_its_target(tmp_path):
    rt, links, _ = make_router(tmp_path, ["accept", "accept", "accept"],
                               hold_s=0.2)
    rt.arm(target=["v1", "v3"])
    assert links["v1"].sent and links["v3"].sent
    assert links["v2"].sent == [], "v2 was commanded despite not being targeted"


# ------------------------------------------------------------------ policies
def test_parallel_ack_commands_everyone_at_once(tmp_path):
    rt, _, _ = make_router(
        tmp_path, [{"behaviour": "accept", "delay": 0.4}] * 3, hold_s=0.1)
    started = time.monotonic()
    result = rt.arm(policy="parallel_ack")
    elapsed = time.monotonic() - started
    assert result.verdict == outcomes.PASSED
    assert elapsed < 1.0, (
        f"parallel_ack took {elapsed:.2f}s for three 0.4s commands; it "
        f"serialised them")


def test_staggered_waits_between_vehicles(tmp_path):
    rt, _, _ = make_router(tmp_path, ["accept"] * 3, hold_s=0.05)
    started = time.monotonic()
    result = rt.arm(policy="staggered", delay_s=0.3)
    elapsed = time.monotonic() - started
    assert result.verdict == outcomes.PASSED
    assert elapsed >= 0.6, (
        f"staggered finished in {elapsed:.2f}s; the delay was not applied")


def test_gated_stops_the_sequence_when_a_vehicle_misses_its_gate(tmp_path):
    """Vehicle i+1 is not commanded into a situation i has not cleared."""
    rt, links, bus = make_router(tmp_path, ["accept"] * 3, hold_s=0.05)
    result = rt.send(
        "TAKEOFF",
        action_for=lambda v: (lambda link: link._do_mode(["GUIDED"])),
        confirm=router.mode_is("GUIDED"),
        policy="gated",
        gate=router.altitude_above(3.0),
        gate_timeout_s=0.5)

    assert result.results[0].outcome == outcomes.ACCEPTED
    assert "gate" in result.results[0].reason
    assert result.results[1].outcome == outcomes.TIMEOUT
    assert "never met the gate" in result.results[1].reason
    assert links["v2"].sent == [], "v2 was commanded after v1 missed its gate"
    assert result.verdict == outcomes.PARTIAL


def test_gated_continues_when_the_gate_is_met(tmp_path):
    rt, links, _ = make_router(tmp_path, ["accept"] * 2, hold_s=0.05)
    for link in links.values():
        link.state.alt = 10.0                    # already above the gate
    result = rt.send(
        "TAKEOFF",
        action_for=lambda v: (lambda link: link._do_mode(["GUIDED"])),
        confirm=router.mode_is("GUIDED"),
        policy="gated", gate=router.altitude_above(3.0), gate_timeout_s=2.0)
    assert result.verdict == outcomes.PASSED
    assert all(link.sent for link in links.values())


def test_an_unknown_policy_is_refused(tmp_path):
    rt, _, _ = make_router(tmp_path, ["accept"])
    with pytest.raises(ValueError, match="unknown group command policy"):
        rt.arm(policy="hope")


# ----------------------------------------------------------------- the abort
def test_an_abort_reports_per_vehicle_results_like_any_other_command(tmp_path):
    """An abort that reaches nobody has aborted nothing."""
    rt, _, _ = make_router(
        tmp_path,
        ["accept", {"behaviour": "deny", "reason": "mode change refused"}],
        hold_s=0.2)
    result = rt.abort(mode="LAND")

    assert result.verdict == outcomes.PARTIAL
    assert result.by_outcome(outcomes.ACCEPTED) == ["v1"]
    assert result.by_outcome(outcomes.DENIED) == ["v2"]
    assert result.command == "ABORT->LAND"


def test_an_abort_that_reaches_nobody_is_failed_not_passed(tmp_path):
    rt, links, _ = make_router(tmp_path, ["accept", "accept"], hold_s=0.1)
    for link in links.values():
        link.stop()
    result = rt.abort()
    assert result.verdict == outcomes.FAILED
    assert set(result.by_outcome(outcomes.NO_LINK)) == {"v1", "v2"}


# ------------------------------------------------------------- the event bus
def test_the_timeline_is_ordered_on_the_routers_clock(tmp_path):
    rt, _, bus = make_router(tmp_path, ["accept"] * 3, hold_s=0.1)
    rt.arm()
    rt.set_mode("GUIDED")
    assert bus.ordered(), "the timeline is not monotonically ordered"


def test_vehicle_time_is_a_field_and_never_the_sort_key():
    """Given a 4.5 s clock offset, sorting on vehicle time reorders causation."""
    bus = eventbus.EventBus()
    bus.emit("first", vehicle="v1", vehicle_time_s=1000.0)
    bus.emit("second", vehicle="v2", vehicle_time_s=10.0)   # far behind
    events = bus.events
    assert [e.kind for e in events] == ["first", "second"], (
        "events were reordered by vehicle time, which would make the timeline "
        "assert a false causal order")
    assert events[0].t < events[1].t
    assert events[1].vehicle_time_s == 10.0, "vehicle time was dropped"


def test_concurrent_emitters_produce_an_ordered_stream():
    """One thread per vehicle link means ordering must be imposed, not assumed."""
    bus = eventbus.EventBus()

    def spam(name):
        for i in range(50):
            bus.emit("tick", vehicle=name, i=i)

    threads = [threading.Thread(target=spam, args=(f"v{n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(bus.events) == 200
    assert bus.ordered()


def test_the_timeline_records_the_group_command_and_its_matrix(tmp_path):
    rt, _, bus = make_router(tmp_path, ["accept", "deny"], hold_s=0.1)
    rt.arm()
    kinds = [e.kind for e in bus.events]
    assert "group_command" in kinds
    assert "group_result" in kinds
    per_vehicle = bus.of_kind("command_result")
    assert {e.vehicle for e in per_vehicle} == {"v1", "v2"}


def test_the_timeline_writes_jsonl_with_its_clock_stated(tmp_path):
    rt, _, bus = make_router(tmp_path, ["accept"], hold_s=0.1)
    rt.arm()
    path = bus.write_jsonl(tmp_path / "timeline.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()

    import json
    header = json.loads(lines[0])
    assert header["kind"] == "timeline_start"
    assert "monotonic" in header["clock"]
    times = [json.loads(l)["t"] for l in lines[1:]]
    assert times == sorted(times)


# ------------------------------------------------------- plotjuggler naming
def test_the_mirror_namespaces_each_vehicles_series():
    from argazui.telemetry_mirror import encode

    class Msg:
        def get_type(self):
            return "ATTITUDE"

        def get_fieldnames(self):
            return ["roll"]
        roll = 0.5

    import json
    plain = json.loads(encode(Msg(), 1.0))
    assert "ATTITUDE" in plain, "the single-vehicle format changed"

    namespaced = json.loads(encode(Msg(), 1.0, namespace="v2"))
    assert "v2/ATTITUDE" in namespaced
    assert namespaced["v2/ATTITUDE"]["roll"] == 0.5
    assert "ATTITUDE" not in namespaced


def test_an_empty_namespace_is_byte_for_byte_the_v1_2_format():
    from argazui.telemetry_mirror import encode

    class Msg:
        def get_type(self):
            return "VFR_HUD"

        def get_fieldnames(self):
            return ["alt"]
        alt = 12.5

    assert encode(Msg(), 2.0) == encode(Msg(), 2.0, namespace="")


# ------------------------------------------------------- the hold window
def test_the_hold_window_is_vehicle_time_not_wall_time(tmp_path):
    """Measured, because a wall-clock constant was wrong in both directions.

    At speedup 5 a 1.5 s wall window is 7.5 VEHICLE seconds — most of the way
    to ArduCopter's 10 s DISARM_DELAY. Under Gazebo lockstep (measured RTF
    ~0.6) the same constant is only ~0.9 vehicle seconds. The timers this
    window is really about all run on the vehicle's clock, so it does too.
    """
    rt, links, _ = make_router(tmp_path, ["accept"], hold_s=1.5)
    link = links["v1"]

    link._speedup = 1.0
    assert rt.hold_wall_seconds(link) == pytest.approx(1.5)

    # Fast-forwarded SITL: the same vehicle-time window is less wall time.
    link._speedup = 5.0
    assert rt.hold_wall_seconds(link) == pytest.approx(0.3)

    # A world running slower than real time needs MORE wall time.
    link._speedup = 0.6
    assert rt.hold_wall_seconds(link) == pytest.approx(2.5)


def test_a_very_slow_world_cannot_hang_a_group_command(tmp_path):
    rt, links, _ = make_router(tmp_path, ["accept"], hold_s=1.5)
    links["v1"]._speedup = 0.001
    assert rt.hold_wall_seconds(links["v1"]) == router.MAX_HOLD_WALL_S


def test_an_unmeasured_speedup_behaves_as_wall_clock(tmp_path):
    """`speedup` is 1.0 until enough telemetry has arrived to know better."""
    rt, links, _ = make_router(tmp_path, ["accept"], hold_s=1.5)
    assert getattr(links["v1"], "speedup", 1.0) == 1.0
    assert rt.hold_wall_seconds(links["v1"]) == pytest.approx(1.5)
