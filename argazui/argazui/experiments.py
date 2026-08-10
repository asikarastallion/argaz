"""Experiments — one declarative file that composes everything below it.

WHAT AN EXPERIMENT IS
---------------------
Every layer this project has built so far answers a question about *one thing*.
A procedure says what to fly. A run says what happened. A campaign says whether
it happens the same way five times. A regression comparison says whether it got
worse than a named baseline. A fault says what the aircraft does when something
is deliberately broken.

What none of them can say is the question an engineer actually turns up with:

    "Does losing GPS during the climb change how this aircraft holds altitude,
     compared with the same climb when nothing is wrong?"

Answering that needs a *controlled* set of runs — the same model, the same
configuration, a nominal group and a faulted group, a stated number of
repetitions, a named set of measurements and a criterion decided in advance.
Every one of those pieces already exists here. What did not exist is a place to
write down which combination of them is being run, so that the combination
itself is reviewable, versionable and repeatable.

That file is an experiment. It adds no new capability to the aircraft, no new
step type, and no new way of judging a flight. It composes.

WHY IT IS CALLED AN EXPERIMENT AND NOT A SCENARIO
-------------------------------------------------
The v1.6 architecture calls this object a *scenario*. This repository has used
that word since v1.4 for something else and cannot reuse it without lying to
the reader: `applies_to.role: scenario` is an off-nominal **procedure**, every
run directory already contains a `scenario.yaml` holding the procedures that
executed, and the environment fingerprint has a `scenario` block listing the
faults they declared. A second meaning laid on top of those would make three
existing artefacts ambiguous, and the one that matters most — the file a
reviewer opens to see what actually ran — is the one that would break.

So the word here is `experiment`, and an off-nominal procedure is still a
scenario. An experiment may *use* a scenario; that is exactly what its faulted
arm is.

WHAT IT IS DELIBERATELY NOT
---------------------------
Not a mission planner: an arm names a procedure that already exists and cannot
describe a flight of its own. Not a simulation DSL: there is no expression
language here, only names and numbers. Not a second execution engine: an arm is
executed by `campaign.CampaignRunner`, which drives the same `ProcedureRunner`
the button drives, and every iteration leaves the ordinary run directory with
the ordinary evidence in it. If any of those stops being true, this module has
grown into the thing the architecture said not to build.

ARMS
----
An experiment is a list of arms. Each arm is "this procedure, this many times",
and it is executed as an ordinary repeatability campaign — so an arm *is* a
campaign, findable and aggregatable by every tool that already reads campaigns.
The experiment is the statement that these particular campaigns belong to one
question, plus the criteria that judge them together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from . import campaign as campaignlib
from . import limitations as limitslib
from . import metrics as metricslib
from . import paths
from . import procedures as procs
from . import trace as tracelib

# Schema 1. Versioned from the first release for the same reason the procedure
# schema is: an experiment file is evidence about what was asked, it outlives
# the checkout that produced it, and a reader has to be able to tell which shape
# they are holding without inferring it from which keys happen to be present.
SCHEMA_VERSION = 1
SUPPORTED_SCHEMAS = (1,)

# How the arms are compared. Stated in the file rather than inferred from how
# many arms there are, because "two arms and no comparison" is a real and honest
# thing to run — two independent repeatability measurements — and guessing that
# it must be a controlled comparison would invent a claim nobody made.
ARMS, BASELINE, REPEATS = "arms", "baseline", "repeats"
POLICIES = (ARMS, BASELINE, REPEATS)

# An arm is either the reference the others are read against, or one of the
# things being read. Exactly one arm may be the baseline under the `arms`
# policy — see `_check_compare`.
REFERENCE, TREATMENT = "reference", "treatment"
ARM_ROLES = (REFERENCE, TREATMENT)

# Bounds. An experiment with one arm is a repeatability measurement and is
# allowed; four is where a document stops being readable as a controlled
# comparison and starts being a matrix nobody checks.
MAX_ARMS = 4
MAX_RUNS_PER_ARM = campaignlib.DEFAULT_RUNS * 10   # 50, the campaign ceiling

# Keys of one `arms:` entry and one `accept:` entry.
ARM_KEYS = ("id", "procedure", "runs", "values", "label", "role", "note")
CRITERION_KEYS = ("id", "arm", "metric", "min", "max", "max_delta", "delta_vs",
                  "min_pass_rate", "message")

# The three shapes an experiment-level criterion may take. Deliberately few.
# Per-run acceptance already exists in the procedure and is where a criterion
# about *the aircraft* belongs; these three are the only things that can be said
# about a GROUP of runs without inventing statistics the sample cannot support.
PASS_RATE, RANGE, DELTA = "pass_rate", "range", "delta"

EXPERIMENT_RUN_PATTERN = re.compile(r"^\d{8}T\d{6}Z_[A-Za-z0-9_.-]+$")


class ExperimentError(ValueError):
    """An experiment file is malformed. Carries the file name for the message."""


def _text(value: Any, where: str, required: bool = False) -> dict:
    """Normalises a user-visible string into {'en': ..., 'tr': ...}."""
    if value is None:
        if required:
            raise ExperimentError(f"{where}: required")
        return {}
    if isinstance(value, str):
        return {"en": value, "tr": value}
    if isinstance(value, dict):
        out = {k: str(v) for k, v in value.items() if k in ("en", "tr")}
        if not out:
            raise ExperimentError(f"{where}: needs an 'en' and/or 'tr' key")
        out.setdefault("tr", out.get("en", ""))
        out.setdefault("en", out.get("tr", ""))
        return out
    raise ExperimentError(f"{where}: expected a string or an {{en, tr}} map")


def _pick(text: dict, lang: str) -> str:
    return text.get(lang) or text.get("en") or ""


# --------------------------------------------------------------------- record
@dataclass
class Arm:
    """One group of runs: a procedure, a repeat count, and what it is for."""

    id: str
    procedure_id: str
    runs: int
    values: dict = field(default_factory=dict)
    label: dict = field(default_factory=dict)
    role: str = TREATMENT
    note: dict = field(default_factory=dict)

    def name(self, lang: str = "en") -> str:
        return _pick(self.label, lang) or self.id

    def as_dict(self, lang: str = "en") -> dict:
        return {"id": self.id, "procedure_id": self.procedure_id,
                "runs": self.runs, "values": dict(self.values),
                "label": self.name(lang), "role": self.role,
                "note": _pick(self.note, lang)}


@dataclass
class Criterion:
    """One acceptance criterion about a GROUP of runs.

    WHY THESE THREE AND NOTHING ELSE
    --------------------------------
    `pass_rate` judges how often the arm met the criteria its procedure already
    declares. `range` judges where a metric's mean landed. `delta` judges how
    far one arm's mean moved from another's.

    Everything a wider language would add — "significantly different",
    "within one standard deviation", "95% of runs" — is a statistical claim,
    and at the sample sizes a SITL campaign produces none of them would mean
    what they say. This module reports n beside every number instead; see
    `analysis.py` for what it refuses to compute.
    """

    id: str
    arm: str
    kind: str
    metric: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    max_delta: Optional[float] = None
    delta_vs: str = ""
    min_pass_rate: Optional[float] = None
    message: dict = field(default_factory=dict)

    def label(self, lang: str = "en") -> str:
        stated = _pick(self.message, lang)
        if stated:
            return stated
        if self.kind == PASS_RATE:
            return (f"{self.arm}: at least "
                    f"{(self.min_pass_rate or 0.0) * 100:.0f}% clean passes")
        if self.kind == RANGE:
            bounds = []
            if self.minimum is not None:
                bounds.append(f"≥ {self.minimum:g}")
            if self.maximum is not None:
                bounds.append(f"≤ {self.maximum:g}")
            return f"{self.arm}: mean {self.metric} {' and '.join(bounds)}"
        return (f"{self.arm}: mean {self.metric} within {self.max_delta:g} of "
                f"{self.delta_vs}")

    def as_dict(self, lang: str = "en") -> dict:
        return {"id": self.id, "arm": self.arm, "kind": self.kind,
                "metric": self.metric, "min": self.minimum,
                "max": self.maximum, "max_delta": self.max_delta,
                "delta_vs": self.delta_vs, "min_pass_rate": self.min_pass_rate,
                "label": self.label(lang)}


@dataclass
class Experiment:
    """One experiment definition, as parsed from its file."""

    id: str
    schema: int
    path: Path
    name: dict
    question: dict
    model_id: str
    values: dict
    arms: list[Arm]
    metrics: list[str]
    accept: list[Criterion]
    policy: str
    reference_arm: str
    limitations: dict
    raw_text: str

    # -------------------------------------------------------------- accessors
    def label(self, lang: str = "en") -> str:
        return _pick(self.name, lang) or self.id

    def asks(self, lang: str = "en") -> str:
        return _pick(self.question, lang)

    def arm(self, arm_id: str) -> Optional[Arm]:
        for entry in self.arms:
            if entry.id == arm_id:
                return entry
        return None

    @property
    def total_runs(self) -> int:
        return sum(arm.runs for arm in self.arms)

    def values_for(self, arm: Arm) -> dict:
        """The experiment's configuration with the arm's own values on top."""
        return {**self.values, **arm.values}

    def as_dict(self, lang: str = "en") -> dict:
        return {
            "schema": self.schema,
            "id": self.id,
            "name": self.label(lang),
            "question": self.asks(lang),
            "model_id": self.model_id,
            "values": dict(self.values),
            "arms": [arm.as_dict(lang) for arm in self.arms],
            "metrics": list(self.metrics),
            "accept": [c.as_dict(lang) for c in self.accept],
            "compare": {"policy": self.policy,
                        "reference_arm": self.reference_arm},
            "total_runs": self.total_runs,
            "limitations": limitslib.as_list(self.limitations, lang),
            "file": self.path.name,
        }

    # ------------------------------------------------------------- execution
    def stamp(self, run_id: str, arm: Arm, index: int) -> dict:
        """The block one run carries so it can be found again without an index.

        Exactly the reasoning `campaign.Definition.stamp` is built on: an
        experiment is reconstructed by reading the runs, so a run that was
        copied out of the tree still says what it belonged to.
        """
        return {"schema": SCHEMA_VERSION, "id": self.id, "run": run_id,
                "arm": arm.id, "arm_role": arm.role, "index": index,
                "of": arm.runs, "model_id": self.model_id,
                "procedure_id": arm.procedure_id, "policy": self.policy}


def experiment_run_id(experiment_id: str,
                      when: Optional[datetime] = None) -> str:
    """`20260810T124500Z_copter_gps_loss_vs_nominal` — sorts by time."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", experiment_id)
    return f"{stamp}_{safe}"


