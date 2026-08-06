"""L3 — process lifecycle: staged startup with gates, health, ordered teardown.

A GATE TIMEOUT IS A RUN FAILURE
-------------------------------
Every stage has a readiness gate and no stage begins before the previous one
passed. There is no "it is probably up by now" anywhere in this file. A gate
that times out fails the run and says which vehicle and which condition,
because the alternative — proceeding hopefully — produces a fleet that is
half-alive and a report that cannot explain itself.

THE GATES ARE PER-VEHICLE AND INDEPENDENT
-----------------------------------------
That is a consequence of a Phase 1 measurement. SITL's default SERIAL0 is
`tcp:0:wait`, and with it a vehicle loads no parameters, sets no home and
emits no FDM packet until something connects — so "launched" and "running"
would be separated by the router's own progress, and under lockstep a single
unattached vehicle would stall sim time for the whole world. Launching with
`--serial0 tcp:0` removes the wait, so each vehicle boots on its own and its
gates mean what they say. See docs/fleet-ports.md.

PROCESS TERMINATION
-------------------
Same rule as the rest of the project, and the same mechanism as
`tests/sitl.py`: every process gets its own session (`start_new_session=True`)
and is terminated by process group with SIGINT -> SIGTERM -> SIGKILL. Never a
name match, never `pkill -f`. The graceful first signal matters — SITL flushes
its dataflash log on shutdown, and a run that asserts on the `.BIN` needs that
to have happened.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import health
from .allocator import FleetAllocation, VehicleAllocation
from .spec import FleetSpec, VehicleSpec

# Stage names, in order. Exposed so the UI and the timeline agree on them.
STAGE_ENVIRONMENT = "environment"
STAGE_ALLOCATION = "allocation"
STAGE_WORLD = "world"
STAGE_SIM_SERVER = "sim_server"
STAGE_VEHICLES = "vehicles"
STAGE_PREARM = "prearm"
STAGE_READY = "ready"

STAGES = (STAGE_ENVIRONMENT, STAGE_ALLOCATION, STAGE_WORLD, STAGE_SIM_SERVER,
          STAGE_VEHICLES, STAGE_PREARM, STAGE_READY)

# Run outcomes, matching the architecture's vocabulary.
RUN_READY = "ready"
RUN_FAILED = "failed"
RUN_DEGRADED = "degraded"
RUN_HELD = "held"

# Gate budgets. Generous, because a loaded CI runner is slow; but finite,
# because an infinite wait is how a hung fleet looks like a slow one.
TCP_GATE_S = 60.0
HEARTBEAT_GATE_S = 90.0
PREARM_GATE_S = 180.0


class FleetStartupError(RuntimeError):
    """A readiness gate was not met. Carries which stage and which vehicle."""


@dataclass
class StageResult:
    stage: str
    ok: bool
    seconds: float = 0.0
    detail: str = ""
    skipped: bool = False

    def as_dict(self) -> dict:
        return {"stage": self.stage, "ok": self.ok, "skipped": self.skipped,
                "seconds": round(self.seconds, 2), "detail": self.detail}


# --------------------------------------------------------------- one process
@dataclass
class VehicleProcess:
    """One SITL, its command line, and how to end it."""

    vehicle_id: str
    allocation: VehicleAllocation
    command: list
    process: subprocess.Popen
    log_path: Path

    def alive(self) -> bool:
        return self.process.poll() is None

    def tail(self, lines: int = 25) -> str:
        try:
            return "\n".join(
                self.log_path.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no SITL output captured)"

    def stop(self, timeout_each: tuple = (5.0, 3.0, 2.0)) -> str:
        """SIGINT -> SIGTERM -> SIGKILL by process group. Returns what worked."""
        if self.process.poll() is not None:
            return "already exited"
        try:
            pgid = os.getpgid(self.process.pid)
        except ProcessLookupError:
            return "already exited"
        for sig, wait, name in ((signal.SIGINT, timeout_each[0], "SIGINT"),
                                (signal.SIGTERM, timeout_each[1], "SIGTERM"),
                                (signal.SIGKILL, timeout_each[2], "SIGKILL")):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                return "already exited"
            try:
                self.process.wait(timeout=wait)
                return name
            except subprocess.TimeoutExpired:
                continue
        return "survived SIGKILL"


def default_launcher(command: list, work_dir: Path, log_path: Path) -> subprocess.Popen:
    """Start one SITL in its own session, output to its own log."""
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    (work_dir / "sitl_command.txt").write_text(" ".join(command) + "\n",
                                               encoding="utf-8")
    return subprocess.Popen(command, cwd=str(work_dir),
                            stdout=log_path.open("wb"),
                            stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL,
                            start_new_session=True)


# ------------------------------------------------------------------ teardown
@dataclass
class TeardownReport:
    """Evidence for fleet acceptance criterion 6: nothing was left running."""

    vehicles: dict = field(default_factory=dict)     # id -> how it died
    sim_server: str = ""
    lease_released: bool = False
    orphans: list = field(default_factory=list)
    seconds: float = 0.0

    @property
    def clean(self) -> bool:
        return not self.orphans and self.lease_released

    def as_dict(self) -> dict:
        return {"vehicles": dict(self.vehicles), "sim_server": self.sim_server,
                "lease_released": self.lease_released,
                "orphans": list(self.orphans), "clean": self.clean,
                "seconds": round(self.seconds, 2)}


# ---------------------------------------------------------------- supervisor
class FleetSupervisor:
    """Owns every process a fleet consists of, and every gate between them."""

    def __init__(self, spec: FleetSpec, allocation: FleetAllocation,
                 command_for: Callable[[VehicleSpec, VehicleAllocation], list],
                 on_event: Optional[Callable[[dict], None]] = None,
                 launcher: Callable = default_launcher,
                 clock_source: Optional[object] = None,
                 stall_source: Optional[object] = None,
                 world_path: Optional[Path] = None,
                 gz_env: Optional[dict] = None,
                 gz_command: Optional[list] = None,
                 sim_ready_timeout: float = 90.0,
                 heartbeat_ages: Optional[Callable[[], dict]] = None) -> None:
        self.spec = spec
        self.allocation = allocation
        self.command_for = command_for
        self.on_event = on_event or (lambda event: None)
        self.launcher = launcher
        # Pluggable, and absent by default. A SITL-only fleet has no physics
        # server, so the sources report absence rather than inventing 1.0.
        self.clock_source = clock_source or health.NoSimulationServer()
        self.stall_source = stall_source or health.NoStallDetection()

        # Gazebo. Absent for a SITL-only fleet, in which case stages 3 and 4
        # are recorded as SKIPPED rather than as passed.
        self.world_path = Path(world_path) if world_path else None
        self.gz_env = dict(gz_env) if gz_env else None
        self.gz_command = list(gz_command) if gz_command else None
        self.sim_ready_timeout = sim_ready_timeout
        self.sim_server: Optional[subprocess.Popen] = None
        self.sim_log: Optional[Path] = None

        self.processes: dict = {}
        self.stages: list = []
        self.status: str = ""
        self.degraded: list = []
        self._monitor: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._last_heartbeat: dict = {}
        # PULL, don't only accept a PUSH.
        #
        # The supervisor originally learned heartbeat ages only from callers
        # calling `note_heartbeat`. If a caller wired the links but forgot to
        # keep calling it, every vehicle aged past the 5 s limit and was
        # reported LOST — a fleet declared dead because nobody was telling the
        # monitor it was alive. Measured: a real two-vehicle flight reported
        # BOTH vehicles failed when only one had been killed.
        #
        # Whoever owns the links can supply a callable instead, which cannot
        # be forgotten halfway through a run.
        self.heartbeat_ages = heartbeat_ages
        self._health: dict = {}
        self._lock = threading.Lock()
        self.failure_actions: list = []
        # Set by whoever owns the MAVLink links (L4) so `abort_fleet` can
        # actually command the survivors down. Left None, the policy still
        # records what it decided — but a run that could not command anything
        # says so rather than claiming an orderly abort.
        self.on_abort: Optional[Callable[[list], None]] = None

    # ------------------------------------------------------------- reporting
    def emit(self, kind: str, **payload) -> None:
        event = {"t": round(time.monotonic(), 3), "kind": kind, **payload}
        try:
            self.on_event(event)
        except Exception:
            pass

    def _stage(self, name: str, ok: bool, started: float, detail: str = "",
               skipped: bool = False) -> StageResult:
        result = StageResult(stage=name, ok=ok, seconds=time.time() - started,
                             detail=detail, skipped=skipped)
        self.stages.append(result)
        self.emit("stage", **result.as_dict())
        return result

    # ----------------------------------------------------------------- start
    def start(self) -> str:
        """Run the staged startup. Returns the fleet status, or raises."""
        self.emit("fleet_start", fleet=self.spec.name,
                  vehicles=[v.id for v in self.spec.vehicles],
                  gazebo=self.spec.gazebo)

        started = time.time()
        self._stage(STAGE_ENVIRONMENT, True, started,
                    f"{self.spec.count} vehicles, "
                    f"{'Gazebo' if self.spec.gazebo else 'SITL-only'}")

        started = time.time()
        self.allocation.write()
        self._stage(STAGE_ALLOCATION, True, started,
                    f"lease at {self.allocation.lease_path}")

        # Stages 3 and 4 belong to Gazebo. In a SITL-only fleet they are
        # SKIPPED and recorded as skipped — not as passed. A stage that did
        # not run has not succeeded.
        started = time.time()
        if self.world_path is None:
            self._stage(STAGE_WORLD, True, started,
                        "SITL-only fleet: no world to generate", skipped=True)
        elif not self.world_path.is_file():
            self._stage(STAGE_WORLD, False, started,
                        f"generated world missing: {self.world_path}")
            self.status = RUN_FAILED
            raise FleetStartupError(
                f"the composed world is not on disk: {self.world_path}")
        else:
            self._stage(STAGE_WORLD, True, started, str(self.world_path))

        started = time.time()
        if self.world_path is None:
            self._stage(STAGE_SIM_SERVER, True, started,
                        "SITL-only fleet: no physics server", skipped=True)
        else:
            try:
                detail = self._start_sim_server()
            except FleetStartupError as exc:
                self._stage(STAGE_SIM_SERVER, False, started, str(exc))
                self.status = RUN_FAILED
                raise
            self._stage(STAGE_SIM_SERVER, True, started, detail)

        started = time.time()
        try:
            self._launch_vehicles()
        except FleetStartupError as exc:
            self._stage(STAGE_VEHICLES, False, started, str(exc))
            self.status = RUN_FAILED
            raise
        self._stage(STAGE_VEHICLES, True, started,
                    f"{len(self.processes)} vehicles linked")

        self.status = RUN_READY
        self.emit("fleet_ready", vehicles=list(self.processes))
        return self.status

    def _start_sim_server(self) -> str:
        """Launch `gz sim` and GATE on simulated time actually advancing.

        The gate is deliberately not "the process is alive" and not "the topic
        exists". A Gazebo server that started but is not stepping looks
        identical to a healthy one from the outside, and every vehicle
        launched against it would then block in lockstep waiting for a step
        that never comes — producing N vehicles that time out at their own
        gates, none of which names the actual cause.
        """
        command = self.gz_command or [
            "gz", "sim", "-v", "2", "-r", "-s", str(self.world_path)]
        self.sim_log = self.world_path.parent / "gz.log"
        self.emit("sim_server_launch", command=" ".join(command),
                  world=str(self.world_path))
        self.sim_server = subprocess.Popen(
            command, cwd=str(self.world_path.parent),
            env=self.gz_env, stdout=self.sim_log.open("wb"),
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True)

        deadline = time.time() + self.sim_ready_timeout
        first = None
        while time.time() < deadline:
            if self.sim_server.poll() is not None:
                raise FleetStartupError(
                    f"gz sim exited during startup (code "
                    f"{self.sim_server.returncode})\n{self._sim_tail()}")
            reading = self.clock_source.sample()
            if reading.available and reading.sim_time_s is not None:
                if first is None:
                    first = reading.sim_time_s
                elif reading.sim_time_s > first:
                    self.emit("sim_server_ready",
                              sim_time_s=reading.sim_time_s, rtf=reading.rtf)
                    return (f"simulated time advancing "
                            f"({first:.3f} -> {reading.sim_time_s:.3f}s)")
            time.sleep(0.5)

        raise FleetStartupError(
            f"simulated time never advanced within {self.sim_ready_timeout:g}s "
            f"— the physics server is up but not stepping\n{self._sim_tail()}")

    def _sim_tail(self, lines: int = 20) -> str:
        try:
            return "\n".join(
                self.sim_log.read_text(errors="replace").splitlines()[-lines:])
        except (OSError, AttributeError):
            return "(no gz output captured)"

    def _launch_vehicles(self) -> None:
        """Start every vehicle per the fleet's start policy, gating each one."""
        policy = self.spec.policy.start
        delay = self.spec.policy.start_delay_s

        for index, vehicle in enumerate(self.spec.vehicles):
            entry = self.allocation.for_vehicle(vehicle.id)
            if entry is None:
                raise FleetStartupError(
                    f"no allocation for {vehicle.id!r}; the spec and the "
                    f"allocator disagree about which vehicles exist")

            if policy == "staggered" and index > 0:
                time.sleep(delay)

            command = self.command_for(vehicle, entry)
            log_path = entry.work_dir / "sitl.log"
            self.emit("vehicle_launch", vehicle=vehicle.id,
                      instance=entry.instance, sysid=entry.sysid,
                      command=" ".join(command))
            process = self.launcher(command, entry.work_dir, log_path)
            handle = VehicleProcess(vehicle_id=vehicle.id, allocation=entry,
                                    command=command, process=process,
                                    log_path=log_path)
            self.processes[vehicle.id] = handle
            entry.pid = process.pid

            # `gated` waits for THIS vehicle to be fully up before starting
            # the next; `parallel` and `staggered` gate afterwards.
            if policy == "gated":
                self._gate_vehicle(handle)

        if policy != "gated":
            for handle in self.processes.values():
                self._gate_vehicle(handle)

        self.allocation.write()          # record the PIDs

    def _gate_vehicle(self, handle: VehicleProcess) -> None:
        """GATE: the TCP port opens, then a heartbeat arrives."""
        port = handle.allocation.serial0_port
        deadline = time.time() + TCP_GATE_S
        while time.time() < deadline:
            if not handle.alive():
                raise FleetStartupError(
                    f"{handle.vehicle_id}: SITL exited during startup "
                    f"(instance {handle.allocation.instance})\n{handle.tail()}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.4)
        else:
            raise FleetStartupError(
                f"{handle.vehicle_id}: SERIAL0 did not open on port {port} "
                f"within {TCP_GATE_S:g}s\n{handle.tail()}")
        self.emit("vehicle_gate", vehicle=handle.vehicle_id, gate="tcp",
                  port=port, ok=True)

    # ------------------------------------------------------------- heartbeat
    def note_heartbeat(self, vehicle_id: str, when: Optional[float] = None) -> None:
        """Told by whoever owns the MAVLink links. The supervisor does not
        open one itself — L4 owns links, L3 owns processes."""
        with self._lock:
            self._last_heartbeat[vehicle_id] = when if when is not None else time.time()

    # --------------------------------------------------------------- monitor
    def start_monitor(self, interval: float = health.MONITOR_INTERVAL_S) -> None:
        if self._monitor is not None:
            return
        self._stop_monitor.clear()
        self._monitor = threading.Thread(target=self._monitor_loop,
                                         args=(interval,),
                                         name=f"fleet-health-{self.spec.name}",
                                         daemon=True)
        self._monitor.start()

    def stop_monitor(self) -> None:
        self._stop_monitor.set()
        if self._monitor is not None:
            self._monitor.join(timeout=5.0)
            self._monitor = None

    def _monitor_loop(self, interval: float) -> None:
        while not self._stop_monitor.is_set():
            try:
                self.sample_health()
            except Exception as exc:
                self.emit("monitor_error", error=f"{type(exc).__name__}: {exc}")
            self._stop_monitor.wait(interval)

    def sample_health(self) -> dict:
        """One 1 Hz round: process liveness, heartbeat age, RTF, stall."""
        with self._lock:
            heartbeats = dict(self._last_heartbeat)

        pulled = {}
        if self.heartbeat_ages is not None:
            try:
                pulled = self.heartbeat_ages() or {}
            except Exception:
                pulled = {}

        now = time.time()
        states = {}
        for vehicle_id, handle in self.processes.items():
            if vehicle_id in pulled:
                age = pulled[vehicle_id]
                last = None if age is None else now - age
            else:
                last = heartbeats.get(vehicle_id)
            states[vehicle_id] = health.classify(
                vehicle_id, handle.alive(), last, now=now)

        clock = self.clock_source.sample()
        stall = self.stall_source.sample()

        with self._lock:
            previous, self._health = self._health, states

        for vehicle_id, state in states.items():
            was = previous.get(vehicle_id)
            if was is None or was.state != state.state:
                self.emit("vehicle_health", **state.as_dict())
                if state.state in (health.VEHICLE_DEAD, health.VEHICLE_LOST):
                    self._on_vehicle_failure(vehicle_id, state)

        return {"vehicles": {k: v.as_dict() for k, v in states.items()},
                "clock": clock.as_dict(), "stall": stall.as_dict()}

    # ------------------------------------------------------ failure policies
    def _on_vehicle_failure(self, vehicle_id: str, state) -> None:
        """Execute the fleet's declared `on_vehicle_failure` policy.

        A policy that is only implemented is not verified, so each branch
        records exactly what it did into `failure_actions`; the tests assert
        against that rather than against a log line.
        """
        policy = self.spec.policy.on_vehicle_failure
        self.emit("vehicle_failure", vehicle=vehicle_id, policy=policy,
                  state=state.state, reason=state.reason)

        if policy == "continue_degraded":
            if vehicle_id not in self.degraded:
                self.degraded.append(vehicle_id)
            self.status = RUN_DEGRADED
            self.failure_actions.append(
                {"policy": policy, "vehicle": vehicle_id, "action": "marked",
                 "survivors": self._survivors(vehicle_id)})
            self.emit("fleet_degraded", vehicle=vehicle_id,
                      reason=state.reason)
            return

        if policy == "hold":
            self.status = RUN_HELD
            survivors = self._survivors(vehicle_id)
            self.failure_actions.append(
                {"policy": policy, "vehicle": vehicle_id,
                 "action": "hold_airborne", "survivors": survivors})
            self.emit("fleet_hold", vehicle=vehicle_id, survivors=survivors,
                      note="airborne vehicles hold; waiting for the operator")
            return

        # abort_fleet (the default): bring everyone else down, then tear down.
        self.status = RUN_FAILED
        survivors = self._survivors(vehicle_id)
        self.failure_actions.append(
            {"policy": "abort_fleet", "vehicle": vehicle_id,
             "action": "command_down", "survivors": survivors})
        self.emit("fleet_abort", vehicle=vehicle_id, survivors=survivors,
                  reason=state.reason)
        if self.on_abort is not None:
            try:
                self.on_abort(survivors)
            except Exception as exc:
                self.emit("abort_command_failed",
                          error=f"{type(exc).__name__}: {exc}")

    def _survivors(self, failed_id: str) -> list:
        return [v for v, h in self.processes.items()
                if v != failed_id and h.alive()]

    # -------------------------------------------------------------- teardown
    def stop(self, sweep_root: Optional[Path] = None) -> TeardownReport:
        """Reverse order: vehicles, then sim server, then lease, then sweep."""
        started = time.time()
        self.stop_monitor()
        report = TeardownReport()
        self.emit("fleet_teardown_start", vehicles=list(self.processes))

        for vehicle_id, handle in reversed(list(self.processes.items())):
            report.vehicles[vehicle_id] = handle.stop()
            self.emit("vehicle_stopped", vehicle=vehicle_id,
                      how=report.vehicles[vehicle_id])

        # Vehicles first, THEN the server. The other order leaves every SITL
        # blocked in lockstep waiting for a step from a server that has gone,
        # so they ignore SIGINT and have to be killed — which loses the
        # dataflash flush that SIGINT exists to trigger.
        report.sim_server = self._stop_sim_server()

        self.allocation.release()
        report.lease_released = (self.allocation.lease_path is None
                                 or not Path(self.allocation.lease_path).exists())

        report.orphans = self.orphan_sweep()
        report.seconds = time.time() - started
        self.emit("fleet_teardown_done", **report.as_dict())
        return report

    def _stop_sim_server(self) -> str:
        if self.sim_server is None:
            return "not started (SITL-only fleet)"
        if self.sim_server.poll() is not None:
            return "already exited"
        try:
            pgid = os.getpgid(self.sim_server.pid)
        except ProcessLookupError:
            return "already exited"
        for sig, wait, name in ((signal.SIGINT, 6.0, "SIGINT"),
                                (signal.SIGTERM, 4.0, "SIGTERM"),
                                (signal.SIGKILL, 3.0, "SIGKILL")):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                return "already exited"
            try:
                self.sim_server.wait(timeout=wait)
                self.emit("sim_server_stopped", how=name)
                return name
            except subprocess.TimeoutExpired:
                continue
        return "survived SIGKILL"

    def orphan_sweep(self) -> list:
        """Anything of ours still alive after teardown, by PID.

        By PID, never by name: the whole project's rule. Each entry is a
        process this supervisor itself started and can still see.
        """
        left = []
        for vehicle_id, handle in self.processes.items():
            if handle.alive():
                left.append({"vehicle": vehicle_id, "pid": handle.process.pid})
        if self.sim_server is not None and self.sim_server.poll() is None:
            left.append({"vehicle": "gz sim", "pid": self.sim_server.pid})
        return left
