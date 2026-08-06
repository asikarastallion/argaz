"""Gazebo's own clock, and who stopped it.

WHERE THE NUMBERS COME FROM
---------------------------
`gz topic -e -t /stats -n 1` prints one `gz.msgs.WorldStatistics`. Shelling out
rather than binding to gz-transport is deliberate and matches the rest of the
project: `versions.py` already reads `gz sim --version` the same way, the
Python bindings are not a dependency this project has, and a subprocess that
fails is a stated absence rather than an import error at start-up.

WHY A STALL NEEDS AN ACCUSED, NOT JUST A SYMPTOM
------------------------------------------------
`lock_step` is on in every ardupilot_gazebo model (measured: `<lock_step>1`).
The server advances one physics step, sends state to each FDM, and waits for
every one of them to answer. So a single SITL that stops answering freezes
simulated time for the entire world.

The symptom is "everything stopped", which points at nobody. Four vehicles are
motionless, sim time is flat, and every link looks equally dead because none of
them is being stepped. This is the most common and most confusing multi-vehicle
failure, and the diagnosis — *which* vehicle went quiet — is the difference
between a five-minute fix and an afternoon.

Two independent signals are used, because either alone can mislead:

    process state   a process stopped with SIGSTOP sits in state 'T' in
                    /proc/<pid>/stat. Definitive when it applies, and it
                    catches the case where the process is alive but frozen —
                    which is exactly what a stall looks like.
    heartbeat age   a SITL that is running but wedged still stops talking.
                    Catches what process state cannot.

A vehicle flagged by either is a suspect. If nothing is flagged the stall is
reported with `suspect_vehicles: []` and says so, rather than blaming whichever
vehicle happened to be checked first.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .health import Sample, StallReport

# How long the world must be crawling before it is called a stall rather than
# a slow patch. Three seconds is long enough that a burst of heavy physics
# does not trip it, short enough that a person watching notices at about the
# same time the monitor does.
STALL_AFTER_S = 3.0

# Simulated seconds per wall second below which the world counts as stalled.
#
# MEASURED, AND NOT WHAT WAS EXPECTED
# -----------------------------------
# The first version tested for sim time being EXACTLY flat, on the assumption
# that lockstep means a frozen vehicle freezes the world. It does not, quite.
# With one SITL held under SIGSTOP, sim time advanced 111.05 -> 113.21 s over
# roughly 50 s of wall clock — an effective RTF of about 0.04. The world
# crawls rather than stopping, because the plugin drains FDM packets that were
# already in the socket buffer before the process was frozen, one per step.
#
# So an exact-flatness test detects nothing at all. A rate test detects both
# the crawl and a true freeze. 0.1 is far below any healthy run measured here
# (0.45-1.12 with three vehicles) and far above the 0.04 of a stalled one.
STALL_RTF = 0.1

# Kept for the true-freeze case: sim time moving by less than this is noise.
SIM_TIME_EPSILON_S = 1e-6


def _proc_state(pid: int) -> Optional[str]:
    """The single-character process state from /proc, or None.

    'T' is stopped (SIGSTOP / SIGTSTP), 'Z' zombie, 'R'/'S'/'D' running,
    sleeping, uninterruptible. Parsed after the last ')' because a process's
    comm field can itself contain parentheses and spaces — the same care
    session.py takes for the same reason.
    """
    try:
        data = Path(f"/proc/{pid}/stat").read_text(errors="replace")
    except (OSError, ValueError):
        return None
    close = data.rfind(")")
    if close == -1:
        return None
    fields = data[close + 2:].split()
    return fields[0] if fields else None


def parse_stats(text: str) -> dict:
    """Pull sim_time, real_time and the RTF out of `gz topic -e` output.

    The message prints nested blocks:

        sim_time { sec: 12 nsec: 345000000 }
        real_time { sec: 13 nsec: 0 }
        real_time_factor: 0.95
        paused: false
    """
    out: dict = {}

    for name in ("sim_time", "real_time"):
        match = re.search(rf"{name}\s*\{{([^}}]*)\}}", text, re.DOTALL)
        if not match:
            continue
        body = match.group(1)
        sec = re.search(r"sec:\s*(-?\d+)", body)
        nsec = re.search(r"nsec:\s*(-?\d+)", body)
        seconds = float(sec.group(1)) if sec else 0.0
        seconds += (float(nsec.group(1)) / 1e9) if nsec else 0.0
        out[name] = seconds

    rtf = re.search(r"real_time_factor:\s*(-?\d+\.?\d*(?:[eE][-+]?\d+)?)", text)
    if rtf:
        try:
            out["real_time_factor"] = float(rtf.group(1))
        except ValueError:
            pass
    paused = re.search(r"paused:\s*(true|false)", text)
    if paused:
        out["paused"] = paused.group(1) == "true"
    iterations = re.search(r"iterations:\s*(\d+)", text)
    if iterations:
        out["iterations"] = int(iterations.group(1))
    return out


def read_stats(topic: str = "/stats", timeout: float = 4.0) -> dict:
    """One reading, or {} if Gazebo did not answer."""
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", topic, "-n", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    return parse_stats(result.stdout)


def parse_world_poses(text: str) -> dict:
    """Every model's pose out of one `.../dynamic_pose/info` message.

    Returns `{"stamp_s": float, "poses": {name: (x, y, z)}}`.

    THE STAMP IS THE POINT
    ----------------------
    One message carries one `header.stamp` and every model's position under
    it. That is a single world state at a single simulated instant — the
    positions in it are simultaneous *by construction*, not by assumption.

    This is why separation is sourced here rather than from each vehicle's
    MAVLink. Reading three vehicles' GLOBAL_POSITION_INT means three reads at
    three moments against three clocks that were measured to disagree by up to
    0.32 s even under lockstep (docs/fleet-clock-drift.md). One message with
    one stamp has no such gap to correct for.
    """
    out: dict = {"stamp_s": None, "poses": {}}

    stamp = re.search(r"header\s*\{.*?stamp\s*\{([^}]*)\}", text, re.DOTALL)
    if stamp:
        body = stamp.group(1)
        sec = re.search(r"sec:\s*(-?\d+)", body)
        nsec = re.search(r"nsec:\s*(-?\d+)", body)
        seconds = float(sec.group(1)) if sec else 0.0
        seconds += (float(nsec.group(1)) / 1e9) if nsec else 0.0
        out["stamp_s"] = seconds

    for block in re.finditer(
            r"pose\s*\{\s*name:\s*\"([^\"]+)\".*?position\s*\{([^}]*)\}",
            text, re.DOTALL):
        name, body = block.group(1), block.group(2)
        values = []
        for axis in ("x", "y", "z"):
            found = re.search(rf"\b{axis}:\s*(-?\d+\.?\d*(?:[eE][-+]?\d+)?)", body)
            values.append(float(found.group(1)) if found else 0.0)
        out["poses"][name] = tuple(values)
    return out


def read_world_poses(world: str, timeout: float = 5.0,
                     env: Optional[dict] = None) -> dict:
    """One simultaneous read of every model's pose in `world`.

    `pose/info` and NOT `dynamic_pose/info`. The dynamic variant carries only
    entities whose pose changed, so a vehicle that has landed and settled
    silently drops out of it — measured: a wiring check lost v2 the moment it
    stopped moving, and read that as "could not determine the pose" rather
    than as "it is exactly where it was". `pose/info` publishes the full world
    state every time, which is what a separation trace and a wiring check both
    need: absence must mean absent, not stationary.
    """
    topic = f"/world/{world}/pose/info"
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", topic, "-n", "1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return {"stamp_s": None, "poses": {}}
    if result.returncode != 0 or not result.stdout.strip():
        return {"stamp_s": None, "poses": {}}
    return parse_world_poses(result.stdout)


class GazeboStats:
    """Real-time factor and simulated time, from the running physics server."""

    name = "gz/stats"

    def __init__(self, topic: str = "/stats",
                 reader: Optional[Callable[[], dict]] = None) -> None:
        self.topic = topic
        self._reader = reader or (lambda: read_stats(self.topic))

    def sample(self) -> Sample:
        stats = self._reader()
        if not stats:
            return Sample(
                available=False,
                reason=f"no reply on {self.topic}; the physics server is not "
                       f"publishing statistics")
        rtf = stats.get("real_time_factor")
        sim = stats.get("sim_time")
        if rtf is None and sim is None:
            return Sample(available=False,
                          reason=f"{self.topic} answered but carried neither a "
                                 f"real-time factor nor a simulated time")
        return Sample(available=True, rtf=rtf, sim_time_s=sim)


class LockstepStallDetector:
    """Notices that simulated time stopped, and names who stopped it."""

    name = "lockstep"

    def __init__(self, clock: GazeboStats, processes: Optional[dict] = None,
                 heartbeat_ages: Optional[Callable[[], dict]] = None,
                 stall_after_s: float = STALL_AFTER_S,
                 stall_rtf: float = STALL_RTF,
                 sim_server_pid: Optional[int] = None) -> None:
        self.clock = clock
        # vehicle_id -> pid. Given by the supervisor, which owns the processes.
        self.processes = dict(processes or {})
        self.heartbeat_ages = heartbeat_ages or (lambda: {})
        self.stall_after_s = stall_after_s
        self.stall_rtf = stall_rtf
        self.sim_server_pid = sim_server_pid
        # (wall, sim) of the last reading that was moving at a healthy rate.
        self._healthy: Optional[tuple] = None
        # When /stats first stopped answering, or None while it answers.
        self._silent_since: Optional[float] = None

    def sample(self, *_args, **_kwargs) -> StallReport:
        reading = self.clock.sample()
        now = time.monotonic()

        if not reading.available or reading.sim_time_s is None:
            return self._server_silent(now, reading.reason)
        self._silent_since = None

        sim = reading.sim_time_s
        if self._healthy is None:
            self._healthy = (now, sim)
            return StallReport(stalled=False, sim_time_s=sim,
                               reason="first reading; nothing to compare yet")

        wall_then, sim_then = self._healthy
        wall_delta = now - wall_then
        if wall_delta <= 0:
            return StallReport(stalled=False, sim_time_s=sim,
                               reason="no wall-clock time has passed")

        observed = (sim - sim_then) / wall_delta

        # Advancing at a healthy rate: reset the window and carry on.
        if observed >= self.stall_rtf:
            self._healthy = (now, sim)
            return StallReport(
                stalled=False, sim_time_s=sim,
                reason=f"simulated time is advancing at {observed:.2f}x")

        # Crawling. Not yet a verdict — a burst of heavy physics looks the
        # same for a moment.
        if wall_delta < self.stall_after_s:
            return StallReport(
                stalled=False, sim_time_s=sim,
                reason=f"simulated time advancing at only {observed:.3f}x for "
                       f"{wall_delta:.1f}s (calling it a stall at "
                       f"{self.stall_after_s:g}s)")

        suspects, why = self._accuse()
        frozen = abs(sim - sim_then) <= SIM_TIME_EPSILON_S
        moved = ("has not advanced at all" if frozen
                 else f"has advanced at only {observed:.3f}x "
                      f"(limit {self.stall_rtf:g}x)")
        return StallReport(
            stalled=True, sim_time_s=sim, stalled_for_s=wall_delta,
            suspect_vehicles=suspects,
            reason=(f"simulated time {moved} for {wall_delta:.1f}s "
                    f"(sim_time {sim:.3f}). " + why))

    def _server_silent(self, now: float, reason: str) -> StallReport:
        """`/stats` stopped answering. When the server is alive, that IS a stall.

        MEASURED, AND IT INVERTS THE OBVIOUS READING
        --------------------------------------------
        Holding one SITL under SIGSTOP does not merely slow the world — the
        `gz` process blocks inside the plugin's

            while (!this->ReceiveServoPacket() && arduPilotOnline)

        loop (ArduPilotPlugin.cc:1206) and stops servicing gz-transport
        entirely. So `gz topic -e -t /stats` times out.

        The first version treated that as "no measurement available" and
        reported `stalled=False` — which is exactly backwards. A physics
        server that is running but has stopped answering is the strongest
        stall signal there is, not the absence of one.
        """
        if self._silent_since is None:
            self._silent_since = now
        silent_for = now - self._silent_since

        alive = (self.sim_server_pid is not None
                 and _proc_state(self.sim_server_pid) not in (None, "Z"))
        if not alive and self.sim_server_pid is not None:
            return StallReport(
                stalled=False,
                reason=f"{reason}; the physics server process is gone, which "
                       f"is a crash rather than a stall")

        if silent_for < self.stall_after_s:
            return StallReport(
                stalled=False,
                reason=f"{reason} (silent for {silent_for:.1f}s; calling it a "
                       f"stall at {self.stall_after_s:g}s)")

        suspects, why = self._accuse(server_frozen=True)
        return StallReport(
            stalled=True, stalled_for_s=silent_for, suspect_vehicles=suspects,
            reason=(f"the physics server has not answered /stats for "
                    f"{silent_for:.1f}s while still running — it is blocked "
                    f"waiting for an FDM. " + why))

    def _accuse(self, server_frozen: bool = False) -> tuple:
        """Which vehicle stopped answering, and on what evidence.

        Process state outranks heartbeat silence, and during a full freeze it
        is the ONLY usable evidence: the world is not stepping, so *no*
        vehicle is sending heartbeats and every link looks equally dead. An
        earlier version listed all three as suspects for that reason, which is
        precisely the useless "everything stopped" answer this detector exists
        to replace.
        """
        stopped, gone = [], []
        for vehicle_id, pid in sorted(self.processes.items()):
            state = _proc_state(pid)
            if state in ("T", "t"):
                stopped.append(vehicle_id)
            elif state == "Z" or state is None:
                gone.append(vehicle_id)

        if stopped:
            others = [v for v in self.processes if v not in stopped]
            return stopped, (
                f"{', '.join(stopped)} is frozen (process state T), so its FDM "
                f"cannot answer and lockstep is waiting for it."
                + (f" {', '.join(others)} are silent as a consequence, not as a"
                   f" cause." if others and server_frozen else ""))
        if gone:
            return gone, (f"{', '.join(gone)} is no longer running, so nothing "
                          f"will answer for it.")

        quiet = sorted(v for v, age in self.heartbeat_ages().items()
                       if age is not None and age > self.stall_after_s * 2)
        if quiet and not server_frozen:
            return quiet, (f"{', '.join(quiet)} stopped sending heartbeats "
                           f"while the others kept talking; its FDM is the "
                           f"most likely one lockstep is waiting for.")
        if server_frozen:
            return [], ("No vehicle process is stopped or missing, so the "
                        "blockage is inside a vehicle that is still running — "
                        "heartbeat age cannot single it out because a frozen "
                        "world silences every vehicle at once.")
        return [], ("No vehicle could be singled out: every process is running "
                    "and every link is still sending heartbeats. The stall is "
                    "somewhere other than a stopped vehicle.")
