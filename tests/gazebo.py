"""Launch a registry model exactly the way the START button does.

THE SINGLE-SOURCE RULE, APPLIED TO TIER 2
-----------------------------------------
The commands come from `session.build_launch_commands(model)` — the same
function the browser path uses — and nothing here composes a `gz sim` or
`sim_vehicle.py` invocation of its own. A tier-2 pass therefore means the
button works for that model. If this module wrote its own commands, a green
model row in `docs/status.md` would be a statement about this file instead.

WHY A PTY AND NOT A PIPE
------------------------
`sim_vehicle.py` starts MAVProxy, which opens an interactive console. Given a
closed stdin it reads EOF and exits immediately; SITL then waits forever for
something to attach to SERIAL0 and the vehicle never leaves INITIALISING.
ArgazUI runs these commands inside a real terminal session, so this must too —
otherwise it is not testing the same thing. This cost an hour to find, from a
symptom ("the model never comes up") that looked like a Gazebo problem.
"""
from __future__ import annotations

import os
import pty
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from argazui import isolation, modelenv, paths, session, simlifecycle
from argazui.mavlink_link import MavlinkLink

# Wall-clock budget for a Gazebo model to boot far enough to send a heartbeat.
# Generous because it covers Gazebo loading a world, SITL starting and, on a
# cold checkout, sim_vehicle.py deciding to rebuild the binary first.
BOOT_TIMEOUT = 300.0
PREARM_TIMEOUT = 300.0

# How long to wait for Gazebo to report a served world. Taken from
# `simlifecycle` rather than restated here, so the browser path and tier 2
# cannot quietly disagree about how patient they are — which is the same
# single-source rule the launch commands themselves follow.
ENVIRONMENT_TIMEOUT = simlifecycle.ENVIRONMENT_READY_TIMEOUT


class GazeboUnavailable(Exception):
    """Gazebo or the model assets are missing — skip, never fail.

    A skipped model is recorded as `untested` in the status table. That is the
    whole point of the distinction: this suite never reports success for a
    model it could not fly, and never reports failure for one it never tried.
    """


class ModelEnvironmentRefused(Exception):
    """The model assets are not the revision the configuration declared.

    NOT a `GazeboUnavailable`, and the distinction is the whole of F-09. A
    missing Gazebo means this machine cannot answer the question, so the model
    is `untested`. A checkout at the wrong revision means the machine WOULD
    answer a question — a different one from the one that was asked — and
    recording that answer under the declared revision's name is exactly the
    unreproducible result the pin exists to prevent.

    It is a configuration failure, and the run record classifies it as
    `environment`. It is never an aircraft acceptance failure.
    """


def preflight() -> None:
    """Everything tier 2 needs, checked before a single process is started."""
    if shutil.which("gz") is None:
        raise GazeboUnavailable("gz is not on PATH (Gazebo is not installed)")
    if not (paths.SITL_MODELS / "Gazebo").is_dir():
        raise GazeboUnavailable(f"SITL_Models assets not found at {paths.SITL_MODELS}")
    pin = modelenv.verify()
    if not pin["ok"]:
        raise ModelEnvironmentRefused(pin["reason"])