def campaign_for(experiment: "Experiment", arm: Arm,
                 when: Optional[datetime] = None) -> campaignlib.Definition:
    """The arm, expressed as the repeatability campaign it actually is.

    This is the whole of the "do not create a second execution engine" rule,
    written once: an arm is turned into a `campaign.Definition` here and handed
    to `campaign.CampaignRunner`, which drives the same `ProcedureRunner` the
    interface drives. Nothing in this module executes anything itself.
    """
    return campaignlib.Definition(
        id=campaignlib.campaign_id(experiment.model_id,
                                   f"{arm.procedure_id}-{arm.id}", when),
        model_id=experiment.model_id,
        procedure_id=arm.procedure_id,
        runs=arm.runs,
        values=experiment.values_for(arm),
        note=f"experiment {experiment.id}, arm {arm.id}")


# --------------------------------------------------------------------- parse
def _check_id(value: Any, where: str) -> str:
    try:
        return tracelib.check_declared(value, where)
    except tracelib.TraceError as exc:
        raise ExperimentError(str(exc)) from exc


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentError(f"{where}: expected a number, got {value!r}")
    return float(value)


def _parse_arm(raw: Any, where: str, known: dict) -> Arm:
    if not isinstance(raw, dict):
        raise ExperimentError(f"{where}: an arm must be a map")
    for key in raw:
        if key not in ARM_KEYS:
            raise ExperimentError(
                f"{where}: unknown arm key '{key}'. Known: {', '.join(ARM_KEYS)}")
    for key in ("id", "procedure", "runs"):
        if raw.get(key) is None:
            raise ExperimentError(f"{where}: an arm needs '{key}'")

    arm_id = _check_id(raw["id"], f"{where}.id")
    procedure_id = str(raw["procedure"])
    procedure = known.get(procedure_id)
    if procedure is None:
        raise ExperimentError(
            f"{where}.procedure: there is no procedure named "
            f"'{procedure_id}'. An experiment composes procedures that already "
            f"exist; it cannot describe a flight of its own.")

    runs = raw["runs"]
    if isinstance(runs, bool) or not isinstance(runs, int) \
            or not 1 <= runs <= MAX_RUNS_PER_ARM:
        raise ExperimentError(
            f"{where}.runs: must be a whole number between 1 and "
            f"{MAX_RUNS_PER_ARM}; got {runs!r}")

    role = raw.get("role", TREATMENT)
    if role not in ARM_ROLES:
        raise ExperimentError(
            f"{where}.role: must be one of {', '.join(ARM_ROLES)}")

    values = raw.get("values") or {}
    if not isinstance(values, dict):
        raise ExperimentError(f"{where}.values: expected a map of inputs")

    return Arm(id=arm_id, procedure_id=procedure_id, runs=runs,
               values={str(k): v for k, v in values.items()},
               label=_text(raw.get("label"), f"{where}.label"),
               role=role, note=_text(raw.get("note"), f"{where}.note"))


