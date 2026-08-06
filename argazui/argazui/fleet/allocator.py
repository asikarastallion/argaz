"""L1 — instance numbers, ports, working directories, and leases on them.

WHAT IS ACTUALLY ALLOCATED
--------------------------
One thing per vehicle: **the SITL instance number**. Every port follows from
it arithmetically, in ArduPilot's own code (`SITL_cmdline.cpp`, `case 'I'`),
so there is no freedom to allocate ports separately and pretending otherwise
would model a flexibility that does not exist. See `docs/fleet-ports.md` for
the measurement.

    instance i  ->  SERIAL0 TCP   5760 + 10*i   bound by SITL
                    FDM in  UDP   9002 + 10*i   bound by GAZEBO

There is deliberately no third port. The architecture note listed
`9003 + 10*i` as "FDM out"; measurement showed the JSON backend ignores its
inbound port entirely and receives on the same unbound socket it sends from,
with an ephemeral source port the Gazebo plugin learns per packet. Reserving
9003 would be reserving something nothing uses.

DETERMINISTIC *AND* PROBED
--------------------------
Instance `i` is derived, not searched for — a fleet of three is 0, 1, 2 and
its ports are predictable, which is what makes a run reproducible. But the
machine is shared, so before committing to `i` both of its ports are
bind-tested, and the result is written to `runs/<run_id>/ports.json` with the
owning PID. Two ArgazUI runs on one machine cannot silently corrupt each
other, and a run killed with SIGKILL does not poison the next one: a lease
whose owner PID is gone is reclaimed.

WHY A BIND TEST AND NOT A CONNECT TEST
--------------------------------------
`connect()` answers "is something listening", which is the wrong question for
the FDM port. Nothing binds `9002 + 10*i` until Gazebo starts, so a connect
test would report every instance free even while a fleet was mid-launch. The
lease file answers that half, and the bind test answers "could SITL and Gazebo
actually take these ports".
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import paths
from .spec import FleetSpec, VehicleSpec

SCHEMA_VERSION = 1

# Measured on this machine; see docs/fleet-ports.md. These are ArduPilot's
# compiled-in defaults, not a choice this project makes.
SERIAL0_BASE = 5760
FDM_BASE = 9002
INSTANCE_STRIDE = 10

# ArduPilot offsets by instance without an upper bound, but every instance
# consumes a block of ten ports and the machine has other things in it. 32 is
# well past `fleet.max_vehicles` on any host this runs on and keeps the search
# finite.
MAX_INSTANCE = 32

LEASE_FILENAME = "ports.json"


class AllocationError(RuntimeError):
    """Resources could not be allocated. Never partially applied."""


def serial0_port(instance: int) -> int:
    return SERIAL0_BASE + INSTANCE_STRIDE * instance


def fdm_port(instance: int) -> int:
    return FDM_BASE + INSTANCE_STRIDE * instance


@dataclass
class VehicleAllocation:
    """Everything one vehicle needs in order to be started."""

    vehicle_id: str
    instance: int
    sysid: int
    serial0_port: int
    fdm_port: int
    work_dir: Path
    pid: Optional[int] = None       # filled in when the process actually starts

    @property
    def connection(self) -> str:
        """The string the fleet router hands to MavlinkLink."""
        return f"tcp:127.0.0.1:{self.serial0_port}"

    def as_dict(self) -> dict:
        return {"vehicle_id": self.vehicle_id, "instance": self.instance,
                "sysid": self.sysid, "serial0_port": self.serial0_port,
                "fdm_port": self.fdm_port, "work_dir": str(self.work_dir),
                "connection": self.connection, "pid": self.pid}


@dataclass
class FleetAllocation:
    """One fleet's resources, and the lease file that records them."""

    run_id: str
    fleet: str
    vehicles: list[VehicleAllocation] = field(default_factory=list)
    owner_pid: int = field(default_factory=os.getpid)
    lease_path: Optional[Path] = None
    created_utc: str = ""
    reclaimed: list[str] = field(default_factory=list)

    def for_vehicle(self, vehicle_id: str) -> Optional[VehicleAllocation]:
        return next((v for v in self.vehicles if v.vehicle_id == vehicle_id), None)

    def as_dict(self) -> dict:
        return {"schema": SCHEMA_VERSION, "run_id": self.run_id,
                "fleet": self.fleet, "owner_pid": self.owner_pid,
                "created_utc": self.created_utc,
                "reclaimed": list(self.reclaimed),
                "vehicles": [v.as_dict() for v in self.vehicles]}

    def write(self, path: Optional[Path] = None) -> Path:
        target = Path(path or self.lease_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.as_dict(), indent=2) + "\n",
                          encoding="utf-8")
        self.lease_path = target
        return target

    def release(self) -> None:
        """Give the ports back by deleting the lease.

        Deliberately tolerant: teardown runs in a `finally`, and a lease file
        that is already gone is the desired end state, not an error.
        """
        if self.lease_path is None:
            return
        try:
            Path(self.lease_path).unlink()
        except (FileNotFoundError, OSError):
            pass


