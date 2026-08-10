"""Procedure runner — executes a parsed procedure against a live vehicle.

THE SINGLE-SOURCE RULE
----------------------
This is the only executor. The TAKEOFF button and the pytest regression suite
both call `ProcedureRunner.run()` on the same YAML file, so a passing test
means a working button — there is no second code path for either to drift
from. Nothing here knows or cares whether it was started by a browser or by
pytest; the only difference is where `on_event` sends its output.

THREADING
---------
Every step is handed to `MavlinkLink.submit()` and therefore runs on the link's
single worker thread, which is the only thread allowed to touch pymavlink.
Waits inside a step go through the link's `_recv_until`, so the message pump
keeps running: vehicle state stays fresh and RC overrides keep being refreshed
for the whole of a two-minute climb.

PARAMETERS ARE RUN-SCOPED AND DECLARED
--------------------------------------
A procedure may only change a parameter it has declared in its `overrides:`
block, with a reason (see SCHEMA.md). The declared values are applied before
the first step and restored when the procedure ends, including when it fails
or is aborted. Upstream `.param` files are never written, and
`result["params_changed"]` records what was set, what it was before, and
whether the restore succeeded.

The declaration requirement is not bureaucracy. A test harness that quietly
edits the vehicle's configuration to make its own test pass is exactly the
failure mode this project exists to expose, so an override has to be visible
in the procedure, in the run directory and at the top of the flight report.

TWO KINDS OF VERDICT
--------------------
`outcome` is `passed`, `failed` or `error`:

  * `passed` — every step ran and every `expect:` criterion held.
  * `failed` — a step or an acceptance criterion did not hold. This is a real
    result about the aircraft, and CI must go red for it.
  * `error`  — the procedure could not be evaluated at all (a bug here, a
    dropped link, a malformed step). Not a verdict about the aircraft.

Vibration, EKF innovation and attitude-tracking findings are NOT part of this.
They are advisories produced by flightlog.py from the dataflash log; they are
recorded and shown, and they never turn a flight into a failure.

CRITERIA HAVE A SHAPE IN TIME
-----------------------------
A criterion used to ask one question: is this true now, or does it become true
before a timeout? That answers "where did the aircraft end up" and nothing
else. Schema 2 adds three shapes that answer *when* and *for how long* —
`within`, `for` and `never` — and they are measured on the vehicle's own clock
so they mean the same thing at speedup 1 and speedup 10. See `_Window`.

OFF-NOMINAL FLOWS
-----------------
Schema 3 adds `failures:` — a declared fault, injected at a stated point in the
flow, held for a stated duration, and cleared. Four things are kept strictly
apart in the record it leaves, because collapsing any two of them is how a
fault-injection test comes to pass for the wrong reason:

    the injected condition   what was actually done to the simulator
    the vehicle response     what the aircraft did while it was done
    the criteria             what the procedure said counts as acceptable
    the verdict              whether they held

**A fault that was successfully injected is not a pass.** The verdict comes
from the criteria and from nothing else, and a fault whose criteria could not
be judged — because the telemetry they rest on never arrived — is reported as
not judged rather than as satisfied.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from pymavlink import mavutil

from . import failures as failurelib
from . import faults as faultlib
from .i18n import t
from .mavlink_link import MavlinkLink, substitute
from .procedures import Expectation, Fault, Procedure, Step, format_duration

# Parameters read once per run to decide which procedure applies. See
# procedures.py for why this is read from the vehicle instead of models.json.
CAPABILITY_PARAMS = ("Q_ENABLE", "Q_TAILSIT_ENABLE", "Q_OPTIONS")

Q_OPTION_FW_TAKEOFF = 1 << 1     # "Allow FW Takeoff"  (ArduPlane/quadplane.cpp)
Q_OPTION_ARM_VTOL = 1 << 18      # "ARMVTOL — arm only in VTOL modes"


def probe_capabilities(link: MavlinkLink, vehicle: Optional[str] = None,
                       timeout: float = 20.0) -> dict:
    """Reads the vehicle's own configuration to decide what kind of aircraft it is.

    A missing Q_ENABLE is not an error: ArduCopter simply has no such
    parameter, and that absence is itself the answer.
    """
    autopilot = vehicle or link.vehicle

    def _probe(l: MavlinkLink) -> dict:
        values = {}
        for name in CAPABILITY_PARAMS:
            values[name] = l._param_get(name, timeout=3.0)
        return {"ok": True, "values": values, "text": ""}

    res = link.submit(_probe, timeout=timeout, label="capabilities")
    values = res.get("values") or {}

    q_enable = values.get("Q_ENABLE")
    q_tailsit = values.get("Q_TAILSIT_ENABLE")
    q_options = values.get("Q_OPTIONS")

    quadplane = bool(q_enable and q_enable > 0)
    caps = {
        "autopilot": autopilot,
        "quadplane": quadplane,
        "tailsitter": bool(quadplane and q_tailsit and q_tailsit > 0),
        "fw_takeoff_allowed": bool(q_options is not None
                                   and int(q_options) & Q_OPTION_FW_TAKEOFF),
        "arm_vtol_only": bool(q_options is not None
                              and int(q_options) & Q_OPTION_ARM_VTOL),
        "raw": {k: v for k, v in values.items() if v is not None},
    }
    if autopilot == "ArduCopter":
        # A Copter has no VTOL-plane concepts at all; do not let an unreadable
        # parameter masquerade as a meaningful False.
        caps.update(quadplane=False, tailsitter=False,
                    fw_takeoff_allowed=False, arm_vtol_only=False)
    return caps


@dataclass
class StepResult:
    index: int
    kind: str
    label: str
    status: str = "pending"        # pending | running | passed | failed | skipped
    text: str = ""
    seconds: float = 0.0

    def as_dict(self) -> dict:
        return {"index": self.index, "kind": self.kind, "label": self.label,
                "status": self.status, "text": self.text,
                "seconds": round(self.seconds, 1)}


@dataclass
class ExpectResult:
    label: str
    condition: dict
    passed: bool = False
    text: str = ""
    # The temporal shape this criterion was judged with, and the duration it
    # named. Recorded so a stored run says which question was asked, not only
    # what the answer was — a `for 5s` that passed and an instantaneous check
    # that passed are different evidence.
    kind: str = "eventually"
    duration: Optional[float] = None
    # What was actually measured, on which clock. `observed` is in seconds of
    # the clock named by `clock`; a criterion that had to fall back to the wall
    # clock says so rather than implying the vehicle's own.
    observed: float = 0.0
    clock: str = "vehicle"

    def as_dict(self) -> dict:
        return {"label": self.label, "condition": _plain(self.condition),
                "passed": self.passed, "text": self.text,
                "kind": self.kind, "duration": self.duration,
                "observed": round(self.observed, 2), "clock": self.clock}


@dataclass
class FaultResult:
    """What one injected fault did, and what the aircraft did about it.

    The four fields the architecture insists on distinguishing are four fields
    here: `injected` (the condition), `observed` (the response, as the seconds
    it was actually held and the evidence that arrived), `expect`/`recovery`
    (the criteria) and `passed` (the verdict). None of them is derived from
    another.
    """

    id: str
    kind: str
    target: str
    label: str
    expected: str = ""
    declared_s: float = 0.0
    # The mechanism, exactly as applied: which parameters were written to what,
    # and what they were before. A scenario that cannot be reproduced from its
    # own record is a story about a flight rather than evidence of one.
    mechanism: str = ""
    changed: dict = field(default_factory=dict)
    applied: bool = False
    cleared: Optional[bool] = None
    text: str = ""
    injected_at_s: Optional[float] = None
    held_s: float = 0.0
    clock: str = "vehicle"
    evidence_required: list = field(default_factory=list)
    evidence_seen: list = field(default_factory=list)
    expect: list = field(default_factory=list)
    recovery: list = field(default_factory=list)
    passed: bool = False

    @property
    def evidence_missing(self) -> list:
        return [s for s in self.evidence_required if s not in self.evidence_seen]

    def as_dict(self) -> dict:
        return {
            "id": self.id, "fault": self.kind, "target": self.target,
            "label": self.label, "expected": self.expected,
            "declared_s": round(self.declared_s, 2),
            "mechanism": self.mechanism, "changed": _plain(self.changed),
            "applied": self.applied, "cleared": self.cleared,
            "text": self.text,
            "injected_at_s": (None if self.injected_at_s is None
                              else round(self.injected_at_s, 2)),
            "held_s": round(self.held_s, 2), "clock": self.clock,
            "evidence_required": list(self.evidence_required),
            "evidence_seen": sorted(self.evidence_seen),
            "evidence_missing": sorted(self.evidence_missing),
            "expect": [e.as_dict() for e in self.expect],
            "recovery": [e.as_dict() for e in self.recovery],
            "passed": self.passed,
        }


def _plain(obj):
    """JSON-safe copy (conditions may hold placeholder strings or numbers)."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