def _check_values(experiment_values: dict, arm: Arm, procedure,
                  where: str) -> None:
    """Every input the experiment sets must be one the procedure declares.

    A typo here is silent and expensive: the procedure would fly its default
    altitude, every number in the report would be about that flight, and the
    document would say the experiment configured something else. So an unknown
    input is refused at load time, with the names that are available.
    """
    declared = {item.name for item in procedure.inputs}
    for name in sorted({**experiment_values, **arm.values}):
        if name not in declared:
            raise ExperimentError(
                f"{where}: '{name}' is not an input of procedure "
                f"'{arm.procedure_id}'. It declares: "
                f"{', '.join(sorted(declared)) or '(none)'}.")


def _parse_criterion(raw: Any, where: str, index: int, arms: list[Arm],
                     metrics: list[str]) -> Criterion:
    if not isinstance(raw, dict):
        raise ExperimentError(f"{where}: a criterion must be a map")
    for key in raw:
        if key not in CRITERION_KEYS:
            raise ExperimentError(
                f"{where}: unknown criterion key '{key}'. Known: "
                f"{', '.join(CRITERION_KEYS)}")
    if raw.get("arm") is None:
        raise ExperimentError(f"{where}: a criterion needs an 'arm'")

    arm_ids = {arm.id for arm in arms}
    arm = str(raw["arm"])
    if arm not in arm_ids:
        raise ExperimentError(
            f"{where}.arm: '{arm}' is not an arm of this experiment. "
            f"Declared: {', '.join(sorted(arm_ids))}.")

    identifier = (_check_id(raw["id"], f"{where}.id") if raw.get("id")
                  else f"a{index + 1}")

    has_bounds = raw.get("min") is not None or raw.get("max") is not None
    has_delta = raw.get("max_delta") is not None or raw.get("delta_vs")
    has_rate = raw.get("min_pass_rate") is not None
    stated = [name for name, present in
              ((PASS_RATE, has_rate), (RANGE, has_bounds), (DELTA, has_delta))
              if present]
    if len(stated) != 1:
        raise ExperimentError(
            f"{where}: state exactly one of 'min_pass_rate', 'min'/'max' or "
            f"'max_delta' + 'delta_vs' — found "
            f"{', '.join(stated) if stated else 'none'}. A criterion that "
            f"judges two things at once has no single reason for its verdict.")
    kind = stated[0]

    metric = str(raw.get("metric") or "")
    if kind in (RANGE, DELTA):
        if not metric:
            raise ExperimentError(f"{where}: a '{kind}' criterion needs a 'metric'")
        if metric not in metrics:
            raise ExperimentError(
                f"{where}.metric: '{metric}' is not in this experiment's "
                f"'metrics:' list. A criterion may only judge a measurement the "
                f"report also shows, or its verdict rests on a number the "
                f"reader cannot see. Declared: {', '.join(metrics) or '(none)'}.")
    elif metric:
        raise ExperimentError(
            f"{where}.metric: a pass-rate criterion is about the runs, not "
            f"about a measurement; drop the metric.")

    minimum = (None if raw.get("min") is None
               else _number(raw["min"], f"{where}.min"))
    maximum = (None if raw.get("max") is None
               else _number(raw["max"], f"{where}.max"))
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ExperimentError(
            f"{where}: min ({minimum:g}) is above max ({maximum:g}), so nothing "
            f"can satisfy it")

    max_delta = None
    delta_vs = ""
    if kind == DELTA:
        if raw.get("max_delta") is None or not raw.get("delta_vs"):
            raise ExperimentError(
                f"{where}: a delta criterion needs both 'max_delta' and "
                f"'delta_vs' — a limit with nothing to measure it from is not "
                f"a criterion")
        max_delta = _number(raw["max_delta"], f"{where}.max_delta")
        if max_delta < 0:
            raise ExperimentError(f"{where}.max_delta: must not be negative")
        delta_vs = str(raw["delta_vs"])
        if delta_vs not in arm_ids:
            raise ExperimentError(
                f"{where}.delta_vs: '{delta_vs}' is not an arm of this "
                f"experiment. Declared: {', '.join(sorted(arm_ids))}.")
        if delta_vs == arm:
            raise ExperimentError(
                f"{where}.delta_vs: an arm compared against itself is always "
                f"zero away from itself")

    rate = None
    if kind == PASS_RATE:
        rate = _number(raw["min_pass_rate"], f"{where}.min_pass_rate")
        if not 0.0 <= rate <= 1.0:
            raise ExperimentError(
                f"{where}.min_pass_rate: a fraction between 0 and 1, "
                f"got {rate:g}")

    return Criterion(id=identifier, arm=arm, kind=kind, metric=metric,
                     minimum=minimum, maximum=maximum, max_delta=max_delta,
                     delta_vs=delta_vs, min_pass_rate=rate,
                     message=_text(raw.get("message"), f"{where}.message"))