# ------------------------------------------------------------------- probing
def _bind_free(port: int, kind: int, reuse: bool, host: str = "127.0.0.1") -> bool:
    """Could a process take this port right now?

    `reuse` differs by protocol, and the difference is measured rather than
    stylistic — see `instance_free`.
    """
    probe = socket.socket(socket.AF_INET, kind)
    try:
        if reuse:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def instance_free(instance: int) -> tuple[bool, str]:
    """(free, why-not). Both ports of the block must be available.

    THE TWO PROBES USE DIFFERENT SOCKET OPTIONS, ON PURPOSE
    -------------------------------------------------------
    TCP is probed **with** `SO_REUSEADDR`, because SITL sets it and this must
    ask the question SITL will ask. It still detects a live vehicle: on Linux
    `SO_REUSEADDR` does not permit binding a port another socket is actively
    listening on (only `SO_REUSEPORT` would). Matching SITL also stops a
    lingering TIME_WAIT from an earlier teardown reading as "busy" and pushing
    every vehicle up an instance.

    UDP is probed **without** it, because with it the probe cannot detect
    anything at all. Measured on this machine:

        SO_REUSEADDR=True   second UDP bind of 127.0.0.1:19002 SUCCEEDED
        SO_REUSEADDR=False  second UDP bind refused (EADDRINUSE)

    That asymmetry is a real Linux behaviour for datagram sockets, and it has
    a sharp consequence for L2. The Gazebo plugin constructs its socket as
    `SocketUDP sock = SocketUDP(true, true)` (ArduPilotPlugin.cc:227) — that
    first `true` is `reuseaddress`. So **two vehicles sharing one
    `fdm_port_in` both bind successfully and silently split the incoming
    packets**; there is no error message and no failed bind to notice. That is
    precisely the failure the per-vehicle model materialisation exists to
    prevent, and it means detecting the collision is this allocator's job
    alone — nothing downstream will report it.
    """
    tcp = serial0_port(instance)
    udp = fdm_port(instance)
    if not _bind_free(tcp, socket.SOCK_STREAM, reuse=True):
        return False, f"TCP {tcp} (SERIAL0) is in use"
    if not _bind_free(udp, socket.SOCK_DGRAM, reuse=False):
        return False, f"UDP {udp} (FDM in) is in use"
    return True, ""


# -------------------------------------------------------------------- leases
def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # someone else's process, but it exists
    return True


@dataclass
class Lease:
    path: Path
    data: dict

    @property
    def owner_pid(self) -> Optional[int]:
        return self.data.get("owner_pid")

    @property
    def run_id(self) -> str:
        return str(self.data.get("run_id", "?"))

    @property
    def live(self) -> bool:
        return _pid_alive(self.owner_pid)

    def instances(self) -> set[int]:
        return {int(v["instance"]) for v in self.data.get("vehicles", [])
                if v.get("instance") is not None}


