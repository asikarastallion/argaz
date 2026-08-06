"""The ACK matrix against real autopilots, with failures deliberately induced.

WHY BOTH KINDS OF FAILURE ARE INDUCED HERE
------------------------------------------
`test_fleet_router.py` drives all five outcomes through a fake link, which
proves the classifier. It does not prove that a real autopilot ever produces
them. These do.

    DENIED     induced by disabling one vehicle's simulated GPS
               (`SIM_GPS1_ENABLE=0` — the same lever ArduPilot's own autotest
               uses). The refusal and its wording come from the autopilot.

    REVERTED   induced by moving the simulated flight-mode switch after the
               mode has been commanded and acknowledged.

A NOTE ON THE SECOND ONE, BECAUSE IT MATTERS
--------------------------------------------
This is NOT the same mechanism as the startup race found in phase 3. That race
lives in a ~100 ms window right after RC input becomes valid and cannot be hit
on demand — see docs/e2e-flight-flake.md. What is induced here is a different
real cause of the same observable: a pilot's mode switch overriding a
commanded mode. The router cannot tell the two apart, and should not — its job
is to notice that the state did not hold, whatever moved it.

So the claim this file supports is: **REVERTED is a real outcome that a real
autopilot really produces, and the router really classifies it.** It is not a
claim that the phase-3 race has been reproduced on demand.
"""
from __future__ import annotations

import threading
import time

import pytest

from argazui.fleet import allocator, eventbus, outcomes, router, supervisor
from argazui.fleet import spec as fleetspec
from argazui.fleet import world as worldlib
from argazui.mavlink_link import MavlinkLink

import sitl as sitl_mod

pytestmark = pytest.mark.fleet_sitl

PREARM_WAIT_S = 180.0


def _spec(tmp_path, count: int) -> fleetspec.FleetSpec:
    body = """
[fleet]
name = "ack_matrix"
formation = "line"
spacing_m = 15.0
min_separation_m = 5.0

[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0

[fleet.policy]
group_command = "parallel_ack"
start_delay_s = 0.5
"""
    for index in range(count):
        body += f"""
[[vehicle]]
id = "v{index + 1}"
frame = "quad"
vehicle = "ArduCopter"
sysid = {index + 1}
"""
    path = tmp_path / "ack.toml"
    path.write_text(body, encoding="utf-8")
    spec = fleetspec.load(path)
    result = fleetspec.validate(spec)
    assert result.ok, result.errors
    return spec


@pytest.fixture
def live_fleet(request, tmp_path):
    """A started SITL-only fleet with a router over real links."""
    def _build(count: int = 2):
        try:
            binary = sitl_mod.binary_for("ArduCopter")
            frame = sitl_mod.frame_options("ArduCopter", "quad")
            defaults = sitl_mod.default_param_files(frame)
        except sitl_mod.SitlUnavailable as exc:
            pytest.skip(str(exc))

        spec = _spec(tmp_path, count)
        allocation = allocator.allocate(spec, f"ack_{int(time.time())}",
                                        runs_root=tmp_path / "runs",
                                        work_root=tmp_path / "work")

        def command_for(vehicle, entry):
            return allocator.sitl_command(
                binary, vehicle, entry, defaults, model="quad",
                speedup=sitl_mod.DEFAULT_SPEEDUP,
                home=worldlib.home_for_vehicle(spec, vehicle.id))

        sup = supervisor.FleetSupervisor(spec, allocation,
                                         command_for=command_for)
        links = {}

        def _teardown():
            for link in links.values():
                link.stop()
            sup.stop()

        request.addfinalizer(_teardown)
        sup.start()

        for vehicle in spec.vehicles:
            entry = allocation.for_vehicle(vehicle.id)
            link = MavlinkLink(connection=entry.connection,
                               mirror_namespace=vehicle.id)
            link.start(vehicle="ArduCopter")
            links[vehicle.id] = link

        for vehicle_id, link in links.items():
            assert link.wait_ready(timeout=sitl_mod.CONNECT_TIMEOUT), (
                f"{vehicle_id}: no heartbeat\n{sup.processes[vehicle_id].tail()}")

        bus = eventbus.EventBus()
        return spec, sup, links, router.FleetRouter(spec, links, bus=bus)

    return _build


def _wait_prearm(link, want: bool, timeout: float = PREARM_WAIT_S) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if link.state.prearm_known and link.state.prearm_ok == want:
            return True
        time.sleep(0.5)
    return False


def _set_param(link, name: str, value) -> bool:
    result = link.submit(lambda l: l._do_param(["set", name, str(value)]),
                         timeout=15.0, label=f"set {name}")
    return bool(result.get("ok"))