def _check_compare(raw: Any, arms: list[Arm], where: str) -> tuple[str, str]:
    if raw is None:
        raise ExperimentError(
            f"{where}: 'compare' is required — an experiment has to say how its "
            f"arms are to be read against each other, because guessing it from "
            f"the arm count would invent a claim nobody made")
    if not isinstance(raw, dict):
        raise ExperimentError(f"{where}: expected a map")
    for key in raw:
        if key not in ("policy", "reference_arm"):
            raise ExperimentError(f"{where}: unknown key '{key}'")

    policy = raw.get("policy")
    if policy not in POLICIES:
        raise ExperimentError(
            f"{where}.policy: must be one of {', '.join(POLICIES)}")

    reference = str(raw.get("reference_arm") or "")
    arm_ids = {arm.id for arm in arms}
    references = [arm for arm in arms if arm.role == REFERENCE]

    if policy == REPEATS:
        if len(arms) != 1:
            raise ExperimentError(
                f"{where}.policy: 'repeats' is one arm flown N times; this "
                f"experiment has {len(arms)}. Use 'arms' and say which one is "
                f"the reference.")
        if reference:
            raise ExperimentError(
                f"{where}.reference_arm: 'repeats' compares nothing, so there "
                f"is nothing for it to be the reference of")
        return policy, ""

    if policy == ARMS:
        if len(arms) < 2:
            raise ExperimentError(
                f"{where}.policy: 'arms' compares one arm against another and "
                f"this experiment has {len(arms)}")
        if not reference:
            raise ExperimentError(
                f"{where}.reference_arm: required under the 'arms' policy — "
                f"a delta needs a stated side to be measured from")
        if reference not in arm_ids:
            raise ExperimentError(
                f"{where}.reference_arm: '{reference}' is not an arm of this "
                f"experiment. Declared: {', '.join(sorted(arm_ids))}.")
        if len(references) != 1 or references[0].id != reference:
            raise ExperimentError(
                f"{where}.reference_arm: exactly one arm must carry "
                f"'role: {REFERENCE}', and it must be '{reference}'. The role "
                f"and this field are the same statement, and a file where they "
                f"disagree has two answers to which side a delta is measured "
                f"from.")
        return policy, reference

    # BASELINE — this run against the previous recorded run of the same
    # experiment. Every arm is compared with its own former self, so there is
    # no reference arm to name.
    if reference:
        raise ExperimentError(
            f"{where}.reference_arm: under 'baseline' each arm is compared "
            f"against its own earlier run, so no arm is the reference")
    return policy, ""


