"""Procedure loading, validation and selection.

A procedure is a declarative flight sequence in `argazui/procedures/*.yaml`.
The format is documented in `argazui/procedures/SCHEMA.md`; this module is its
reference implementation and the validator is deliberately strict, because a
typo in a procedure must fail at load time rather than half way through a
takeoff.

WHY SELECTION IS CAPABILITY-BASED
---------------------------------
The registry's `vehicle_class` (Copter / Plane / VTOL) is not enough to choose
a takeoff. Two examples from this repository's own model set:

  * SkyCat TVBS is registered as a plain "QuadPlane" but its parameter file
    sets Q_TAILSIT_ENABLE=1 — it is a tailsitter, and the tailsitter arming
    problem applies to it.
  * Swan-K1 ships Q_OPTIONS=262274, which has bit 1 (Allow FW Takeoff) and
    bit 18 (ARMVTOL) set. Those bits change what a NAV_TAKEOFF mission item
    means and which modes the aircraft will arm in.

Neither fact is visible in `models.json`. So the capabilities a procedure
matches against are READ FROM THE VEHICLE over MAVLink (see
`probe_capabilities` in procrunner.py) and the class string is only used as a
hint for the autopilot type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from . import faults as faultlib
from . import paths
from . import trace as tracelib

# The current schema. Schema 1 files are still loaded unchanged; schema 2 adds
# the temporal acceptance criteria and the instantaneous attitude conditions
# introduced in v1.3, schema 3 adds the `failures:` block — controlled fault
# injection — introduced in v1.4, and schema 4 adds author-declared trace
# identifiers (v1.5). A file has to declare the version whose features it uses.
# Extending a schema in place would have been quieter and worse: an older
# ArgazUI would have read a `within:`, a `failures:` or an `id:` it does not
# implement out of a document claiming a version it satisfies.
SCHEMA_VERSION = 4
SUPPORTED_SCHEMAS = (1, 2, 3, 4)

# Still reserved (see SCHEMA.md). `failures:` left this list in v1.4; `mission:`
# stays, so that nothing starts depending on a half-defined meaning before the
# mission runner exists.
RESERVED_KEYS = ("mission",)

STEP_TYPES = (
    "set_param", "get_param", "set_mode", "arm", "disarm",
    "rc_override", "rc_release", "send_command", "upload_mission",
    "wait_for", "sleep",
)

CONDITION_KEYS = (
    "armed", "mode", "mode_in", "alt_above", "alt_below",
    "climb_rate_above", "climb_rate_below", "groundspeed_above",
    "prearm_ok", "param", "attitude_stable",
)

# Instantaneous attitude conditions, new in schema 2. They answer "what is the
# aircraft doing right now", which is what the temporal primitives below need:
# `attitude_stable` is accumulated over the whole procedure and cannot be asked
# to hold "for 5 s" or "never", because it is already an answer about all of it.
CONDITION_KEYS_V2 = ("roll_within", "pitch_within",
                     "angular_rate_above", "angular_rate_below")

# Conditions whose value is an ordered [low, high] band rather than a number.
BAND_CONDITIONS = ("roll_within", "pitch_within")

# Temporal acceptance keys, new in schema 2. Exactly one may appear on an
# `expect:` entry — see `_parse_expect` for why combining them is rejected
# rather than given a defined-but-unreadable meaning.
TEMPORAL_KEYS = ("within", "for", "never")

# Duration suffixes. A duration must carry one: `for: 5` is ambiguous in a file
# that also writes altitudes and PWM values as bare numbers, and this project
# has already paid once for a number whose unit was only in someone's head.
# `m` is deliberately NOT accepted — in a flight procedure it reads as metres.
DURATION_UNITS = {"ms": 0.001, "s": 1.0, "sec": 1.0, "min": 60.0}

# `attitude_stable` is judged over the whole procedure rather than at an
# instant, and a violation already in the past cannot be undone by waiting —
# see MONOTONE_CONDITIONS in procrunner.py.
STABILITY_KEYS = ("roll", "pitch", "max_rate", "tolerance", "min_seconds")

# `scenario`, new in v1.4, is the role an off-nominal flow declares. It is
# deliberately NOT a third button: takeoff and land are auto-selected from
# probed capabilities, and a scenario is always chosen by name, because
# injecting a fault is never something that should happen because a heuristic
# thought it applied.
ROLES = ("takeoff", "land", "scenario")

# Roles a capability probe may pick automatically.
AUTO_ROLES = ("takeoff", "land")

# Keys of a `failures:` entry (schema 3).
FAULT_KEYS = ("id", "fault", "target", "options", "inject_after_step", "start",
              "duration", "expected", "expect", "recovery", "evidence")

# applies_to keys that are matched against probed vehicle capabilities.
CAPABILITY_KEYS = ("autopilot", "quadplane", "tailsitter", "fw_takeoff_allowed",
                   "arm_vtol_only")


class ProcedureError(ValueError):
    """A procedure file is malformed. Carries the file name for the message."""


def _text(value: Any, where: str) -> dict:
    """Normalises a user-visible string into {'en': ..., 'tr': ...}."""
    if value is None:
        return {}
    if isinstance(value, str):
        return {"en": value, "tr": value}
    if isinstance(value, dict):
        out = {k: str(v) for k, v in value.items() if k in ("en", "tr")}
        if not out:
            raise ProcedureError(f"{where}: needs an 'en' and/or 'tr' key")
        out.setdefault("tr", out.get("en", ""))
        out.setdefault("en", out.get("tr", ""))
        return out
    raise ProcedureError(f"{where}: expected a string or an {{en, tr}} map")


def parse_duration(value: Any, where: str) -> float:
    """"10s" / "500ms" / "2min" -> seconds. A bare number is rejected.

    The unit is mandatory rather than defaulted. Every other number in this
    format is a metre, a degree, a PWM count or a parameter value, and a
    duration that looked like any of them would be read wrong exactly once —
    silently, in flight, by whoever inherits the file.
    """
    if isinstance(value, bool) or not isinstance(value, str):
        raise ProcedureError(
            f"{where}: a duration needs an explicit unit, e.g. \"10s\", "
            f"\"500ms\" or \"2min\" — got {value!r}")
    text = value.strip().lower().replace(" ", "")
    for suffix in sorted(DURATION_UNITS, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)]
            try:
                seconds = float(number) * DURATION_UNITS[suffix]
            except ValueError:
                break
            if seconds <= 0:
                raise ProcedureError(f"{where}: a duration must be positive, got {value!r}")
            return seconds
    raise ProcedureError(
        f"{where}: {value!r} is not a duration. Use one of "
        f"{', '.join(sorted(DURATION_UNITS))} — 'm' is not accepted because in a "
        f"flight procedure it reads as metres.")


def format_duration(seconds: float) -> str:
    """Seconds back to the written form, so a message quotes what the file says."""
    if seconds < 1.0:
        return f"{seconds * 1000:g}ms"
    if seconds >= 120.0 and abs(seconds / 60.0 - round(seconds / 60.0)) < 1e-9:
        return f"{seconds / 60.0:g}min"
    return f"{seconds:g}s"


def _check_condition(cond: Any, where: str, schema: int = SCHEMA_VERSION) -> dict:
    if not isinstance(cond, dict) or not cond:
        raise ProcedureError(f"{where}: a condition must be a non-empty map")
    known = CONDITION_KEYS + (CONDITION_KEYS_V2 if schema >= 2 else ())
    for key in cond:
        if key in CONDITION_KEYS_V2 and schema < 2:
            raise ProcedureError(
                f"{where}: '{key}' was added in procedure schema 2; this file "
                f"declares schema {schema}. Set 'schema: 2' to use it.")
        if key not in known:
            raise ProcedureError(
                f"{where}: unknown condition '{key}'. Known: {', '.join(known)}")
    if "param" in cond:
        p = cond["param"]
        if not isinstance(p, dict) or "name" not in p:
            raise ProcedureError(f"{where}: param condition needs a 'name'")
    if "attitude_stable" in cond:
        _check_stability(cond["attitude_stable"], f"{where}.attitude_stable")
    for key in BAND_CONDITIONS:
        if key in cond:
            _check_band(cond[key], f"{where}.{key}")
    for key in ("angular_rate_above", "angular_rate_below"):
        if key in cond and not isinstance(cond[key], str):
            if float(cond[key]) <= 0:
                raise ProcedureError(
                    f"{where}.{key}: must be a positive rate in deg/s")
    return cond


def _check_band(band: Any, where: str) -> None:
    """An ordered [low, high] pair in degrees.

    Strict about the order for the same reason `_check_stability` is: a
    reversed band rejects everything, which reads as a broken aircraft rather
    than a broken procedure.
    """
    if (not isinstance(band, (list, tuple)) or len(band) != 2
            or not all(isinstance(v, (int, float)) for v in band)):
        raise ProcedureError(f"{where}: expected [low, high] in degrees")
    if float(band[0]) >= float(band[1]):
        raise ProcedureError(
            f"{where}: low ({band[0]}) must be below high ({band[1]})")


def _check_stability(spec: Any, where: str) -> None:
    """Validates an attitude envelope limit.

    Deliberately strict about the band being a two-element ordered pair: a
    reversed band silently rejects everything, which would look like a broken
    aircraft rather than a broken procedure.
    """
    if not isinstance(spec, dict) or not spec:
        raise ProcedureError(f"{where}: expected a map of limits, "
                             f"e.g. {{max_rate: 90, tolerance: 2}}")
    for key in spec:
        if key not in STABILITY_KEYS:
            raise ProcedureError(
                f"{where}: unknown limit '{key}'. Known: {', '.join(STABILITY_KEYS)}")
    if not any(k in spec for k in ("roll", "pitch", "max_rate")):
        raise ProcedureError(
            f"{where}: state at least one of roll, pitch or max_rate — an envelope "
            f"criterion that limits nothing accepts everything")
    for axis in ("roll", "pitch"):
        if axis not in spec:
            continue
        band = spec[axis]
        if (not isinstance(band, (list, tuple)) or len(band) != 2
                or not all(isinstance(v, (int, float)) for v in band)):
            raise ProcedureError(f"{where}.{axis}: expected [low, high] in degrees")
        if float(band[0]) >= float(band[1]):
            raise ProcedureError(
                f"{where}.{axis}: low ({band[0]}) must be below high ({band[1]})")
    if "max_rate" in spec and float(spec["max_rate"]) <= 0:
        raise ProcedureError(f"{where}.max_rate: must be a positive rate in deg/s")
    for key in ("tolerance", "min_seconds"):
        if key in spec and float(spec[key]) < 0:
            raise ProcedureError(f"{where}.{key}: must not be negative")


@dataclass
class Step:
    kind: str
    value: Any
    name: dict = field(default_factory=dict)
    timeout: Optional[float] = None
    on_fail: str = "abort"
    when: Optional[dict] = None
    # An author-declared identifier, or None to derive one from position.
    # A step id is only ever read inside the run that produced it, so position
    # is a good enough name — see trace.py.
    id: Optional[str] = None

    def label(self, lang: str = "en") -> str:
        if self.name:
            return self.name.get(lang) or self.name.get("en") or self.kind
        return self.kind


@dataclass
class Expectation:
    """One acceptance criterion, optionally with a temporal shape.

    Schema 1 had exactly one shape: evaluate the condition, waiting up to
    `timeout` for it to become true. That shape is unchanged and is still what
    an entry with no temporal key means.

    Schema 2 adds three, and each answers a question the single shape could
    not:

        within   the condition must BECOME true inside a deadline
        hold_for the condition must then REMAIN true, continuously
        never    the condition must NOT become true at any point in a window

    `hold_for` is spelled `for:` in YAML; `for` is a Python keyword.
    """

    condition: dict
    timeout: float = 30.0
    message: dict = field(default_factory=dict)
    within: Optional[float] = None
    hold_for: Optional[float] = None
    never: Optional[float] = None
    # An author-declared identifier. Unlike a step's, a criterion's id is
    # quoted OUTSIDE its own run — in the coverage report, in the "what was not
    # tested" list, in a comparison of two runs months apart — so it needs a
    # name that survives somebody inserting a criterion above it. Absent, one
    # is derived from position and marked as derived. See trace.py.
    id: Optional[str] = None

    @property
    def kind(self) -> str:
        """Which of the four shapes this is — the evaluator dispatches on it."""
        if self.within is not None:
            return "within"
        if self.hold_for is not None:
            return "for"
        if self.never is not None:
            return "never"
        return "eventually"

    @property
    def duration(self) -> Optional[float]:
        return {"within": self.within, "for": self.hold_for,
                "never": self.never}.get(self.kind)

    def label(self, lang: str = "en") -> str:
        if self.message:
            return self.message.get(lang) or self.message.get("en") or ""
        stated = ", ".join(f"{k}={v}" for k, v in self.condition.items())
        if self.kind == "eventually":
            return stated
        return f"{stated} [{self.kind} {format_duration(self.duration or 0.0)}]"


@dataclass
class Fault:
    """One declared, controlled fault — the `failures:` block of schema 3.

    Every field the architecture requires of a fault is here and none is
    optional-by-omission:

        inject_after_step  WHERE in the flow it happens
        start              the state that must hold before it is injected
        duration           how long it is held, on the vehicle's clock
        fault + target     WHAT is degraded, and which instance of it
        expected           what a person should expect to see — in words
        expect / recovery  what a machine decides the verdict on
        evidence           the telemetry the verdict is only valid with

    `expected` is prose and `expect` is criteria, and the pair is deliberate. A
    scenario whose expected behaviour is only expressible as a threshold has
    usually not been thought through, and one with only prose cannot be
    verified at all.
    """

    id: str
    kind: str
    target: str
    options: dict
    inject_after_step: int
    duration: float
    expected: dict
    expect: list[Expectation] = field(default_factory=list)
    recovery: list[Expectation] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    start_condition: Optional[dict] = None
    start_within: float = 60.0

    def label(self, lang: str = "en") -> str:
        return f"{self.id} ({faultlib.label_for(self.kind, lang)})"

    def expected_text(self, lang: str = "en") -> str:
        return self.expected.get(lang) or self.expected.get("en") or ""

    def as_dict(self, lang: str = "en") -> dict:
        return {
            "id": self.id, "fault": self.kind, "target": self.target,
            "options": dict(self.options),
            "inject_after_step": self.inject_after_step,
            "duration": self.duration,
            "duration_text": format_duration(self.duration),
            "expected": self.expected_text(lang),
            "start": ({"condition": _plain_condition(self.start_condition),
                       "within": self.start_within}
                      if self.start_condition else None),
            "expect": [e.label(lang) for e in self.expect],
            "recovery": [e.label(lang) for e in self.recovery],
            "evidence": list(self.evidence),
        }


def _plain_condition(cond: Optional[dict]) -> dict:
    return {str(k): v for k, v in (cond or {}).items()}


@dataclass
class Override:
    """A parameter this procedure needs changed, and why.

    WHY A DECLARATION RATHER THAN JUST A STEP
    -----------------------------------------
    v1.1 phase 1 let any `set_param` step quietly rewrite the vehicle. That is
    the same class of behaviour this project exists to catch: a test tool that
    adjusts the aircraft until its own test passes proves nothing. Declaring
    the change here forces three things — it is visible in the procedure, the
    reason is written down in both languages, and the run directory and the
    flight report both lead with the list.
    """

    param: str
    value: Any
    reason: dict = field(default_factory=dict)
    restore: bool = True

    def reason_text(self, lang: str = "en") -> str:
        return self.reason.get(lang) or self.reason.get("en") or ""

    def as_dict(self, lang: str = "en") -> dict:
        return {"param": self.param, "value": self.value,
                "reason": self.reason_text(lang), "restore": self.restore}


@dataclass
class Input:
    name: str
    label: dict
    default: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def as_dict(self, lang: str = "en") -> dict:
        out = {"name": self.name,
               "label": self.label.get(lang) or self.label.get("en") or self.name,
               "default": self.default}
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        return out


@dataclass
class Procedure:
    id: str
    schema: int
    path: Path
    name: dict
    description: dict
    sources: list[str]
    role: str
    applies_to: dict
    default: bool
    priority: int
    inputs: list[Input]
    overrides: list[Override]
    steps: list[Step]
    expect: list[Expectation]
    timeout: float
    raw_text: str
    failures: list[Fault] = field(default_factory=list)

    def label(self, lang: str = "en") -> str:
        return self.name.get(lang) or self.name.get("en") or self.id

    def describe(self, lang: str = "en") -> str:
        return self.description.get(lang) or self.description.get("en") or ""

    def default_values(self) -> dict:
        return {i.name: i.default for i in self.inputs}

    def as_dict(self, lang: str = "en") -> dict:
        return {
            "id": self.id,
            "name": self.label(lang),
            "description": self.describe(lang),
            "role": self.role,
            "default": self.default,
            "priority": self.priority,
            "sources": self.sources,
            "inputs": [i.as_dict(lang) for i in self.inputs],
            "overrides": [o.as_dict(lang) for o in self.overrides],
            "steps": [{"name": s.label(lang), "kind": s.kind} for s in self.steps],
            "expect": [e.label(lang) for e in self.expect],
            "failures": [f.as_dict(lang) for f in self.failures],
        }

    def matches(self, caps: dict) -> bool:
        """True when every capability the procedure states equals the probe."""
        for key in CAPABILITY_KEYS:
            if key not in self.applies_to:
                continue                       # not stated -> don't care
            want = self.applies_to[key]
            got = caps.get(key)
            if got is None:                    # couldn't probe it -> can't match
                return False
            if isinstance(want, bool):
                if bool(got) != want:
                    return False
            elif got != want:
                return False
        return True


# --------------------------------------------------------------------------- parse
def _parse_step(raw: Any, where: str, schema: int = SCHEMA_VERSION) -> Step:
    if not isinstance(raw, dict):
        raise ProcedureError(f"{where}: a step must be a map")
    kinds = [k for k in raw if k in STEP_TYPES]
    if len(kinds) != 1:
        raise ProcedureError(
            f"{where}: a step needs exactly one step-type key, found {kinds or 'none'}. "
            f"Known: {', '.join(STEP_TYPES)}")
    kind = kinds[0]
    for key in raw:
        if key not in STEP_TYPES and key not in ("name", "timeout", "on_fail",
                                                 "when", "id"):
            raise ProcedureError(f"{where}: unknown step key '{key}'")

    value = raw[kind]
    if kind == "get_param":
        if not isinstance(value, dict) or "name" not in value:
            raise ProcedureError(f"{where}: get_param needs a 'name'")
        value = dict(value)
        if "fail_message" in value:
            value["fail_message"] = _text(value["fail_message"], f"{where}.fail_message")
    elif kind == "set_param":
        if not isinstance(value, dict) or "name" not in value or "value" not in value:
            raise ProcedureError(f"{where}: set_param needs 'name' and 'value'")
    elif kind == "arm" or kind == "disarm":
        value = value if isinstance(value, dict) else {}
    elif kind == "rc_override":
        if not isinstance(value, dict) or not isinstance(value.get("channels"), dict):
            raise ProcedureError(f"{where}: rc_override needs a 'channels' map")
    elif kind == "send_command":
        if not isinstance(value, dict) or "command" not in value:
            raise ProcedureError(f"{where}: send_command needs a 'command'")
        if value.get("type", "long") not in ("long", "int"):
            raise ProcedureError(f"{where}: send_command type must be 'long' or 'int'")
    elif kind == "upload_mission":
        items = (value or {}).get("items") if isinstance(value, dict) else None
        if not items:
            raise ProcedureError(f"{where}: upload_mission needs a non-empty 'items'")
    elif kind == "wait_for":
        value = _check_condition(value, f"{where}.wait_for", schema)

    on_fail = raw.get("on_fail", "abort")
    if on_fail not in ("abort", "continue"):
        raise ProcedureError(f"{where}: on_fail must be 'abort' or 'continue'")

    return Step(
        kind=kind,
        value=value,
        name=_text(raw.get("name"), f"{where}.name"),
        timeout=float(raw["timeout"]) if raw.get("timeout") is not None else None,
        on_fail=on_fail,
        when=(_check_condition(raw["when"], f"{where}.when", schema)
              if raw.get("when") else None),
        id=_check_id(raw.get("id"), f"{where}.id", schema),
    )


def _check_unique_ids(declared: list, where: str, what: str) -> None:
    named = [value for value in declared if value]
    duplicates = sorted({value for value in named if named.count(value) > 1})
    if duplicates:
        raise ProcedureError(
            f"{where}: two {what}s share the id "
            f"{', '.join(repr(d) for d in duplicates)}. An identifier is "
            f"quoted outside this file, so it has to name one thing.")


def _check_id(value: Any, where: str, schema: int) -> Optional[str]:
    """Validates an author-declared trace identifier, or returns None.

    Rejected at load time rather than sanitised, for the same reason a bad
    duration is: an identifier is quoted in tables, URLs and shell commands,
    and one that needs escaping in any of them is one that will be got wrong
    somewhere.
    """
    if value is None:
        return None
    if schema < 4:
        raise ProcedureError(
            f"{where}: trace identifiers were added in procedure schema 4; "
            f"this file declares schema {schema}. Set 'schema: 4' to use them.")
    try:
        return tracelib.check_declared(value, where)
    except tracelib.TraceError as exc:
        raise ProcedureError(str(exc)) from exc


def _parse_expect(raw: Any, where: str, schema: int) -> Expectation:
    """One `expect:` entry, including its temporal shape.

    The combinations rejected here are rejected because there is no reading of
    them that stays deterministic, and a criterion whose meaning depends on the
    reader is worse than one that does not exist.
    """
    if not isinstance(raw, dict) or "condition" not in raw:
        raise ProcedureError(f"{where}: needs a 'condition'")
    for key in raw:
        if key not in ("condition", "timeout", "message", "id") + TEMPORAL_KEYS:
            raise ProcedureError(f"{where}: unknown key '{key}'")

    stated = [key for key in TEMPORAL_KEYS if raw.get(key) is not None]
    if stated and schema < 2:
        raise ProcedureError(
            f"{where}: temporal criteria ({', '.join(stated)}) were added in "
            f"procedure schema 2; this file declares schema {schema}. Set "
            f"'schema: 2' to use them.")
    if len(stated) > 1:
        raise ProcedureError(
            f"{where}: state at most one of {', '.join(TEMPORAL_KEYS)} — "
            f"{' and '.join(stated)} together have no single evaluation order. "
            f"Split them into separate criteria.")

    condition = _check_condition(raw["condition"], f"{where}.condition", schema)
    if stated and "attitude_stable" in condition:
        raise ProcedureError(
            f"{where}: 'attitude_stable' is already accumulated over the whole "
            f"procedure, so it cannot also be judged '{stated[0]}'. Use "
            f"roll_within / pitch_within / angular_rate_above for an "
            f"instantaneous condition, or drop the temporal key.")
    if "within" in stated and raw.get("timeout") is not None:
        raise ProcedureError(
            f"{where}: 'within' and 'timeout' are two names for the same "
            f"deadline. Keep 'within', which states its unit.")

    return Expectation(
        condition=condition,
        timeout=float(raw.get("timeout", 30)),
        message=_text(raw.get("message"), f"{where}.message"),
        within=(parse_duration(raw["within"], f"{where}.within")
                if raw.get("within") is not None else None),
        hold_for=(parse_duration(raw["for"], f"{where}.for")
                  if raw.get("for") is not None else None),
        never=(parse_duration(raw["never"], f"{where}.never")
               if raw.get("never") is not None else None),
        id=_check_id(raw.get("id"), f"{where}.id", schema),
    )


def _parse_fault(raw: Any, where: str, schema: int, step_count: int) -> Fault:
    """One `failures:` entry.

    Validated hard, for a reason this project has met before in a milder form:
    a mis-declared acceptance criterion produces a wrong verdict, and a
    mis-declared fault produces a wrong verdict *about an aircraft that was
    never actually degraded*. Every rejection below is a case where the run
    would otherwise have looked like an off-nominal test and been a nominal
    one.
    """
    if schema < 3:
        raise ProcedureError(
            f"{where}: 'failures:' was added in procedure schema 3; this file "
            f"declares schema {schema}. Set 'schema: 3' to use it.")
    if not isinstance(raw, dict):
        raise ProcedureError(f"{where}: a fault must be a map")
    for key in raw:
        if key not in FAULT_KEYS:
            raise ProcedureError(
                f"{where}: unknown fault key '{key}'. Known: {', '.join(FAULT_KEYS)}")
    for key in ("id", "fault", "target", "inject_after_step", "duration",
                "expected", "evidence"):
        if raw.get(key) is None:
            raise ProcedureError(f"{where}: a fault needs '{key}'")

    try:
        options = faultlib.check_declaration(
            raw["fault"], raw["target"], raw.get("options"), where)
    except (ValueError, TypeError) as exc:
        raise ProcedureError(str(exc)) from exc

    after = raw["inject_after_step"]
    if not isinstance(after, int) or isinstance(after, bool) \
            or not 0 <= after <= step_count:
        raise ProcedureError(
            f"{where}: inject_after_step must be a step number between 0 and "
            f"{step_count} (0 injects before the first step); got {after!r}")

    duration = parse_duration(raw["duration"], f"{where}.duration")

    start_condition = None
    start_within = 60.0
    start = raw.get("start")
    if start is not None:
        if not isinstance(start, dict) or "condition" not in start:
            raise ProcedureError(
                f"{where}.start: needs a 'condition' (and optionally a 'within')")
        for key in start:
            if key not in ("condition", "within"):
                raise ProcedureError(f"{where}.start: unknown key '{key}'")
        start_condition = _check_condition(start["condition"],
                                           f"{where}.start.condition", schema)
        if start.get("within") is not None:
            start_within = parse_duration(start["within"], f"{where}.start.within")

    expect = [_parse_expect(item, f"{where}.expect[{i}]", schema)
              for i, item in enumerate(raw.get("expect") or [])]
    recovery = [_parse_expect(item, f"{where}.recovery[{i}]", schema)
                for i, item in enumerate(raw.get("recovery") or [])]
    if not expect and not recovery:
        raise ProcedureError(
            f"{where}: state at least one criterion under 'expect' (judged while "
            f"the fault is held) or 'recovery' (judged after it is cleared). A "
            f"fault with no criteria proves only that the fault was injected, "
            f"which is not a result about the aircraft.")

    evidence = raw["evidence"]
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list) or not evidence:
        raise ProcedureError(
            f"{where}.evidence: list at least one signal the verdict rests on. "
            f"Known: {', '.join(faultlib.EVIDENCE_SIGNALS)}")
    for signal in evidence:
        if signal not in faultlib.EVIDENCE_SIGNALS:
            raise ProcedureError(
                f"{where}.evidence: unknown signal '{signal}'. Known: "
                f"{', '.join(faultlib.EVIDENCE_SIGNALS)}")

    return Fault(
        id=str(raw["id"]), kind=str(raw["fault"]), target=str(raw["target"]),
        options=options, inject_after_step=after, duration=duration,
        expected=_text(raw["expected"], f"{where}.expected"),
        expect=expect, recovery=recovery, evidence=list(evidence),
        start_condition=start_condition, start_within=start_within,
    )


def parse(text: str, path: Path) -> Procedure:
    """Parses and validates one procedure document."""
    where = path.name
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProcedureError(f"{where}: not valid YAML — {exc}") from exc
    if not isinstance(doc, dict):
        raise ProcedureError(f"{where}: the top level must be a map")

    for key in RESERVED_KEYS:
        if key in doc:
            raise ProcedureError(
                f"{where}: '{key}:' is reserved for a later schema and is not "
                f"implemented. See SCHEMA.md.")

    version = doc.get("schema")
    if version not in SUPPORTED_SCHEMAS:
        raise ProcedureError(
            f"{where}: schema must be one of "
            f"{', '.join(str(v) for v in SUPPORTED_SCHEMAS)}, found {version!r}")

    pid = doc.get("id")
    if pid != path.stem:
        raise ProcedureError(f"{where}: id {pid!r} must equal the filename stem {path.stem!r}")

    sources = doc.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ProcedureError(
            f"{where}: 'sources' must list at least one documentation URL — a procedure "
            f"has to say where its flow comes from")

    applies = doc.get("applies_to")
    if not isinstance(applies, dict):
        raise ProcedureError(f"{where}: 'applies_to' is required")
    role = applies.get("role")
    if role not in ROLES:
        raise ProcedureError(f"{where}: applies_to.role must be one of {ROLES}")
    for key in applies:
        if key not in CAPABILITY_KEYS + ("role", "default", "priority"):
            raise ProcedureError(f"{where}: unknown applies_to key '{key}'")

    inputs = []
    for i, raw in enumerate(doc.get("inputs") or []):
        if not isinstance(raw, dict) or "name" not in raw:
            raise ProcedureError(f"{where}: inputs[{i}] needs a 'name'")
        if raw.get("type", "number") != "number":
            raise ProcedureError(f"{where}: inputs[{i}] type must be 'number' in schema 1")
        inputs.append(Input(
            name=str(raw["name"]),
            label=_text(raw.get("label") or raw["name"], f"{where}.inputs[{i}].label"),
            default=float(raw.get("default", 0)),
            minimum=None if raw.get("min") is None else float(raw["min"]),
            maximum=None if raw.get("max") is None else float(raw["max"]),
        ))

    overrides = []
    raw_overrides = doc.get("overrides")
    if raw_overrides is not None and not isinstance(raw_overrides, list):
        raise ProcedureError(f"{where}: 'overrides' must be a list")
    for i, raw in enumerate(raw_overrides or []):
        spot = f"{where}.overrides[{i}]"
        if not isinstance(raw, dict):
            raise ProcedureError(f"{spot}: an override must be a map")
        for key in raw:
            if key not in ("param", "value", "reason", "restore"):
                raise ProcedureError(f"{spot}: unknown override key '{key}'")
        if "param" not in raw or "value" not in raw:
            raise ProcedureError(f"{spot}: an override needs 'param' and 'value'")
        # The reason is mandatory. An override without a stated justification
        # is exactly the silent reconfiguration this schema exists to prevent,
        # so it fails at load time rather than in flight.
        if not raw.get("reason"):
            raise ProcedureError(
                f"{spot}: override of {raw['param']!r} needs a 'reason' — a procedure "
                f"may not change the vehicle's configuration without saying why")
        overrides.append(Override(
            param=str(raw["param"]).upper(),
            value=raw["value"],
            reason=_text(raw["reason"], f"{spot}.reason"),
            restore=bool(raw.get("restore", True)),
        ))
    declared = {o.param for o in overrides}
    if len(declared) != len(overrides):
        raise ProcedureError(f"{where}: the same parameter is overridden twice")

    raw_steps = doc.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ProcedureError(f"{where}: 'steps' must be a non-empty list")
    steps = [_parse_step(s, f"{where}.steps[{i}]", version)
             for i, s in enumerate(raw_steps)]

    # A `set_param` step may only touch a declared override. The step type
    # still exists because a procedure can legitimately need to change a value
    # part way through its own flow; what it may not do is introduce a change
    # that the `overrides:` block, the run directory and the report never saw.
    for i, step in enumerate(steps):
        if step.kind != "set_param":
            continue
        name = str(step.value["name"]).upper()
        if name not in declared:
            raise ProcedureError(
                f"{where}.steps[{i}]: set_param writes {name}, which is not declared in "
                f"'overrides:'. Declare it there with a reason, or drop the step.")

    raw_expect = doc.get("expect")
    if not isinstance(raw_expect, list) or not raw_expect:
        raise ProcedureError(
            f"{where}: 'expect' must be a non-empty list — a procedure without acceptance "
            f"criteria cannot be said to have passed")
    expect = [_parse_expect(raw, f"{where}.expect[{i}]", version)
              for i, raw in enumerate(raw_expect)]

    # Declared identifiers must be unique within the file they name. Two
    # criteria sharing one would make the coverage report and the "what was not
    # tested" list silently merge two different claims into one row.
    _check_unique_ids([s.id for s in steps], where, "step")
    _check_unique_ids([e.id for e in expect], where, "criterion")

    raw_failures = doc.get("failures")
    if raw_failures is not None and not isinstance(raw_failures, list):
        raise ProcedureError(f"{where}: 'failures' must be a list")
    failures = [_parse_fault(item, f"{where}.failures[{i}]", version, len(steps))
                for i, item in enumerate(raw_failures or [])]
    identifiers = {f.id for f in failures}
    if len(identifiers) != len(failures):
        raise ProcedureError(f"{where}: two faults share an id")
    # Faults are injected in flow order and held one at a time. Declaring two
    # at the same point would give the file an execution order the reader
    # cannot see, so it is refused rather than resolved by list position.
    points = [f.inject_after_step for f in failures]
    if len(set(points)) != len(points):
        raise ProcedureError(
            f"{where}: two faults are injected after the same step. One fault "
            f"is held at a time; give them different injection points.")

    return Procedure(
        id=pid,
        schema=version,
        path=path,
        name=_text(doc.get("name") or pid, f"{where}.name"),
        description=_text(doc.get("description"), f"{where}.description"),
        sources=[str(s) for s in sources],
        role=role,
        applies_to=applies,
        default=bool(applies.get("default", False)),
        priority=int(applies.get("priority", 0)),
        inputs=inputs,
        overrides=overrides,
        steps=steps,
        expect=expect,
        timeout=float(doc.get("timeout", 300)),
        raw_text=text,
        failures=failures,
    )


# --------------------------------------------------------------------------- registry
_cache: dict[str, Procedure] = {}
_cache_stamp: Optional[tuple] = None


def _dir_stamp(directory: Path) -> tuple:
    return tuple(sorted((p.name, p.stat().st_mtime_ns)
                        for p in directory.glob("*.yaml")))


def load_all(directory: Optional[Path] = None, force: bool = False) -> dict[str, Procedure]:
    """Loads every procedure, re-reading only when a file changed on disk."""
    global _cache, _cache_stamp
    directory = directory or paths.PROCEDURES_DIR
    if not directory.is_dir():
        return {}
    stamp = _dir_stamp(directory)
    if not force and stamp == _cache_stamp:
        return _cache
    loaded: dict[str, Procedure] = {}
    for path in sorted(directory.glob("*.yaml")):
        proc = parse(path.read_text(encoding="utf-8"), path)
        if proc.id in loaded:
            raise ProcedureError(f"{path.name}: duplicate procedure id {proc.id!r}")
        loaded[proc.id] = proc
    _cache, _cache_stamp = loaded, stamp
    return loaded


def get(procedure_id: str) -> Optional[Procedure]:
    return load_all().get(procedure_id)


def candidates(role: str, caps: dict) -> list[Procedure]:
    """Every procedure that fits these capabilities, best first."""
    matching = [p for p in load_all().values() if p.role == role and p.matches(caps)]
    return sorted(matching, key=lambda p: (p.default, p.priority), reverse=True)


def scenarios(caps: Optional[dict] = None) -> list[Procedure]:
    """Off-nominal flows, optionally filtered to a probed aircraft.

    Never auto-selected. A scenario injects a fault, and a fault is not
    something that should start because a capability heuristic decided it
    applied — it is chosen by name, every time.
    """
    found = [p for p in load_all().values() if p.role == "scenario"]
    if caps is not None:
        found = [p for p in found if p.matches(caps)]
    return sorted(found, key=lambda p: p.id)


def select(role: str, caps: dict, model: Optional[dict] = None) -> Optional[Procedure]:
    """Chooses the procedure for a role.

    A model may pin its own choice in models.json:

        "procedures": {"takeoff": "plane_takeoff_auto"}

    A pin wins outright — it is how a model with a genuinely unusual airframe
    escapes the capability rules without anyone editing this file.
    """
    pinned = ((model or {}).get("procedures") or {}).get(role)
    if pinned:
        proc = get(pinned)
        if proc is None:
            raise ProcedureError(
                f"model '{(model or {}).get('id')}' pins procedure {pinned!r}, "
                f"which does not exist")
        return proc
    for proc in candidates(role, caps):
        if proc.default:
            return proc
    return None
