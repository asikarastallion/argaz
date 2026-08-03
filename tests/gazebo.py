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

from argazui import paths, session
from argazui.mavlink_link import MavlinkLink

# Wall-clock budget for a Gazebo model to boot far enough to send a heartbeat.
# Generous because it covers Gazebo loading a world, SITL starting and, on a
# cold checkout, sim_vehicle.py deciding to rebuild the binary first.
BOOT_TIMEOUT = 300.0
PREARM_TIMEOUT = 300.0


class GazeboUnavailable(Exception):
    """Gazebo or the model assets are missing — skip, never fail.

    A skipped model is recorded as `untested` in the status table. That is the
    whole point of the distinction: this suite never reports success for a
    model it could not fly, and never reports failure for one it never tried.
    """


def preflight() -> None:
    """Everything tier 2 needs, checked before a single process is started."""
    if shutil.which("gz") is None:
        raise GazeboUnavailable("gz is not on PATH (Gazebo is not installed)")
    if not (paths.SITL_MODELS / "Gazebo").is_dir():
        raise GazeboUnavailable(f"SITL_Models assets not found at {paths.SITL_MODELS}")


@dataclass
class Simulation:
    """A running Gazebo + SITL + MAVProxy stack, and the link into it."""

    model: dict
    process: subprocess.Popen
    log: Path
    link: MavlinkLink
    _master_fd: int

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
                return True
            time.sleep(1.0)
        return False

    def stop(self) -> None:
        """Same rule as everywhere else here: by process group, never by name.

        Gazebo, SITL and MAVProxy are three processes in one session. SIGINT
        first so SITL flushes its dataflash log, which the run artefacts need.
        """
        self.link.stop()
        try:
            pgid = os.getpgid(self.process.pid)
        except ProcessLookupError:
            return
        for sig, wait in ((signal.SIGINT, 8.0), (signal.SIGTERM, 5.0),
                          (signal.SIGKILL, 3.0)):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                break
            try:
                self.process.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            os.close(self._master_fd)
        except OSError:
            pass


def start(model: dict, log_dir: Path, on_event=None, on_log=None) -> Simulation:
    """Boot `model` and return a connected link, or raise GazeboUnavailable."""
    preflight()
    commands = session.build_launch_commands(model)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{model['id']}-simulation.log"

    master, slave = pty.openpty()
    handle = log.open("wb")
    process = subprocess.Popen(
        ["/bin/bash", "-c", "\n".join(commands)],
        stdout=handle, stderr=subprocess.STDOUT, stdin=slave,
        start_new_session=True)
    os.close(slave)

    link = MavlinkLink(port=paths.UI_MAVLINK_PORT, on_event=on_event,
                       on_log=on_log)
    link.start(vehicle=model.get("vehicle") or "ArduPlane")
    sim = Simulation(model=model, process=process, log=log, link=link,
                     _master_fd=master)

    if not link.wait_ready(timeout=BOOT_TIMEOUT):
        tail = sim.tail()
        sim.stop()
        # Not a GazeboUnavailable: the assets were there and the launch was
        # attempted. A model that will not boot is a FAILING model, and the
        # status table has to say so rather than quietly calling it untested.
        raise TimeoutError(
            f"{model['id']}: no MAVLink heartbeat within {BOOT_TIMEOUT:.0f}s "
            f"of the launch commands\n{tail}")
    return sim


def launch_commands(model: dict) -> list[str]:
    """Exposed so a run record can show exactly what was typed."""
    return session.build_launch_commands(model)
