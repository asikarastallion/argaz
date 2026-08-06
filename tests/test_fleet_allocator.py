"""L1 — instance/port allocation and leases.

These bind real sockets, which is why they are not quite "pure" — but they
start no vehicle, fork nothing and finish in milliseconds, so they belong with
the fast tier rather than with the tiers that fly.

THE FACTS BEING ASSERTED ARE MEASURED ONES
------------------------------------------
The arithmetic here is not a convention this project chose; it is what
ArduPilot does, measured on this machine and written up in
`docs/fleet-ports.md`. These tests pin the allocator to that measurement, and
the ones about `sitl_command` pin the three flags whose absence produced real,
diagnosed failures:

    --serial0 tcp:0   without it SITL blocks before boot until something
                      connects, and under lockstep that stalls the whole world
    --sysid N         without it every instance reports sysid 1
    no port overrides an explicit value equal to the compiled-in default is
                      silently re-offset by the -I handler
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from argazui.fleet import allocator, spec as fleetspec

pytestmark = pytest.mark.tier1


def two_vehicle_spec(tmp_path: Path) -> fleetspec.FleetSpec:
    path = tmp_path / "probe.toml"
    path.write_text("""
[fleet]
name = "probe"
formation = "line"
spacing_m = 10.0
min_separation_m = 5.0

[fleet.origin]
lat = -35.363262
lon = 149.165237
alt = 584.0

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
    return fleetspec.load(path)


# ------------------------------------------------------------- the arithmetic
@pytest.mark.parametrize("instance,serial0,fdm", [
    (0, 5760, 9002),
    (1, 5770, 9012),
    (2, 5780, 9022),
    (7, 5830, 9072),
])
def test_the_port_block_matches_what_ardupilot_actually_does(instance, serial0, fdm):
    """Measured with three live instances; see docs/fleet-ports.md."""
    assert allocator.serial0_port(instance) == serial0
    assert allocator.fdm_port(instance) == fdm


def test_there_is_no_third_port_in_the_block():
    """9003+10i is NOT allocated, because the JSON backend never uses it.

    SITL receives FDM state on the same unbound socket it sends from, with an
    ephemeral source port the Gazebo plugin learns per packet. An allocator
    that reserved 9003 would be reserving something nothing binds.
    """
    exported = {name for name in dir(allocator) if "port" in name.lower()}
    assert exported == {"serial0_port", "fdm_port"}, (
        f"a new port function appeared: {sorted(exported)}. If it is real, "
        f"measure it into docs/fleet-ports.md first.")


# ------------------------------------------------------------------ allocating
def test_a_fleet_gets_consecutive_instances_from_zero(tmp_path):
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "20260805T120000Z_probe",
                                    runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")
    assert [v.instance for v in allocation.vehicles] == [0, 1]
    assert [v.serial0_port for v in allocation.vehicles] == [5760, 5770]
    assert [v.fdm_port for v in allocation.vehicles] == [9002, 9012]
    assert [v.sysid for v in allocation.vehicles] == [1, 2]


def test_each_vehicle_gets_its_own_working_directory(tmp_path):
    """Shared directories are how two vehicles write the same dataflash log."""
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "run_a", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")
    dirs = [v.work_dir for v in allocation.vehicles]
    assert len(set(dirs)) == 2
    assert dirs[0].name == "v1" and dirs[0].parent.name == "run_a"


def test_the_connection_string_is_what_the_router_will_dial(tmp_path):
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "run_b", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")
    assert allocation.vehicles[1].connection == "tcp:127.0.0.1:5770"


def test_a_busy_port_is_skipped_rather_than_collided_with(tmp_path):
    """Deterministic *and* probed: instance 0 is preferred, not assumed."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        holder.bind(("127.0.0.1", allocator.serial0_port(0)))
        holder.listen(1)
        spec = two_vehicle_spec(tmp_path)
        allocation = allocator.allocate(spec, "run_c", runs_root=tmp_path / "runs",
                                        work_root=tmp_path / "work")
        assert 0 not in [v.instance for v in allocation.vehicles], \
            "instance 0's SERIAL0 port was taken and it was allocated anyway"
        assert [v.instance for v in allocation.vehicles] == [1, 2]
    finally:
        holder.close()


def test_a_busy_fdm_port_also_skips_the_instance(tmp_path):
    """Gazebo binds this one, so a free TCP port is not enough."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        holder.bind(("127.0.0.1", allocator.fdm_port(0)))
        spec = two_vehicle_spec(tmp_path)
        allocation = allocator.allocate(spec, "run_d", runs_root=tmp_path / "runs",
                                        work_root=tmp_path / "work")
        assert 0 not in [v.instance for v in allocation.vehicles]
    finally:
        holder.close()


# ---------------------------------------------------------------------- leases
def test_a_lease_records_the_owner_and_survives_a_read(tmp_path):
    spec = two_vehicle_spec(tmp_path)
    runs = tmp_path / "runs"
    allocation = allocator.allocate(spec, "run_e", runs_root=runs,
                                    work_root=tmp_path / "work")
    path = allocation.write()
    assert path.is_file()

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["owner_pid"] == os.getpid()
    assert document["run_id"] == "run_e"
    assert [v["instance"] for v in document["vehicles"]] == [0, 1]


def test_a_live_lease_holds_its_instances_against_a_second_fleet(tmp_path):
    """Two ArgazUI runs on one machine must not silently corrupt each other."""
    runs = tmp_path / "runs"
    first = allocator.allocate(two_vehicle_spec(tmp_path), "run_first",
                               runs_root=runs, work_root=tmp_path / "w1")
    first.write()

    second = allocator.allocate(two_vehicle_spec(tmp_path), "run_second",
                                runs_root=runs, work_root=tmp_path / "w2")
    assert [v.instance for v in second.vehicles] == [2, 3], (
        "the second fleet reused instances a live lease already holds")


