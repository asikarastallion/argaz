"""Simulation lifecycle: which layer a start-up failure happened in.

WHY THIS EXISTS
---------------
`gz sim … &` followed by `sleep 6` was the entire Gazebo handshake, and no exit
status of any launched command was ever read. Everything that could go wrong
below the aircraft therefore arrived at the classifier wearing the same
costume: a step that timed out. A missing world file, a `sim_vehicle.py` that
decided to rebuild, a wrong `--frame`, a Gazebo that started and died — all of
them were reported as `procedure` / `step-timeout`, which is a statement about
a flow that never had an aircraft under it.

v1.6.1 closed the worst of that at the top: `ProcedureRunner` refuses to start
when no heartbeat has ever arrived, and that abort is `environment`. It is the
right guard in the wrong place to answer the next question — *which* part of
the environment failed. "No heartbeat" is the symptom of five different
diseases.

WHAT THIS IS
------------
A record and a classifier. `Lifecycle` remembers which phase a start-up reached
and when, and maps the phase it stopped in onto the failure taxonomy that
already exists. It starts nothing, launches nothing and owns no process.

WHAT THIS IS NOT
----------------
A second execution engine. The launch is still shell text typed into a real
pty, `TerminalSession` still owns the processes, `MavlinkLink` still owns
readiness, and `ProcedureRunner` is still the only executor. Nothing here
schedules or supervises; `Manager` and `tests/gazebo.py` drive it, because they
are the two places that already know what was started.

THE LADDER, AND WHY EACH RUNG IS A DIFFERENT FACT
--------------------------------------------------
    ENVIRONMENT_STARTING  the simulator process was launched
    ENVIRONMENT_READY     it is serving a world — not merely running
    VEHICLE_STARTING      the autopilot process was launched
    VEHICLE_READY         it is talking, and it says it is fit to fly
    PROCEDURE_RUNNING     the executor has it
    COMPLETED             with a verdict that is about the aircraft

"the process exists" and "the process is doing its job" are two rungs on
purpose. A PID proves that `fork` succeeded. Gazebo holds a PID for the several
seconds it spends failing to find a mesh, and SITL holds one while it waits
forever for a physics backend that is not answering.
"""
from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import failures

SCHEMA = 1

# ------------------------------------------------------------------- phases
CREATED = "created"
ENVIRONMENT_STARTING = "environment_starting"
ENVIRONMENT_READY = "environment_ready"
VEHICLE_STARTING = "vehicle_starting"
VEHICLE_READY = "vehicle_ready"
PROCEDURE_RUNNING = "procedure_running"
COMPLETED = "completed"

ENVIRONMENT_FAILED = "environment_failed"
VEHICLE_START_FAILED = "vehicle_start_failed"
VEHICLE_NOT_READY = "vehicle_not_ready"
PROCEDURE_FAILED = "procedure_failed"
ACCEPTANCE_FAILED = "acceptance_failed"

PHASES = (CREATED, ENVIRONMENT_STARTING, ENVIRONMENT_READY, VEHICLE_STARTING,
          VEHICLE_READY, PROCEDURE_RUNNING, COMPLETED,
          ENVIRONMENT_FAILED, VEHICLE_START_FAILED, VEHICLE_NOT_READY,
          PROCEDURE_FAILED, ACCEPTANCE_FAILED)

TERMINAL = frozenset({COMPLETED, ENVIRONMENT_FAILED, VEHICLE_START_FAILED,
                      VEHICLE_NOT_READY, PROCEDURE_FAILED, ACCEPTANCE_FAILED})
FAILED = TERMINAL - {COMPLETED}

# The order a nominal start-up passes through. Used to check that a recorded
# history is a lifecycle and not a set of labels: a run that reports
# VEHICLE_READY without ever reporting ENVIRONMENT_READY has not described
# anything that happened.
NOMINAL = (CREATED, ENVIRONMENT_STARTING, ENVIRONMENT_READY, VEHICLE_STARTING,
           VEHICLE_READY, PROCEDURE_RUNNING, COMPLETED)

