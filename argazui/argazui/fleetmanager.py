"""The server-side owner of a fleet run, for the Fleet tab.

WHY THIS IS A SEPARATE CLASS FROM `Manager`
-------------------------------------------
`app.Manager` owns the single-vehicle path — two terminals, one MAVLink link,
one run recorder. v1.3's first rule is that path does not change, so the fleet
does not reach into it. This class owns its own supervisor, its own links and
its own router, and the two share nothing but the process they run in.

WHAT THE INTERFACE IS ALLOWED TO SAY
------------------------------------
Everything this returns is either measured or explicitly absent with a reason.
There is no field that reports a plausible number when nothing was observed —
`separation` and `rtf` both carry `measured: false` and a `reason` when they
cannot speak, and the page renders that reason rather than a dash.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import paths
from .fleet import (allocator, artifacts, criteria, eventbus, gzstats,
                    outcomes, router, separation, supervisor, wiring)
from .fleet import report as fleetreport
from .fleet import spec as fleetspec
from .fleet import world as worldlib
from .mavlink_link import MavlinkLink

# How long a vehicle may be silent before the grid calls its link stale. Same
# 5 s the health monitor uses, kept in one place so the card and the monitor
# cannot disagree.
from .fleet.health import HEARTBEAT_LOST_S


class FleetManager:
    """One fleet at a time: validate, start, command, observe, stop."""

    def __init__(self, on_log: Optional[Callable[[str], None]] = None,
                 on_event: Optional[Callable[[dict], None]] = None) -> None:
        self.on_log = on_log or (lambda text: None)
        self.on_event = on_event or (lambda event: None)
        self.lock = threading.RLock()

        self.spec: Optional[fleetspec.FleetSpec] = None
        self.sup: Optional[supervisor.FleetSupervisor] = None
        self.rt: Optional[router.FleetRouter] = None
        self.links: dict = {}
        self.allocation = None
        self.composed = None
        self.bus: Optional[eventbus.EventBus] = None
        self.run_dir: Optional[Path] = None
        self.run_id: str = ""
        self.starting = False
        self.error: str = ""
        self.launch_transcript: list = []

        self.separation: Optional[separation.SeparationMonitor] = None
        self.separation_reason: str = ""
        self._rtf_samples: list = []
        self._sep_started: Optional[float] = None
        self._monitor: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()

        # Exactly one interactive MAVProxy, for the focused vehicle. N
        # vehicles do NOT get N consoles: that is N processes and N terminals
        # for a fleet the operator watches through the grid.
        self.console_vehicle: str = ""
        self.console_process = None

    # ----------------------------------------------------------- inventory
    def fleets(self) -> list:
        """Every spec with its validation badge, and the reason when it fails."""
        out = []
        for name in fleetspec.available():
            entry = {"name": name, "ok": False, "errors": [], "warnings": [],
                     "notes": [], "vehicles": 0, "gazebo": False,
                     "description": ""}
            try:
                result = fleetspec.validate_by_name(name)
            except fleetspec.FleetSpecError as exc:
                entry["errors"] = [str(exc)]
                out.append(entry)
                continue
            entry.update(ok=result.ok, errors=list(result.errors),
                         warnings=list(result.warnings),
                         notes=list(result.notes),
                         vehicles=result.spec.count,
                         gazebo=result.spec.gazebo,
                         description=result.spec.description)
            out.append(entry)
        return out

    # --------------------------------------------------------------- start
    def start(self, name: str) -> dict:
        with self.lock:
            if self.sup is not None or self.starting:
                return {"ok": False, "text": "a fleet is already running; "
                                             "stop it first"}
            self.starting = True
            self.error = ""
            self.launch_transcript = []

        thread = threading.Thread(target=self._start, args=(name,),
                                  name=f"fleet-start-{name}", daemon=True)
        thread.start()
        return {"ok": True, "text": f"starting fleet {name}"}

    def _transcript(self, line: str) -> None:
        self.launch_transcript.append(line)
        self.on_log(line)

    def _start(self, name: str) -> None:
        try:
            spec = fleetspec.load_by_name(name)
            result = fleetspec.validate(spec)
            if not result.ok:
                # Validation failing here is not a bug — it is the L0 gate
                # doing its job before a single process exists. The reason
                # goes straight to the page.
                raise RuntimeError("; ".join(result.errors))
            self.spec = spec
            self._bring_up()
        except Exception as exc:
            with self.lock:
                self.starting = False
                self.error = f"{type(exc).__name__}: {exc}"
            self._transcript(f"# fleet failed to start: {exc}")
            try:
                self.stop()
            except Exception:
                pass

    def _bring_up(self) -> None:
        spec = self.spec
        binary, defaults, model_arg, base_model, base_world = _resolve_launch(spec)

        self.run_id = (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                       + f"_fleet_{spec.name}")
        self.run_dir = paths.RUNS_DIR / self.run_id
        self.allocation = allocator.allocate(
            spec, self.run_id, runs_root=paths.RUNS_DIR,
            work_root=paths.RUN_DIR / "fleet")
        self.bus = eventbus.EventBus(sink=lambda e: self.on_event(e.as_dict()))

        env = None
        world_path = None
        if spec.gazebo:
            self.composed = worldlib.compose(
                spec, self.allocation, base_world, base_model, self.run_dir,
                gazebo_model_name=base_model.name)
            world_path = self.composed.world_path
            env = os.environ.copy()
            env["GZ_SIM_RESOURCE_PATH"] = worldlib.resource_path(
                self.composed, ":".join(filter(None, [
                    str(paths.SITL_MODELS / "Gazebo" / "models"),
                    str(paths.SITL_MODELS / "Gazebo" / "worlds"),
                    env.get("GZ_SIM_RESOURCE_PATH", "")])))
            self._transcript(f"# generated world: {world_path}")

        def command_for(vehicle, entry):
            entry.work_dir.mkdir(parents=True, exist_ok=True)
            command = allocator.sitl_command(
                binary, vehicle, entry, defaults, model=model_arg, speedup=1.0,
                home=worldlib.home_for_vehicle(spec, vehicle.id))
            self._transcript(" ".join(command))
            return command

        clock = (gzstats.GazeboStats() if spec.gazebo
                 else None)
        self.sup = supervisor.FleetSupervisor(
            spec, self.allocation, command_for=command_for,
            on_event=lambda e: self.bus.emit(
                e.get("kind", "event"),
                **{k: v for k, v in e.items() if k not in ("kind", "t")}),
            clock_source=clock, world_path=world_path, gz_env=env,
            heartbeat_ages=self._heartbeat_ages)
        if spec.gazebo:
            if world_path:
                self._transcript(f"gz sim -v 2 -r -s {world_path}")
        self.sup.start()

        if spec.gazebo:
            self.sup.stall_source = gzstats.LockstepStallDetector(
                clock,
                processes={v: h.process.pid
                           for v, h in self.sup.processes.items()},
                sim_server_pid=(self.sup.sim_server.pid
                                if self.sup.sim_server else None),
                heartbeat_ages=self._heartbeat_ages)

        for vehicle in spec.vehicles:
            entry = self.allocation.for_vehicle(vehicle.id)
            link = MavlinkLink(connection=entry.connection,
                               mirror_port=paths.PLOTJUGGLER_PORT,
                               mirror_namespace=vehicle.id)
            link.start(vehicle=(vehicle.vehicle or "ArduCopter"))
            self.links[vehicle.id] = link
        for vehicle_id, link in self.links.items():
            link.wait_ready(timeout=150)
            self.sup.note_heartbeat(vehicle_id)

        self.rt = router.FleetRouter(spec, self.links, bus=self.bus)
        self.sup.on_abort = lambda survivors: self.rt.abort(survivors,
                                                           mode="LAND")

        # Separation may speak only under Gazebo, and only because the world
        # pose message is one world state at one instant. See
        # docs/fleet-clock-drift.md — this is not "Gazebo is running".
        if spec.gazebo:
            self.separation = separation.SeparationMonitor(
                spec.min_separation_m, time_base_valid=True)
            self.separation_reason = ""
        else:
            self.separation_reason = (
                "SITL-only fleet: the vehicles do not share a clock, so two "
                "positions carry no common time base and a distance computed "
                "across them would not be a distance "
                "(docs/fleet-clock-drift.md)")
            self.separation = separation.SeparationMonitor(
                spec.min_separation_m, time_base_valid=False,
                reason=self.separation_reason)

        with self.lock:
            self.starting = False
        self._start_monitor()

    def _heartbeat_ages(self) -> dict:
        return {v: (None if not l.state.last_heartbeat
                    else time.time() - l.state.last_heartbeat)
                for v, l in self.links.items()}

    # ------------------------------------------------------------- monitor
    def _start_monitor(self) -> None:
        self._stop_monitor.clear()
        self._monitor = threading.Thread(target=self._monitor_loop,
                                         name="fleet-ui-monitor", daemon=True)
        self._monitor.start()

    def _monitor_loop(self) -> None:
        while not self._stop_monitor.is_set():
            try:
                self._sample()
            except Exception:
                pass
            self._stop_monitor.wait(0.5)

    def _sample(self) -> None:
        if self.sup is None:
            return
        for vehicle_id in self.links:
            self.sup.note_heartbeat(vehicle_id)

        if self.spec is not None and self.spec.gazebo and self.sup.clock_source:
            reading = self.sup.clock_source.sample()
            if reading.available and reading.rtf is not None:
                if self._sep_started is None:
                    self._sep_started = time.monotonic()
                self._rtf_samples.append(
                    (time.monotonic() - self._sep_started, reading.rtf,
                     reading.sim_time_s))
                del self._rtf_samples[:-600]

            world = (self.spec.world or "").replace(".sdf", "")
            data = gzstats.read_world_poses(_world_name(self.composed) or world)
            stamp = data.get("stamp_s")
            if stamp is not None and self.separation is not None:
                fixes = [separation.Fix(vehicle_id=v, east_m=p[0],
                                        north_m=p[1], up_m=p[2], t_s=stamp)
                         for v in self.links
                         if (p := data["poses"].get(v))]
                if len(fixes) >= 2:
                    self.separation.sample(fixes)

    # ------------------------------------------------------------ commands
    def command(self, name: str, target, policy: Optional[str] = None) -> dict:
        if self.rt is None:
            return {"ok": False, "text": "no fleet is running"}
        name = (name or "").upper()
        try:
            if name == "ARM":
                result = self.rt.arm(target=target, policy=policy)
            elif name == "DISARM":
                result = self.rt.disarm(target=target, policy=policy)
            elif name.startswith("MODE "):
                result = self.rt.set_mode(name.split(" ", 1)[1],
                                          target=target, policy=policy)
            elif name == "TAKEOFF":
                alt = 15.0

                def _takeoff(vehicle_id):
                    def _run(link):
                        armed = link._do_arm([], arm=True)
                        if not armed.get("ok"):
                            return armed
                        return link._do_takeoff([str(alt)])
                    return _run

                result = self.rt.send("TAKEOFF", action_for=_takeoff,
                                      confirm=router.armed_is(True),
                                      target=target, policy=policy,
                                      gate=router.altitude_above(alt * 0.4),
                                      gate_timeout_s=120.0, ack_timeout=90.0)
            else:
                return {"ok": False, "text": f"unknown fleet command {name!r}"}
        except ValueError as exc:
            return {"ok": False, "text": str(exc)}
        return {"ok": True, "result": result.as_dict()}

    # ------------------------------------------------------- attach console
    def attach(self, vehicle_id: str) -> dict:
        """Exactly one interactive MAVProxy, for the focused vehicle."""
        if self.allocation is None:
            return {"ok": False, "text": "no fleet is running"}
        entry = self.allocation.for_vehicle(vehicle_id)
        if entry is None:
            return {"ok": False, "text": f"no vehicle {vehicle_id!r}"}
        self.detach()
        self.console_vehicle = vehicle_id
        return {"ok": True, "vehicle": vehicle_id,
                "command": f"mavproxy.py --master {entry.connection} --console"}

    def detach(self) -> dict:
        self.console_vehicle = ""
        return {"ok": True}

    # ---------------------------------------------------------------- stop
    def stop(self) -> dict:
        with self.lock:
            self._stop_monitor.set()
            if self._monitor is not None:
                self._monitor.join(timeout=3.0)
                self._monitor = None
            for link in self.links.values():
                try:
                    link.stop()
                except Exception:
                    pass
            report = None
            if self.sup is not None:
                report = self.sup.stop()
                self._write_artifacts(report)
            self.links = {}
            self.sup = None
            self.rt = None
            self.separation = None
            self._rtf_samples = []
            self._sep_started = None
            self.console_vehicle = ""
            spec, self.spec = self.spec, None
            return {"ok": True,
                    "text": (f"fleet {spec.name} stopped" if spec
                             else "no fleet was running"),
                    "teardown": report.as_dict() if report else None,
                    "run_dir": str(self.run_dir) if self.run_dir else ""}

    def _write_artifacts(self, teardown) -> None:
        if self.run_dir is None or self.spec is None:
            return
        try:
            artifacts.write_rtf_csv(
                self.run_dir / "rtf.csv", self._rtf_samples,
                reason=("SITL-only fleet: there is no physics server to "
                        "report a real-time factor")
                if not self.spec.gazebo else "")
            rows = self.separation.csv_rows() if self.separation else []
            artifacts.write_separation_csv(
                self.run_dir / "separation.csv", rows,
                reason=self.separation_reason)
            if self.bus is not None:
                self.bus.write_jsonl(self.run_dir / "timeline.jsonl")
            evaluated = self._criteria(teardown)
            fleetreport.write(self.run_dir / "fleet_report.md", self.spec,
                              evaluated, run_id=self.run_id,
                              teardown=teardown, allocation=self.allocation,
                              commands=([self.rt.last_result.as_dict()]
                                        if self.rt and self.rt.last_result
                                        else None),
                              timeline_events=len(self.bus.events)
                              if self.bus else 0)
            artifacts.write_fleet_json(
                self.run_dir / "fleet.json", self.spec, self.allocation,
                authorisations=self._authorisations(),
                extra={"criteria": [c.as_dict() for c in evaluated],
                       "verdict": criteria.fleet_verdict(evaluated)})
        except Exception as exc:
            self.on_log(f"fleet artefacts could not be written: {exc}")

    def _authorisations(self) -> dict:
        if self.spec is not None and self.spec.gazebo:
            return {
                "separation": artifacts.separation_authorisation(
                    True, "/world/<world>/pose/info",
                    "one world-state message carries every model's position "
                    "under a single header stamp, so the positions are "
                    "simultaneous by construction"),
                "rtf": {"measured": True, "source": "/stats",
                        "justification": "read from the running physics server"},
            }
        return {
            "separation": artifacts.separation_authorisation(
                False, "", self.separation_reason),
            "rtf": {"measured": False, "source": "",
                    "justification": "SITL-only fleet: no physics server"},
        }

    def _criteria(self, teardown) -> list:
        spec = self.spec
        closest: dict = {}
        for t_s, _pair, distance in (self.separation.csv_rows()
                                     if self.separation else []):
            if t_s not in closest or distance < closest[t_s]:
                closest[t_s] = distance
        return [
            criteria.separation_criterion(
                sorted(closest.items()), spec.min_separation_m,
                measuring=bool(self.separation and self.separation.measuring),
                refusal_reason=self.separation_reason,
                authorised_by="/world/<world>/pose/info — one world-state "
                              "message under a single header stamp"),
            criteria.rtf_criterion(
                [(t, r) for t, r, _ in self._rtf_samples if r is not None],
                floor=spec.max_rtf_drop, available=bool(spec.gazebo),
                absence_reason="SITL-only fleet: there is no physics server "
                               "to report a real-time factor",
                authorised_by="/stats, read from the running physics server"),
            criteria.teardown_criterion(
                teardown,
                authorised_by="the supervisor's own process table and lease "
                              "file"),
        ]

    # -------------------------------------------------------------- status
    def status(self) -> dict:
        """Everything the Fleet page shows, measured or explicitly absent."""
        with self.lock:
            running = self.sup is not None
            spec = self.spec

        vehicles = []
        if spec is not None:
            for vehicle in spec.vehicles:
                link = self.links.get(vehicle.id)
                entry = (self.allocation.for_vehicle(vehicle.id)
                         if self.allocation else None)
                state = link.state.as_dict() if link else {}
                age = state.get("heartbeat_age")
                vehicles.append({
                    "id": vehicle.id,
                    "sysid": vehicle.sysid,
                    "model": vehicle.model or vehicle.frame or "?",
                    "role": vehicle.role,
                    "mode": state.get("mode", "—"),
                    "armed": bool(state.get("armed")),
                    "alt": state.get("alt"),
                    "prearm_known": bool(state.get("prearm_known")),
                    "prearm_ok": bool(state.get("prearm_ok")),
                    "heartbeat_age": age,
                    "link_stale": (age is None or age > HEARTBEAT_LOST_S),
                    "serial0_port": entry.serial0_port if entry else None,
                    "connection": entry.connection if entry else "",
                })

        return {
            "running": running,
            "starting": self.starting,
            "error": self.error,
            "name": spec.name if spec else "",
            "gazebo": bool(spec.gazebo) if spec else False,
            "run_id": self.run_id if running else "",
            "vehicles": vehicles,
            "policies": list(fleetspec.GROUP_COMMAND_POLICIES),
            "default_policy": (spec.policy.group_command if spec
                               else "parallel_ack"),
            "separation": self._separation_status(),
            "rtf": self._rtf_status(),
            "last_command": (self.rt.last_result.as_dict()
                             if self.rt and self.rt.last_result else None),
            "console_vehicle": self.console_vehicle,
            "launch_transcript": list(self.launch_transcript),
            "min_separation_m": spec.min_separation_m if spec else None,
            "max_rtf_drop": spec.max_rtf_drop if spec else None,
        }

    def _separation_status(self) -> dict:
        if self.separation is None:
            return {"measured": False, "reason": "no fleet is running",
                    "minimum_m": None, "current_m": None, "series": []}
        if not self.separation.measuring:
            return {"measured": False, "reason": self.separation_reason,
                    "minimum_m": None, "current_m": None, "series": []}
        history = self.separation.history
        by_time: dict = {}
        for pair in history:
            if pair.t_s not in by_time or pair.distance_m < by_time[pair.t_s]:
                by_time[pair.t_s] = pair.distance_m
        series = sorted(by_time.items())[-120:]
        return {
            "measured": True, "reason": "",
            "minimum_m": self.separation.minimum_seen,
            "current_m": series[-1][1] if series else None,
            "limit_m": self.separation.min_separation_m,
            "violations": len(self.separation.violations),
            "series": [[round(t, 2), round(d, 3)] for t, d in series],
        }

    def _rtf_status(self) -> dict:
        if self.spec is None or not self.spec.gazebo:
            return {"measured": False, "rtf": None,
                    "reason": "SITL-only fleet: there is no physics server to "
                              "report a real-time factor"}
        if not self._rtf_samples:
            return {"measured": False, "rtf": None,
                    "reason": "the physics server has not reported a "
                              "real-time factor yet"}
        recent = [r for _, r, _ in self._rtf_samples[-10:] if r is not None]
        return {"measured": True, "reason": "",
                "rtf": round(sum(recent) / len(recent), 3) if recent else None,
                "floor": self.spec.max_rtf_drop,
                "series": [[round(t, 1), round(r, 3)]
                           for t, r, _ in self._rtf_samples[-120:]
                           if r is not None]}


def _world_name(composed) -> str:
    """The `<world name=>` of the generated world, which gz topics key on."""
    if composed is None:
        return ""
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(composed.world_path).getroot()
        world = root.find("world")
        return world.get("name", "") if world is not None else ""
    except Exception:
        return ""


def _resolve_launch(spec):
    """Binary, defaults, `--model`, model dir and base world for this fleet."""
    import json as _json

    autotest = paths.ARDUPILOT / "Tools" / "autotest"
    info = _json.loads(
        (autotest / "pysim" / "vehicleinfo.json").read_text(encoding="utf-8"))

    first = spec.vehicles[0]
    if first.model:
        registry = _json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
        model = next(m for m in registry["models"] if m["id"] == first.model)
        autopilot = model.get("vehicle") or "ArduCopter"
        frame_name = model.get("frame") or "quad"
        base_model = paths.SITL_MODELS / "Gazebo" / "models" / first.model
        base_world = paths.SITL_MODELS / "Gazebo" / "worlds" / (spec.world or "")
        model_arg = "JSON"
    else:
        autopilot = first.vehicle or "ArduCopter"
        frame_name = first.frame or "quad"
        base_model = None
        base_world = None
        model_arg = frame_name

    binary_name = {"ArduCopter": "arducopter", "ArduPlane": "arduplane"}[autopilot]
    binary = paths.ARDUPILOT / "build" / "sitl" / "bin" / binary_name

    frames = (info.get(autopilot) or {}).get("frames") or {}
    entry = frames.get(frame_name) or {}
    names = entry.get("default_params_filename") or []
    names = [names] if isinstance(names, str) else names
    defaults = [autotest / n for n in names]

    if first.model:
        registry = _json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
        model = next(m for m in registry["models"] if m["id"] == first.model)
        param = model.get("param_file") or ""
        if param.startswith("$SITL_MODELS"):
            candidate = Path(str(paths.SITL_MODELS)
                             + param[len("$SITL_MODELS"):])
            if candidate.is_file():
                defaults.append(candidate)

    return binary, defaults, model_arg, base_model, base_world
