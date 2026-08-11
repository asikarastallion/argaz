"""Quantitative flight metrics — measured quantities, never a verdict.

WHAT A METRIC IS, AND WHAT IT IS NOT
------------------------------------
A metric is a number derived from evidence a flight already produced: how long
the climb took, how far the achieved attitude lagged the demanded one, how fast
the airframe was turning at its worst. It is not an acceptance criterion and it
cannot fail a run.

That separation is deliberate and it is the same one advisories already have:

    expect:      decides pass/fail.        Declared per procedure. CI goes red.
    advisories:  health findings.          Thresholds from ArduPilot's own docs.
    metrics:     measured quantities.      No threshold at all, on their own.

A metric only acquires a threshold when it is compared against a baseline —
see regression.py. Giving it one here would have quietly turned this module
into a second acceptance system with limits nobody declared in a procedure.

WHY THIS SMALL SET
------------------
Every number in `CATALOGUE` answers a question someone actually asks of a
flight, and each names the signal it came from. A module that computed
everything computable would produce a wall of numbers with no stated meaning,
and the first regression comparison would drown in noise from quantities nobody
chose to watch.

IDENTITY, BECAUSE THESE GET COMPARED
------------------------------------
A metric is identified by `key` plus `procedure`. Run-scoped metrics come from
the dataflash log, which covers the whole session, and carry no procedure;
procedure-scoped ones name the procedure they belong to, because "time to
target altitude" means nothing without saying whose target.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

# 2 (v1.6 corrective): every metric now states the CLOCK it was measured on
#   and the WINDOW it was measured over. Both were previously implicit and both
#   were wrong somewhere — `mode_transition_latency_max` was host wall-clock
#   seconds sitting in a table of vehicle-clock seconds, and
#   `time_outside_attitude_envelope` covered the whole log while the criterion
#   of the same name covered one procedure. Nothing that existed moved.
SCHEMA = 2

# ---------------------------------------------------------------- clocks
# WHICH CLOCK A NUMBER IS ON IS PART OF THE NUMBER
# ------------------------------------------------
# Under SITL speedup a wall-clock second is not a second of flight, so the same
# manoeuvre measured on the two clocks gives answers that differ by the speedup
# factor. A metric that did not say which one it used could be compared against
# a baseline taken at a different speedup and report a degradation caused by a
# command-line argument.
#
#   VEHICLE  the aircraft's own clock — dataflash TimeUS, or ATTITUDE
#            .time_boot_ms live. This is the right base for anything that
#            describes what the AIRCRAFT did.
#   WALL     this process's clock. Correct only for a quantity that genuinely
#            describes host execution, and no metric in the catalogue below is
#            one; it is kept as a value so a fallback can be honest about
#            having been taken.
CLOCK_VEHICLE, CLOCK_WALL = "vehicle", "wall"

# ---------------------------------------------------------------- windows
# The stretch of the flight a metric was measured over. Stated for the same
# reason the clock is: `attitude_stable` (an acceptance criterion) is scoped to
# one procedure, and a metric over the whole log that shares its name and its
# bands would look like it contradicted it.
#
#   PROCEDURE  from the first step of a procedure to its last criterion
#   ARMED      the armed interval(s) the dataflash log records — the flight
#   LOG        every record in the log, including time on the ground
WINDOW_PROCEDURE, WINDOW_ARMED, WINDOW_LOG = "procedure", "armed", "log"

# Direction that is NOT a regression. Every metric here reads better lower, but
# the field is explicit rather than assumed: a comparator that hard-codes
# "smaller is better" silently reports the wrong verdict the first time a
# metric like "altitude held" is added.
LOWER, HIGHER = "lower", "higher"

# Longest interval between two log samples that is counted at face value, in
# seconds. Beyond it the gap is a hole in the log rather than a long stretch of
# flight in one attitude, and counting it in full would let a logging dropout
# manufacture — or excuse — time outside an envelope. Same reasoning, and the
# same number, as `StabilityWatch.MAX_GAP`.
MAX_SAMPLE_GAP_S = 0.5

# key -> what it measures. `source` names the log message or the recorded step
# the number is derived from, so a reader can go back to the evidence;
# `clock` and `window` say on what time base and over what stretch of the
# flight, because neither is guessable from a unit of seconds.
CATALOGUE: dict[str, dict] = {
    "time_to_target_alt": {
        "unit": "s", "better": LOWER, "scope": "procedure",
        "clock": CLOCK_VEHICLE, "window": WINDOW_ARMED,
        "source": "POS.RelHomeAlt against the altitude the procedure asked for, "
                  "measured from arming on the log's own clock",
        "label": {"en": "Time to target altitude",
                  "tr": "Hedef irtifaya ulasma suresi"},
    },
    "tracking_error_roll_max": {
        "clock": CLOCK_VEHICLE, "window": WINDOW_LOG,
        "unit": "deg", "better": LOWER, "scope": "run",
        "source": "ATT.DesRoll - ATT.Roll",
        "label": {"en": "Peak roll tracking error",
                  "tr": "En yuksek yatis takip hatasi"},
    },
    "tracking_error_pitch_max": {
        "clock": CLOCK_VEHICLE, "window": WINDOW_LOG,
        "unit": "deg", "better": LOWER, "scope": "run",
        "source": "ATT.DesPitch - ATT.Pitch",
        "label": {"en": "Peak pitch tracking error",
                  "tr": "En yuksek yunuslama takip hatasi"},
    },
    "tracking_error_roll_rms": {
        "clock": CLOCK_VEHICLE, "window": WINDOW_LOG,
        "unit": "deg", "better": LOWER, "scope": "run",
        "source": "ATT.DesRoll - ATT.Roll, root mean square",
        "label": {"en": "RMS roll tracking error",
                  "tr": "Yatis takip hatasi (RMS)"},
    },
    "tracking_error_pitch_rms": {
        "clock": CLOCK_VEHICLE, "window": WINDOW_LOG,
        "unit": "deg", "better": LOWER, "scope": "run",
        "source": "ATT.DesPitch - ATT.Pitch, root mean square",
        "label": {"en": "RMS pitch tracking error",
                  "tr": "Yunuslama takip hatasi (RMS)"},
    },
    "peak_angular_rate": {
        "clock": CLOCK_VEHICLE, "window": WINDOW_LOG,
        "unit": "deg/s", "better": LOWER, "scope": "run",
        "source": "IMU.GyrX/GyrY/GyrZ, largest magnitude on any axis",
        "label": {"en": "Peak angular rate", "tr": "En yuksek acisal hiz"},
    },
    "time_outside_attitude_envelope": {
        "unit": "s", "better": LOWER, "scope": "run",
        "clock": CLOCK_VEHICLE, "window": WINDOW_ARMED,
        # WINDOW_ARMED, and not WINDOW_LOG as it was until the v1.6 corrective
        # release. The `attitude_stable` acceptance criterion measures one
        # procedure; this metric measured every record in the log including
        # time parked on the runway, so the two could report 0.0 s and 40 s for
        # the same flight and both be right. Scoped to the armed interval they
        # answer near enough the same question for a reader to compare them,
        # and `window` states the residual difference rather than hiding it.
        "source": "ATT.Roll/ATT.Pitch against the envelope the procedure "
                  "declared, over the log's armed interval(s)",
        "label": {"en": "Time outside the attitude envelope",
                  "tr": "Tutum zarfinin disinda gecen sure"},
    },
    "mode_transition_latency_max": {
        "unit": "s", "better": LOWER, "scope": "procedure",
        "clock": CLOCK_VEHICLE, "window": WINDOW_PROCEDURE,
        # ON THE VEHICLE'S CLOCK, and not the host's as it was until the v1.6
        # corrective release. It is the only metric derived from a recorded
        # STEP rather than from the log, and the step was timed with
        # `time.time()` — so at speedup 5 it read one fifth of the flight time
        # it claimed to describe, and comparing two runs flown at different
        # speedups reported a regression caused by a command-line argument.
        # `StepResult.vehicle_seconds` is the same interval on the aircraft's
        # clock; where that clock was not running the metric says so and falls
        # back, rather than quietly mixing the two.
        "source": "the duration of each set_mode step on the vehicle's own "
                  "clock, ending when the heartbeat confirms the new mode by "
                  "number",
        "label": {"en": "Slowest mode transition",
                  "tr": "En yavas mod gecisi"},
    },
}


@dataclass
class Metric:
    """One measured quantity, with everything needed to read it correctly."""

    key: str
    value: Optional[float]        # None means "not measurable here", see `detail`
    unit: str
    better: str
    source: str
    scope: str = "run"
    # Which clock the number is on, and which stretch of the flight it covers.
    # Both travel WITH the value rather than being looked up from the
    # catalogue, because a run archived today is read by a comparison written
    # later, and a metric whose meaning has to be resolved against the current
    # code is a metric that changes meaning when the code does.
    clock: str = CLOCK_VEHICLE
    window: str = WINDOW_LOG
    procedure: str = ""
    detail: str = ""

    @property
    def identity(self) -> tuple[str, str]:
        """What makes two metrics the same metric, across runs."""
        return (self.key, self.procedure)

    def as_dict(self) -> dict:
        out = asdict(self)
        composed = f"{self.key}@{self.procedure}" if self.procedure else self.key
        out["identity"] = composed
        # The same string under the name the traceability chain uses for every
        # other link (v1.5). `identity` stays because runs recorded since v1.3
        # carry it and a reader of those must keep working.
        out["metric_id"] = composed
        return out

    def label(self, lang: str = "en") -> str:
        entry = CATALOGUE.get(self.key, {}).get("label", {})
        return entry.get(lang) or entry.get("en") or self.key


def _metric(key: str, value: Optional[float], *, procedure: str = "",
            detail: str = "", clock: Optional[str] = None,
            window: Optional[str] = None) -> Metric:
    spec = CATALOGUE[key]
    return Metric(key=key, value=value, unit=spec["unit"], better=spec["better"],
                  source=spec["source"], scope=spec["scope"],
                  clock=clock or spec["clock"], window=window or spec["window"],
                  procedure=procedure, detail=detail)


# --------------------------------------------------------------------- context
def context_from_result(result: dict) -> dict:
    """What the procedures asked for, pulled out of a run's own result.json.

    The dataflash log knows what the aircraft did; it does not know what it was
    told to do. Target altitudes, the declared attitude envelope and the
    measured mode-change durations all live in the run record, and reading them
    here is what keeps `flightlog.py` free of any knowledge of procedures.
    """
    targets: list[dict] = []
    transitions: list[dict] = []
    envelope: dict = {}

    for entry in result.get("procedures") or []:
        procedure = entry.get("procedure") or ""
        outcome = entry.get("result") or {}

        values = entry.get("values") or outcome.get("values") or {}
        if entry.get("role") == "takeoff" and values.get("alt") is not None:
            try:
                targets.append({"procedure": procedure, "alt_m": float(values["alt"])})
            except (TypeError, ValueError):
                pass

        for step in outcome.get("steps") or []:
            if step.get("kind") == "set_mode" and step.get("status") == "passed":
                # The vehicle's own clock where the runner could measure it,
                # this process's only where it could not — and the fallback is
                # recorded rather than silently mixed into the same number. A
                # step recorded before `vehicle_seconds` existed has only the
                # wall figure, and says so.
                vehicle = step.get("vehicle_seconds")
                transitions.append({
                    "procedure": procedure,
                    "label": step.get("label") or "set_mode",
                    "seconds": float(vehicle if vehicle is not None
                                     else (step.get("seconds") or 0.0)),
                    "clock": (CLOCK_VEHICLE if vehicle is not None
                              else CLOCK_WALL)})

        # The first declared envelope wins. A run that flies two procedures with
        # different bands has no single "time outside the envelope", and
        # inventing one by merging them would be a number with no owner.
        for criterion in outcome.get("expect") or []:
            limits = (criterion.get("condition") or {}).get("attitude_stable")
            if limits and not envelope:
                envelope = {"procedure": procedure, **limits}

    return {"targets": targets, "mode_transitions": transitions,
            "envelope": envelope}


# ------------------------------------------------------------------- computing
def _weighted_seconds(samples: list[tuple], predicate) -> float:
    """Seconds spent where `predicate` holds, weighted by the log's own clock."""
    total = 0.0
    previous: Optional[float] = None
    for sample in samples:
        when = sample[0]
        if previous is not None and when > previous:
            step = min(when - previous, MAX_SAMPLE_GAP_S)
            if predicate(sample):
                total += step
        previous = when
    return total