def test_a_stale_lease_is_reclaimed_and_says_so(tmp_path):
    """A run killed with SIGKILL must not poison the next one."""
    runs = tmp_path / "runs"
    allocation = allocator.allocate(two_vehicle_spec(tmp_path), "run_dead",
                                    runs_root=runs, work_root=tmp_path / "w")
    allocation.owner_pid = _a_pid_that_is_gone()
    allocation.write()

    fresh = allocator.allocate(two_vehicle_spec(tmp_path), "run_new",
                               runs_root=runs, work_root=tmp_path / "w2")
    assert [v.instance for v in fresh.vehicles] == [0, 1], \
        "instances held only by a dead owner were not reclaimed"
    assert any("run_dead" in note for note in fresh.reclaimed), fresh.reclaimed


def test_a_stale_lease_file_is_not_deleted(tmp_path):
    """It belongs to a run directory, which is evidence, not scratch space."""
    runs = tmp_path / "runs"
    allocation = allocator.allocate(two_vehicle_spec(tmp_path), "run_dead",
                                    runs_root=runs, work_root=tmp_path / "w")
    allocation.owner_pid = _a_pid_that_is_gone()
    lease = allocation.write()
    allocator.allocate(two_vehicle_spec(tmp_path), "run_new", runs_root=runs,
                       work_root=tmp_path / "w2")
    assert lease.is_file(), "a stale lease was deleted; that edits an archived run"


def test_releasing_a_lease_frees_the_instances(tmp_path):
    runs = tmp_path / "runs"
    first = allocator.allocate(two_vehicle_spec(tmp_path), "run_one",
                               runs_root=runs, work_root=tmp_path / "w1")
    first.write()
    first.release()
    second = allocator.allocate(two_vehicle_spec(tmp_path), "run_two",
                                runs_root=runs, work_root=tmp_path / "w2")
    assert [v.instance for v in second.vehicles] == [0, 1]


def test_releasing_twice_is_not_an_error(tmp_path):
    """Teardown runs in a finally; an already-released lease is the goal."""
    allocation = allocator.allocate(two_vehicle_spec(tmp_path), "run_x",
                                    runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "w")
    allocation.write()
    allocation.release()
    allocation.release()


def test_a_corrupt_lease_file_is_ignored_not_fatal(tmp_path):
    runs = tmp_path / "runs" / "broken"
    runs.mkdir(parents=True)
    (runs / allocator.LEASE_FILENAME).write_text("{not json", encoding="utf-8")
    allocation = allocator.allocate(two_vehicle_spec(tmp_path), "run_ok",
                                    runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "w")
    assert [v.instance for v in allocation.vehicles] == [0, 1]


def _a_pid_that_is_gone() -> int:
    """A PID that certainly does not exist: one we reaped ourselves."""
    import subprocess
    dead = subprocess.Popen(["true"])
    dead.wait()
    return dead.pid


# ------------------------------------------------------------- the SITL argv
def test_the_command_carries_the_three_flags_that_were_measured(tmp_path):
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "run_argv", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "w")
    command = allocator.sitl_command(
        Path("/opt/ardupilot/arducopter"), spec.vehicles[1],
        allocation.vehicles[1], defaults=[Path("/tmp/copter.parm")])

    assert "-I1" in command
    # Without this SITL blocks before boot and stalls lockstep for everyone.
    assert command[command.index("--serial0") + 1] == "tcp:0"
    # Without this every instance reports sysid 1.
    assert command[command.index("--sysid") + 1] == "2"
    # -I derives the ports; an explicit override equal to the default is
    # silently re-offset by the -I handler, so none are passed.
    assert not any(flag in command for flag in
                   ("--sim-port-in", "--sim-port-out", "--base-port"))


def test_the_home_argument_survives_a_southern_latitude(tmp_path):
    """`--home -35.36,...` is parsed as an OPTION, not as a value.

    The SITL binary uses getopt. A value beginning with `-` in a separate argv
    entry is taken for the next flag, and the binary answers by printing its
    usage and exiting — which looks exactly like "SITL would not start" with
    no clue as to why. The `=` form is unambiguous.

    The default ArduPilot home is at latitude -35.363262, so every fleet that
    does not override it hits this.
    """
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "run_home", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "w")
    command = allocator.sitl_command(
        Path("/opt/ardupilot/arducopter"), spec.vehicles[0],
        allocation.vehicles[0], defaults=[],
        home="-35.3632620,149.1652370,584.00,0.0")

    assert "--home=-35.3632620,149.1652370,584.00,0.0" in command, command
    assert "--home" not in command, (
        "the bare flag form puts the value in its own argv entry, where a "
        "leading minus is read as the next option")
    # `--custom-location` belongs to sim_vehicle.py, not to the binary.
    assert not any(a.startswith("--custom-location") for a in command)


def test_the_command_is_pure(tmp_path):
    """A launch transcript preview must not touch the filesystem."""
    spec = two_vehicle_spec(tmp_path)
    allocation = allocator.allocate(spec, "run_pure", runs_root=tmp_path / "runs",
                                    work_root=tmp_path / "work")
    before = sorted(p.name for p in tmp_path.iterdir())
    for _ in range(3):
        allocator.sitl_command(Path("/opt/x/arducopter"), spec.vehicles[0],
                               allocation.vehicles[0], defaults=[])
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not allocation.vehicles[0].work_dir.exists(), \
        "allocation created a working directory; that belongs to the supervisor"
