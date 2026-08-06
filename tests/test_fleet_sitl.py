"""Fleet tier — two real SITLs, no Gazebo: arm, take off, land, tear down.

WHAT THIS TIER IS AND IS NOT
----------------------------
It is the fleet engine against real autopilots: real ports, the real
supervisor, real readiness gates, the real v1.1 procedure engine once per
vehicle, and the real teardown. Roughly 80% of the fleet engine does not
involve Gazebo at all, and this is the tier that proves that part in minutes
rather than needing a GPU and a 10 GB image.

**It verifies NO model.** These are SITL's own generic frames, exactly as in
tier 1. `docs/status.md` reads model rows from the `tier2` marker; this tier
carries `fleet_sitl` precisely so a fleet result can never be mistaken for a
model result.

WHAT IT DELIBERATELY DOES NOT MEASURE
-------------------------------------
Separation. Without Gazebo there is no lockstep, so the vehicles' clocks carry
a constant offset of boot-stagger x speedup — measured at 0.9 s at speedup 1
and 4.5 s at speedup 5 (docs/fleet-clock-drift.md). Distances computed across
that are not distances. The monitor refuses to emit and the run says so.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from argazui import procedures as procs
from argazui.fleet import (allocator, health, separation, supervisor,
                           world as worldlib)
from argazui.fleet import spec as fleetspec
from argazui.mavlink_link import MavlinkLink
from argazui.procrunner import ProcedureRunner, probe_capabilities

import sitl as sitl_mod

pytestmark = pytest.mark.fleet_sitl

TAKEOFF_ALT = 15.0


@pytest.fixture
def pair_spec(tmp_path) -> fleetspec.FleetSpec:
    """Two SITL quads, from the shipped spec so the test flies what ships."""
    shipped = (Path(__file__).resolve().parent.parent / "argazui" / "config"
               / "fleets" / "sitl_pair.toml")
    spec = fleetspec.load(shipped)
    result = fleetspec.validate(spec)
    assert result.ok, f"the shipped sitl_pair spec does not validate: {result.errors}"
    return spec


def _binary():
    try:
        return sitl_mod.binary_for("ArduCopter")
    except sitl_mod.SitlUnavailable as exc:
        pytest.skip(str(exc))


def _defaults(frame: str):
    try:
        info = sitl_mod.frame_options("ArduCopter", frame)
        return sitl_mod.default_param_files(info)
    except sitl_mod.SitlUnavailable as exc:
        pytest.skip(str(exc))


@pytest.fixture
def fleet(request, pair_spec, tmp_path):
    """A started 2-vehicle fleet, with links, torn down at the end."""
    binary = _binary()
    defaults = _defaults("quad")
    run_id = f"fleet_{int(time.time())}"
    allocation = allocator.allocate(pair_spec, run_id,
                                    runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")

    def command_for(vehicle, entry):
        return allocator.sitl_command(
            binary, vehicle, entry, defaults, model="quad",
            speedup=sitl_mod.DEFAULT_SPEEDUP,
            home=worldlib.home_for_vehicle(pair_spec, vehicle.id))

    events = []
    sup = supervisor.FleetSupervisor(pair_spec, allocation,
                                     command_for=command_for,
                                     on_event=events.append)
    links = {}

    def _teardown():
        for link in links.values():
            link.stop()
        report = sup.stop()
        request.node._teardown_report = report

    request.addfinalizer(_teardown)

    sup.start()

    for vehicle in pair_spec.vehicles:
        entry = allocation.for_vehicle(vehicle.id)
        link = MavlinkLink(connection=entry.connection)
        link.start(vehicle="ArduCopter")
        links[vehicle.id] = link

    for vehicle_id, link in links.items():
        assert link.wait_ready(timeout=sitl_mod.CONNECT_TIMEOUT), (
            f"{vehicle_id}: no heartbeat from "
            f"{allocation.for_vehicle(vehicle_id).connection} within "
            f"{sitl_mod.CONNECT_TIMEOUT:.0f}s\n"
            f"{sup.processes[vehicle_id].tail()}")
        sup.note_heartbeat(vehicle_id)

    return sup, links, events, allocation


def _wait_prearm(link: MavlinkLink, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if link.state.prearm_known and link.state.prearm_ok:
            return True
        time.sleep(0.5)
    return False


# --------------------------------------------------------------- the flight
def test_two_vehicles_arm_take_off_land_and_tear_down(fleet, request):
    """The Phase 3 gate, end to end, against real autopilots.

    Each vehicle is flown by the SAME `ProcedureRunner` on the SAME
    `copter_takeoff` / `copter_land` YAML the single-vehicle TAKEOFF button
    runs. There is no fleet-specific takeoff logic anywhere — that is the
    single-source rule applied at fleet scale.
    """
    sup, links, events, allocation = fleet

    # -- every vehicle is distinctly addressed ---------------------------
    sysids = {vid: link.state.sysid for vid, link in links.items()}
    assert sysids == {"v1": 1, "v2": 2}, (
        f"vehicles are not distinctly addressed: {sysids}. Every command is "
        f"addressed by sysid, so duplicates would reach both.")

    # -- pre-arm gate, per vehicle ---------------------------------------
    for vehicle_id, link in links.items():
        assert _wait_prearm(link, sitl_mod.PREARM_TIMEOUT), (
            f"{vehicle_id}: pre-arm checks never passed within "
            f"{sitl_mod.PREARM_TIMEOUT:.0f}s")

    # -- take off, both, via the shipped procedure ------------------------
    results = {}
    for vehicle_id, link in links.items():
        caps = probe_capabilities(link, vehicle="ArduCopter")
        takeoff = procs.select("takeoff", caps)
        assert takeoff is not None, f"{vehicle_id}: no takeoff procedure matched"
        assert takeoff.id == "copter_takeoff", takeoff.id
        runner = ProcedureRunner(link)
        results[vehicle_id] = runner.run(takeoff, {"alt": TAKEOFF_ALT})

    for vehicle_id, result in results.items():
        assert result["outcome"] == "passed", (
            f"{vehicle_id} takeoff {result['outcome']}: {result['text']}\n"
            f"{sup.processes[vehicle_id].tail()}")

    # Both really are airborne, measured rather than acknowledged.
    for vehicle_id, link in links.items():
        assert link.state.alt > TAKEOFF_ALT * 0.8, (
            f"{vehicle_id} reported a passed takeoff at {link.state.alt:.1f} m")

    # -- land, both --------------------------------------------------------
    for vehicle_id, link in links.items():
        caps = probe_capabilities(link, vehicle="ArduCopter")
        land = procs.select("land", caps)
        assert land is not None and land.id == "copter_land"
        result = ProcedureRunner(link).run(land)
        assert result["outcome"] == "passed", (
            f"{vehicle_id} land {result['outcome']}: {result['text']}")
        assert not link.state.armed, f"{vehicle_id} is still armed after landing"

    assert sup.status == supervisor.RUN_READY, (
        f"the fleet degraded during a clean flight: {sup.status}")


def test_teardown_leaves_no_orphans_and_releases_the_lease(fleet, request):
    """Fleet acceptance criterion 6, asserted rather than assumed."""
    sup, links, events, allocation = fleet
    pids = [h.process.pid for h in sup.processes.values()]
    lease = Path(allocation.lease_path)
    assert lease.is_file()

    for link in links.values():
        link.stop()
    report = sup.stop()

    assert report.orphans == [], f"orphan processes survived teardown: {report.orphans}"
    assert report.lease_released is True
    assert not lease.exists()
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert report.clean is True


def test_each_vehicle_kept_its_own_working_directory(fleet):
    """Isolation, verified against what SITL actually wrote.

    The filesystem-level test in test_fleet_supervisor.py uses a fake process.
    This one checks that two REAL autopilots each produced their own eeprom
    and their own log, in their own directory.
    """
    sup, links, events, allocation = fleet
    dirs = {v.vehicle_id: v.work_dir for v in allocation.vehicles}
    assert dirs["v1"] != dirs["v2"]

    for vehicle_id, directory in dirs.items():
        assert (directory / "sitl.log").is_file(), f"{vehicle_id} wrote no log"
        assert (directory / "sitl_command.txt").is_file()

    # eeprom.bin is written by SITL itself once it has run.
    eeproms = {v: (d / "eeprom.bin") for v, d in dirs.items()}
    present = {v: p for v, p in eeproms.items() if p.is_file()}
    assert present, "neither vehicle wrote an eeprom; did SITL really run?"
    if len(present) == 2:
        assert eeproms["v1"].resolve() != eeproms["v2"].resolve()


def test_no_vehicle_wrote_into_the_ardupilot_tree(fleet):
    from argazui import paths

    sup, links, events, allocation = fleet
    ardupilot = paths.ARDUPILOT.resolve()
    for entry in allocation.vehicles:
        assert ardupilot not in entry.work_dir.resolve().parents, (
            f"{entry.vehicle_id} ran inside the ArduPilot checkout")


def test_separation_refuses_to_measure_without_a_shared_clock(fleet):
    """The honest-absence rule, at fleet scale.

    Two free-running SITLs carry a constant clock offset of boot-stagger x
    speedup (0.9 s at speedup 1, 4.5 s at speedup 5 — measured, see
    docs/fleet-clock-drift.md). A distance computed across that is not a
    distance, so nothing is emitted and the reason is recorded.
    """
    sup, links, events, allocation = fleet
    monitor = separation.SeparationMonitor(
        min_separation_m=5.0, time_base_valid=False,
        reason="SITL-only fleet: vehicles do not share a clock")

    fixes = [separation.Fix(vehicle_id=vid, east_m=0.0, north_m=0.0,
                            up_m=link.state.alt, t_s=time.time())
             for vid, link in links.items()]
    result = monitor.sample(fixes)

    assert result.measured is False
    assert result.pairs == []
    assert monitor.csv_rows() == [], "separation.csv was populated anyway"

    verdict = monitor.verdict()
    assert verdict["passed"] is None, (
        "an unevaluated criterion reported a verdict; None and True are the "
        "two answers this project exists to keep apart")
    assert verdict["claim"] == "no relative-geometry claim was made"


def test_the_health_monitor_reports_absent_rtf_rather_than_one(fleet):
    sup, links, events, allocation = fleet
    sample = sup.sample_health()

    assert sample["clock"]["available"] is False
    assert sample["clock"]["rtf"] is None
    for vehicle_id in links:
        assert sample["vehicles"][vehicle_id]["process_alive"] is True


def test_the_launch_transcript_records_the_exact_commands(fleet):
    """Nothing is hidden: the argv each vehicle was started with is on disk."""
    sup, links, events, allocation = fleet
    launches = [e for e in events if e["kind"] == "vehicle_launch"]
    assert len(launches) == 2
    for event in launches:
        assert "--serial0 tcp:0" in event["command"], (
            "the measured no-wait flag is missing; vehicles would block until "
            "the router connected")
        assert f"--sysid {event['sysid']}" in event["command"]
        assert "--home=" in event["command"], (
            "home must use the = form; a southern latitude in a separate argv "
            "entry is parsed as an option and SITL prints usage and exits")
        written = (allocation.for_vehicle(event["vehicle"]).work_dir
                   / "sitl_command.txt").read_text()
        assert written.strip() == event["command"].strip()
