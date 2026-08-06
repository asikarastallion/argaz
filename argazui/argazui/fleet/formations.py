"""Spawn geometry — where each vehicle starts, in metres from the fleet origin.

PURE, AND DELIBERATELY SO
-------------------------
Nothing here reads a file, opens a socket or knows what a vehicle is. It turns
a formation name and a count into a list of offsets, and that is all. The
separation validator (L0) and the world composer (L2) both call it, which is
the reason it is its own module: if the validator computed spawn points one
way and the SDF generator another, a fleet could pass validation at 6 m
spacing and be built at 4 m.

AXES
----
ENU, in metres, with the fleet origin at (0, 0):

    east_m   +east
    north_m  +north
    up_m     +up, above the origin's altitude
    yaw_deg  compass heading, 0 = north, clockwise positive

`up_m` is a small positive number rather than zero. A model spawned exactly on
the ground plane starts intersecting it, and Gazebo answers that by launching
the vehicle into the air on the first physics step.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Enough to clear the ground plane without a visible drop when physics starts.
DEFAULT_UP_M = 0.2

FORMATIONS = ("grid", "line", "circle", "explicit")


class FormationError(ValueError):
    """A formation cannot be generated as asked."""


@dataclass(frozen=True)
class Point:
    """One spawn offset from the fleet origin."""

    east_m: float
    north_m: float
    up_m: float = DEFAULT_UP_M
    yaw_deg: float = 0.0

    def as_dict(self) -> dict:
        return {"east_m": round(self.east_m, 3), "north_m": round(self.north_m, 3),
                "up_m": round(self.up_m, 3), "yaw_deg": round(self.yaw_deg, 1)}


def distance_m(a: Point, b: Point) -> float:
    """Horizontal separation. Vertical is excluded on purpose.

    Two multirotors 0.2 m apart vertically and 0 m apart horizontally are in
    the same place as far as spawn collision physics is concerned. Counting
    the vertical offset would let a fleet declare adequate separation it does
    not have.
    """
    return math.hypot(a.east_m - b.east_m, a.north_m - b.north_m)


def closest_pair(points: list[Point]) -> tuple[float, int, int]:
    """(distance, index, index) of the two nearest spawn points.

    Returns (inf, -1, -1) for fewer than two points — one vehicle cannot
    violate a separation rule, and reporting 0.0 would say it had.
    """
    best, left, right = math.inf, -1, -1
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            d = distance_m(points[i], points[j])
            if d < best:
                best, left, right = d, i, j
    return best, left, right


# ------------------------------------------------------------------ generators
def grid(count: int, spacing_m: float, up_m: float = DEFAULT_UP_M,
         yaw_deg: float = 0.0) -> list[Point]:
    """`ceil(sqrt(N))` per side, row-major, centred on the origin.

    Centred rather than growing from the origin so that adding a vehicle moves
    the whole formation symmetrically instead of pushing it off the runway.
    """
    _check(count, spacing_m, "grid")
    side = math.ceil(math.sqrt(count))
    middle = (side - 1) / 2.0
    points = []
    for index in range(count):
        row, column = divmod(index, side)
        points.append(Point(east_m=(column - middle) * spacing_m,
                            north_m=(middle - row) * spacing_m,
                            up_m=up_m, yaw_deg=yaw_deg))
    return points


def line(count: int, spacing_m: float, up_m: float = DEFAULT_UP_M,
         yaw_deg: float = 0.0) -> list[Point]:
    """Along the east axis, centred on the origin."""
    _check(count, spacing_m, "line")
    middle = (count - 1) / 2.0
    return [Point(east_m=(index - middle) * spacing_m, north_m=0.0,
                  up_m=up_m, yaw_deg=yaw_deg)
            for index in range(count)]


def circle(count: int, radius_m: float, up_m: float = DEFAULT_UP_M) -> list[Point]:
    """Evenly spaced on a circle, every vehicle facing the centre.

    Vehicle `k` sits at bearing `360k/N` from the origin, so it faces the
    centre by heading in the opposite direction: `bearing + 180`.
    """
    if count < 1:
        raise FormationError("a circle formation needs at least one vehicle")
    if radius_m <= 0:
        raise FormationError(f"circle radius_m must be positive, got {radius_m!r}")
    points = []
    for index in range(count):
        bearing = 360.0 * index / count
        theta = math.radians(bearing)
        points.append(Point(east_m=radius_m * math.sin(theta),
                            north_m=radius_m * math.cos(theta),
                            up_m=up_m,
                            yaw_deg=(bearing + 180.0) % 360.0))
    return points


def _check(count: int, spacing_m: float, name: str) -> None:
    if count < 1:
        raise FormationError(f"a {name} formation needs at least one vehicle")
    if spacing_m <= 0:
        raise FormationError(f"{name} spacing_m must be positive, got {spacing_m!r}")


def generate(formation: str, count: int, spacing_m: float = 10.0,
             radius_m: float = 20.0, up_m: float = DEFAULT_UP_M) -> list[Point]:
    """Dispatch by name. `explicit` is not generated — the spec supplies it."""
    if formation == "grid":
        return grid(count, spacing_m, up_m)
    if formation == "line":
        return line(count, spacing_m, up_m)
    if formation == "circle":
        return circle(count, radius_m, up_m)
    if formation == "explicit":
        raise FormationError(
            "the 'explicit' formation is not generated: every vehicle must "
            "carry its own spawn block")
    raise FormationError(
        f"unknown formation {formation!r}; expected one of {', '.join(FORMATIONS)}")