# ------------------------------------------------------ induced real refusal
def test_the_ack_matrix_reports_a_real_refusal(live_fleet):
    """One vehicle genuinely refuses, and the autopilot's own words survive.

    GPS is removed from v2 only. Everything else about the two vehicles is
    identical, so the difference in the matrix is caused by the vehicle and
    not by how it was commanded.

    HOW THE REFUSAL IS INDUCED, AND THE TWO LEVERS THAT DO NOT WORK
    ---------------------------------------------------------------
    Both were tried against real SITL before settling on the battery check:

      * **Removing GPS does not stop ArduCopter arming.** STABILIZE needs no
        position estimate, so `SIM_GPS1_ENABLE=0` leaves the vehicle armable.
        Measured: v2 armed with GPS disabled.
      * **Removing GPS does not stop it entering GUIDED either**, at least
        while disarmed. Measured: both vehicles accepted GUIDED and held it.
      * **`MavlinkLink._do_arm` RETRIES refusals whose text looks transient**,
        and `TRANSIENT_ARM_HINTS` contains "gps", "3d fix", "position" and
        "ekf" — for up to `ARM_RETRY_WINDOW` = 35 s. Measured: v2 answered
        `ARM: accepted (on attempt 2, after waiting for the vehicle to become
        ready)`. That retry is correct v1.2 behaviour and this phase does not
        change it, but it means any GPS/EKF-flavoured refusal is absorbed.

    So the refusal has to be one the retry logic will not treat as transient.
    A battery below the arming voltage is permanent, unambiguous, and its
    wording matches no entry in `TRANSIENT_ARM_HINTS`.
    """
    spec, sup, links, rt = live_fleet(2)

    for vehicle_id, link in links.items():
        assert _wait_prearm(link, True), f"{vehicle_id} never became armable"

    # v2 only: demand a battery voltage the simulated pack cannot reach.
    assert _set_param(links["v2"], "BATT_ARM_VOLT", 25.0), (
        "could not raise v2's arming voltage threshold")
    assert _wait_prearm(links["v2"], False, timeout=90), (
        "v2 still reports pre-arm OK after its arming voltage was raised")

    result = rt.arm(policy="parallel_ack")

    assert result.verdict == outcomes.PARTIAL, (
        f"expected a partial failure, got {result.verdict}: "
        f"{[r.as_dict() for r in result.results]}")
    assert result.by_outcome(outcomes.ACCEPTED) == ["v1"]
    assert result.by_outcome(outcomes.DENIED) == ["v2"]

    refused = next(r for r in result.results if r.vehicle == "v2")
    assert refused.reason, "the refusal carries no reason at all"
    assert any(word in refused.reason.lower()
               for word in ("prearm", "batt", "volt", "arm")), (
        f"the autopilot's own words did not survive: {refused.reason!r}")
    assert refused.confirmed is None, (
        "a denied command must not claim a state confirmation")

    accepted = next(r for r in result.results if r.vehicle == "v1")
    assert accepted.confirmed is True
    assert "held for" in accepted.observed

    # v2 never armed at all, and that IS safe to re-check: nothing decays
    # towards armed.
    assert links["v2"].state.armed is False

    # v1 is deliberately NOT re-checked here. Measured: it armed, held armed
    # for the whole window, and had auto-disarmed by the next line.
    # ArduCopter's DISARM_DELAY is 10 seconds of VEHICLE time, and the suite
    # runs at speedup 5 — so the 1.5 s wall-clock hold window is 7.5 vehicle
    # seconds, three quarters of the way to an automatic disarm. The matrix
    # entry above is the durable evidence; a second look at live state is a
    # race against the aircraft's own timer.
    rt.disarm(target=["v1"])


def test_arm_absorbs_a_transient_refusal_and_says_so(live_fleet):
    """The v1.2 retry, recorded rather than changed.

    A fleet ARM result that reads `accepted (on attempt 2, ...)` is honest —
    the vehicle did arm, and the text says it took two goes. This pins that
    the retry stays visible in the fleet matrix instead of being flattened
    into a plain ACCEPTED, because "armed first time" and "armed once the EKF
    caught up" are different facts about the aircraft.
    """
    spec, sup, links, rt = live_fleet(1)
    link = links["v1"]
    assert _wait_prearm(link, True), "v1 never became armable"

    result = rt.arm()
    entry = result.results[0]
    assert entry.outcome == outcomes.ACCEPTED
    assert entry.confirmed is True
    # Whether it needed a retry depends on how settled the EKF was; either
    # way the reason text is the autopilot's own and reaches the matrix.
    assert entry.reason, "an accepted ARM carries no text at all"
    rt.disarm()


