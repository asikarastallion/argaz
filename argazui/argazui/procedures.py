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

from . import paths

# The current schema. Schema 1 files are still loaded unchanged; schema 2 adds
# the temporal acceptance criteria and the instantaneous attitude conditions
# introduced in v1.3, and a file has to declare 2 to use them. Extending
# schema 1 in place would have been quieter and worse: an older ArgazUI would
# have read a `within:` it does not implement out of a document claiming a
# version it satisfies.
SCHEMA_VERSION = 2
SUPPORTED_SCHEMAS = (1, 2)

# Reserved for a later schema (see SCHEMA.md). Rejected now so that nothing
# starts depending on a half-defined meaning before the scenario runner exists.
RESERVED_KEYS = ("mission", "failures")

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

ROLES = ("takeoff", "land")

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
        if key not in STEP_TYPES and key not in ("name", "timeout", "on_fail", "when"):
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
    )


def _parse_expect(raw: Any, where: str, schema: int) -> Expectation:
    """One `expect:` entry, including its temporal shape.

    The combinations rejected here are rejected because there is no reading of
    them that stays deterministic, and a criterion whose meaning depends on the
    reader is worse than one that does not exist.
    """
    if not isinstance(raw, dict) or "condition" not in raw:
        raise ProcedureError(f"{where}: needs a 'condition'")
    for key in raw:
        if key not in ("condition", "timeout", "message") + TEMPORAL_KEYS:
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
