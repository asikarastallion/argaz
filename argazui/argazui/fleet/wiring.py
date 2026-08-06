"""Proof that N autopilots are wired to N models, and not to each other.

THE HOLE THIS CLOSES
--------------------
The allocator stops two vehicles sharing an FDM port before launch. It cannot
stop a *mis-wiring*: `ArduPilotPlugin` learns where to send state from
whichever socket sends to it first (`get_client_address`, ArduPilotPlugin.cc
:1434), so if v1's SITL were pointed at v2's port, the pair would run happily
with v1's servos driving model 2.

Nothing in the port map, the lease file or the generated SDF would show it.
Both vehicles would fly. The separation trace would be a smooth, plausible
curve describing a fleet that does not exist.

THE CHECK
---------
    1. record every model's pose in Gazebo
    2. command exactly ONE vehicle to move
    3. re-read every model's pose
    4. assert the commanded model moved, and no other moved beyond noise
    5. repeat per vehicle

It runs at FLEET READY, before any acceptance criterion is evaluated, and a
failure ABORTS the fleet rather than warning. Every measurement taken after a
mis-wire is meaningless, and a report that averaged them would be worse than
no report at all.

WHY THE POSE COMES FROM GAZEBO AND THE COMMAND GOES OVER MAVLINK
----------------------------------------------------------------
Deliberately opposite ends. Reading the vehicle's own MAVLink position back
would prove only that SITL agrees with itself — a mis-wired vehicle reports a
perfectly consistent position for the model it is actually driving. The
question is whether the autopilot ArgazUI *addressed* moved the model ArgazUI
*placed*, so the command and the observation have to come from different
sides.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# How far a model may move while "stationary". Gazebo models settle, drift on
# their suspension and jitter at rest; this is comfortably above that and far
# below any commanded movement.
NOISE_M = 0.30

# How far the commanded model must move to count as having responded.
MOVED_M = 1.0


class WiringError(RuntimeError):
    """The fleet is mis-wired, or the check could not be carried out."""


@dataclass
class Pose:
    x: float
    y: float
    z: float

    def distance(self, other: "Pose") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2
                + (self.z - other.z) ** 2) ** 0.5

    def as_dict(self) -> dict:
        return {"x": round(self.x, 3), "y": round(self.y, 3),
                "z": round(self.z, 3)}


def parse_pose(text: str) -> Optional[Pose]:
    """Pull the first position block out of `gz model -m <name> --pose`.

        [Pose]
          [-5 5 0.19 0 0 0]

    Two shapes are accepted because the tool's output has varied: a bracketed
    six-number pose line, and a `position { x: ... }` block.
    """
    block = re.search(r"position\s*\{([^}]*)\}", text, re.DOTALL)
    if block:
        body = block.group(1)
        values = {}
        for axis in ("x", "y", "z"):
            found = re.search(rf"\b{axis}:\s*(-?\d+\.?\d*(?:[eE][-+]?\d+)?)", body)
            values[axis] = float(found.group(1)) if found else 0.0
        return Pose(**values)

    for line in text.splitlines():
        numbers = re.findall(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?", line)
        if len(numbers) >= 6 and "[" in line:
            return Pose(float(numbers[0]), float(numbers[1]), float(numbers[2]))
    return None


def read_pose(model: str, env: Optional[dict] = None,
              timeout: float = 10.0) -> Optional[Pose]:
    try:
        result = subprocess.run(["gz", "model", "-m", model, "--pose"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return parse_pose(result.stdout)


@dataclass
class VehicleWiring:
    vehicle: str
    moved_m: float = 0.0
    others: dict = field(default_factory=dict)
    # Each model's own movement over the same window with NO command given.
    # The band a stray is judged against is derived from this rather than
    # assumed, because a hovering vehicle is not stationary.
    floors: dict = field(default_factory=dict)
    ok: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {"vehicle": self.vehicle, "moved_m": round(self.moved_m, 3),
                "others": {k: round(v, 3) for k, v in self.others.items()},
                "floors": dict(self.floors),
                "ok": self.ok, "reason": self.reason}


@dataclass
class WiringReport:
    checks: list = field(default_factory=list)
    ok: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reason": self.reason,
                "checks": [c.as_dict() for c in self.checks]}


def verify_wiring(vehicle_ids: list, move: Callable[[str], None],
                  settle_s: float = 4.0,
                  pose_reader: Callable = read_pose,
                  noise_m: float = NOISE_M,
                  moved_m: float = MOVED_M,
                  measure_floor: bool = True,
                  floor_margin: float = 3.0) -> WiringReport:
    """Command each vehicle in turn and check that only its model moves.

    `move(vehicle_id)` must produce an unambiguous movement of that vehicle —
    an altitude step is the usual choice, because it is large, fast and does
    not depend on a position estimate the way a horizontal move does.

    THE NOISE BAND IS MEASURED, NOT ASSUMED
    ---------------------------------------
    The first version used a fixed 0.30 m band and reported a mis-wire that
    was not one. A vehicle already hovering from its own earlier check drifted
    0.47 m in eight seconds while station-keeping — real movement, caused by
    the aircraft holding position rather than by anyone's command.

    "Stationary" is therefore not a constant. Before each vehicle is
    commanded, every model's movement is observed over the same settle window
    with NO command given; that is the floor for those conditions. A stray is
    movement beyond `floor_margin` times its own floor, or beyond `noise_m`,
    whichever is larger.

    This keeps the check strict where it matters — an idle model on the ground
    has a floor near zero, so a mis-wire that moved it metres is still caught —
    while not accusing an airframe of being mis-wired for doing its job.
    """
    report = WiringReport()

    for vehicle_id in vehicle_ids:
        # -- the floor: how much does each model move on its own, right now?
        floors = {vid: 0.0 for vid in vehicle_ids}
        if measure_floor:
            quiet_before = {vid: pose_reader(vid) for vid in vehicle_ids}
            if any(p is None for p in quiet_before.values()):
                report.ok = False
                report.reason = ("could not read poses while measuring the "
                                 "stationary noise floor")
                return report
            time.sleep(settle_s)
            quiet_after = {vid: pose_reader(vid) for vid in vehicle_ids}
            for vid in vehicle_ids:
                if quiet_before[vid] and quiet_after[vid]:
                    floors[vid] = quiet_before[vid].distance(quiet_after[vid])

        before = {vid: pose_reader(vid) for vid in vehicle_ids}
        missing = [vid for vid, pose in before.items() if pose is None]
        if missing:
            report.ok = False
            report.reason = (f"could not read the pose of {', '.join(missing)} "
                             f"from Gazebo; the wiring check cannot be carried "
                             f"out and the fleet must not be trusted")
            return report

        move(vehicle_id)
        time.sleep(settle_s)

        after = {vid: pose_reader(vid) for vid in vehicle_ids}
        missing = [vid for vid, pose in after.items() if pose is None]
        if missing:
            report.ok = False
            report.reason = (f"lost the pose of {', '.join(missing)} during the "
                             f"wiring check")
            return report

        check = VehicleWiring(vehicle=vehicle_id)
        check.moved_m = before[vehicle_id].distance(after[vehicle_id])
        for other in vehicle_ids:
            if other == vehicle_id:
                continue
            check.others[other] = before[other].distance(after[other])

        check.floors = {k: round(v, 3) for k, v in floors.items()}
        limits = {k: max(noise_m, floors.get(k, 0.0) * floor_margin)
                  for k in check.others}
        strays = {k: v for k, v in check.others.items() if v > limits[k]}

        if check.moved_m < moved_m:
            check.ok = False
            check.reason = (
                f"commanded {vehicle_id} but its model moved only "
                f"{check.moved_m:.2f} m (needed {moved_m:g} m). Either the "
                f"command did not take effect, or this autopilot is driving a "
                f"different model.")
        elif strays:
            check.ok = False
            check.reason = (
                f"commanded {vehicle_id} alone, but "
                + ", ".join(f"{k} moved {v:.2f} m against a {limits[k]:.2f} m "
                            f"limit (its own idle drift was "
                            f"{floors.get(k, 0.0):.2f} m)"
                            for k, v in strays.items())
                + ". One autopilot is driving more than one model, or two "
                  "share an FDM port.")
        else:
            check.ok = True
            widest = max(check.others.values()) if check.others else 0.0
            check.reason = (
                f"{vehicle_id} moved {check.moved_m:.2f} m; the widest other "
                f"movement was {widest:.2f} m, inside its measured limit")
        report.checks.append(check)

    report.ok = bool(report.checks) and all(c.ok for c in report.checks)
    if not report.checks:
        report.reason = "no vehicles were checked"
    elif report.ok:
        report.reason = (f"{len(report.checks)} vehicles each moved their own "
                         f"model and nobody else's")
    else:
        report.reason = "; ".join(c.reason for c in report.checks if not c.ok)
    return report
