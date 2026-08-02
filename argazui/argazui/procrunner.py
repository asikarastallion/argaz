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
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from pymavlink import mavutil

from .i18n import t
from .mavlink_link import MavlinkLink, substitute
from .procedures import Procedure, Step

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

    def as_dict(self) -> dict:
        return {"label": self.label, "condition": _plain(self.condition),
                "passed": self.passed, "text": self.text}


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
        started = time.time()
        aborted_text = ""
        outcome = OUTCOME_PASSED

        self._emit("start", procedure=proc.id, name=proc.label(self.lang),
                   values=_plain(values), steps=[s.as_dict() for s in steps],
                   overrides=[o.as_dict(self.lang) for o in proc.overrides])

        try:
            self._apply_overrides(proc, values, changed_params)
            # From here to the last acceptance check, how the aircraft behaves
            # is on the record. Reset after the overrides so the parameter
            # writes — during which the vehicle is still sitting on the ground
            # — are not counted as flight.
            self.link.stability.reset()

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

            # ---------------------------------------------------- acceptance
            expects = []
            for exp in proc.expect:
                cond = self._resolve_condition(exp.condition, values)
                ok, seen = self._wait_for(cond, exp.timeout)
                er = ExpectResult(label=exp.label(self.lang), condition=cond,
                                  passed=ok, text=seen)
                expects.append(er)
                self._emit("expect", expect=er.as_dict())

            passed = all(e.passed for e in expects) and \
                all(s.status in ("passed", "skipped") for s in steps)
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
        self._emit("done", result=result)
        return result

    def _unevaluated(self, proc: Procedure, steps: list[StepResult]) -> list[ExpectResult]:
        """Marks the criteria that never got a chance to run."""
        for s in steps:
            if s.status in ("pending", "running"):
                s.status = "skipped" if s.status == "pending" else "failed"
        return [ExpectResult(label=e.label(self.lang), condition=_plain(e.condition),
                             passed=False, text=t("proc_not_evaluated"))
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