class ProcedureAborted(Exception):
    """A step or criterion did not hold — a verdict about the aircraft."""


OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_ERROR = "error"

# Conditions measured over the procedure so far rather than at this instant.
# Polling them is worse than pointless: the quantity only accumulates, so a
# `_wait_for` loop would spin until its timeout and then report the same
# verdict it had at the first check — while the aircraft carried on doing
# whatever it was doing. They are evaluated exactly once.
MONOTONE_CONDITIONS = ("attitude_stable",)

# Applied when a procedure states a band but no forgiveness. Every real flight
# crosses a limit briefly — a mode change, a gust, the moment thrust takes the
# weight — and a criterion with no tolerance would fail those. One second is
# short enough that a tumble cannot hide inside it.
DEFAULT_STABILITY_TOLERANCE = 1.0

# Below this much measured attitude, the criterion FAILS rather than passes.
# A missing telemetry stream must never read as good behaviour: "nothing was
# measured" and "nothing was wrong" are the two answers this project exists to
# keep apart.
DEFAULT_STABILITY_MIN_SECONDS = 5.0

# ------------------------------------------------------------ temporal criteria
# How often a temporal criterion re-reads the vehicle's state, in WALL-CLOCK
# seconds. It is a wall-clock number on purpose: it is a property of this
# process's polling loop, not of the flight.
#
# The consequence has to be stated rather than hidden: an excursion shorter
# than one interval of VEHICLE time — this many wall seconds times the SITL
# speedup — can pass between two samples unseen. `never` is therefore a claim
# about what was observed at this rate, and `attitude_stable` remains the
# criterion that weighs every attitude sample the vehicle sent.
TEMPORAL_SAMPLE_S = 0.2

# The vehicle's clock is the right measure for a duration, and it stops
# advancing the moment ATTITUDE stops arriving. A criterion waiting on a dead
# stream is not a criterion, it is a hang — so every window also carries a
# wall-clock backstop, sized from the measured speedup with room to spare, and
# says which of the two ended it.
WALL_BACKSTOP_FACTOR = 3.0
WALL_BACKSTOP_MARGIN = 15.0

# How long the vehicle's clock may stand still before the window stops
# believing it, in WALL seconds.
#
# WHY A STOPPED CLOCK NEEDS DETECTING AT ALL
# ------------------------------------------
# v1.3 only asked whether the clock had gone backwards or never started. That
# covers a link that was never up; it does not cover one that dies mid-window,
# where `time_boot_ms` simply keeps its last value. The window then measured
# `now - start` = 0 for its whole duration and reported `clock: "vehicle"` —
# a stalled stream described as a healthy measurement of zero seconds. v1.4's
# `mavlink_interrupt` makes that case routine rather than theoretical, which is
# why it is fixed here rather than worked around in the fault.
#
# Two seconds is far past due at any speedup this project runs: ATTITUDE is
# requested at 10 Hz of VEHICLE time (ATTITUDE_STREAM_HZ), so a sample is owed
# every 0.1 s at speedup 1 and every 0.02 s at speedup 5.
STALL_AFTER_WALL_S = 2.0

# Fewest samples a `for`/`never` window must collect before its verdict means
# anything. Two samples cannot describe a duration.
MIN_TEMPORAL_SAMPLES = 3

# Which conditions rest on which telemetry, and the state flag that says that
# telemetry has actually been seen. A criterion that claims "the rate never
# exceeded 90°/s" while no ATTITUDE ever arrived is reporting silence as
# success, which is the exact failure this project was written to remove.
CONDITION_EVIDENCE = {
    "roll_within": "attitude_known", "pitch_within": "attitude_known",
    "angular_rate_above": "attitude_known", "angular_rate_below": "attitude_known",
    "attitude_stable": "attitude_known", "prearm_ok": "prearm_known",
}


