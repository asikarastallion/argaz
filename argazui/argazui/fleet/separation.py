"""Pairwise separation — and the conditions under which it refuses to answer.

THE REFUSAL IS THE FEATURE
--------------------------
Separation is the headline measurement of a fleet: four vehicles airborne, the
minimum pairwise distance recorded over the whole run, a violation failing
acceptance. It is also the measurement easiest to fake, because computing a
distance from two positions always produces a number.

That number means something only if the two positions were sampled at the same
instant. Under Gazebo they were: the physics server drives every SITL in
lockstep off one clock. Without Gazebo they were not — each SITL free-runs,
their clocks drift apart (measured; see docs/fleet-clock-drift.md), and
subtracting two positions taken at unknown different moments does not give a
distance. It gives a plausible-looking number with no defined error.

So in SITL-only mode this monitor **emits nothing at all** and states why, and
the fleet report prints that reason where the separation section would be.
An empty separation.csv with a stated reason is an honest artefact. A
populated one whose time base is undefined is a lie that passes review.

    "we did not measure this"  and  "we measured it and it was fine"
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Reported alongside every violation so a reader can tell a graze from a
# collision course without opening the CSV.
WARN_FACTOR = 1.5


@dataclass(frozen=True)
class Fix:
    """One vehicle's position at one instant, in metres from the fleet origin."""

    vehicle_id: str
    east_m: float
    north_m: float
    up_m: float
    t_s: float


@dataclass
class PairDistance:
    a: str
    b: str
    distance_m: float
    t_s: float

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b,
                "distance_m": round(self.distance_m, 3),
                "t_s": round(self.t_s, 3)}


@dataclass
class SeparationResult:
    """What one sampling round produced, or why it produced nothing."""

    measured: bool
    reason: str = ""
    pairs: list = field(default_factory=list)
    minimum_m: Optional[float] = None
    violation: bool = False
    warning: bool = False

    def as_dict(self) -> dict:
        return {"measured": self.measured, "reason": self.reason,
                "pairs": [p.as_dict() for p in self.pairs],
                "minimum_m": (None if self.minimum_m is None
                              else round(self.minimum_m, 3)),
                "violation": self.violation, "warning": self.warning}


class SeparationMonitor:
    """Pairwise distances at 2 Hz — when, and only when, they mean something.

    `time_base_valid=False` makes every call return `measured=False` with the
    stated reason and no pairs. There is deliberately no override: a caller
    that wants numbers from an undefined time base is asking for the exact
    failure this class exists to prevent.
    """

    def __init__(self, min_separation_m: float, time_base_valid: bool,
                 reason: str = "") -> None:
        self.min_separation_m = float(min_separation_m)
        self.time_base_valid = bool(time_base_valid)
        self.reason = reason if not time_base_valid else ""
        if not time_base_valid and not self.reason:
            raise ValueError(
                "refusing to measure separation requires a stated reason; it "
                "is printed in the fleet report where the numbers would be")
        self.history: list = []
        self.minimum_seen: Optional[float] = None
        self.violations: list = []

    # ------------------------------------------------------------------ query
    @property
    def measuring(self) -> bool:
        return self.time_base_valid

    def sample(self, fixes: list) -> SeparationResult:
        """One round. `fixes` is every vehicle's current position."""
        if not self.time_base_valid:
            return SeparationResult(measured=False, reason=self.reason)
        if len(fixes) < 2:
            return SeparationResult(
                measured=False,
                reason=f"only {len(fixes)} vehicle position(s) available; "
                       f"separation needs at least two")

        pairs = []
        for i in range(len(fixes)):
            for j in range(i + 1, len(fixes)):
                a, b = fixes[i], fixes[j]
                pairs.append(PairDistance(
                    a=a.vehicle_id, b=b.vehicle_id,
                    distance_m=math.dist((a.east_m, a.north_m, a.up_m),
                                         (b.east_m, b.north_m, b.up_m)),
                    t_s=max(a.t_s, b.t_s)))

        closest = min(pairs, key=lambda p: p.distance_m)
        violation = closest.distance_m < self.min_separation_m
        warning = (not violation
                   and closest.distance_m < self.min_separation_m * WARN_FACTOR)

        self.history.extend(pairs)
        if self.minimum_seen is None or closest.distance_m < self.minimum_seen:
            self.minimum_seen = closest.distance_m
        if violation:
            self.violations.append(closest)

        return SeparationResult(measured=True, pairs=pairs,
                                minimum_m=closest.distance_m,
                                violation=violation, warning=warning)

    # ----------------------------------------------------------------- report
    def verdict(self) -> dict:
        """The fleet-level acceptance answer for criterion 2.

        `passed` is None — not True — when nothing was measured. A criterion
        that was never evaluated has no verdict, and reporting one as passed
        is how an unearned tick gets into a table.
        """
        if not self.time_base_valid:
            return {"measured": False, "passed": None, "reason": self.reason,
                    "minimum_m": None, "violations": 0,
                    "claim": "no relative-geometry claim was made"}
        if self.minimum_seen is None:
            return {"measured": False, "passed": None,
                    "reason": "no position pairs were ever sampled",
                    "minimum_m": None, "violations": 0,
                    "claim": "no relative-geometry claim was made"}
        return {"measured": True,
                "passed": not self.violations,
                "reason": "",
                "minimum_m": round(self.minimum_seen, 3),
                "min_separation_m": self.min_separation_m,
                "violations": len(self.violations),
                "claim": (f"minimum pairwise separation "
                          f"{self.minimum_seen:.2f} m against a "
                          f"{self.min_separation_m:g} m limit")}

    def csv_rows(self) -> list:
        """`separation.csv` content. Empty when nothing was measured."""
        return [(round(p.t_s, 3), f"{p.a}-{p.b}", round(p.distance_m, 3))
                for p in self.history]