def read_leases(root: Optional[Path] = None) -> list[Lease]:
    """Every lease file under `root`. A malformed one is ignored, not fatal."""
    root = Path(root or paths.RUNS_DIR)
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.rglob(LEASE_FILENAME)):
        try:
            out.append(Lease(path=path,
                             data=json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return out


def held_instances(root: Optional[Path] = None) -> tuple[set[int], list[str]]:
    """(instances held by a live lease, names of the stale ones reclaimed).

    A stale lease is not deleted here. It belongs to a run directory that is
    evidence of what happened, and quietly removing a file from an archived
    run to free a port would be editing the record. It is only ignored.
    """
    held: set[int] = set()
    reclaimed: list[str] = []
    for lease in read_leases(root):
        if lease.live:
            held |= lease.instances()
        else:
            reclaimed.append(f"{lease.run_id} (owner pid "
                             f"{lease.owner_pid} is gone)")
    return held, reclaimed


# ---------------------------------------------------------------- allocation
def work_dir_for(run_id: str, vehicle_id: str,
                 root: Optional[Path] = None) -> Path:
    """`argazui/run/fleet/<run_id>/<vehicle_id>/`.

    Per vehicle, and per run, because each one needs its own `eeprom.bin`,
    its own dataflash logs and — for models that need them — its own copy of
    the Lua scripts. Sharing one directory between vehicles is how two of them
    end up writing the same log.
    """
    base = Path(root) if root else (paths.RUN_DIR / "fleet")
    return base / run_id / vehicle_id


def allocate(spec: FleetSpec, run_id: str, runs_root: Optional[Path] = None,
             work_root: Optional[Path] = None,
             lease_path: Optional[Path] = None) -> FleetAllocation:
    """Assign an instance block to every vehicle, or raise having assigned none.

    All-or-nothing on purpose: a fleet that got three of its four vehicles
    allocated is not a smaller fleet, it is a failed launch, and leaving a
    partial lease behind would make the next attempt fail too.
    """
    held, reclaimed = held_instances(runs_root)

    allocation = FleetAllocation(
        run_id=run_id, fleet=spec.name, reclaimed=reclaimed,
        created_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    taken: set[int] = set(held)
    refused: list[str] = []

    for vehicle in spec.vehicles:
        instance = _next_instance(taken, refused)
        if instance is None:
            raise AllocationError(
                f"no free SITL instance for {vehicle.id!r} below {MAX_INSTANCE}. "
                + (f"Refused: {'; '.join(refused[-6:])}. " if refused else "")
                + (f"Held by live runs: {sorted(held)}." if held else ""))
        taken.add(instance)
        allocation.vehicles.append(VehicleAllocation(
            vehicle_id=vehicle.id,
            instance=instance,
            sysid=vehicle.sysid,
            serial0_port=serial0_port(instance),
            fdm_port=fdm_port(instance),
            work_dir=work_dir_for(run_id, vehicle.id, work_root)))

    if lease_path is None:
        lease_path = Path(runs_root or paths.RUNS_DIR) / run_id / LEASE_FILENAME
    allocation.lease_path = Path(lease_path)
    return allocation


def _next_instance(taken: set[int], refused: list[str]) -> Optional[int]:
    for instance in range(MAX_INSTANCE):
        if instance in taken:
            continue
        free, why = instance_free(instance)
        if free:
            return instance
        refused.append(f"instance {instance}: {why}")
        taken.add(instance)          # do not probe it again for this fleet
    return None


def sitl_command(binary: Path, vehicle: VehicleSpec,
                 allocation: VehicleAllocation, defaults: list[Path],
                 model: str = "quad", speedup: float = 1.0,
                 home: Optional[str] = None) -> list[str]:
    """The exact argv for one vehicle. Pure — builds a list, touches nothing.

    Three choices here are measurements rather than preferences, all recorded
    in docs/fleet-ports.md:

    `--serial0 tcp:0`  removes the `:wait` in SITL's default `tcp:0:wait`.
        With the default, a vehicle does not load parameters, set home or emit
        a single FDM packet until something connects to its SERIAL0 — and
        under lockstep one unattached vehicle stalls sim time for the whole
        world. Booting each vehicle independently of the router is what makes
        the readiness gates per-vehicle rather than serialised.

    `--sysid N`  because `-I` does NOT set the sysid. Three instances launched
        without it all report sysid 1, and every "addressed" command would
        reach all of them.

    no port overrides  because `-I` derives them, and an explicit override
        equal to the compiled-in default is silently re-offset by the `-I`
        handler. Deriving is the only style with no ordering hazard.

    `--home=<value>`  is the binary's own flag, and it is written with an `=`.
        Two separate traps, both hit during the Phase 2 hand-run:

        * `--custom-location` belongs to **sim_vehicle.py**, not to the SITL
          binary. The architecture note names it because that is what a person
          types; the fleet path launches the binary directly, and the binary
          calls it `--home|-O`.
        * the value starts with a minus for any southern latitude, and
          ArduPilot parses its command line with getopt. `--home -35.36,...`
          puts the value in its own argv entry, where the leading `-` is read
          as the next option — SITL prints its usage and exits. The failure
          presents as "SITL would not start" with the reason buried in a
          200-line usage dump. The `=` form is unambiguous.
    """
    command = [str(binary),
               "--model", model,
               "--speedup", str(speedup),
               f"-I{allocation.instance}",
               "--serial0", "tcp:0",
               "--sysid", str(allocation.sysid),
               "-w"]
    if defaults:
        command += ["--defaults", ",".join(str(p) for p in defaults)]
    if home:
        command.append(f"--home={home}")
    return command