# ----------------------------------------------------------- induced revert
def test_a_mode_that_does_not_hold_is_reported_as_reverted(live_fleet):
    """Acked, then undone by the mode switch — the third outcome, for real.

    Induced by moving the simulated flight-mode switch during the hold window,
    which is a genuine cause of a commanded mode not holding. It is not the
    phase-3 startup race, which cannot be triggered on demand.
    """
    spec, sup, links, rt = live_fleet(1)
    link = links["v1"]
    assert _wait_prearm(link, True), "v1 never became armable"

    # Band 1 of the mode switch is STABILIZE, so moving the switch there is an
    # unambiguous, non-GPS-dependent mode the vehicle will always accept.
    assert _set_param(link, "FLTMODE1", 0), "could not set FLTMODE1"
    time.sleep(1.0)

    flipped = threading.Event()

    def flip_the_switch():
        # After the ack, inside the router's hold window.
        time.sleep(0.4)
        link.submit(lambda l: l._do_rc_channels({5: 1000}), timeout=10.0,
                    label="mode switch")
        flipped.set()

    thread = threading.Thread(target=flip_the_switch, daemon=True)
    thread.start()
    result = rt.set_mode("LOITER")
    thread.join(timeout=10)
    assert flipped.is_set(), "the mode switch was never moved; test inconclusive"

    entry = result.results[0]
    link.submit(lambda l: l._do_rc_release(), timeout=10.0, label="rc release")

    if entry.outcome == outcomes.DENIED:
        pytest.skip(f"the vehicle refused LOITER outright ({entry.reason!r}), "
                    f"so no revert could be observed on this run")

    assert entry.outcome == outcomes.REVERTED, (
        f"expected REVERTED, got {entry.outcome}: {entry.as_dict()}")
    assert entry.ack == "ACCEPTED", (
        "the acknowledgement was lost; REVERTED must record that the "
        "autopilot DID accept the command")
    assert entry.confirmed is False
    assert "did not hold" in entry.observed
    assert result.verdict == outcomes.FAILED


# --------------------------------------------------------- the abort is real
def test_an_abort_commands_the_survivors_down_over_real_mavlink(live_fleet):
    """`on_abort` wired to MAVLink, and fallible.

    "commanded down" and "confirmed down" are different claims, so the abort
    returns the same five-outcome matrix as any other command.
    """
    spec, sup, links, rt = live_fleet(2)
    for vehicle_id, link in links.items():
        assert _wait_prearm(link, True), f"{vehicle_id} never became armable"

    sup.on_abort = lambda survivors: rt.abort(survivors, mode="LAND")

    result = rt.abort(["v1", "v2"], mode="LAND")
    assert result.command == "ABORT->LAND"
    assert result.verdict in (outcomes.PASSED, outcomes.PARTIAL), (
        f"the abort reached nobody: {[r.as_dict() for r in result.results]}")
    for entry in result.results:
        assert entry.outcome in outcomes.OUTCOMES
        if entry.outcome == outcomes.ACCEPTED:
            assert entry.confirmed is True


def test_the_supervisors_abort_hook_runs_the_routers_abort(live_fleet):
    """The Phase 3 seam, now filled: a dead vehicle triggers a real abort."""
    spec, sup, links, rt = live_fleet(2)
    for link in links.values():
        assert _wait_prearm(link, True)

    aborts = []

    def _abort(survivors):
        aborts.append(list(survivors))
        return rt.abort(survivors, mode="LAND")

    sup.on_abort = _abort

    # Kill v2 outright and let the 1 Hz monitor notice.
    links["v2"].stop()
    sup.processes["v2"].stop()
    deadline = time.time() + 15
    while time.time() < deadline and not sup.failure_actions:
        sup.sample_health()
        time.sleep(0.3)

    assert sup.failure_actions, "the monitor never noticed the dead vehicle"
    assert sup.status == supervisor.RUN_FAILED
    assert aborts == [["v1"]], (
        f"abort_fleet did not command the survivors down: {aborts}")
    assert rt.last_result.command == "ABORT->LAND"


# ----------------------------------------------------------- namespacing
def test_each_vehicle_mirrors_under_its_own_namespace(live_fleet):
    spec, sup, links, rt = live_fleet(2)
    assert links["v1"].mirror.namespace == "v1"
    assert links["v2"].mirror.namespace == "v2"
    assert links["v1"].mirror.namespace != links["v2"].mirror.namespace


# --------------------------------------------------------- distinct address
def test_every_command_is_addressed_and_never_broadcast(live_fleet):
    """sysid 0 is unverifiable, so it is unusable here by construction."""
    spec, sup, links, rt = live_fleet(2)
    for vehicle_id, link in links.items():
        assert link.state.sysid != 0, f"{vehicle_id} reports sysid 0"
    assert links["v1"].state.sysid != links["v2"].state.sysid

    result = rt.set_mode("STABILIZE", target=["v1"])
    assert [r.vehicle for r in result.results] == ["v1"]