class _Window:
    """A bounded observation window, measured on the vehicle's own clock.

    WHY NOT `time.time()`
    ---------------------
    A procedure that says `within: 10s` is making a claim about the aircraft,
    and under SITL speedup ten wall-clock seconds are not ten seconds of
    flight. Every duration here is therefore counted on `ATTITUDE.time_boot_ms`
    — the same clock `StabilityWatch` weighs its samples with — so a criterion
    means the same thing at speedup 1 and speedup 10.

    WHY THERE IS STILL A WALL-CLOCK CEILING
    ---------------------------------------
    That clock only advances while telemetry arrives. If the stream dies the
    window would never close, so the wall clock ends it instead and `stalled`
    records that the answer came from the fallback. Reporting a wall-clock
    measurement as though it were vehicle time would quietly make every
    duration in a run's evidence wrong by the speedup factor — so when the
    fallback is in use, wall seconds are converted with the LAST MEASURED
    speedup and the result still means what the procedure asked for.

    THE FALLBACK IS STICKY
    ----------------------
    Once a window has fallen back it stays fallen back, even if telemetry
    returns. Switching measures half way through would produce a duration that
    is neither one clock nor the other, and this project has no use for a
    number whose unit changed mid-measurement.
    """

    def __init__(self, link: MavlinkLink, budget: float) -> None:
        self.link = link
        self.budget = budget
        self.wall_start = time.time()
        self.vehicle_start = self._read_clock()
        # Frozen at construction: the measurement itself is what stops the
        # link's estimate from updating, so a window must not use a speedup
        # that its own stall prevented from being refreshed.
        self.speedup = max(getattr(link, "speedup", 1.0) or 1.0, 0.1)
        self.wall_limit = (budget / self.speedup * WALL_BACKSTOP_FACTOR
                           + WALL_BACKSTOP_MARGIN)
        self.samples = 0
        self._seen = self.vehicle_start
        self._moved_at = self.wall_start
        self._stalled = self.vehicle_start is None

    def _read_clock(self) -> Optional[float]:
        clock = getattr(self.link.state, "vehicle_clock_s", 0.0) or 0.0
        return clock if clock > 0 else None

    def _observe(self) -> Optional[float]:
        """Reads the vehicle clock and remembers when it last moved."""
        now = self._read_clock()
        if now is not None and (self._seen is None or now > self._seen):
            self._seen, self._moved_at = now, time.time()
        return now

    @property
    def stalled(self) -> bool:
        """Is the vehicle's clock unusable, so the wall clock is doing the work?"""
        if self._stalled:
            return True
        now = self._observe()
        if now is None or self.vehicle_start is None or now < self.vehicle_start:
            self._stalled = True
        elif (time.time() - self._moved_at) >= STALL_AFTER_WALL_S:
            self._stalled = True
        return self._stalled

    @property
    def clock(self) -> str:
        return "wall" if self.stalled else "vehicle"

    @property
    def elapsed(self) -> float:
        if self.stalled:
            # Wall seconds scaled by the speedup this window opened with, so
            # the number stays a statement about the aircraft's time rather
            # than about this process's.
            return (time.time() - self.wall_start) * self.speedup
        return (self._observe() or 0.0) - (self.vehicle_start or 0.0)

    @property
    def expired(self) -> bool:
        return (self.elapsed >= self.budget
                or (time.time() - self.wall_start) >= self.wall_limit)

    def tick(self) -> None:
        """One sampling interval, with the link's message pump kept running."""
        self.samples += 1
        self.link.submit(_pump_for(TEMPORAL_SAMPLE_S),
                         timeout=TEMPORAL_SAMPLE_S + 6.0, label="observe")
        # Sampled here and not only when a property is read. `_observe` records
        # WHEN the clock last moved, and a reader that arrives after a long
        # silence would otherwise see one late advance and reset that stamp to
        # now — reporting a dead stream as healthy because it had a pulse at
        # some point since the last look.
        self._observe()

    def note(self) -> str:
        """A suffix stating the fallback, or nothing when the clock was fine."""
        return " " + t("temporal_stalled") if self.stalled else ""


def _pump_for(seconds: float):
    """A worker-thread job that just keeps the link's message pump running.

    Used for `sleep`, for `rc_override: hold:`, and between condition checks.
    It matters that this goes through the link rather than `time.sleep()`:
    while it runs, vehicle state keeps updating and — critically — the RC
    override keepalive keeps firing, so a held stick stays held.
    """
    def _fn(link: MavlinkLink) -> dict:
        link._recv_until(lambda m: False, timeout=seconds)
        return {"ok": True, "text": ""}
    return _fn


