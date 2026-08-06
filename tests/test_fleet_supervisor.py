"""L3 — supervisor logic: gates, failure policies, teardown, isolation.

Pure where it can be. These tests drive the real `FleetSupervisor` with a fake
launcher, so the staging, the gates, the policy branches and the teardown
ordering are exercised without waiting on a real autopilot. The Gazebo-free
2-vehicle flight that proves the same code against real SITL lives in
`test_fleet_sitl.py`.

WHY A FAKE LAUNCHER RATHER THAN A FAKE SUPERVISOR
-------------------------------------------------
The thing worth testing is the supervisor's own decisions: which stage runs,
what a gate does when it is not met, which branch a failure policy takes, and
what order teardown happens in. Substituting the *process* keeps all of that
real and only removes the binary. Substituting the supervisor would test a
second implementation, which is the failure this project's single-source rule
exists to prevent.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from argazui.fleet import allocator, health, separation, supervisor
from argazui.fleet import spec as fleetspec

pytestmark = pytest.mark.tier1


# --------------------------------------------------------------- fake vehicle
# A process that behaves like SITL for the two things the supervisor observes:
# it stays alive, and it opens a TCP port. Nothing else is simulated, because
# nothing else is what L3 looks at.
FAKE_SITL = """
import socket, sys, time
port = int(sys.argv[1])
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(5)
while True:
    time.sleep(0.2)
"""

NEVER_LISTENS = """
import sys, time
while True:
    time.sleep(0.2)
"""

EXITS_AT_ONCE = """
import sys
sys.exit(3)
"""


@pytest.fixture
def fake_binary(tmp_path):
    def _make(body: str, name: str) -> Path:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        return path
    return _make


def two_vehicle_spec(tmp_path) -> fleetspec.FleetSpec:
    path = tmp_path / "pair.toml"
    path.write_text("""
[fleet]
name = "pair"
formation = "line"
spacing_m = 10.0
min_separation_m = 5.0