# ----------------------------------------------------------------- taxonomy
# Each failure phase maps onto the seven-category taxonomy that already exists.
# NOTHING NEW IS ADDED TO IT: the point of this module is that a failure is
# reported at the layer it happened in, not that there is a new vocabulary for
# layers. `acceptance` remains the only category that means the aircraft did
# something wrong, which is why exactly one phase maps to it.
PHASE_FAILURES: dict[str, tuple[str, str]] = {
    ENVIRONMENT_FAILED: (failures.ENVIRONMENT, failures.CODE_ENVIRONMENT_NOT_READY),
    # `environment` and not a category of its own: SITL failing to start is the
    # simulator not coming up, and the taxonomy already has a word for that.
    # `vehicle_readiness` is reserved for a vehicle that IS running and reports
    # itself unfit, which is a fact about the aircraft's configuration.
    VEHICLE_START_FAILED: (failures.ENVIRONMENT, failures.CODE_VEHICLE_START_FAILED),
    VEHICLE_NOT_READY: (failures.VEHICLE_READINESS, failures.CODE_PREARM),
    PROCEDURE_FAILED: (failures.PROCEDURE, failures.CODE_STEP_FAILED),
    ACCEPTANCE_FAILED: (failures.ACCEPTANCE, failures.CODE_CRITERION_FAILED),
}


@dataclass
class Transition:
    phase: str
    at: float                  # wall clock, seconds since the epoch
    since_start: float         # wall seconds since the lifecycle was created
    detail: str = ""

    def as_dict(self) -> dict:
        return {"phase": self.phase, "since_start_s": round(self.since_start, 2),
                "detail": self.detail}


@dataclass
class Lifecycle:
    """Where a simulation start-up got to, and how long each rung took.

    The timings are wall clock and are labelled as such. They are not metrics
    about the aircraft and never enter a verdict — they measure how long the
    host took to bring an environment up, which is a fact about the host.
    """

    label: str = ""
    started: float = field(default_factory=time.time)
    history: list[Transition] = field(default_factory=list)
    on_log: Optional[Callable[[str], None]] = None

    def __post_init__(self) -> None:
        if not self.history:
            self._record(CREATED, "")

    # -- transitions ------------------------------------------------------
    @property
    def phase(self) -> str:
        return self.history[-1].phase if self.history else CREATED

    @property
    def failed(self) -> bool:
        return self.phase in FAILED

    def _record(self, phase: str, detail: str) -> None:
        if phase not in PHASES:
            raise ValueError(f"{phase!r} is not a lifecycle phase")
        now = time.time()
        self.history.append(Transition(phase=phase, at=now,
                                       since_start=now - self.started,
                                       detail=detail))
        if self.on_log:
            self.on_log(f"[lifecycle] {phase}" + (f" — {detail}" if detail else ""))

    def enter(self, phase: str, detail: str = "") -> str:
        """Move to `phase`. A terminal phase is not left again.

        The guard is not tidiness. A start-up that failed and then recorded a
        later success would produce a history in which the failure is present
        and invisible, which is worse than not recording it at all.
        """
        if self.phase in TERMINAL:
            return self.phase
        self._record(phase, detail)
        return phase

    def fail(self, phase: str, detail: str) -> str:
        if phase not in FAILED:
            raise ValueError(f"{phase!r} is not a lifecycle failure phase")
        return self.enter(phase, detail)

    # -- readings ---------------------------------------------------------
    def reached(self, phase: str) -> bool:
        return any(entry.phase == phase for entry in self.history)

    def seconds_to(self, phase: str) -> Optional[float]:
        """Wall seconds from creation to the first time `phase` was entered."""
        for entry in self.history:
            if entry.phase == phase:
                return round(entry.since_start, 2)
        return None

    def failure(self) -> Optional[dict]:
        """The failure taxonomy entry for a lifecycle that stopped, or None."""
        if not self.failed:
            return None
        category, code = PHASE_FAILURES[self.phase]
        return {"category": category, "code": code, "phase": self.phase,
                "detail": self.history[-1].detail}

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "label": self.label,
            "phase": self.phase,
            "clock": "wall",
            "history": [entry.as_dict() for entry in self.history],
            # The three latencies worth naming. Each is None when the rung was
            # never reached, which is a different answer from zero.
            "timings_s": {
                "environment_ready": self.seconds_to(ENVIRONMENT_READY),
                "vehicle_ready": self.seconds_to(VEHICLE_READY),
                "total": round(self.history[-1].since_start, 2) if self.history else None,
            },
            "failure": self.failure(),
        }


# ------------------------------------------------------------------- probes
# Everything below answers a question about the machine. None of it knows what
# a procedure is, and none of it can change a verdict.

# `gz topic -l` answers in about two seconds on an idle host, so a probe budget
# under that would report "not ready" for the tool rather than for Gazebo.
GZ_PROBE_TIMEOUT = 8.0

# How long to wait for Gazebo to report a SERVED WORLD before giving up on the
# environment rung. Both launch paths use this one value, so the browser and
# tier 2 do not quietly disagree about how patient they are.
#
# Measured: the ten tier-2 models in this release reached ENVIRONMENT_READY
# between 2.08 s and 2.10 s on a warm cache. 120 s is therefore not a guess at
# the normal case — it is room for a cold asset cache and a large world, on a
# rung whose failure is diagnosed rather than merely waited out (see
# `wait_for_gazebo`'s `alive` argument).
ENVIRONMENT_READY_TIMEOUT = 120.0