@dataclass
class Simulation:
    """A running Gazebo + SITL + MAVProxy stack, and the link into it."""

    model: dict
    process: subprocess.Popen
    log: Path
    link: MavlinkLink
    _master_fd: int
    # Which rung the start-up reached, and what this simulation owns. The same
    # two objects `Manager` keeps for the browser path, for the same reason:
    # tier 2 verifies the button, so it has to record what the button records.
    lifecycle: Optional[simlifecycle.Lifecycle] = None
    resources: Optional[isolation.RunResources] = None

    def tail(self, lines: int = 40) -> str:
        try:
            text = self.log.read_text(errors="replace")
        except OSError:
            return "(no simulation output captured)"
        return "\n".join(text.splitlines()[-lines:])

    def wait_prearm(self, timeout: float = PREARM_TIMEOUT) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.link.state.prearm_known and self.link.state.prearm_ok:
                if self.lifecycle is not None:
                    self.lifecycle.enter(simlifecycle.VEHICLE_READY,
                                         "pre-arm checks pass")
                return True
            time.sleep(1.0)
        if self.lifecycle is not None:
            # `vehicle_readiness` and not `environment`: this vehicle is
            # running and talking, and it says it is not fit to fly. That is a
            # fact about the aircraft's configuration, and the taxonomy has a
            # category for it that is not `acceptance`.
            self.lifecycle.fail(simlifecycle.VEHICLE_NOT_READY,
                                f"pre-arm checks did not pass within "
                                f"{timeout:.0f}s")
        return False

    def stop(self) -> None:
        """Same rule as everywhere else here: by process group, never by name.

        Gazebo, SITL and MAVProxy are three processes in one SESSION, and not
        necessarily in one process group. SIGINT first so SITL flushes its
        dataflash log, which the run artefacts need.

        WHY THE SESSION SWEEP IS HERE AND NOT ONLY THE LAUNCHER'S GROUP
        ---------------------------------------------------------------
        This used to signal `os.getpgid(self.process.pid)` and then `break` the
        escalation as soon as `self.process.wait()` returned — that is, as soon
        as the launching *bash* exited. Anything that had left that process
        group, or that outlived bash while ignoring SIGINT, was never escalated
        against and simply stayed running.

        It was not hypothetical. The v1.7 ownership check reported it on the
        first release that had one:

            "released": false,
            "survivors": [{"pid": 313898, "pgid": 313826, "sid": 313826,
                           "command": "gz sim -v4 -r -s wsc_aircraft_runway.sdf"}]

        A live Gazebo, holding its port, after a test that reported success.

        `TerminalSession.stop_children` — the browser path — has always walked
        the whole kernel session and escalated over every process group in it.
        This is the same asymmetry the audit found for readiness, in the
        teardown direction, and the fix is the same: use the one implementation
        rather than a second, weaker one.

        Cleanup is then CHECKED. `verify_released` asks the kernel whether the
        processes this simulation owned are gone and whether its ports are
        free, and the answer goes into the run record — so "no orphan was left"
        is a claim with evidence rather than the absence of a complaint. It is
        asked whatever brought us here: a pass, a failure, a timeout, a
        cancelled session or an exception, because `addfinalizer` calls this in
        all five cases.
        """
        self.link.stop()
        try:
            sid = os.getsid(self.process.pid)
        except (ProcessLookupError, OSError):
            self._verify_cleanup()
            return

        for sig, wait in ((signal.SIGINT, 8.0), (signal.SIGTERM, 5.0),
                          (signal.SIGKILL, 3.0)):
            # Recomputed each round, by the kernel, from the session id — so a
            # process that changed group between rounds is still found and one
            # that has died is not signalled again.
            #
            # `exclude_pgid=-1` excludes nothing: process group ids are
            # positive, and unlike the browser path there is no shell of our
            # own to spare here. `self.process` IS the launched bash, and it is
            # meant to go. The session was created by `start_new_session=True`,
            # so it contains this simulation and nothing else — the test runner
            # is in a different one and cannot be reached from here.
            groups = session.pgids_in_session(sid, exclude_pgid=-1)
            if not groups:
                break
            for pgid in groups:
                try:
                    os.killpg(pgid, sig)
                except (ProcessLookupError, PermissionError):
                    continue
            deadline = time.time() + wait
            while time.time() < deadline:
                if not session.pgids_in_session(sid, exclude_pgid=-1):
                    break
                time.sleep(0.2)

        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.close(self._master_fd)
        except OSError:
            pass
        self._verify_cleanup()

    def _verify_cleanup(self) -> None:
        if self.resources is not None:
            self.resources.verify_released()
        if self.lifecycle is not None and not self.lifecycle.failed:
            self.lifecycle.enter(simlifecycle.COMPLETED, "simulation stopped")


class EnvironmentFailed(Exception):
    """The simulator did not come up. Not a statement about any aircraft.

    Carries the lifecycle that got this far, so the caller can put the layer
    the start-up stopped in into the run record rather than reconstructing it
    from a message.
    """

    def __init__(self, text: str, lifecycle: simlifecycle.Lifecycle) -> None:
        super().__init__(text)
        self.lifecycle = lifecycle


