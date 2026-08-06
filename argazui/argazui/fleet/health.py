"""L5 primitives — the sources a fleet's health is measured from.

WHY THE SOURCES ARE PLUGGABLE AND WHY THAT IS NOT OVER-ENGINEERING
------------------------------------------------------------------
A fleet runs in two very different worlds. With Gazebo there is a physics
server that publishes `/stats`, and real-time factor and lockstep progress are
things that can be read. Without Gazebo — the tier the CI actually runs —
there is no server at all. Every SITL free-runs on its own clock.

The tempting shortcut is for the SITL-only path to report `rtf = 1.0`, because
"nothing is slowing it down". That would be a fabricated measurement, and a
fabricated measurement is worse than a missing one: it satisfies the
acceptance criterion `RTF never fell below the threshold` without anything
having been observed. So the source reports **absence with a reason**, and
`Sample.available` is False. Nothing downstream is allowed to turn that into
a number.

    "we did not measure this"  and  "we measured it and it was fine"
    are the two answers this project exists to keep apart.

WHAT EACH SOURCE ANSWERS
------------------------
    SimClockSource   is simulated time advancing, and how fast against
                     wall-clock? Gazebo's /stats in Phase 5; absent here.
    LinkHealth       how long since this vehicle's last heartbeat?
    ClockSpread      how far apart are the vehicles' own clocks? Meaningful
                     ONLY without lockstep, where it is the thing that makes
                     relative geometry unmeasurable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

# A vehicle whose last heartbeat is older than this is LOST. Same 5 s the
# architecture specifies; kept here so the monitor and the report cannot
# disagree about it.
HEARTBEAT_LOST_S = 5.0

# How often the health monitor samples. 1 Hz: fast enough that a stall is
# noticed within a second, slow enough that the monitor is not itself a load
# on a machine already running N physics loops.
MONITOR_INTERVAL_S = 1.0


@dataclass(frozen=True)
class Sample:
    """One reading, or a stated absence of one.

    `available=False` is a first-class answer, not an error. `value` is None
    whenever it is False, and `reason` says why — that string reaches the
    fleet report verbatim.
    """

    available: bool
    reason: str = ""
    rtf: Optional[float] = None
    sim_time_s: Optional[float] = None

    def as_dict(self) -> dict:
        return {"available": self.available, "reason": self.reason,
                "rtf": self.rtf, "sim_time_s": self.sim_time_s}


class SimClockSource(Protocol):
    """Where simulated time and real-time factor come from."""

    name: str

    def sample(self) -> Sample:
        ...


class NoSimulationServer:
    """SITL-only: there is no physics server, so there is no RTF.

    This is the whole point of the pluggable source. It never returns a
    number, and the reason it gives is what the fleet report prints instead of
    an RTF row.
    """

    name = "none"

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or (
            "SITL-only fleet: there is no physics server to report a "
            "real-time factor, so none was measured")

    def sample(self) -> Sample:
        return Sample(available=False, reason=self.reason)


class CallableClockSource:
    """Adapts any callable into a source. The seam Phase 5's Gazebo reader uses.

    Kept deliberately thin: the Gazebo implementation is a `/stats`
    subscription, and wrapping it here means the monitor, the report and the
    tests never learn which one they are talking to.
    """

    def __init__(self, fn: Callable[[], Sample], name: str = "callable") -> None:
        self._fn = fn
        self.name = name

    def sample(self) -> Sample:
        try:
            return self._fn()
        except Exception as exc:                       # a source must never
            return Sample(available=False,             # take the monitor down
                          reason=f"{self.name} source failed: "
                                 f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------- clocks
@dataclass
class ClockSpread:
    """How far apart the vehicles' own clocks are.

    WHY THIS MATTERS, AND ONLY WITHOUT LOCKSTEP
    -------------------------------------------
    Under Gazebo the physics server drives every SITL in lockstep, so all
    vehicles share one simulated clock and two positions sampled "at the same
    time" really are simultaneous.

    Without Gazebo there is no such thing. Each SITL free-runs on its own
    scheduler, and two vehicles' `time_boot_ms` drift apart. A separation
    figure computed from positions carrying different time bases is not a
    distance — it is two snapshots of different instants subtracted from each
    other, and its error grows with the drift.

    So this is measured, and what it constrains is stated rather than assumed.
    """

    samples: dict = field(default_factory=dict)     # vehicle_id -> (wall, boot_s)

    def observe(self, vehicle_id: str, boot_s: float,
                when: Optional[float] = None) -> None:
        self.samples[vehicle_id] = (when if when is not None else time.time(),
                                    boot_s)

    @property
    def spread_s(self) -> Optional[float]:
        """Widest gap between any two vehicles' clocks, corrected for the
        wall-clock moment each was read at. None with fewer than two."""
        if len(self.samples) < 2:
            return None
        reference = max(w for w, _ in self.samples.values())
        adjusted = [boot + (reference - wall)
                    for wall, boot in self.samples.values()]
        return max(adjusted) - min(adjusted)

    def as_dict(self) -> dict:
        return {"vehicles": len(self.samples),
                "spread_s": (None if self.spread_s is None
                             else round(self.spread_s, 4))}


# ------------------------------------------------------------- vehicle health
VEHICLE_OK = "ok"
VEHICLE_LOST = "lost"
VEHICLE_DEAD = "dead"           # the process itself is gone
VEHICLE_STARTING = "starting"


@dataclass
class VehicleHealth:
    vehicle_id: str
    state: str = VEHICLE_STARTING
    process_alive: bool = True
    heartbeat_age_s: Optional[float] = None
    reason: str = ""

    def as_dict(self) -> dict:
        return {"vehicle_id": self.vehicle_id, "state": self.state,
                "process_alive": self.process_alive,
                "heartbeat_age_s": (None if self.heartbeat_age_s is None
                                    else round(self.heartbeat_age_s, 2)),
                "reason": self.reason}


def classify(vehicle_id: str, process_alive: bool,
             last_heartbeat: Optional[float],
             now: Optional[float] = None) -> VehicleHealth:
    """One vehicle's health from the two things that can be observed.

    Order matters: a dead process is reported as DEAD rather than LOST even
    though its heartbeats also stopped. "The process exited" and "the link
    went quiet" call for different actions, and collapsing them would send
    somebody looking at the network for a vehicle that crashed.
    """
    now = now if now is not None else time.time()
    if not process_alive:
        return VehicleHealth(vehicle_id, VEHICLE_DEAD, False, None,
                             "the SITL process exited")
    if last_heartbeat is None:
        return VehicleHealth(vehicle_id, VEHICLE_STARTING, True, None,
                             "no heartbeat received yet")
    age = now - last_heartbeat
    if age > HEARTBEAT_LOST_S:
        return VehicleHealth(vehicle_id, VEHICLE_LOST, True, age,
                             f"no heartbeat for {age:.1f}s "
                             f"(limit {HEARTBEAT_LOST_S:g}s)")
    return VehicleHealth(vehicle_id, VEHICLE_OK, True, age, "")


# ---------------------------------------------------------------- stall report
@dataclass
class StallReport:
    """Which vehicle stopped answering, when sim time stops advancing.

    In a lockstep world one silent FDM freezes every vehicle, and the symptom
    — "everything stopped" — points at no one. The diagnosis is the vehicle
    whose FDM went quiet longest ago, and naming it is the difference between
    a five-minute fix and an afternoon.

    Phase 5 fills this from the Gazebo path. It exists here so the monitor and
    the report already have its shape.
    """

    stalled: bool = False
    sim_time_s: Optional[float] = None
    stalled_for_s: Optional[float] = None
    suspect_vehicles: list = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        return {"stalled": self.stalled, "sim_time_s": self.sim_time_s,
                "stalled_for_s": (None if self.stalled_for_s is None
                                  else round(self.stalled_for_s, 2)),
                "suspect_vehicles": list(self.suspect_vehicles),
                "reason": self.reason}


class NoStallDetection:
    """SITL-only: without a shared clock there is no stall to detect.

    Not "no stall was found" — no such measurement exists here. Each SITL runs
    its own physics as fast as it can, so one falling behind is not visible to
    any other and there is nothing to compare against.
    """

    name = "none"

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or (
            "SITL-only fleet: vehicles do not share a clock, so lockstep "
            "stall detection does not apply")

    def sample(self, *_args, **_kwargs) -> StallReport:
        return StallReport(stalled=False, reason=self.reason)