def within_armed(samples: list[tuple], armed_intervals: list[dict]) -> list[tuple]:
    """Only the samples recorded while the vehicle was armed.

    WHY A METRIC ABOUT THE AIRFRAME STOPS AT THE ARMED INTERVAL
    -----------------------------------------------------------
    A dataflash log opens before the flight and closes after it, so a
    whole-log measurement of "time outside the attitude envelope" includes the
    aircraft sitting on the runway — where a tailsitter is at 0° pitch and a
    band of [55,115]° is violated for every second of it. The number was
    correct and unusable, and it disagreed loudly with the acceptance criterion
    that shares its name and its bands.

    An empty interval list means the log never recorded an arming, in which
    case there is no flight to scope to and the samples are returned unchanged
    — with `window` reporting that, rather than a zero implying a clean flight.
    """
    if not armed_intervals:
        return list(samples)
    spans = [(float(i["armed_at"]), float(i["disarmed_at"]))
             for i in armed_intervals]
    return [s for s in samples
            if any(start <= s[0] <= end for start, end in spans)]


def _time_to_target(altitude: list[tuple], target_m: float,
                    from_s: float) -> Optional[float]:
    for when, value in altitude:
        if when >= from_s and value >= target_m:
            return round(when - from_s, 2)
    return None


def compute(*, altitude: list[tuple], attitude: list[tuple],
            attitude_stats: dict, gyro_peak_dps: Optional[float],
            armed_intervals: list[dict], context: Optional[dict] = None,
            ) -> list[dict]:
    """Every metric this run can support, as plain dictionaries.

    A metric that cannot be derived is emitted with `value: null` and a stated
    reason rather than left out. An absent key and a measurement that could not
    be made look identical to a reader, and only one of them is a fact.
    """
    context = context or {}
    metrics: list[Metric] = []

    # ------------------------------------------------------- time to target
    started = armed_intervals[0]["armed_at"] if armed_intervals else 0.0
    targets = context.get("targets") or []
    if not targets:
        metrics.append(_metric(
            "time_to_target_alt", None,
            detail="no procedure in this run declared a target altitude"))
    for target in targets:
        if not altitude:
            metrics.append(_metric(
                "time_to_target_alt", None, procedure=target["procedure"],
                detail="the log carries no altitude records"))
            continue
        seconds = _time_to_target(altitude, target["alt_m"], started)
        metrics.append(_metric(
            "time_to_target_alt", seconds, procedure=target["procedure"],
            detail=(f"{target['alt_m']:g} m above home, measured from arming at "
                    f"{started:.1f} s"
                    if seconds is not None else
                    f"{target['alt_m']:g} m above home was never reached in this log")))

    # ------------------------------------------------------ attitude tracking
    for axis in ("roll", "pitch"):
        for kind in ("max", "rms"):
            key = f"tracking_error_{axis}_{kind}"
            value = attitude_stats.get(f"{axis}_{kind}")
            metrics.append(_metric(
                key, None if value is None else float(value),
                detail=("" if value is not None else
                        "the log carries no ATT records")))

    # ---------------------------------------------------------- angular rate
    metrics.append(_metric(
        "peak_angular_rate",
        None if gyro_peak_dps is None else round(float(gyro_peak_dps), 2),
        detail=("" if gyro_peak_dps is not None else
                "the log carries no IMU records")))

    # ------------------------------------------------------- envelope excursion
    envelope = context.get("envelope") or {}
    bands = {axis: envelope[axis] for axis in ("roll", "pitch") if axis in envelope}
    if not bands:
        metrics.append(_metric(
            "time_outside_attitude_envelope", None,
            detail="no procedure in this run declared a roll or pitch envelope"))
    elif not attitude:
        metrics.append(_metric(
            "time_outside_attitude_envelope", None,
            detail="the log carries no ATT records"))
    else:
        index = {"roll": 2, "pitch": 4}     # (t, DesRoll, Roll, DesPitch, Pitch)

        def outside(sample: tuple) -> bool:
            for axis, (low, high) in bands.items():
                if not (low <= sample[index[axis]] <= high):
                    return True
            return False

        stated = ", ".join(f"{axis} [{band[0]:g},{band[1]:g}]°"
                           for axis, band in bands.items())
        flown = within_armed(attitude, armed_intervals)
        window = WINDOW_ARMED if armed_intervals else WINDOW_LOG
        scope_text = (f"over {len(armed_intervals)} armed interval(s)"
                      if armed_intervals else
                      "over the WHOLE log — it records no arming, so there is "
                      "no flight to scope to")
        metrics.append(_metric(
            "time_outside_attitude_envelope",
            round(_weighted_seconds(flown, outside), 2), window=window,
            detail=(f"envelope declared by {envelope.get('procedure', '?')}: "
                    f"{stated}, {scope_text}. The `attitude_stable` criterion "
                    f"of the same name is scoped to its own procedure, so the "
                    f"two windows are close but not identical.")))

    # -------------------------------------------------- mode change latency
    transitions = context.get("mode_transitions") or []
    if not transitions:
        metrics.append(_metric(
            "mode_transition_latency_max", None,
            detail="no mode change was recorded in this run"))
    else:
        by_procedure: dict[str, list[dict]] = {}
        for item in transitions:
            by_procedure.setdefault(item["procedure"], []).append(item)
        for procedure, items in by_procedure.items():
            worst = max(items, key=lambda i: i["seconds"])
            clock = worst.get("clock", CLOCK_WALL)
            metrics.append(_metric(
                "mode_transition_latency_max", round(worst["seconds"], 2),
                procedure=procedure, clock=clock,
                detail=(f"slowest of {len(items)} change(s): {worst['label']}"
                        + ("" if clock == CLOCK_VEHICLE else
                           " — measured on the HOST clock, because the "
                           "vehicle's own clock was not running during the "
                           "step; not comparable across a change of SITL "
                           "speedup"))))

    return [m.as_dict() for m in metrics]


def by_identity(metrics: list[dict]) -> dict[tuple, dict]:
    """Metrics keyed the way a comparison needs them."""
    return {(m.get("key"), m.get("procedure") or ""): m for m in (metrics or [])}


def measured(metrics: list[dict]) -> list[dict]:
    return [m for m in (metrics or []) if m.get("value") is not None]


def label_for(key: str, lang: str = "en") -> str:
    entry = CATALOGUE.get(key, {}).get("label", {})
    return entry.get(lang) or entry.get("en") or key


def catalogue(lang: str = "en") -> list[dict]:
    """The published catalogue, for the documentation portal and the API."""
    return [{"key": key, "unit": spec["unit"], "better": spec["better"],
             "scope": spec["scope"], "source": spec["source"],
             "clock": spec["clock"], "window": spec["window"],
             "label": label_for(key, lang)}
            for key, spec in CATALOGUE.items()]