def start(model: dict, log_dir: Path, on_event=None, on_log=None) -> Simulation:
    """Boot `model` and return a connected link, one lifecycle rung at a time.

    Raises `GazeboUnavailable` when this machine cannot answer the question at
    all, `ModelEnvironmentRefused` when it would answer a different one, and
    `EnvironmentFailed` when the simulator was launched and did not come up.
    The three are separate because they are three different results: untested,
    a configuration error, and an environment failure. None of them is a
    verdict about an airframe.
    """
    preflight()
    lifecycle = simlifecycle.Lifecycle(label=model["id"], on_log=on_log)
    resources = isolation.RunResources(label=model["id"])

    blocking = [h for h in resources.check_ports(isolation.wanted_ports())
                if not h.ours]
    if blocking:
        detail = isolation.describe(blocking)
        lifecycle.fail(simlifecycle.ENVIRONMENT_FAILED, detail)
        # A held port is the machine's problem, not the model's, and a model
        # cannot be reported failed for it. Skip, so the model stays `untested`.
        raise GazeboUnavailable(
            f"a port tier 2 needs is already held, and this suite will not "
            f"terminate a process it did not start:\n{detail}")

    commands = session.build_launch_commands(model)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{model['id']}-simulation.log"

    master, slave = pty.openpty()
    handle = log.open("wb")
    lifecycle.enter(simlifecycle.ENVIRONMENT_STARTING,
                    f"{len(commands)} launch line(s)")
    process = subprocess.Popen(
        ["/bin/bash", "-c", "\n".join(commands)],
        stdout=handle, stderr=subprocess.STDOUT, stdin=slave,
        start_new_session=True)
    os.close(slave)
    # The bash this started is its own kernel session, which is what makes
    # every later ownership question answerable by the kernel rather than by a
    # process name.
    try:
        resources.sid = os.getsid(process.pid)
    except (ProcessLookupError, OSError):
        resources.sid = None

    link = MavlinkLink(port=paths.UI_MAVLINK_PORT, on_event=on_event,
                       on_log=on_log)
    link.start(vehicle=model.get("vehicle") or "ArduPlane")
    sim = Simulation(model=model, process=process, log=log, link=link,
                     _master_fd=master, lifecycle=lifecycle,
                     resources=resources)

    def _alive() -> bool:
        return process.poll() is None

    # ------------------------------------------------------------ environment
    if model.get("world"):
        ready, detail = simlifecycle.wait_for_gazebo(
            timeout=ENVIRONMENT_TIMEOUT, alive=_alive)
        if ready:
            lifecycle.enter(simlifecycle.ENVIRONMENT_READY, detail)
        elif not _alive():
            # The launch shell is gone before any vehicle appeared. That is the
            # environment, and it is now said in those words instead of arriving
            # 300 seconds later as an absent heartbeat.
            lifecycle.fail(simlifecycle.ENVIRONMENT_FAILED, detail)
            tail = sim.tail()
            sim.stop()
            raise EnvironmentFailed(
                f"{model['id']}: the simulation environment failed before any "
                f"vehicle appeared — {detail}\n{tail}", lifecycle)
        else:
            # Still running, just not advertising a world. `gz topic` may be
            # absent from a PATH that has `gz sim`, so this is recorded and the
            # vehicle wait below is what decides.
            lifecycle.enter(simlifecycle.ENVIRONMENT_STARTING, detail)
    else:
        lifecycle.enter(simlifecycle.ENVIRONMENT_READY,
                        "this model needs no simulator of its own")

    # ---------------------------------------------------------------- vehicle
    lifecycle.enter(simlifecycle.VEHICLE_STARTING, "waiting for MAVLink")
    if not link.wait_ready(timeout=BOOT_TIMEOUT):
        # WHICH LAYER FAILED, NOT MERELY THAT ONE DID
        # -------------------------------------------
        # Gazebo serving a world and no vehicle appearing is SITL's problem;
        # no world and no vehicle is the simulator's. Both produced the
        # identical TimeoutError before v1.7, and they are two different
        # investigations.
        environment_up = lifecycle.reached(simlifecycle.ENVIRONMENT_READY)
        phase = (simlifecycle.VEHICLE_START_FAILED if environment_up
                 else simlifecycle.ENVIRONMENT_FAILED)
        detail = (f"no MAVLink heartbeat within {BOOT_TIMEOUT:.0f}s of the "
                  f"launch commands"
                  + ("" if environment_up
                     else "; Gazebo never reported a served world"))
        lifecycle.fail(phase, detail)
        tail = sim.tail()
        sim.stop()
        raise EnvironmentFailed(f"{model['id']}: {detail}\n{tail}", lifecycle)

    phase, detail = simlifecycle.vehicle_readiness(link)
    lifecycle.enter(simlifecycle.VEHICLE_STARTING, detail)
    return sim


def launch_commands(model: dict) -> list[str]:
    """Exposed so a run record can show exactly what was typed."""
    return session.build_launch_commands(model)