[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0

[fleet.policy]
start = "parallel"
start_delay_s = 0.0
on_vehicle_failure = "abort_fleet"

[[vehicle]]
id = "v1"
frame = "quad"
vehicle = "ArduCopter"
sysid = 1

[[vehicle]]
id = "v2"
frame = "quad"
vehicle = "ArduCopter"
sysid = 2
""", encoding="utf-8")
    spec = fleetspec.load(path)
    fleetspec.resolve_spawns(spec)
    return spec


def build(tmp_path, fake_binary, body: str = FAKE_SITL, **kwargs):
    spec = two_vehicle_spec(tmp_path)
    for key, value in kwargs.pop("policy", {}).items():
        object.__setattr__(spec.policy, key, value)
    script = fake_binary(body, "fake_sitl.py")
    allocation = allocator.allocate(spec, "run_sup", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")

    def command_for(vehicle, entry):
        return [sys.executable, str(script), str(entry.serial0_port)]

    events = []
    sup = supervisor.FleetSupervisor(
        spec, allocation, command_for=command_for,
        on_event=events.append, **kwargs)
    return sup, events


# ------------------------------------------------------------------- staging
def test_a_sitl_only_fleet_records_the_gazebo_stages_as_skipped_not_passed(
        tmp_path, fake_binary):
    """A stage that did not run has not succeeded.

    Reporting "world generation: ok" for a fleet that generated no world is
    the same class of untruth as a green test that flew nothing.
    """
    sup, _ = build(tmp_path, fake_binary)
    try:
        sup.start()
    finally:
        sup.stop()

    by_name = {s.stage: s for s in sup.stages}
    assert by_name[supervisor.STAGE_WORLD].skipped is True
    assert by_name[supervisor.STAGE_SIM_SERVER].skipped is True
    assert by_name[supervisor.STAGE_VEHICLES].skipped is False
    assert "no world" in by_name[supervisor.STAGE_WORLD].detail


def test_the_stages_run_in_order_and_stop_at_the_first_failure(tmp_path,
                                                               fake_binary):
    sup, _ = build(tmp_path, fake_binary, body=NEVER_LISTENS)
    supervisor.TCP_GATE_S, original = 3.0, supervisor.TCP_GATE_S
    try:
        with pytest.raises(supervisor.FleetStartupError, match="SERIAL0 did not open"):
            sup.start()
    finally:
        supervisor.TCP_GATE_S = original
        sup.stop()

    names = [s.stage for s in sup.stages]
    assert names[:4] == [supervisor.STAGE_ENVIRONMENT, supervisor.STAGE_ALLOCATION,
                         supervisor.STAGE_WORLD, supervisor.STAGE_SIM_SERVER]
    assert names[-1] == supervisor.STAGE_VEHICLES
    assert sup.stages[-1].ok is False
    assert supervisor.STAGE_PREARM not in names, (
        "pre-arm was attempted after the vehicle gate failed")
    assert sup.status == supervisor.RUN_FAILED


def test_a_vehicle_that_exits_immediately_fails_the_gate_with_its_output(
        tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary, body=EXITS_AT_ONCE)
    try:
        with pytest.raises(supervisor.FleetStartupError, match="exited during startup"):
            sup.start()
    finally:
        sup.stop()


def test_a_gate_timeout_names_the_vehicle_and_the_port(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary, body=NEVER_LISTENS)
    supervisor.TCP_GATE_S, original = 2.0, supervisor.TCP_GATE_S
    try:
        with pytest.raises(supervisor.FleetStartupError) as caught:
            sup.start()
    finally:
        supervisor.TCP_GATE_S = original
        sup.stop()
    message = str(caught.value)
    assert "v1" in message
    assert str(sup.allocation.vehicles[0].serial0_port) in message


# ---------------------------------------------------------- failure policies
def _fail_one(sup, vehicle_id: str) -> None:
    """Kill one vehicle's process and let the monitor observe it."""
    sup.processes[vehicle_id].stop()
    deadline = time.time() + 10
    while time.time() < deadline:
        sup.sample_health()
        if sup.failure_actions:
            return
        time.sleep(0.2)


def test_abort_fleet_commands_the_survivors_down_and_marks_the_run_failed(
        tmp_path, fake_binary):
    """The policy must EXECUTE, not merely be configured.

    `on_abort` is the seam L4 fills with real LAND/RTL commands. Asserting on
    what it was handed is asserting that the policy ran and knew who was left.
    """
    sup, events = build(tmp_path, fake_binary,
                        policy={"on_vehicle_failure": "abort_fleet"})
    commanded = []
    sup.on_abort = commanded.append
    try:
        sup.start()
        _fail_one(sup, "v2")
    finally:
        sup.stop()

    assert sup.status == supervisor.RUN_FAILED
    action = sup.failure_actions[0]
    assert action["policy"] == "abort_fleet"
    assert action["vehicle"] == "v2"
    assert action["action"] == "command_down"
    assert action["survivors"] == ["v1"]
    assert commanded == [["v1"]], (
        "abort_fleet did not actually command the survivors down")
    assert any(e["kind"] == "fleet_abort" for e in events)


def test_continue_degraded_marks_the_vehicle_and_keeps_the_fleet_running(
        tmp_path, fake_binary):
    sup, events = build(tmp_path, fake_binary,
                        policy={"on_vehicle_failure": "continue_degraded"})
    commanded = []
    sup.on_abort = commanded.append
    try:
        sup.start()
        _fail_one(sup, "v2")
        assert sup.processes["v1"].alive(), "the surviving vehicle was stopped"
    finally:
        sup.stop()

    assert sup.status == supervisor.RUN_DEGRADED
    assert sup.degraded == ["v2"]
    assert sup.failure_actions[0]["action"] == "marked"
    assert commanded == [], "continue_degraded must not command anyone down"
    assert any(e["kind"] == "fleet_degraded" for e in events)


def test_hold_keeps_the_survivors_up_and_waits(tmp_path, fake_binary):
    sup, events = build(tmp_path, fake_binary,
                        policy={"on_vehicle_failure": "hold"})
    try:
        sup.start()
        _fail_one(sup, "v2")
        assert sup.processes["v1"].alive()
    finally:
        sup.stop()

    assert sup.status == supervisor.RUN_HELD
    assert sup.failure_actions[0]["action"] == "hold_airborne"
    assert any(e["kind"] == "fleet_hold" for e in events)


def test_a_failure_is_reported_once_not_every_monitor_tick(tmp_path, fake_binary):
    """A 1 Hz monitor must not produce one abort per second."""
    sup, _ = build(tmp_path, fake_binary,
                   policy={"on_vehicle_failure": "continue_degraded"})
    try:
        sup.start()
        _fail_one(sup, "v2")
        for _ in range(5):
            sup.sample_health()
    finally:
        sup.stop()
    assert len(sup.failure_actions) == 1, sup.failure_actions


# ----------------------------------------------------------------- teardown
def test_teardown_stops_every_vehicle_and_leaves_no_orphans(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary)
    sup.start()
    pids = [h.process.pid for h in sup.processes.values()]
    report = sup.stop()

    assert report.orphans == []
    assert report.clean is True
    assert set(report.vehicles) == {"v1", "v2"}
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_teardown_releases_the_port_lease(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary)
    sup.start()
    lease = Path(sup.allocation.lease_path)
    assert lease.is_file(), "the lease was never written"
    report = sup.stop()
    assert not lease.exists()
    assert report.lease_released is True


def test_teardown_happens_in_reverse_order(tmp_path, fake_binary):
    sup, events = build(tmp_path, fake_binary)
    sup.start()
    sup.stop()
    stopped = [e["vehicle"] for e in events if e["kind"] == "vehicle_stopped"]
    assert stopped == ["v2", "v1"], (
        "vehicles must be torn down in the reverse of the order they started")


def test_teardown_is_idempotent(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary)
    sup.start()
    sup.stop()
    second = sup.stop()
    assert second.orphans == []
    assert second.clean is True


# ------------------------------------------------------------- stale leases
def test_a_lease_whose_owner_is_gone_is_reclaimed_not_blocking(tmp_path):
    """kill -9 the supervisor, then start a new fleet.

    A run killed with SIGKILL cannot tidy up after itself, so its lease file
    stays on disk holding instances 0 and 1. If a lease were honoured purely
    because it exists, one hard kill would make the machine unusable for
    fleets until somebody deleted a file by hand.
    """
    runs = tmp_path / "runs"
    dead = runs / "dead_run"
    dead.mkdir(parents=True)
    # A PID that cannot be alive: our own child, reaped.
    corpse = subprocess.Popen([sys.executable, "-c", "pass"])
    corpse.wait()
    (dead / allocator.LEASE_FILENAME).write_text(
        '{"schema": 1, "run_id": "dead_run", "fleet": "pair", '
        f'"owner_pid": {corpse.pid}, "vehicles": ['
        '{"vehicle_id": "v1", "instance": 0}, '
        '{"vehicle_id": "v2", "instance": 1}]}', encoding="utf-8")

    held, reclaimed = allocator.held_instances(runs)
    assert held == set(), "a dead run's instances are still held"
    assert any("dead_run" in entry for entry in reclaimed)

    spec = two_vehicle_spec(tmp_path)
    fresh = allocator.allocate(spec, "new_run", runs_root=runs,
                               work_root=tmp_path / "work")
    assert [v.instance for v in fresh.vehicles] == [0, 1], (
        "the new fleet was pushed off instances 0 and 1 by a dead run's lease")
    assert any("dead_run" in entry for entry in fresh.reclaimed)


def test_a_real_sigkilled_supervisor_does_not_block_the_next_fleet(tmp_path):
    """The literal scenario: `kill -9` the supervisor, then start another fleet.

    Stronger than synthesising a dead PID, because it exercises the actual
    thing that goes wrong — a process that had no chance to run any cleanup,
    holding a lease file it wrote before dying. SIGKILL cannot be caught, so
    no amount of `finally` in the supervisor would have released it.
    """
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    marker = tmp_path / "lease_written"

    # A stand-in supervisor: writes a real lease through the real allocator,
    # then sits there until it is killed.
    script = tmp_path / "doomed_supervisor.py"
    script.write_text(f"""
import sys, time, pathlib
sys.path.insert(0, {str(Path(__file__).resolve().parent.parent / 'argazui')!r})
from argazui.fleet import allocator, spec as fleetspec
spec = fleetspec.load(pathlib.Path({str(tmp_path / 'pair.toml')!r}))
fleetspec.resolve_spawns(spec)
alloc = allocator.allocate(spec, "doomed", runs_root=pathlib.Path({str(runs)!r}),
                           work_root=pathlib.Path({str(tmp_path / 'w')!r}))
alloc.write()
pathlib.Path({str(marker)!r}).write_text(str([v.instance for v in alloc.vehicles]))
while True:
    time.sleep(0.2)
""", encoding="utf-8")

    two_vehicle_spec(tmp_path)          # writes tmp_path/pair.toml
    doomed = subprocess.Popen([sys.executable, str(script)],
                              start_new_session=True)
    try:
        deadline = time.time() + 30
        while time.time() < deadline and not marker.is_file():
            time.sleep(0.2)
        assert marker.is_file(), "the doomed supervisor never wrote its lease"
        claimed = marker.read_text()

        leases = allocator.read_leases(runs)
        assert leases and leases[0].live, "the lease is not seen as live"

        os.killpg(os.getpgid(doomed.pid), signal.SIGKILL)
        doomed.wait(timeout=10)
    finally:
        if doomed.poll() is None:                     # never leave it running
            os.killpg(os.getpgid(doomed.pid), signal.SIGKILL)
            doomed.wait(timeout=10)

    # The lease file is still on disk, and its owner is gone.
    lease_file = runs / "doomed" / allocator.LEASE_FILENAME
    assert lease_file.is_file()

    held, reclaimed = allocator.held_instances(runs)
    assert held == set(), f"a SIGKILLed run still holds {held}"
    assert any("doomed" in entry for entry in reclaimed)

    spec = two_vehicle_spec(tmp_path)
    fresh = allocator.allocate(spec, "after_kill", runs_root=runs,
                               work_root=tmp_path / "work2")
    assert str([v.instance for v in fresh.vehicles]) == claimed, (
        "the next fleet did not reuse the instances the killed run held")


def test_a_live_lease_is_honoured(tmp_path):
    """The other half: a lease whose owner IS alive must not be stolen."""
    runs = tmp_path / "runs"
    live = runs / "live_run"
    live.mkdir(parents=True)
    (live / allocator.LEASE_FILENAME).write_text(
        '{"schema": 1, "run_id": "live_run", "fleet": "pair", '
        f'"owner_pid": {os.getpid()}, "vehicles": ['
        '{"vehicle_id": "v1", "instance": 0}, '
        '{"vehicle_id": "v2", "instance": 1}]}', encoding="utf-8")

    held, reclaimed = allocator.held_instances(runs)
    assert held == {0, 1}
    assert reclaimed == []

    spec = two_vehicle_spec(tmp_path)
    fresh = allocator.allocate(spec, "new_run", runs_root=runs,
                               work_root=tmp_path / "work")
    assert 0 not in [v.instance for v in fresh.vehicles]
    assert 1 not in [v.instance for v in fresh.vehicles]


def test_the_stale_lease_file_is_not_deleted(tmp_path):
    """Reclaiming a lease must not edit the archived run it belongs to.

    The run directory is evidence of what happened. Silently removing a file
    from it to free a port would be rewriting the record.
    """
    runs = tmp_path / "runs"
    dead = runs / "dead_run"
    dead.mkdir(parents=True)
    corpse = subprocess.Popen([sys.executable, "-c", "pass"])
    corpse.wait()
    lease = dead / allocator.LEASE_FILENAME
    lease.write_text(
        '{"schema": 1, "run_id": "dead_run", "fleet": "p", '
        f'"owner_pid": {corpse.pid}, "vehicles": '
        '[{"vehicle_id": "v1", "instance": 0}]}', encoding="utf-8")

    allocator.held_instances(runs)
    assert lease.is_file(), "reclaiming a lease deleted an archived run's file"


# ------------------------------------------------- working-directory isolation
def test_each_vehicle_gets_its_own_working_directory(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary)
    try:
        sup.start()
    finally:
        sup.stop()
    dirs = {v: sup.allocation.for_vehicle(v).work_dir for v in ("v1", "v2")}
    assert dirs["v1"] != dirs["v2"]
    assert dirs["v1"].is_dir() and dirs["v2"].is_dir()
    assert dirs["v1"].name == "v1" and dirs["v2"].name == "v2"


def test_a_file_written_by_one_vehicle_is_invisible_to_the_other(tmp_path,
                                                                 fake_binary):
    """Parameter and eeprom isolation, at the filesystem level.

    Every vehicle writes `eeprom.bin`, its own dataflash logs and — for models
    that need them — its own Lua scripts. Sharing a directory is how two
    vehicles end up writing the same log and how a parameter set on one shows
    up on the other.
    """
    sup, _ = build(tmp_path, fake_binary)
    try:
        sup.start()
        v1 = sup.allocation.for_vehicle("v1").work_dir
        v2 = sup.allocation.for_vehicle("v2").work_dir
        (v1 / "eeprom.bin").write_bytes(b"vehicle-one-parameters")
        assert not (v2 / "eeprom.bin").exists(), (
            "vehicle 2 can see vehicle 1's eeprom")
        (v2 / "eeprom.bin").write_bytes(b"vehicle-two-parameters")
        assert (v1 / "eeprom.bin").read_bytes() == b"vehicle-one-parameters"
    finally:
        sup.stop()


def test_no_vehicle_writes_into_the_ardupilot_tree(tmp_path, fake_binary):
    """Working directories live under the run root, never beside the source.

    v1.0's bug: SITL run from the ArduPilot checkout left eeprom.bin, logs and
    terrain data in the source tree, so a `git status` there was never clean
    and two models overwrote each other's state.
    """
    from argazui import paths

    sup, _ = build(tmp_path, fake_binary)
    for entry in sup.allocation.vehicles:
        resolved = entry.work_dir.resolve()
        assert paths.ARDUPILOT.resolve() not in resolved.parents, (
            f"{entry.vehicle_id} would run inside the ArduPilot checkout: "
            f"{resolved}")
        assert str(resolved).startswith(str(tmp_path.resolve()))


# --------------------------------------------------------- honest absences
def test_rtf_is_reported_absent_not_fabricated(tmp_path, fake_binary):
    """There is no physics server here, so there is no real-time factor.

    Reporting 1.0 would satisfy the acceptance criterion "RTF never fell below
    the threshold" without anything having been observed.
    """
    sup, _ = build(tmp_path, fake_binary)
    try:
        sup.start()
        sample = sup.sample_health()
    finally:
        sup.stop()

    assert sample["clock"]["available"] is False
    assert sample["clock"]["rtf"] is None
    assert "no physics server" in sample["clock"]["reason"]


def test_stall_detection_reports_that_it_does_not_apply(tmp_path, fake_binary):
    sup, _ = build(tmp_path, fake_binary)
    try:
        sup.start()
        sample = sup.sample_health()
    finally:
        sup.stop()
    assert sample["stall"]["stalled"] is False
    assert "do not share a clock" in sample["stall"]["reason"]


def test_the_sources_are_pluggable_so_phase_5_can_supply_gazebo(tmp_path,
                                                                fake_binary):
    """The seam, exercised — otherwise "pluggable" is an untested claim."""
    def gazebo_like() -> health.Sample:
        return health.Sample(available=True, rtf=0.87, sim_time_s=42.5)

    sup, _ = build(tmp_path, fake_binary,
                   clock_source=health.CallableClockSource(gazebo_like, "gz"))
    try:
        sup.start()
        sample = sup.sample_health()
    finally:
        sup.stop()
    assert sample["clock"]["available"] is True
    assert sample["clock"]["rtf"] == 0.87


def test_a_source_that_raises_does_not_take_the_monitor_down(tmp_path,
                                                             fake_binary):
    def broken() -> health.Sample:
        raise RuntimeError("gz transport went away")

    sup, _ = build(tmp_path, fake_binary,
                   clock_source=health.CallableClockSource(broken, "gz"))
    try:
        sup.start()
        sample = sup.sample_health()
    finally:
        sup.stop()
    assert sample["clock"]["available"] is False
    assert "gz transport went away" in sample["clock"]["reason"]


def test_the_monitor_can_pull_heartbeat_ages_instead_of_being_pushed(
        tmp_path, fake_binary):
    """A caller that forgets to push must not make the whole fleet look dead.

    Measured during a real two-vehicle flight: the harness called
    `note_heartbeat` once at start-up and never again, so both vehicles aged
    past the 5 s limit and BOTH were reported failed when only one had been
    killed. A pull cannot be forgotten halfway through a run.
    """
    ages = {"v1": 0.1, "v2": 0.1}
    sup, _ = build(tmp_path, fake_binary,
                   policy={"on_vehicle_failure": "continue_degraded"},
                   heartbeat_ages=lambda: dict(ages))
    try:
        sup.start()
        # Nothing is ever pushed, and yet nothing is LOST.
        sample = sup.sample_health()
        assert all(v["state"] == health.VEHICLE_OK
                   for v in sample["vehicles"].values()), sample["vehicles"]
        assert sup.failure_actions == []

        # One vehicle genuinely goes quiet; only that one is accused.
        ages["v2"] = 30.0
        sample = sup.sample_health()
        assert sample["vehicles"]["v1"]["state"] == health.VEHICLE_OK
        assert sample["vehicles"]["v2"]["state"] == health.VEHICLE_LOST
        assert [a["vehicle"] for a in sup.failure_actions] == ["v2"]
    finally:
        sup.stop()