def parse(text: str, path: Path,
          known_procedures: Optional[dict] = None) -> Experiment:
    """Parses and validates one experiment document."""
    where = path.name
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExperimentError(f"{where}: not valid YAML — {exc}") from exc
    if not isinstance(doc, dict):
        raise ExperimentError(f"{where}: the top level must be a map")

    known = procs.load_all() if known_procedures is None else known_procedures

    version = doc.get("schema")
    if version not in SUPPORTED_SCHEMAS:
        raise ExperimentError(
            f"{where}: schema must be one of "
            f"{', '.join(str(v) for v in SUPPORTED_SCHEMAS)}, found {version!r}")

    identifier = doc.get("id")
    if identifier != path.stem:
        raise ExperimentError(
            f"{where}: id {identifier!r} must equal the filename stem "
            f"{path.stem!r}")

    for key in doc:
        if key not in ("schema", "id", "name", "question", "model", "values",
                       "arms", "metrics", "accept", "compare", "limitations"):
            raise ExperimentError(f"{where}: unknown key '{key}'")

    model_id = doc.get("model")
    if not model_id or not isinstance(model_id, str):
        raise ExperimentError(
            f"{where}: 'model' must name one registry entry — an experiment is "
            f"a controlled comparison, and two aircraft is not one")

    # The question is mandatory. An experiment with no stated question is a
    # batch of runs, and the document it produces would be a table of numbers
    # with nothing to read them against.
    question = _text(doc.get("question"), f"{where}.question", required=True)

    values = doc.get("values") or {}
    if not isinstance(values, dict):
        raise ExperimentError(f"{where}.values: expected a map of inputs")
    values = {str(k): v for k, v in values.items()}

    raw_arms = doc.get("arms")
    if not isinstance(raw_arms, list) or not raw_arms:
        raise ExperimentError(f"{where}: 'arms' must be a non-empty list")
    if len(raw_arms) > MAX_ARMS:
        raise ExperimentError(
            f"{where}: at most {MAX_ARMS} arms. Beyond that the document stops "
            f"being a controlled comparison and becomes a matrix nobody checks.")
    arms = [_parse_arm(raw, f"{where}.arms[{i}]", known)
            for i, raw in enumerate(raw_arms)]
    seen = [arm.id for arm in arms]
    duplicates = sorted({name for name in seen if seen.count(name) > 1})
    if duplicates:
        raise ExperimentError(
            f"{where}: two arms share the id {', '.join(duplicates)}. Every "
            f"number in the report is attributed to an arm by that name.")
    for index, arm in enumerate(arms):
        _check_values(values, arm, known[arm.procedure_id],
                      f"{where}.arms[{index}].values")

    raw_metrics = doc.get("metrics")
    if not isinstance(raw_metrics, list) or not raw_metrics:
        raise ExperimentError(
            f"{where}: 'metrics' must name at least one measurement — an "
            f"experiment that measures nothing cannot answer a question about "
            f"a difference")
    metrics: list[str] = []
    for item in raw_metrics:
        key = str(item)
        if key not in metricslib.CATALOGUE:
            raise ExperimentError(
                f"{where}.metrics: '{key}' is not a metric this project "
                f"computes. Known: {', '.join(sorted(metricslib.CATALOGUE))}.")
        if key in metrics:
            raise ExperimentError(f"{where}.metrics: '{key}' is listed twice")
        metrics.append(key)

    policy, reference = _check_compare(doc.get("compare"), arms,
                                       f"{where}.compare")

    raw_accept = doc.get("accept")
    if raw_accept is not None and not isinstance(raw_accept, list):
        raise ExperimentError(f"{where}: 'accept' must be a list")
    accept = [_parse_criterion(raw, f"{where}.accept[{i}]", i, arms, metrics)
              for i, raw in enumerate(raw_accept or [])]
    identifiers = [c.id for c in accept]
    duplicates = sorted({name for name in identifiers
                         if identifiers.count(name) > 1})
    if duplicates:
        raise ExperimentError(
            f"{where}: two criteria share the id {', '.join(duplicates)}")

    try:
        limits = limitslib.parse(doc.get("limitations"), f"{where}.limitations")
    except limitslib.LimitationError as exc:
        raise ExperimentError(str(exc)) from exc

    return Experiment(
        id=identifier, schema=version, path=path,
        name=_text(doc.get("name") or identifier, f"{where}.name"),
        question=question, model_id=model_id, values=values, arms=arms,
        metrics=metrics, accept=accept, policy=policy, reference_arm=reference,
        limitations=limits, raw_text=text)


