"""Fleet tier 3 — three vehicles in one real Gazebo world.

THE ONLY FLEET TIER THAT MAY VERIFY A MODEL
-------------------------------------------
Same rule as tier 2 for single vehicles: this is where a registered model
actually flies in a fleet. `fleet_sitl` proves the engine on SITL's own
frames and claims nothing about any airframe.

WHAT IS CHECKED BEFORE ANYTHING IS MEASURED
-------------------------------------------
The cross-wiring check runs first, and a failure ABORTS rather than warns.
Every number taken after a mis-wire describes a fleet that does not exist —
a smooth, plausible separation curve for vehicles wired to each other's
models. There is no point measuring anything until it is known that vehicle
*i*'s autopilot moves model *i*.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import time
from pathlib import Path

import pytest

from argazui import paths
from argazui.fleet import (allocator, artifacts, criteria, eventbus,
                           gzstats, outcomes, router, separation,
                           supervisor, wiring)
from argazui.fleet import report as fleetreport
from argazui.fleet import spec as fleetspec
from argazui.fleet import world as worldlib
from argazui.mavlink_link import MavlinkLink

import sitl as sitl_mod

pytestmark = pytest.mark.fleet_gazebo

SITL_MODELS = paths.SITL_MODELS
BASE_WORLD = SITL_MODELS / "Gazebo" / "worlds" / "hexapod_copter_runway.sdf"
BASE_MODEL = SITL_MODELS / "Gazebo" / "models" / "hexapod_copter"
PARAM = SITL_MODELS / "Gazebo" / "config" / "hexapod_copter.param"
LUA = SITL_MODELS / "Gazebo" / "scripts" / "hexapod_copter.lua"
WORLD_NAME = "runway"
TAKEOFF_ALT = 12.0


def _need(path: Path, what: str) -> None:
    if not path.exists():
        pytest.skip(f"{what} not found at {path}")


@pytest.fixture(scope="module")
def gazebo_fleet(request):
    """A composed, started 3-vehicle Gazebo fleet, recorded under runs/."""
    _need(BASE_WORLD, "the hexapod world")
    _need(BASE_MODEL, "the hexapod model")
    if shutil.which("gz") is None:
        pytest.skip("gz is not on PATH; this tier needs Gazebo")
    try:
        binary = sitl_mod.binary_for("ArduCopter")
        frame = sitl_mod.frame_options("ArduCopter", "hexa")
        defaults = sitl_mod.default_param_files(frame)
    except sitl_mod.SitlUnavailable as exc:
        pytest.skip(str(exc))
    if PARAM.is_file():
        defaults = defaults + [PARAM]

    spec = fleetspec.load_by_name("hexapod_trio")
    validation = fleetspec.validate(spec)
    if not validation.ok:
        pytest.skip("hexapod_trio does not validate on this machine: "
                    + "; ".join(validation.errors))

    run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_fleet_hexapod_trio"
    runs_root = paths.RUNS_DIR
    run_dir = runs_root / run_id
    allocation = allocator.allocate(spec, run_id, runs_root=runs_root,
                                    work_root=paths.RUN_DIR / "fleet")
    composed = worldlib.compose(spec, allocation, BASE_WORLD, BASE_MODEL,
                                run_dir, gazebo_model_name="hexapod_copter")

    env = os.environ.copy()
    env["GZ_SIM_RESOURCE_PATH"] = worldlib.resource_path(
        composed, ":".join(filter(None, [
            str(SITL_MODELS / "Gazebo" / "models"),
            str(SITL_MODELS / "Gazebo" / "worlds"),
            env.get("GZ_SIM_RESOURCE_PATH", "")])))

    home = worldlib.home_for(spec)

    def command_for(vehicle, entry):
        entry.work_dir.mkdir(parents=True, exist_ok=True)
        if LUA.is_file():
            (entry.work_dir / "scripts").mkdir(exist_ok=True)
            shutil.copy2(LUA, entry.work_dir / "scripts" / LUA.name)
        return allocator.sitl_command(binary, vehicle, entry, defaults,
                                      model="JSON", speedup=1.0, home=home)

    bus = eventbus.EventBus()
    clock = gzstats.GazeboStats()
    sup = supervisor.FleetSupervisor(
        spec, allocation, command_for=command_for,
        on_event=lambda e: bus.emit(e.get("kind", "event"),
                                    **{k: v for k, v in e.items()
                                       if k not in ("kind", "t")}),
        clock_source=clock, world_path=composed.world_path, gz_env=env)
    links: dict = {}

    state: dict = {}
    done: dict = {}

    def _finalise():
        """Tear the fleet down and write the report. Safe to call twice.

        Explicit rather than hidden in a finalizer: the report is the last
        artefact because criterion 6 is a fact about the END of the run, and
        the test that reads it has to be able to say when that moment was.
        pytest finalizer ordering is not a good place to encode that.
        """
        if done.get("finalised"):
            return done["report"]
        done["finalised"] = True
        for link in links.values():
            link.stop()
        teardown_report = sup.stop()
        state["teardown"] = teardown_report

        # THE REPORT IS WRITTEN LAST, ON PURPOSE.
        # Acceptance criterion 6 is "no orphan processes, all port leases
        # released" — a statement about the END of the run. A report written
        # before teardown can only ever mark it not-measured, which is honest
        # but needlessly incomplete: the fact simply was not available yet.
        collected = list(state.get("criteria") or [])
        collected.append(criteria.teardown_criterion(
            teardown_report,
            authorised_by="the supervisor's own process table and lease file"))
        fleetreport.write(
            run_dir / "fleet_report.md", spec, collected, run_id=run_id,
            wiring=state.get("wiring"), commands=state.get("commands"),
            teardown=teardown_report, allocation=allocation,
            timeline_events=len(bus.events))
        artifacts.write_fleet_json(
            run_dir / "fleet.json", spec, allocation,
            authorisations=state.get("authorisations", {}),
            extra={"wiring": state.get("wiring"),
                   "criteria": [c.as_dict() for c in collected],
                   "verdict": criteria.fleet_verdict(collected)})
        done["report"] = teardown_report
        return teardown_report

    request.addfinalizer(_finalise)

    sup.start()
    sup.stall_source = gzstats.LockstepStallDetector(
        clock,
        processes={v: h.process.pid for v, h in sup.processes.items()},
        heartbeat_ages=lambda: {
            v: (None if not l.state.last_heartbeat
                else time.time() - l.state.last_heartbeat)
            for v, l in links.items()})

    for vehicle in spec.vehicles:
        entry = allocation.for_vehicle(vehicle.id)
        link = MavlinkLink(connection=entry.connection,
                           mirror_namespace=vehicle.id)
        link.start(vehicle="ArduCopter")
        links[vehicle.id] = link
    for vid, link in links.items():
        assert link.wait_ready(timeout=150), (
            f"{vid}: no heartbeat\n{sup.processes[vid].tail()}")
        sup.note_heartbeat(vid)

    rt = router.FleetRouter(spec, links, bus=bus)

    deadline = time.time() + 300
    pending = set(links)
    while time.time() < deadline and pending:
        for vid in list(pending):
            st = links[vid].state
            if st.prearm_known and st.prearm_ok:
                pending.discard(vid)
        time.sleep(1.0)
    assert not pending, f"never became armable: {sorted(pending)}"

    return {"spec": spec, "sup": sup, "links": links, "rt": rt, "bus": bus,
            "clock": clock, "allocation": allocation, "composed": composed,
            "run_dir": run_dir, "env": env, "state": state,
            "finalise": _finalise}


# ------------------------------------------------------- wiring comes first
def test_the_fleet_is_wired_one_autopilot_to_one_model(gazebo_fleet):
    """Runs before any acceptance criterion. A failure aborts the fleet."""
    fleet = gazebo_fleet
    rt, links = fleet["rt"], fleet["links"]

    def pose_of(model):
        data = gzstats.read_world_poses(WORLD_NAME, env=fleet["env"])
        xyz = data["poses"].get(model)
        return wiring.Pose(*xyz) if xyz else None

    def move_one(vehicle_id):
        """Command the climb and do not return until it has happened.

        A fixed wall-clock settle is the wrong instrument here. Measured: at
        three vehicles the world runs at ~0.6x, so an 8 s window is under 5 s
        of vehicle time and a vehicle climbed only 0.84 m — read as a possible
        mis-wire when it was simply a short look. Waiting on the vehicle's own
        altitude is condition-based, the same discipline the readiness gates
        use, and it makes the check independent of simulation rate.
        """
        # A COMMAND THAT FAILED IS NOT A MIS-WIRE.
        #
        # Measured: a run where v2 simply did not arm reported "commanded v2
        # but its model moved only 0.02 m ... this autopilot is driving a
        # different model". That is a false accusation with a real cause, and
        # it sends the reader hunting a wiring fault that does not exist. Each
        # command is checked, and a refusal is reported as a refusal.
        moded = rt.set_mode("GUIDED", target=[vehicle_id])
        assert moded.verdict == outcomes.PASSED, (
            f"{vehicle_id} would not enter GUIDED, so the wiring check could "
            f"not be carried out: {[r.as_dict() for r in moded.results]}")
        armed_now = rt.arm(target=[vehicle_id])
        assert armed_now.verdict == outcomes.PASSED, (
            f"{vehicle_id} would not arm, so the wiring check could not be "
            f"carried out: {[r.as_dict() for r in armed_now.results]}")

        link = links[vehicle_id]
        result = link.submit(lambda l: l._do_takeoff(["8"]), timeout=30,
                             label="takeoff")
        assert result.get("ok"), (
            f"{vehicle_id} refused TAKEOFF, so the wiring check could not be "
            f"carried out: {result.get('text')}")

        deadline = time.time() + 120
        while time.time() < deadline and link.state.alt < 4.0:
            if not link.state.armed:
                break
            time.sleep(0.5)
        assert link.state.alt >= 4.0, (
            f"{vehicle_id} was commanded to 8 m, accepted it, and reached only "
            f"{link.state.alt:.2f} m (armed={link.state.armed}). That is a "
            f"flight problem on that vehicle, not evidence about the wiring.")

    report = wiring.verify_wiring([v.id for v in fleet["spec"].vehicles],
                                  move=move_one, settle_s=6.0,
                                  pose_reader=pose_of)
    fleet["wiring"] = report
    fleet["state"]["wiring"] = report.as_dict()

    # Bring everyone down whatever the verdict.
    rt.set_mode("LAND")
    deadline = time.time() + 90
    while time.time() < deadline and any(l.state.armed for l in links.values()):
        time.sleep(1.0)

    if not report.ok:
        rt.abort(mode="LAND")
    assert report.ok, (
        "the fleet is mis-wired; every measurement after this point would "
        "describe a fleet that does not exist.\n" + report.reason)
    for check in report.checks:
        assert check.moved_m > wiring.MOVED_M


# ---------------------------------------------------------------- the flight
def test_three_vehicles_fly_with_rtf_and_separation_recorded(gazebo_fleet):
    fleet = gazebo_fleet
    rt, links, spec = fleet["rt"], fleet["links"], fleet["spec"]
    run_dir = fleet["run_dir"]

    # Separation is authorised by the world-pose message being ONE world state
    # at ONE simulated instant — not by Gazebo merely being present. Vehicle
    # clocks were measured to disagree by up to 0.32 s even under lockstep.
    monitor = separation.SeparationMonitor(spec.min_separation_m,
                                           time_base_valid=True)
    rtf_samples: list = []
    sep_reason = ""

    rt.set_mode("GUIDED")

    # ARM IS PART OF EACH VEHICLE'S OWN GATED STEP, NOT A PRELUDE.
    #
    # Measured: arming all three up front and then running a gated takeoff
    # fails the last vehicle with
    #
    #     TAKEOFF 12m: REJECTED (MAV_RESULT_FAILED) — otopilot: Disarming motors
    #
    # because `gated` makes vehicle i+1 wait for vehicle i to pass its
    # altitude gate — roughly 18 s for three vehicles — and ArduCopter's
    # DISARM_DELAY auto-disarms an armed vehicle sitting on the ground after
    # 10 s. The safest policy therefore has the longest ground wait, and
    # arming early is exactly what makes it fail.
    def arm_and_takeoff(vehicle_id):
        def _run(link):
            armed_here = link._do_arm([], arm=True)
            if not armed_here.get("ok"):
                return armed_here
            return link._do_takeoff([str(TAKEOFF_ALT)])
        return _run

    gated = rt.send(
        "TAKEOFF", action_for=arm_and_takeoff,
        confirm=router.armed_is(True), policy="gated",
        gate=router.altitude_above(5.0), gate_timeout_s=120.0,
        ack_timeout=90.0)
    assert gated.verdict == outcomes.PASSED, [r.as_dict() for r in gated.results]
    # Every vehicle really climbed through its gate, in order.
    for entry in gated.results:
        assert entry.outcome == outcomes.ACCEPTED, entry.as_dict()

    highest: dict = {vid: None for vid in links}
    started = time.monotonic()
    while time.monotonic() - started < 40:
        for vid, link in links.items():
            alt = link.state.alt
            if highest[vid] is None or alt > highest[vid]:
                highest[vid] = alt
        sample = fleet["clock"].sample()
        rtf_samples.append((time.monotonic() - started, sample.rtf,
                            sample.sim_time_s))
        data = gzstats.read_world_poses(WORLD_NAME, env=fleet["env"])
        stamp = data.get("stamp_s")
        fixes = [separation.Fix(vehicle_id=vid, east_m=p[0], north_m=p[1],
                                up_m=p[2], t_s=stamp)
                 for vid in links
                 if (p := data["poses"].get(vid)) and stamp is not None]
        monitor.sample(fixes)
        time.sleep(0.5)

    verdict = monitor.verdict()
    assert verdict["measured"] is True, verdict
    assert verdict["passed"] is True, (
        f"separation violated: minimum {verdict['minimum_m']} m against "
        f"{spec.min_separation_m} m")

    measured_rtf = [r for _, r, _ in rtf_samples if r is not None]
    assert measured_rtf, "no real-time factor was recorded at all"

    rt.set_mode("LAND")
    deadline = time.time() + 120
    while time.time() < deadline and any(l.state.armed for l in links.values()):
        time.sleep(1.0)

    # ------------------------------------------------------------ artefacts
    # `csv_rows()` is one row per PAIR per sample. The criterion asks about
    # the fleet's closest approach, so rows are reduced to the minimum
    # distance at each timestamp — otherwise whichever pair happened to be
    # written last would stand in for the whole fleet.
    closest_at: dict = {}
    for t_s, _pair, distance in monitor.csv_rows():
        if t_s not in closest_at or distance < closest_at[t_s]:
            closest_at[t_s] = distance
    sep_rows = sorted(closest_at.items())

    evaluated = [
        criteria.separation_criterion(
            sep_rows, spec.min_separation_m, measuring=monitor.measuring,
            authorised_by=f"/world/{WORLD_NAME}/pose/info — one world-state "
                          f"message carries every model's position under a "
                          f"single header stamp, so the positions are "
                          f"simultaneous by construction"),
        criteria.rtf_criterion(
            [(t, r) for t, r, _ in rtf_samples if r is not None],
            floor=spec.max_rtf_drop, available=True,
            authorised_by="/stats, read from the running physics server"),
        criteria.altitude_criterion(
            {vid: highest.get(vid) for vid in links}, target_m=5.0,
            authorised_by="VFR_HUD altitude over each vehicle's own link"),
    ]

    # Handed to the fixture, which writes the report AFTER teardown so that
    # criterion 6 ("no orphans, lease released") can be judged rather than
    # marked not-measured. The report is the last artefact written because one
    # of its claims is about the end of the run.
    state = fleet["state"]
    state["criteria"] = evaluated
    state["commands"] = [gated.as_dict()]
    state["authorisations"] = {
        "separation": artifacts.separation_authorisation(
            monitor.measuring, f"/world/{WORLD_NAME}/pose/info",
            "one world-state message carries every model's position under a "
            "single header stamp, so the positions are simultaneous by "
            "construction; vehicle clocks were measured to disagree by up to "
            "0.32 s even under lockstep (docs/fleet-clock-drift.md)"),
        "rtf": {"measured": True, "source": "/stats",
                "justification": "read from the running physics server"},
    }

    artifacts.write_rtf_csv(run_dir / "rtf.csv", rtf_samples)
    artifacts.write_separation_csv(run_dir / "separation.csv",
                                   monitor.csv_rows(), reason=sep_reason)
    fleet["bus"].write_jsonl(run_dir / "timeline.jsonl")

    assert (run_dir / "rtf.csv").is_file()
    assert (run_dir / "separation.csv").is_file()
    assert (run_dir / "world" / "fleet.sdf").is_file()
    rows = (run_dir / "separation.csv").read_text().splitlines()
    assert len(rows) > 1, "separation.csv has a header and nothing else"

    # Everything evaluated here must have held; the report is checked by the
    # test below, once the fixture has written it.
    for c in evaluated:
        assert c.outcome != criteria.FAILED, c.as_dict()


# ------------------------------------------------------------- induced stall
def test_a_stopped_vehicle_stalls_lockstep_and_is_named(gazebo_fleet):
    """The headline diagnostic, made to happen on purpose.

    SIGSTOP freezes one SITL. Under lockstep the physics server waits for its
    FDM and simulated time stops for the WHOLE world — every vehicle looks
    equally dead. The monitor must name the one that stopped.
    """
    fleet = gazebo_fleet
    detector = fleet["sup"].stall_source
    pid = fleet["sup"].processes["v2"].process.pid

    detector.sample()
    time.sleep(1.5)
    healthy = detector.sample()
    assert healthy.stalled is False, healthy.as_dict()

    os.kill(pid, signal.SIGSTOP)
    try:
        stalled = None
        deadline = time.time() + 40
        while time.time() < deadline:
            got = detector.sample()
            if got.stalled:
                stalled = got
                break
            time.sleep(0.5)
        assert stalled is not None, "sim time kept advancing with v2 frozen"
        assert "v2" in stalled.suspect_vehicles, (
            f"the stall was detected but blamed on {stalled.suspect_vehicles} "
            f"instead of v2: {stalled.reason}")
        assert "v2" in stalled.reason
        assert stalled.stalled_for_s and stalled.stalled_for_s > 0
    finally:
        os.kill(pid, signal.SIGCONT)

    recovered = None
    deadline = time.time() + 40
    while time.time() < deadline:
        got = detector.sample()
        if not got.stalled:
            recovered = got
            break
        time.sleep(0.5)
    assert recovered is not None, "simulated time never resumed after SIGCONT"


def test_the_simulation_server_survived_the_whole_run(gazebo_fleet):
    """Checked before the fixture tears down, so `gz sim` is still expected up."""
    fleet = gazebo_fleet
    assert fleet["sup"].sim_server is not None
    assert fleet["sup"].sim_server.poll() is None, "gz sim died mid-run"
    assert fleet["sup"].orphan_sweep() == [
        {"vehicle": v, "pid": h.process.pid}
        for v, h in fleet["sup"].processes.items() if h.alive()
    ] + ([{"vehicle": "gz sim", "pid": fleet["sup"].sim_server.pid}]
         if fleet["sup"].sim_server.poll() is None else [])


def test_the_report_is_written_after_teardown_and_is_complete(request,
                                                              gazebo_fleet):
    """The report is the LAST artefact, because one of its claims is the end.

    Criterion 6 is "no orphan processes, all port leases released" — a fact
    that does not exist until teardown has happened. Writing the report first
    can only ever mark it not-measured, which is honest but needlessly
    incomplete. So the fixture writes it afterwards, and this check runs at
    session end to read what it produced.
    """
    fleet = gazebo_fleet
    run_dir = fleet["run_dir"]

    teardown_report = fleet["finalise"]()
    assert teardown_report is not None

    def _check():
        path = run_dir / "fleet_report.md"
        assert path.is_file(), "the fixture never wrote fleet_report.md"
        text = path.read_text(encoding="utf-8")

        assert "## What this run did not claim" in text
        assert "What authorised each claim" in text
        assert "says nothing about whether any MODEL is supported" in text
        assert "single header stamp" in text, (
            "the report does not say what authorised the separation claim")
        assert "Cross-wiring check" in text

        # Teardown WAS evaluated, so the run is not INCOMPLETE for that reason.
        assert "no orphan processes, all port leases released" in text
        assert "the fleet was never torn down under supervision" not in text, (
            "the teardown criterion is still not-measured; the report was "
            "written before teardown")

        document = json.loads((run_dir / "fleet.json").read_text())
        assert document["verdict"] in ("PASSED", "FAILED", "INCOMPLETE")
        ids = {c["id"] for c in document["criteria"]}
        assert "teardown" in ids
        assert document["environment"]["argazui"], (
            "reproducibility metadata is missing its ArgazUI version")

    _check()