def gazebo_serving(timeout: float = GZ_PROBE_TIMEOUT) -> tuple[bool, str]:
    """Is a Gazebo server actually serving a world?

    WHY THE TOPIC LIST AND NOT THE PROCESS
    ---------------------------------------
    A `gz sim` PID means `fork` succeeded. Gazebo holds one while it fails to
    resolve `model://runway`, prints "Unable to find uri", and exits — which is
    a real failure this project has already hit, documented in
    docker/container-env.sh. Its transport layer only advertises `/world/<name>/…`
    once a world is loaded and the server is stepping it, so the presence of
    such a topic is the strongest readiness statement available without adding
    a dependency.

    Returns (ready, detail). `detail` is written for a person reading a console.
    """
    try:
        result = subprocess.run(["gz", "topic", "-l"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True,
                                timeout=timeout, check=False)
    except FileNotFoundError:
        return False, "gz is not on PATH, so Gazebo readiness cannot be probed"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"gz topic -l did not answer within {timeout:g}s: {exc}"
    topics = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    worlds = sorted({t.split("/")[2] for t in topics
                     if t.startswith("/world/") and len(t.split("/")) > 2})
    if worlds:
        return True, f"Gazebo is serving world(s): {', '.join(worlds)}"
    if topics:
        return False, ("Gazebo transport is up but no world is loaded "
                       f"({len(topics)} topic(s), none under /world/)")
    return False, "no Gazebo transport topics — no simulator is serving"


def wait_for_gazebo(timeout: float, poll: float = 2.0,
                    alive: Optional[Callable[[], bool]] = None
                    ) -> tuple[bool, str]:
    """Poll `gazebo_serving` until it answers yes, the budget runs out, or the
    process this environment belongs to has gone.

    `alive` is what turns a timeout into a diagnosis. Waiting the full budget
    for a simulator that exited two seconds in reports "it did not become
    ready", which is true and useless; asking whether it is still there reports
    that it died, which is the sentence a person needs.
    """
    deadline = time.time() + timeout
    detail = "not probed"
    while time.time() < deadline:
        if alive is not None and not alive():
            return False, ("the simulator process is gone — Gazebo exited "
                           "before it served a world")
        ready, detail = gazebo_serving()
        if ready:
            return True, detail
        time.sleep(poll)
    return False, f"{detail} (waited {timeout:g}s)"


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Is something accepting TCP connections there?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def wait_for_sitl(port: int, timeout: float, host: str = "127.0.0.1",
                  poll: float = 0.5,
                  alive: Optional[Callable[[], bool]] = None
                  ) -> tuple[bool, str]:
    """Wait until SITL's serial0 TCP server accepts a connection.

    "SITL is running" and "SITL is operational" are different facts, and this
    is the boundary between them: the binary opens serial0 once it is past
    initialisation and ready for a ground station. `tests/sitl.py` has polled
    this port since the suite was written, and the audit named the asymmetry —
    the test path checked and the UI and tier-2 paths did not, so a tier-1 pass
    proved a lifecycle nothing else used. Same probe on both sides now.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if alive is not None and not alive():
            return False, ("the vehicle process is gone — SITL exited before "
                           f"it opened {host}:{port}")
        if port_open(port, host):
            return True, f"SITL is serving {host}:{port}"
        time.sleep(poll)
    return False, (f"SITL did not open {host}:{port} within {timeout:g}s — the "
                   f"process may exist, but it is not operational")


def vehicle_readiness(link) -> tuple[str, str]:
    """Which of the three vehicle rungs a live link has reached.

    Returns one of VEHICLE_STARTING / VEHICLE_READY / VEHICLE_NOT_READY with a
    sentence. The `known`/`ok` pairs on `VehicleState` are what make this
    possible: "not yet observed" and "observed unhealthy" are different states,
    and a single boolean could not tell them apart.
    """
    state = getattr(link, "state", None)
    if state is None or not getattr(state, "heartbeat_known", False):
        return VEHICLE_STARTING, "no heartbeat has arrived from the vehicle yet"
    if not getattr(state, "prearm_known", False):
        return VEHICLE_STARTING, ("the vehicle is talking but has not yet "
                                  "reported its pre-arm health")
    if not getattr(state, "prearm_ok", False):
        return VEHICLE_NOT_READY, ("the vehicle reports its pre-arm checks are "
                                   "not passing")
    return VEHICLE_READY, "heartbeat received and pre-arm checks pass"
