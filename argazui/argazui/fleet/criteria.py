"""Fleet-level acceptance: three outcomes, judged on time rather than extremes.

THREE OUTCOMES, AND WHY THE THIRD IS NOT OPTIONAL
-------------------------------------------------
    passed         evaluated, and it held
    failed         evaluated, and it did not
    not-measured   it could not be evaluated at all

A criterion that could not be evaluated must never render as a pass. That is
the same untruth as a skipped test counted green — the failure this whole
project exists to remove — and at fleet level it is easier to commit, because
six criteria rendering as a tidy row of ticks reads as a healthy run whether
or not anything was measured.

`not-measured` is therefore a first-class result with a mandatory reason, and
the report lists every claim the run did NOT make in plain words.

JUDGED ON TIME, NOT ON THE WORST SAMPLE
---------------------------------------
v1.1 settled this for attitude: a peak is one sample, and one sample is noise.
What separates a manoeuvre from a loss of control is how LONG the aircraft
stays outside its band. `StabilityWatch` has counted seconds-outside on the
vehicle's own clock ever since.

The same reasoning applies to a fleet, and this project's own data makes the
case. A three-vehicle run measured RTF min 0.265 with a median of 0.42. A run
that dipped to 0.265 for a fraction of a second and a run that sat there
throughout are different animals, and a criterion keyed on the minimum cannot
tell them apart — it would fail both, or pass both, depending on where the
line was drawn.

So every threshold criterion asks: **how many seconds was it outside, against
how many seconds of forgiveness the spec declared?**

EVERY SAMPLE CARRIES ITS OWN INTERVAL
-------------------------------------
Time outside is accumulated by weighting each sample by the gap to the
previous one, capped at `MAX_GAP_S`. This is `StabilityWatch`'s method and it
is used for the same two reasons: samples do not arrive evenly, and a gap in
the data must be able neither to manufacture nor to excuse time outside a
band.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

PASSED = "passed"
FAILED = "failed"
NOT_MEASURED = "not-measured"

OUTCOMES = (PASSED, FAILED, NOT_MEASURED)

# An interval longer than this is a gap in the data, not a long stretch in one
# state. Counted at this value rather than in full, exactly as StabilityWatch
# does, so a dropout can neither invent nor excuse time outside a band.
MAX_GAP_S = 1.0

# Seconds outside a band that a run forgives when the spec declares nothing.
# Every real run crosses a limit briefly — a vehicle taking the weight on its
# rotors, one heavy physics step — and a criterion with no forgiveness fails
# those. Declared per fleet; this is only the fallback.
DEFAULT_TOLERANCE_S = 1.0


@dataclass
class Criterion:
    """One fleet-level claim, its verdict, and what permitted it."""

    id: str
    title: str
    outcome: str
    detail: str = ""
    # Which measurement allows this claim to be made at all. Copied into the
    # report so a reader can tell a measured claim from a configured one
    # without leaving the run directory.
    authorised_by: str = ""
    # Why nothing could be judged. Mandatory when outcome is not-measured.
    reason: str = ""
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"{self.id}: unknown outcome {self.outcome!r}; "
                             f"expected one of {', '.join(OUTCOMES)}")
        if self.outcome == NOT_MEASURED and not self.reason:
            raise ValueError(
                f"{self.id}: a not-measured criterion needs a reason. An "
                f"unexplained absence reads as an oversight; a stated one is "
                f"a result.")

    @property
    def passed(self) -> bool:
        return self.outcome == PASSED

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "outcome": self.outcome,
                "detail": self.detail, "authorised_by": self.authorised_by,
                "reason": self.reason, "evidence": dict(self.evidence)}


def time_outside(samples: list, predicate, max_gap_s: float = MAX_GAP_S) -> tuple:
    """(seconds outside, seconds observed) for a series of (t, value).

    `samples` must be (t, value) in a single consistent time base — the caller
    states which. The first sample carries no time, because an interval nobody
    observed is the only honest weight for it.
    """
    outside = 0.0
    observed = 0.0
    previous_t: Optional[float] = None
    for t, value in samples:
        if previous_t is not None and t > previous_t:
            dt = min(t - previous_t, max_gap_s)
            observed += dt
            if predicate(value):
                outside += dt
        previous_t = t
    return outside, observed


def _band_criterion(cid: str, title: str, samples: list, predicate,
                    tolerance_s: float, units: str, authorised_by: str,
                    describe_outside: str,
                    not_measured_reason: str = "",
                    min_seconds: float = 0.0) -> Criterion:
    """The shared shape of every threshold criterion."""
    if not samples:
        return Criterion(cid, title, NOT_MEASURED, authorised_by=authorised_by,
                         reason=not_measured_reason
                         or "no samples were recorded")

    outside, observed = time_outside(samples, predicate)
    if observed <= 0:
        return Criterion(cid, title, NOT_MEASURED, authorised_by=authorised_by,
                         reason=f"{len(samples)} sample(s) arrived but they "
                                f"span no time, so nothing could be judged")
    if observed < min_seconds:
        return Criterion(
            cid, title, NOT_MEASURED, authorised_by=authorised_by,
            reason=f"only {observed:.1f}s of data ({units}); at least "
                   f"{min_seconds:g}s is needed before a verdict means "
                   f"anything")

    held = outside <= tolerance_s
    detail = (f"{outside:.2f}s {describe_outside} out of {observed:.1f}s "
              f"observed ({units}), against a {tolerance_s:g}s tolerance")
    return Criterion(cid, title, PASSED if held else FAILED, detail=detail,
                     authorised_by=authorised_by,
                     evidence={"seconds_outside": round(outside, 3),
                               "seconds_observed": round(observed, 3),
                               "tolerance_s": tolerance_s,
                               "samples": len(samples)})


# ------------------------------------------------------------------- the six
def separation_criterion(rows: list, min_separation_m: float,
                         measuring: bool, authorised_by: str = "",
                         refusal_reason: str = "",
                         tolerance_s: float = DEFAULT_TOLERANCE_S) -> Criterion:
    """Criterion 2: pairwise separation held for the run.

    `rows` are (t, distance) in SIMULATED seconds — the stamp on the world
    state the positions came from. Time outside is therefore vehicle time,
    which is what the aircraft experienced.
    """
    title = f"minimum pairwise separation ≥ {min_separation_m:g} m"
    if not measuring:
        return Criterion(
            "separation", title, NOT_MEASURED,
            authorised_by=authorised_by,
            reason=refusal_reason or
                   "the separation monitor did not emit, so no "
                   "relative-geometry claim was made")
    return _band_criterion(
        "separation", title, rows,
        predicate=lambda d: d < min_separation_m,
        tolerance_s=tolerance_s, units="simulated time",
        authorised_by=authorised_by,
        describe_outside=f"below {min_separation_m:g} m",
        not_measured_reason=refusal_reason)


def rtf_criterion(samples: list, floor: float, available: bool,
                  authorised_by: str = "", absence_reason: str = "",
                  tolerance_s: float = DEFAULT_TOLERANCE_S) -> Criterion:
    """Criterion 4: the simulation kept up.

    `samples` are (t, rtf) in WALL seconds, and that is deliberate: real-time
    factor is the ratio of simulated to wall time, so "how long was it
    degraded" is a wall-clock question. Stated here so the report can say
    which clock it counted on.
    """
    title = f"real-time factor stayed at or above {floor:g}"
    if not available:
        return Criterion("rtf", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason=absence_reason or
                                "no physics server was running, so there was "
                                "no real-time factor to measure")
    return _band_criterion(
        "rtf", title, samples, predicate=lambda r: r < floor,
        tolerance_s=tolerance_s, units="wall-clock time",
        authorised_by=authorised_by,
        describe_outside=f"below {floor:g}",
        not_measured_reason=absence_reason)


def altitude_criterion(reached: dict, target_m: float,
                       authorised_by: str = "") -> Criterion:
    """Criterion 1: every vehicle reached the target altitude.

    `reached` maps vehicle id -> highest altitude seen, or None where nothing
    was observed. A vehicle with no data makes the whole criterion
    not-measured rather than failing it: "it did not climb" and "nobody
    watched" are different statements.
    """
    title = f"every vehicle reached {target_m:g} m"
    if not reached:
        return Criterion("altitude", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason="no vehicle altitudes were recorded")
    unseen = sorted(v for v, a in reached.items() if a is None)
    if unseen:
        return Criterion("altitude", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason=f"no altitude was observed for "
                                f"{', '.join(unseen)}, so the fleet-level "
                                f"claim cannot be made")
    short = {v: a for v, a in reached.items() if a < target_m}
    detail = ", ".join(f"{v} {a:.1f} m" for v, a in sorted(reached.items()))
    return Criterion("altitude", title, FAILED if short else PASSED,
                     detail=detail, authorised_by=authorised_by,
                     evidence={"reached": {k: round(v, 2)
                                           for k, v in reached.items()},
                               "target_m": target_m,
                               "short": sorted(short)})


def per_vehicle_criterion(results: dict, authorised_by: str = "") -> Criterion:
    """Criterion 3: every vehicle passed its own acceptance criteria.

    `results` maps vehicle id -> outcome string from the procedure engine
    (`passed` / `failed` / `error`), or None where no procedure ran. A vehicle
    that ran nothing contributes not-measured, never a pass.
    """
    title = "every vehicle passed its own acceptance criteria"
    if not results:
        return Criterion("per_vehicle", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason="no procedure ran on any vehicle, so nothing "
                                "was asserted about any of them")
    unrun = sorted(v for v, o in results.items() if not o)
    if unrun:
        return Criterion("per_vehicle", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason=f"no procedure ran on {', '.join(unrun)}, so "
                                f"the fleet-level claim cannot be made")
    bad = sorted(v for v, o in results.items() if o != "passed")
    detail = ", ".join(f"{v}: {o}" for v, o in sorted(results.items()))
    return Criterion("per_vehicle", title, FAILED if bad else PASSED,
                     detail=detail, authorised_by=authorised_by,
                     evidence={"results": dict(results), "failed": bad})


def dataflash_criterion(logs: dict, authorised_by: str = "") -> Criterion:
    """Criterion 5: every vehicle produced a retrievable dataflash log."""
    title = "every vehicle produced a .BIN that could be retrieved"
    if not logs:
        return Criterion("dataflash", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason="no vehicle working directories were inspected")
    missing = sorted(v for v, path in logs.items() if not path)
    detail = ", ".join(f"{v}: {p or 'none'}" for v, p in sorted(logs.items()))
    return Criterion("dataflash", title, FAILED if missing else PASSED,
                     detail=detail, authorised_by=authorised_by,
                     evidence={"missing": missing})


def teardown_criterion(report, authorised_by: str = "") -> Criterion:
    """Criterion 6: nothing was left running and the lease went back."""
    title = "no orphan processes, all port leases released"
    if report is None:
        return Criterion("teardown", title, NOT_MEASURED,
                         authorised_by=authorised_by,
                         reason="the fleet was never torn down under "
                                "supervision, so nothing observed its exit")
    orphans = list(getattr(report, "orphans", []) or [])
    released = bool(getattr(report, "lease_released", False))
    problems = []
    if orphans:
        problems.append(f"{len(orphans)} orphan process(es): {orphans}")
    if not released:
        problems.append("the port lease was not released")
    return Criterion("teardown", title, FAILED if problems else PASSED,
                     detail="; ".join(problems) or
                            "every process exited and the lease was released",
                     authorised_by=authorised_by,
                     evidence={"orphans": orphans,
                               "lease_released": released})


# ------------------------------------------------------------------- verdict
FLEET_PASSED = "PASSED"
FLEET_FAILED = "FAILED"
FLEET_INCOMPLETE = "INCOMPLETE"


def fleet_verdict(criteria: list) -> str:
    """The run's overall answer.

    INCOMPLETE is separate from PASSED on purpose. A run where everything that
    WAS measured held, but half the criteria could not be evaluated, has not
    passed — it has not been tested. Collapsing the two is precisely the
    unearned tick this project exists to remove.
    """
    if not criteria:
        return FLEET_INCOMPLETE
    if any(c.outcome == FAILED for c in criteria):
        return FLEET_FAILED
    if any(c.outcome == NOT_MEASURED for c in criteria):
        return FLEET_INCOMPLETE
    return FLEET_PASSED