# ------------------------------------------------------------------ registry
_cache: dict[str, Experiment] = {}
_cache_stamp: Optional[tuple] = None


def _dir_stamp(directory: Path) -> tuple:
    return tuple(sorted((p.name, p.stat().st_mtime_ns)
                        for p in directory.glob("*.yaml")))


def load_all(directory: Optional[Path] = None,
             force: bool = False) -> dict[str, Experiment]:
    """Loads every experiment, re-reading only when a file changed on disk."""
    global _cache, _cache_stamp
    directory = directory or paths.EXPERIMENTS_DIR
    if not directory.is_dir():
        return {}
    stamp = (str(directory),) + _dir_stamp(directory)
    if not force and stamp == _cache_stamp:
        return _cache
    loaded: dict[str, Experiment] = {}
    for path in sorted(directory.glob("*.yaml")):
        item = parse(path.read_text(encoding="utf-8"), path)
        if item.id in loaded:
            raise ExperimentError(f"{path.name}: duplicate experiment id {item.id!r}")
        loaded[item.id] = item
    _cache, _cache_stamp = loaded, stamp
    return loaded


def get(experiment_id: str) -> Optional[Experiment]:
    return load_all().get(experiment_id)


# ----------------------------------------------------------------- execution
class ExperimentRunner:
    """Flies every arm of an experiment, in order, through `CampaignRunner`.

    WHY THERE IS SO LITTLE HERE
    ---------------------------
    That is the feature. The architecture's rule for this release is *do not
    create a second execution engine*, and the way to obey it is for this class
    to own nothing but the order of the arms and the identity that ties their
    runs together. Everything else — starting the aircraft, waiting for it,
    running the procedure, recording the run, tearing it down, aggregating the
    iterations — is done by code that already existed and that the interface
    already drives.

    `launch` is called once per iteration and must return a session with the
    same two methods `CampaignRunner` requires:

        run(procedure_id, values) -> (result: dict, run_dir: Path)
        close()                   -> tear the iteration down

    It is given the arm, the campaign that arm is being flown as, and the
    iteration index, so that the caller can stamp the run with both the
    campaign and the experiment before it starts.
    """

    def __init__(self, experiment: Experiment, run_id: str,
                 launch: Callable[[Arm, campaignlib.Definition, int], Any],
                 on_progress: Optional[Callable[[dict], None]] = None,
                 when: Optional[datetime] = None) -> None:
        self.experiment = experiment
        self.run_id = run_id
        self.launch = launch
        self.on_progress = on_progress or (lambda event: None)
        self.when = when or datetime.now(timezone.utc)
        # arm id -> the campaign that arm was flown as. The analysis reads the
        # runs rather than this map; it is here so the interface can name the
        # campaign while the experiment is still in the air.
        self.campaigns: dict[str, campaignlib.Definition] = {}
        self.iterations: dict[str, list[dict]] = {}
        self._runner: Optional[campaignlib.CampaignRunner] = None
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True
        if self._runner is not None:
            self._runner.cancel()

    @property
    def done(self) -> int:
        return sum(len(rows) for rows in self.iterations.values())

    def _emit(self, event: str, **payload) -> None:
        try:
            self.on_progress({"type": "experiment", "event": event,
                              "experiment": self.experiment.id,
                              "run": self.run_id, **payload})
        except Exception:
            pass

    def run(self) -> dict[str, list[dict]]:
        """Flies every arm. Returns the iteration rows, keyed by arm id."""
        self._emit("start", definition=self.experiment.as_dict(),
                   total_runs=self.experiment.total_runs)
        for arm in self.experiment.arms:
            if self._cancel:
                self._emit("cancelled", arm=arm.id)
                break
            definition = campaign_for(self.experiment, arm, self.when)
            self.campaigns[arm.id] = definition
            self._emit("arm_start", arm=arm.id, campaign=definition.id,
                       runs=arm.runs, procedure=arm.procedure_id)
            runner = campaignlib.CampaignRunner(
                definition,
                launch=lambda index, arm=arm, definition=definition:
                    self.launch(arm, definition, index),
                on_progress=self._on_campaign_event)
            self._runner = runner
            self.iterations[arm.id] = runner.run()
            self._runner = None
            self._emit("arm_done", arm=arm.id, campaign=definition.id,
                       flown=len(self.iterations[arm.id]))
        self._emit("done", flown=self.done)
        return self.iterations

    def _on_campaign_event(self, event: dict) -> None:
        """A campaign's own progress, forwarded unchanged.

        Not translated into experiment vocabulary: the arm really is a
        campaign, and a reader watching the terminal should see the same
        messages a campaign produces, plus the experiment's own around them.
        """
        self.on_progress(event)