class ProcedureRunner:
    """Runs one procedure at a time against one vehicle."""

    def __init__(self, link: MavlinkLink,
                 on_event: Optional[Callable[[dict], None]] = None,
                 lang: str = "en"):
        self.link = link
        self.on_event = on_event or (lambda e: None)
        self.lang = lang
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    # ------------------------------------------------------------------ helpers
    def _emit(self, kind: str, **payload) -> None:
        try:
            self.on_event({"type": "procedure", "event": kind, **payload})
        except Exception:
            pass

    def _resolve(self, value, values: dict):
        """Fills {placeholders} and returns a number where the text was numeric."""
        if isinstance(value, str):
            try:
                value = substitute(value, values)
            except KeyError as exc:
                raise ProcedureAborted(t("proc_unknown_placeholder", name=exc)) from exc
            try:
                return float(value)
            except ValueError:
                return value
        return value

    def _resolve_condition(self, cond: dict, values: dict) -> dict:
        out = {}
        for key, raw in cond.items():
            if key == "param" and isinstance(raw, dict):
                out[key] = {k: self._resolve(v, values) for k, v in raw.items()}
            elif key == "attitude_stable" and isinstance(raw, dict):
                out[key] = {k: ([float(self._resolve(b, values)) for b in v]
                                if isinstance(v, (list, tuple))
                                else float(self._resolve(v, values)))
                            for k, v in raw.items()}
            elif key == "mode_in":
                out[key] = [str(self._resolve(v, values)) for v in raw]
            elif key in ("roll_within", "pitch_within"):
                out[key] = [float(self._resolve(v, values)) for v in raw]
            elif key in ("mode",):
                out[key] = str(raw)
            elif key in ("armed", "prearm_ok"):
                out[key] = bool(raw)
            else:
                out[key] = float(self._resolve(raw, values))
        return out

    # ------------------------------------------------------------------ conditions
    def _check(self, cond: dict) -> tuple[bool, str]:
        """Evaluates a resolved condition against the link's current state.

        Returns (satisfied, description-of-what-was-actually-seen) so a failure
        can say "alt 3.2 m" rather than only "not satisfied".
        """
        st = self.link.state
        seen = []
        ok = True
        for key, want in cond.items():
            if key == "armed":
                ok &= (st.armed == want)
                seen.append(f"armed={st.armed}")
            elif key == "prearm_ok":
                ok &= (st.prearm_ok == want)
                seen.append(f"prearm_ok={st.prearm_ok}")
            elif key == "mode":
                ok &= (st.mode == want)
                seen.append(f"mode={st.mode}")
            elif key == "mode_in":
                ok &= (st.mode in want)
                seen.append(f"mode={st.mode}")
            elif key == "alt_above":
                ok &= (st.alt > want)
                seen.append(f"alt={st.alt:.1f}m")
            elif key == "alt_below":
                ok &= (st.alt < want)
                seen.append(f"alt={st.alt:.1f}m")
            elif key == "climb_rate_above":
                ok &= (st.climb > want)
                seen.append(f"climb={st.climb:+.1f}m/s")
            elif key == "climb_rate_below":
                ok &= (st.climb < want)
                seen.append(f"climb={st.climb:+.1f}m/s")
            elif key == "groundspeed_above":
                ok &= (st.groundspeed > want)
                seen.append(f"gs={st.groundspeed:.1f}m/s")
            elif key == "roll_within":
                low, high = want
                ok &= (low <= st.roll <= high)
                seen.append(f"roll={st.roll:.1f}° (band [{low:g},{high:g}])")
            elif key == "pitch_within":
                low, high = want
                ok &= (low <= st.pitch <= high)
                seen.append(f"pitch={st.pitch:.1f}° (band [{low:g},{high:g}])")
            elif key == "angular_rate_above":
                ok &= (st.max_angular_rate > want)
                seen.append(f"rate={st.max_angular_rate:.0f}°/s (limit {want:g})")
            elif key == "angular_rate_below":
                ok &= (st.max_angular_rate < want)
                seen.append(f"rate={st.max_angular_rate:.0f}°/s (limit {want:g})")
            elif key == "attitude_stable":
                held, text = self._check_stability(want)
                ok &= held
                seen.append(text)
            elif key == "param":
                value = self.link.submit(
                    lambda l, n=want["name"]: {"ok": True, "value": l._param_get(n)},
                    timeout=8.0, label=f"param {want['name']}").get("value")
                seen.append(f"{want['name']}={value}")
                if value is None:
                    ok = False
                else:
                    if want.get("min") is not None and value < want["min"]:
                        ok = False
                    if want.get("max") is not None and value > want["max"]:
                        ok = False
                    if want.get("equals") is not None and value != want["equals"]:
                        ok = False
        return ok, ", ".join(seen)

    def _check_stability(self, limits: dict) -> tuple[bool, str]:
        """Judges the attitude envelope this procedure has accumulated.

        The verdict is stated in seconds, not in peaks: how long the aircraft
        spent outside each declared band, against the forgiveness the procedure
        declared. A peak is one sample and one sample is noise; time outside is
        what separates a manoeuvre from a loss of control.
        """
        watch = self.link.stability
        tolerance = float(limits.get("tolerance", DEFAULT_STABILITY_TOLERANCE))
        minimum = float(limits.get("min_seconds", DEFAULT_STABILITY_MIN_SECONDS))
        measured = watch.seconds

        if measured < minimum:
            # Not "we saw nothing wrong" — "we saw nothing".
            return False, t("stab_no_data", measured=f"{measured:.1f}",
                            needed=f"{minimum:g}")

        ok = True
        parts = []
        for axis in ("roll", "pitch"):
            if axis not in limits:
                continue
            low, high = limits[axis]
            outside = watch.outside_seconds(axis, low, high)
            if outside > tolerance:
                ok = False
            parts.append(t("stab_axis", axis=axis, low=f"{low:g}", high=f"{high:g}",
                           outside=f"{outside:.1f}"))
        if "max_rate" in limits:
            limit = float(limits["max_rate"])
            above = watch.rate_above_seconds(limit)
            if above > tolerance:
                ok = False
            parts.append(t("stab_rate", limit=f"{limit:g}", above=f"{above:.1f}",
                           peak=f"{watch.report().get('rate_peak', 0):.0f}"))
        return ok, t("stab_summary", detail="; ".join(parts),
                     tolerance=f"{tolerance:g}", measured=f"{measured:.0f}")

    def _wait_for(self, cond: dict, timeout: float) -> tuple[bool, str]:
        # See MONOTONE_CONDITIONS: an envelope that has already been broken
        # stays broken, so waiting on one only delays the same answer.
        if any(key in cond for key in MONOTONE_CONDITIONS):
            return self._check(cond)
        deadline = time.time() + timeout
        seen = ""
        while time.time() < deadline:
            if self._cancel:
                raise ProcedureAborted(t("proc_cancelled"))
            ok, seen = self._check(cond)
            if ok:
                return True, seen
            self.link.submit(_pump_for(0.4), timeout=6.0, label="wait")
        return False, seen

    # ------------------------------------------------------------------ temporal
    def _unmeasurable(self, cond: dict) -> str:
        """Which telemetry this condition needs and has not seen, if any.

        Returns an empty string when everything it rests on has been observed.
        A `for` or a `never` makes a positive claim about a stretch of time, so
        it has to be refused outright when the stream backing it never arrived
        — otherwise silence reads as good behaviour.
        """
        state = self.link.state
        for key in cond:
            flag = CONDITION_EVIDENCE.get(key)
            if flag and not getattr(state, flag, False):
                return t("temporal_no_evidence", condition=key,
                         signal=flag.replace("_known", ""))
        return ""

    def _evaluate(self, exp: Expectation, cond: dict) -> ExpectResult:
        """One acceptance criterion, judged with the shape the procedure asked for."""
        result = ExpectResult(label=exp.label(self.lang), condition=cond,
                              kind=exp.kind, duration=exp.duration)
        if exp.kind == "eventually":
            result.passed, result.text = self._wait_for(cond, exp.timeout)
            return result
        if exp.kind == "within":
            return self._expect_within(result, cond, exp.within or 0.0)
        if exp.kind == "for":
            return self._expect_for(result, cond, exp.hold_for or 0.0, exp.timeout)
        return self._expect_never(result, cond, exp.never or 0.0)

    def _expect_within(self, result: ExpectResult, cond: dict,
                       limit: float) -> ExpectResult:
        """The condition must become true before the window closes."""
        window = _Window(self.link, limit)
        seen = ""
        while True:
            if self._cancel:
                raise ProcedureAborted(t("proc_cancelled"))
            ok, seen = self._check(cond)
            result.observed, result.clock = window.elapsed, window.clock
            if ok:
                result.passed = True
                result.text = t("temporal_within_ok",
                                elapsed=format_duration(max(window.elapsed, 0.0)),
                                limit=format_duration(limit),
                                seen=seen) + window.note()
                return result
            if window.expired:
                break
            window.tick()
        result.observed, result.clock = window.elapsed, window.clock
        result.text = t("temporal_within_fail", limit=format_duration(limit),
                        elapsed=format_duration(max(window.elapsed, 0.0)),
                        seen=seen) + window.note()
        return result

    def _expect_for(self, result: ExpectResult, cond: dict, hold: float,
                    timeout: float) -> ExpectResult:
        """The condition must become true, then hold continuously.

        A lapse inside the hold window FAILS; it does not restart the count. A
        restarting window would let a condition that flickers on and off pass
        eventually, which is the opposite of what "continuously" means, and the
        failure text would no longer describe what the aircraft did.
        """
        missing = self._unmeasurable(cond)
        if missing:
            result.text = missing
            return result

        # Phase 1 — acquire. Bounded by `timeout`, which is the schema-1 wait.
        acquired, seen = self._wait_for(cond, timeout)
        if not acquired:
            result.text = t("temporal_for_never_started",
                            limit=format_duration(hold),
                            timeout=f"{timeout:g}", seen=seen)
            return result

        # Phase 2 — hold, on the vehicle's clock.
        window = _Window(self.link, hold)
        while not window.expired:
            if self._cancel:
                raise ProcedureAborted(t("proc_cancelled"))
            window.tick()
            ok, seen = self._check(cond)
            result.observed, result.clock = window.elapsed, window.clock
            if not ok:
                result.text = t("temporal_for_lapsed",
                                held=format_duration(max(window.elapsed, 0.0)),
                                limit=format_duration(hold),
                                seen=seen) + window.note()
                return result
        result.observed, result.clock = window.elapsed, window.clock
        if window.samples < MIN_TEMPORAL_SAMPLES:
            result.text = t("temporal_too_few_samples", samples=window.samples,
                            needed=MIN_TEMPORAL_SAMPLES)
            return result
        result.passed = True
        result.text = t("temporal_for_ok",
                        held=format_duration(max(window.elapsed, 0.0)),
                        limit=format_duration(hold), samples=window.samples,
                        seen=seen) + window.note()
        return result

    def _expect_never(self, result: ExpectResult, cond: dict,
                      window_s: float) -> ExpectResult:
        """The condition must not become true at any observed moment."""
        missing = self._unmeasurable(cond)
        if missing:
            result.text = missing
            return result

        window = _Window(self.link, window_s)
        seen = ""
        while not window.expired:
            if self._cancel:
                raise ProcedureAborted(t("proc_cancelled"))
            violated, seen = self._check(cond)
            result.observed, result.clock = window.elapsed, window.clock
            if violated:
                result.text = t("temporal_never_fail",
                                elapsed=format_duration(max(window.elapsed, 0.0)),
                                limit=format_duration(window_s),
                                seen=seen) + window.note()
                return result
            window.tick()
        result.observed, result.clock = window.elapsed, window.clock
        if window.samples < MIN_TEMPORAL_SAMPLES:
            result.text = t("temporal_too_few_samples", samples=window.samples,
                            needed=MIN_TEMPORAL_SAMPLES)
            return result
        result.passed = True
        result.text = t("temporal_never_ok",
                        observed=format_duration(max(window.elapsed, 0.0)),
                        samples=window.samples, seen=seen) + window.note()
        return result

    # ------------------------------------------------------------------ faults
    def _prepare_faults(self, proc: Procedure) -> dict:
        """Ask the simulator whether every declared fault can be injected.

        Runs before the first step and before any override, so a scenario whose
        mechanism is missing costs nothing and changes nothing. This is the
        fail-closed rule: the alternative is a flight that looks off-nominal in
        the run listing and was nominal in the air.
        """
        prepared: dict[str, faultlib.Injector] = {}
        for fault in proc.failures:
            injector = faultlib.injector_for(fault.kind, fault.target, fault.options)
            try:
                injector.probe(self.link)
            except faultlib.FaultUnavailable as exc:
                raise ProcedureAborted(
                    t("fault_unavailable", id=fault.id,
                      kind=faultlib.label_for(fault.kind, self.lang),
                      err=exc)) from exc
            prepared[fault.id] = injector
            self._emit("fault_ready", fault=fault.as_dict(self.lang),
                       mechanism=injector.mechanism_text)
        return prepared

    def _faults_at(self, proc: Procedure, injectors: dict, after_step: int,
                   values: dict, out: list) -> None:
        """Runs any fault declared for this point in the flow."""
        for fault in proc.failures:
            if fault.inject_after_step != after_step:
                continue
            self._emit("fault_start", fault=fault.as_dict(self.lang))
            result = self._inject_fault(fault, injectors[fault.id], values)
            out.append(result)
            self._emit("fault_done", fault=result.as_dict())

    # How long to wait for telemetry to resume after a fault is cleared, in
    # WALL seconds. It is a property of this process's patience rather than of
    # the flight, so it is not on the vehicle's clock — which is precisely the
    # thing that is not running when this matters.
    RESYNC_TIMEOUT_S = 20.0

    def _resync(self, timeout: float = RESYNC_TIMEOUT_S) -> bool:
        """Waits for fresh telemetry after a fault. Returns whether it arrived.

        WHY A CLEARED FAULT IS NOT THE SAME AS A RECOVERED ONE
        ------------------------------------------------------
        `recovery:` criteria are claims about the aircraft *after* the fault.
        The moment the fault is lifted, every field of `link.state` still holds
        what arrived before it — so `{armed: true} within: 15s` passed "after
        0 ms" against a reading the blackout itself had frozen. That is silence
        reported as success, which is the one thing this project exists to
        remove.

        It also breaks the window after it. The vehicle's clock resumes with a
        jump of however long the fault lasted, so the first sample of the next
        window can put it straight past its budget — a `never: 5s` that
        collected one reading and honestly reported that it could not judge
        anything from it.

        Both are fixed here rather than in either scenario, because both follow
        from what a fault IS and not from which fault it was.
        """
        before = getattr(self.link.state, "vehicle_clock_s", 0.0) or 0.0
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._cancel:
                raise ProcedureAborted(t("proc_cancelled"))
            self.link.submit(_pump_for(TEMPORAL_SAMPLE_S),
                             timeout=TEMPORAL_SAMPLE_S + 6.0, label="resync")
            now = getattr(self.link.state, "vehicle_clock_s", 0.0) or 0.0
            if now > before:
                return True
        return False

    def _evidence_seen(self, required: list, seen: set) -> None:
        """Records which of the required signals have actually been observed."""
        for signal in required:
            flag = faultlib.EVIDENCE_SIGNALS.get(signal)
            if flag and getattr(self.link.state, flag, False):
                seen.add(signal)

    def _inject_fault(self, fault: Fault, injector: faultlib.Injector,
                      values: dict) -> FaultResult:
        """Injects one declared fault, holds it, clears it, and judges it.

        Order matters and is the order of the record: wait for the state the
        scenario names, degrade, watch, restore, then ask whether the aircraft
        did what the procedure said it must. The restore is in a `finally`, so
        an aborted or cancelled scenario cannot leave the simulated vehicle
        degraded for whatever runs next.
        """
        result = FaultResult(
            id=fault.id, kind=fault.kind, target=fault.target,
            label=fault.label(self.lang), expected=fault.expected_text(self.lang),
            declared_s=fault.duration, mechanism=injector.mechanism_text,
            evidence_required=list(fault.evidence))
        seen: set = set()

        # ---------------------------------------------------------- start
        if fault.start_condition:
            cond = self._resolve_condition(fault.start_condition, values)
            holds, observed = self._wait_for(cond, fault.start_within)
            if not holds:
                raise ProcedureAborted(
                    t("fault_start_missed", id=fault.id,
                      limit=format_duration(fault.start_within), seen=observed))

        # --------------------------------------------------------- inject
        try:
            injector.apply(self.link)
        except faultlib.FaultRefused as exc:
            result.text = str(exc)
            self._emit("fault", fault=result.as_dict())
            raise ProcedureAborted(
                t("fault_refused", id=fault.id, err=exc)) from exc
        result.applied = True
        result.injected_at_s = getattr(self.link.state, "vehicle_clock_s", 0.0) or None
        result.changed = dict(injector.changed)
        self._emit("fault", fault=result.as_dict(), state="injected")

        window = _Window(self.link, fault.duration)
        try:
            # Criteria first, inside the hold window. They are the reason the
            # fault exists, and evaluating them here is what makes them a
            # statement about the degraded aircraft rather than the recovered
            # one.
            for exp in fault.expect:
                cond = self._resolve_condition(exp.condition, values)
                judged = self._evaluate(exp, cond)
                result.expect.append(judged)
                self._evidence_seen(result.evidence_required, seen)
                self._emit("fault_expect", fault=fault.id, expect=judged.as_dict())

            # `duration` is a MINIMUM hold. If the criteria above finished
            # early the remainder is still held, so the aircraft spends the
            # time the scenario declared in the degraded state; if they
            # overran it, the fault was held longer and the record says so
            # rather than the declaration being taken as what happened.
            while not window.expired:
                if self._cancel:
                    raise ProcedureAborted(t("proc_cancelled"))
                window.tick()
                self._evidence_seen(result.evidence_required, seen)
            result.held_s, result.clock = window.elapsed, window.clock
        finally:
            result.cleared = injector.clear(self.link)
            result.changed = dict(injector.changed)
            self._emit("fault", fault=result.as_dict(), state="cleared")

        if not result.cleared:
            # Not a verdict about the aircraft, and it must not be reported as
            # one: the simulator is still degraded, so nothing measured after
            # this point means what it says.
            result.text = t("fault_not_cleared", id=fault.id)
            return result

        # ------------------------------------------------------- recovery
        # Fresh telemetry first. Everything below is a claim about the aircraft
        # after the fault, and the state it would otherwise be judged against
        # is the state the fault stopped from being updated.
        if not self._resync():
            result.text = t("fault_no_resync", id=fault.id,
                            seconds=f"{self.RESYNC_TIMEOUT_S:g}")
            result.evidence_seen = sorted(seen)
            return result
        self._evidence_seen(result.evidence_required, seen)

        for exp in fault.recovery:
            cond = self._resolve_condition(exp.condition, values)
            judged = self._evaluate(exp, cond)
            result.recovery.append(judged)
            self._evidence_seen(result.evidence_required, seen)
            self._emit("fault_recovery", fault=fault.id, expect=judged.as_dict())

        result.evidence_seen = sorted(seen)
        judged_all = result.expect + result.recovery
        if result.evidence_missing:
            # Silence is not success. The criteria may all have "held" against
            # a state nothing ever wrote to.
            result.text = t("fault_no_evidence", id=fault.id,
                            signals=", ".join(result.evidence_missing))
            return result
        result.passed = all(e.passed for e in judged_all)
        result.text = t("fault_passed" if result.passed else "fault_failed",
                        id=fault.id, held=format_duration(max(result.held_s, 0.0)),
                        criteria=len(judged_all))
        return result

    # ------------------------------------------------------------------ steps
    def _run_step(self, step: Step, values: dict, changed_params: dict) -> dict:
        kind, raw = step.kind, step.value
        default_timeout = {"arm": 70.0, "disarm": 20.0, "set_mode": 15.0,
                           "wait_for": 60.0, "upload_mission": 40.0}.get(kind, 15.0)
        timeout = step.timeout if step.timeout is not None else default_timeout

        if kind == "sleep":
            seconds = float(self._resolve(raw, values))
            self.link.submit(_pump_for(seconds), timeout=seconds + 10, label="sleep")
            return {"ok": True, "text": t("proc_slept", seconds=f"{seconds:g}")}

        if kind == "set_mode":
            mode = str(raw).upper()
            return self.link.submit(lambda l: l._do_mode([mode]), timeout, f"mode {mode}")

        if kind == "arm":
            force = bool(raw.get("force", False))
            recover = bool(raw.get("recover", True))
            args = ["force"] if force else []
            return self.link.submit(
                lambda l: l._do_arm(args, arm=True, recover=recover), timeout, "arm")

        if kind == "disarm":
            args = ["force"] if raw.get("force") else []
            return self.link.submit(
                lambda l: l._do_arm(args, arm=False), timeout, "disarm")

        if kind == "set_param":
            name = str(raw["name"]).upper()
            value = self._resolve(raw["value"], values)

            def _set(l: MavlinkLink, n=name, v=value) -> dict:
                previous = l._param_get(n)
                res = l._do_param(["set", n, str(v)])
                if res.get("ok"):
                    res["previous"] = previous
                return res

            res = self.link.submit(_set, timeout, f"param set {name}")
            if res.get("ok") and name not in changed_params:
                # Only the FIRST value seen is remembered, so restoring returns
                # the vehicle to how the procedure found it.
                changed_params[name] = {"restore_to": res.get("previous"),
                                        "set_to": value}
            return res

        if kind == "get_param":
            name = str(raw["name"]).upper()
            res = self.link.submit(
                lambda l, n=name: {"ok": True, "value": l._param_get(n)},
                timeout, f"param {name}")
            value = res.get("value")
            if value is None:
                return {"ok": False, "text": t("param_unreadable", name=name)}
            if raw.get("store_as"):
                values[str(raw["store_as"])] = value
            low, high = raw.get("min"), raw.get("max")
            out_of_range = ((low is not None and value < float(low))
                            or (high is not None and value > float(high)))
            if out_of_range:
                msg = raw.get("fail_message") or {}
                text = (msg.get(self.lang) or msg.get("en")
                        or t("proc_param_out_of_range", name=name, value=f"{value:g}"))
                return {"ok": False, "text": text.replace("{value}", f"{value:g}")}
            return {"ok": True, "text": f"{name} = {value:g}"}

        if kind == "rc_override":
            channels = {int(c): int(self._resolve(p, values))
                        for c, p in raw["channels"].items()}
            res = self.link.submit(lambda l: l._do_rc_channels(channels), timeout, "rc")
            hold = float(raw.get("hold", 0) or 0)
            if res.get("ok") and hold > 0:
                self.link.submit(_pump_for(hold), timeout=hold + 10, label="hold")
            return res

        if kind == "rc_release":
            return self.link.submit(lambda l: l._do_rc_release(), timeout, "rc release")

        if kind == "send_command":
            command_id = _enum(mavutil.mavlink, raw["command"])
            frame = _enum(mavutil.mavlink, raw["frame"]) if raw.get("frame") else None
            params = {k: self._resolve(v, values)
                      for k, v in (raw.get("params") or {}).items()}
            accept = [_enum(mavutil.mavlink, f"MAV_RESULT_{n}")
                      for n in (raw.get("accept") or ["ACCEPTED"])]
            ctype = raw.get("type", "long")
            return self.link.submit(
                lambda l: l._do_send_command(command_id, ctype, frame, params,
                                             accept, str(raw["command"])),
                timeout, str(raw["command"]))

        if kind == "upload_mission":
            items = []
            for item in raw["items"]:
                out = {"command": _enum(mavutil.mavlink, item["command"])}
                if item.get("frame"):
                    out["frame"] = _enum(mavutil.mavlink, item["frame"])
                for key in ("p1", "p2", "p3", "p4", "x", "y", "z"):
                    if item.get(key) is not None:
                        out[key] = self._resolve(item[key], values)
                items.append(out)
            return self.link.submit(
                lambda l: l._do_upload_mission(items), timeout, "mission")

        if kind == "wait_for":
            cond = self._resolve_condition(raw, values)
            ok, seen = self._wait_for(cond, timeout)
            if ok:
                return {"ok": True, "text": seen}
            return {"ok": False,
                    "text": t("proc_wait_timeout", seconds=f"{timeout:g}", seen=seen)}

        return {"ok": False, "text": t("proc_unknown_step", kind=kind)}

    # ------------------------------------------------------------------ overrides
    def _apply_overrides(self, proc: Procedure, values: dict,
                         changed_params: dict) -> None:
        """Writes every declared override before the first step runs.

        Applying them up front rather than mid-flow is what makes the contract
        checkable: for the whole procedure the vehicle is configured exactly as
        the `overrides:` block says, and `_restore` puts it back afterwards.
        """
        for override in proc.overrides:
            value = self._resolve(override.value, values)
            name = override.param

            def _set(link: MavlinkLink, n=name, v=value) -> dict:
                previous = link._param_get(n)
                res = link._do_param(["set", n, str(v)])
                if res.get("ok"):
                    res["previous"] = previous
                return res

            res = self.link.submit(_set, 15.0, f"override {name}")
            record = {"set_to": value, "restore_to": res.get("previous"),
                      "restore": bool(override.restore),
                      "reason": override.reason_text(self.lang),
                      "applied": bool(res.get("ok"))}
            changed_params[name] = record
            self._emit("override", override={"param": name, **_plain(record)})
            if not res.get("ok"):
                raise ProcedureAborted(
                    t("proc_override_failed", name=name,
                      value=f"{value:g}" if isinstance(value, float) else value,
                      text=res.get("text", "")))

    # ------------------------------------------------------------------ run
    def run(self, proc: Procedure, values: Optional[dict] = None) -> dict:
        """Executes a procedure and returns a machine-readable result."""
        self._cancel = False
        values = {**proc.default_values(), **(values or {})}
        steps = [StepResult(index=i, kind=s.kind, label=s.label(self.lang))
                 for i, s in enumerate(proc.steps)]
        changed_params: dict = {}
        fault_results: list[FaultResult] = []
        started = time.time()
        aborted_text = ""
        outcome = OUTCOME_PASSED

        self._emit("start", procedure=proc.id, name=proc.label(self.lang),
                   values=_plain(values), steps=[s.as_dict() for s in steps],
                   overrides=[o.as_dict(self.lang) for o in proc.overrides],
                   failures=[f.as_dict(self.lang) for f in proc.failures])

        try:
            # Before anything is written to the vehicle: a scenario whose fault
            # mechanism is not on this firmware must not fly at all.
            injectors = self._prepare_faults(proc)
            self._apply_overrides(proc, values, changed_params)
            # From here to the last acceptance check, how the aircraft behaves
            # is on the record. Reset after the overrides so the parameter
            # writes — during which the vehicle is still sitting on the ground
            # — are not counted as flight.
            self.link.stability.reset()

            # A fault may be declared for the point before the first step.
            self._faults_at(proc, injectors, 0, values, fault_results)

            for step, result in zip(proc.steps, steps):
                if self._cancel:
                    raise ProcedureAborted(t("proc_cancelled"))
                if time.time() - started > proc.timeout:
                    raise ProcedureAborted(
                        t("proc_overall_timeout", seconds=f"{proc.timeout:g}"))

                if step.when is not None:
                    holds, seen = self._check(self._resolve_condition(step.when, values))
                    if not holds:
                        result.status = "skipped"
                        result.text = t("proc_skipped", seen=seen)
                        self._emit("step", step=result.as_dict())
                        continue

                result.status = "running"
                self._emit("step", step=result.as_dict())

                at = time.time()
                res = self._run_step(step, values, changed_params)
                result.seconds = time.time() - at
                result.text = res.get("text", "")
                result.status = "passed" if res.get("ok") else "failed"
                self._emit("step", step=result.as_dict())

                if not res.get("ok") and step.on_fail == "abort":
                    raise ProcedureAborted(result.text)

                # Injection points are counted in completed steps, so
                # `inject_after_step: 3` means "after the third step has run".
                self._faults_at(proc, injectors, result.index + 1, values,
                                fault_results)

            # ---------------------------------------------------- acceptance
            expects = []
            for exp in proc.expect:
                cond = self._resolve_condition(exp.condition, values)
                er = self._evaluate(exp, cond)
                expects.append(er)
                self._emit("expect", expect=er.as_dict())

            passed = (all(e.passed for e in expects)
                      and all(s.status in ("passed", "skipped") for s in steps)
                      # A declared fault whose criteria did not hold fails the
                      # procedure exactly as an `expect:` entry does. Anything
                      # else would make an off-nominal scenario a report rather
                      # than a test.
                      and all(f.passed for f in fault_results))
            outcome = OUTCOME_PASSED if passed else OUTCOME_FAILED

        except ProcedureAborted as exc:
            aborted_text = str(exc)
            outcome = OUTCOME_FAILED
            expects = self._unevaluated(proc, steps)
        except Exception as exc:
            # Anything that is not a flight verdict: a malformed step reaching
            # the runner, the link dropping, a bug in here. Before this, such
            # an exception escaped into the procedure thread and the UI simply
            # stopped updating. It is now an `error` outcome — distinct from a
            # `failed` one, because it says nothing about the aircraft.
            aborted_text = t("proc_internal_error", err=f"{type(exc).__name__}: {exc}")
            outcome = OUTCOME_ERROR
            expects = self._unevaluated(proc, steps)
        finally:
            self._restore(changed_params)
            # Second guarantee, after the injector's own `finally`: a scenario
            # that died between `apply` and `clear` must not leave this
            # process's link degraded for whatever runs next.
            self.link.clear_link_fault()

        passed = outcome == OUTCOME_PASSED
        result = {
            "ok": passed,
            "outcome": outcome,
            "procedure": proc.id,
            "name": proc.label(self.lang),
            "role": proc.role,
            "values": _plain(values),
            "steps": [s.as_dict() for s in steps],
            "expect": [e.as_dict() for e in expects],
            # What was done to the simulator, and what the aircraft did about
            # it. Empty for every nominal procedure, which is most of them.
            "faults": [f.as_dict() for f in fault_results],
            # The measured envelope, recorded whether or not any criterion
            # asked about it. A procedure that declares no attitude limit still
            # leaves the evidence behind for whoever reads the run later.
            "stability": self.link.stability.report(),
            "params_changed": _plain(changed_params),
            "seconds": round(time.time() - started, 1),
            "text": aborted_text or (t("proc_passed", name=proc.label(self.lang))
                                     if passed else
                                     t("proc_failed", name=proc.label(self.lang))),
        }
        # WHY THE CLASSIFICATION IS COMPUTED HERE AND NOT BY THE READER
        # -------------------------------------------------------------
        # Everything it rests on — which step failed, whether an override took,
        # whether a fault could be injected — is in this document. Working it
        # out again later means writing a second implementation of the same
        # judgement, and the two would disagree the first time a step type was
        # added. The category is stored, so `docs/status.md`, the run listing
        # and the report all read one answer.
        failure = failurelib.classify_procedure(result)
        result["failure"] = failure.as_dict() if failure else None
        self._emit("done", result=result)
        return result

    def _unevaluated(self, proc: Procedure, steps: list[StepResult]) -> list[ExpectResult]:
        """Marks the criteria that never got a chance to run."""
        for s in steps:
            if s.status in ("pending", "running"):
                s.status = "skipped" if s.status == "pending" else "failed"
        return [ExpectResult(label=e.label(self.lang), condition=_plain(e.condition),
                             passed=False, text=t("proc_not_evaluated"),
                             kind=e.kind, duration=e.duration)
                for e in proc.expect]

    def _restore(self, changed_params: dict) -> None:
        """Puts back every parameter the procedure changed.

        Runs from a `finally`, so an aborted, cancelled or errored procedure
        leaves the vehicle configured exactly as it was found. Whether each
        restore actually succeeded is recorded — a failed restore is a fact
        about the vehicle's current state and has to reach the run directory
        instead of being assumed away.
        """
        for name, record in changed_params.items():
            if record.get("restore") is False:
                record["restored"] = None       # deliberately left in place
                continue
            previous = record.get("restore_to")
            if previous is None:
                # The parameter could not be read before it was written, so
                # there is nothing to put back and nothing to claim.
                record["restored"] = None
                continue
            res = self.link.submit(
                lambda l, n=name, v=previous: l._do_param(["set", n, str(v)]),
                timeout=10.0, label=f"restore {name}")
            record["restored"] = bool(res.get("ok"))
            if not res.get("ok"):
                self._emit("restore_failed",
                           override={"param": name, "restore_to": previous,
                                     "text": res.get("text", "")})


def _enum(module, name: str) -> int:
    """Resolves a MAVLink enum name through pymavlink, with a clear failure."""
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise ProcedureAborted(t("proc_unknown_enum", name=name)) from exc
