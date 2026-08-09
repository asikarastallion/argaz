"""Run-to-run comparison: is this flight worse than the one before it?

WHAT THIS LAYER IS FOR
----------------------
A run says whether its acceptance criteria held. That is a verdict about one
flight against limits somebody declared. It cannot see the thing that actually
happens to a simulation project over months: every criterion still passes, and
the aircraft is quietly getting worse at flying. Tracking error creeps up, the
climb takes four seconds longer, a mode change that used to confirm in 100 ms
now takes two seconds. Nothing fails, and something is wrong.

So metrics from one run are compared against metrics from a named baseline,
and a degradation past a declared threshold is a machine-readable, CI-consumable
failure.

TWO RUNS ARE NOT COMPARABLE JUST BECAUSE THEY EXIST
---------------------------------------------------
This is the part that has to be strict, and it is the reason fingerprint.py
exists. A comparison across a different model, a different procedure, a
different ArduPilot or an edited parameter file is not a measurement of
anything — it is two unrelated numbers subtracted. So:

  * a different model or a different set of procedures is HARD incomparable.
    There is no flag for it; the runs are not about the same thing.
  * a changed procedure hash, model configuration or ArduPilot commit makes the
    comparison `incomparable` and says exactly which field changed. It can be
    overridden with `ignore_config_drift`, because "I changed the firmware and
    I want to see what that did to the numbers" is a real question — but it has
    to be asked out loud.

Nothing here is ever compared silently.

WHY RELATIVE DELTAS HAVE A FLOOR
--------------------------------
An RMS tracking error of 0.02° that becomes 0.04° is +100% and means nothing:
both numbers are noise. Judging purely on the relative change would fill CI
with red for quantities that are, in engineering terms, identical. Every metric
therefore also has an absolute floor, and a change smaller than that floor is
`unchanged` no matter how large the percentage looks.

NO DATABASE
-----------
A baseline is a run directory. Comparisons read `result.json` and write
`regression.json` / `regression.md` beside the current run. That is the whole
storage design, and it is deliberate: the evidence for a comparison should be
readable with the same tools as the evidence for a flight.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import metrics as metricslib
from . import fingerprint as fp
from . import paths

SCHEMA = 1

# Per-metric verdicts.
IMPROVED, DEGRADED, UNCHANGED, INCOMPARABLE = (
    "improved", "degraded", "unchanged", "incomparable")

# Overall verdicts. `regressed` is the only one that fails CI; `incomparable`
# is a different kind of "no" and gets its own exit code, because "these runs
# do not line up" is not the same news as "this build got worse".
PASSED, REGRESSED, NOT_COMPARABLE = "passed", "regressed", "incomparable"

# A relative change up to this fraction is `unchanged`. 10% is not a law of
# nature; it is the point below which SITL's own run-to-run scatter dominates,
# measured on repeated tier-1 takeoffs of the same frame. Override per metric
# in argaz.toml — see docs/regression.md.
DEFAULT_TOLERANCE = 0.10

# Absolute floors, in each metric's own unit. Below these a change is not
# reportable regardless of its percentage. Each is roughly the resolution at
# which the underlying measurement means anything: a tenth of a degree of
# attitude error, a tenth of a second of wall time, a couple of degrees per
# second of body rate.
DEFAULT_FLOORS: dict[str, float] = {
    "time_to_target_alt": 0.5,
    "tracking_error_roll_max": 1.0,
    "tracking_error_pitch_max": 1.0,
    "tracking_error_roll_rms": 0.1,
    "tracking_error_pitch_rms": 0.1,
    "peak_angular_rate": 2.0,
    "time_outside_attitude_envelope": 0.2,
    "mode_transition_latency_max": 0.1,
}


class RunNotReadable(ValueError):
    """A run directory that cannot take part in a comparison, and why."""


# --------------------------------------------------------------------- config
def thresholds(config: Optional[dict] = None) -> dict:
    """The tolerance and floor for every metric, from argaz.toml or defaults.

        [regression]
        default_tolerance = 0.10

        [regression.tolerance]
        peak_angular_rate = 0.25

        [regression.floor]
        time_to_target_alt = 1.0
    """
    config = paths.REGRESSION if config is None else config
    default = float(config.get("default_tolerance", DEFAULT_TOLERANCE))
    tolerance = config.get("tolerance") or {}
    floor = config.get("floor") or {}
    out = {}
    for key in metricslib.CATALOGUE:
        out[key] = {
            "tolerance": float(tolerance.get(key, default)),
            "floor": float(floor.get(key, DEFAULT_FLOORS.get(key, 0.0))),
        }
    return {"default_tolerance": default, "metrics": out}


def _limits(key: str, table: dict) -> tuple[float, float]:
    entry = table["metrics"].get(key)
    if entry:
        return entry["tolerance"], entry["floor"]
    return table["default_tolerance"], DEFAULT_FLOORS.get(key, 0.0)


# ----------------------------------------------------------------- run loading
def load_run(target: Path) -> dict:
    """A run directory reduced to what a comparison needs.

    Reads `result.json` only. `report.json` carries the plotted series, which
    is megabytes of data no comparison looks at, and a comparison that had to
    parse it would be unusable on a directory whose report was pruned.
    """
    directory = Path(target)
    if directory.is_file() and directory.name == "result.json":
        directory = directory.parent
    if not directory.is_dir():
        raise RunNotReadable(f"{directory} is not a run directory")
    path = directory / "result.json"
    if not path.is_file():
        raise RunNotReadable(
            f"{directory.name} has no result.json — it is a session that never "
            f"finished, or a directory that is not a run")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunNotReadable(f"{path} could not be read: {exc}") from exc

    return {
        "run_id": result.get("run_id") or directory.name,
        "dir": str(directory),
        "schema": result.get("schema"),
        "status": result.get("status"),
        "started_utc": result.get("started_utc"),
        "model_id": (result.get("model") or {}).get("id"),
        "procedures": sorted({entry.get("procedure") for entry in
                              result.get("procedures") or [] if entry.get("procedure")}),
        "metrics": result.get("metrics") or [],
        "fingerprint": result.get("fingerprint") or fp.read(directory),
    }


def previous_run_for(current: dict, root: Optional[Path] = None) -> Optional[dict]:
    """The newest earlier run of the same model, or None.

    Used by the UI's "compare with the previous run" and by nothing that must
    be reproducible: a baseline chosen by recency is a convenience, and CI
    should always name its baseline explicitly.
    """
    root = Path(root) if root else paths.RUNS_DIR
    if not root.is_dir():
        return None
    candidates: list[dict] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name == Path(current["dir"]).name:
            continue
        try:
            run = load_run(entry)
        except RunNotReadable:
            continue
        if run["model_id"] != current["model_id"] or not run["metrics"]:
            continue
        if (run["started_utc"] or "") >= (current["started_utc"] or ""):
            continue
        candidates.append(run)
    if not candidates:
        return None
    return max(candidates, key=lambda r: r["started_utc"] or "")


# ------------------------------------------------------------- compatibility
def compatibility(baseline: dict, current: dict,
                  ignore_config_drift: bool = False) -> dict:
    """Whether these two runs may be compared at all, and on what grounds."""
    blocking: list[dict] = []
    drift: list[dict] = []

    if baseline["model_id"] != current["model_id"]:
        blocking.append({
            "field": "model", "baseline": baseline["model_id"],
            "current": current["model_id"],
            "reason": "the two runs flew different aircraft"})
    if baseline["procedures"] != current["procedures"]:
        blocking.append({
            "field": "procedures", "baseline": baseline["procedures"],
            "current": current["procedures"],
            "reason": "the two runs executed different procedures"})
    for run, side in ((baseline, "baseline"), (current, "current")):
        if not run["metrics"]:
            blocking.append({
                "field": f"{side}.metrics", "baseline": None, "current": None,
                "reason": (f"the {side} run has no metrics — it predates v1.3, "
                           f"or its flight report was never generated. Run "
                           f"`argazui report {Path(run['dir']).name}`.")})

    drift = fp.differences(baseline["fingerprint"], current["fingerprint"])

    comparable = not blocking and (ignore_config_drift or not drift)
    return {"comparable": comparable, "blocking": blocking,
            "configuration_drift": drift,
            "drift_ignored": bool(drift and ignore_config_drift)}


# ------------------------------------------------------------------ comparing
def _classify(key: str, better: str, before: float, after: float,
              table: dict) -> tuple[str, float, Optional[float]]:
    tolerance, floor = _limits(key, table)
    delta = after - before
    relative = (delta / abs(before)) if before else None

    # A baseline of exactly zero has no percentage, and the floor is then the
    # only test there is — which is precisely the case the floor was added for.
    if abs(delta) <= floor:
        return UNCHANGED, delta, relative
    if relative is not None and abs(relative) <= tolerance:
        return UNCHANGED, delta, relative
    worse = delta > 0 if better == metricslib.LOWER else delta < 0
    return (DEGRADED if worse else IMPROVED), delta, relative


def compare(baseline: dict, current: dict, config: Optional[dict] = None,
            ignore_config_drift: bool = False) -> dict:
    """The full comparison, as one machine-readable document."""
    table = thresholds(config)
    compat = compatibility(baseline, current, ignore_config_drift)

    before = metricslib.by_identity(baseline["metrics"])
    after = metricslib.by_identity(current["metrics"])

    comparisons: list[dict] = []
    for identity in sorted(set(before) | set(after)):
        key, procedure = identity
        left, right = before.get(identity), after.get(identity)
        spec = metricslib.CATALOGUE.get(key, {})
        row: dict[str, Any] = {
            "key": key, "procedure": procedure,
            "label": metricslib.label_for(key),
            "unit": (left or right or {}).get("unit", spec.get("unit", "")),
            "better": (left or right or {}).get("better", spec.get("better", "")),
            "baseline": (left or {}).get("value"),
            "current": (right or {}).get("value"),
            "delta": None, "relative": None, "verdict": INCOMPARABLE,
            "tolerance": _limits(key, table)[0], "floor": _limits(key, table)[1],
            "reason": "",
        }
        if not compat["comparable"]:
            row["reason"] = "the runs are not comparable; see 'compatibility'"
        elif left is None:
            row["reason"] = "the baseline run does not have this metric"
        elif right is None:
            row["reason"] = "the current run does not have this metric"
        elif left.get("value") is None or right.get("value") is None:
            row["reason"] = ((left.get("detail") or right.get("detail"))
                             or "the metric could not be measured on one side")
        else:
            verdict, delta, relative = _classify(
                key, row["better"], float(left["value"]), float(right["value"]),
                table)
            row.update(verdict=verdict, delta=round(delta, 4),
                       relative=None if relative is None else round(relative, 4))
        comparisons.append(row)

    tally: dict[str, int] = {}
    for row in comparisons:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1

    if not compat["comparable"]:
        verdict = NOT_COMPARABLE
    elif tally.get(DEGRADED):
        verdict = REGRESSED
    else:
        verdict = PASSED

    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "baseline": {k: baseline[k] for k in
                     ("run_id", "dir", "status", "started_utc", "model_id",
                      "procedures")},
        "current": {k: current[k] for k in
                    ("run_id", "dir", "status", "started_utc", "model_id",
                     "procedures")},
        "compatibility": compat,
        "thresholds": table,
        "counts": tally,
        "metrics": comparisons,
        "degraded": [f"{r['key']}@{r['procedure']}" if r["procedure"] else r["key"]
                     for r in comparisons if r["verdict"] == DEGRADED],
    }


# ------------------------------------------------------------------ rendering
def _number(value, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):.3g}{(' ' + unit) if unit else ''}"


VERDICT_MARK = {IMPROVED: "improved", DEGRADED: "**DEGRADED**",
                UNCHANGED: "unchanged", INCOMPARABLE: "*incomparable*"}


def render(comparison: dict) -> str:
    """The comparison as a document a person reads. Same facts, no new ones."""
    out: list[str] = []
    add = out.append
    base, cur = comparison["baseline"], comparison["current"]

    add(f"# Regression comparison — {cur['run_id']}")
    add("")
    add(f"Generated {comparison['generated_utc']}.")
    add("")
    add("| | run | status | started (UTC) |")
    add("|---|---|---|---|")
    add(f"| baseline | `{base['run_id']}` | {base['status']} | {base['started_utc']} |")
    add(f"| current | `{cur['run_id']}` | {cur['status']} | {cur['started_utc']} |")
    add("")

    verdict = comparison["verdict"]
    headline = {
        PASSED: "**No regression.** No metric degraded past its threshold.",
        REGRESSED: "**REGRESSION.** At least one metric degraded past its threshold.",
        NOT_COMPARABLE: "**Not comparable.** These two runs were not produced "
                        "under conditions that make their numbers mean the same "
                        "thing, so nothing below was compared.",
    }[verdict]
    add(headline)
    add("")

    compat = comparison["compatibility"]
    if compat["blocking"]:
        add("### Why they cannot be compared")
        add("")
        for item in compat["blocking"]:
            add(f"- `{item['field']}` — {item['reason']} "
                f"(baseline `{item['baseline']}`, current `{item['current']}`)")
        add("")
    if compat["configuration_drift"]:
        add("### Configuration differences")
        add("")
        add("These are what the environment fingerprints disagree on. A "
            "comparison across any of them measures the change as much as it "
            "measures the aircraft"
            + (", and was made anyway because it was explicitly asked for."
               if compat["drift_ignored"] else "."))
        add("")
        for item in compat["configuration_drift"]:
            add(f"- **{item['what']}** (`{item['field']}`, {item['reason']}) — "
                f"baseline `{item['baseline']}`, current `{item['current']}`")
        add("")

    add("## Metrics")
    add("")
    add("| Metric | Baseline | Current | Δ | Δ% | Tolerance | Verdict |")
    add("|---|---:|---:|---:|---:|---:|---|")
    for row in comparison["metrics"]:
        name = row["label"] + (f" — `{row['procedure']}`" if row["procedure"] else "")
        relative = "—" if row["relative"] is None else f"{row['relative'] * 100:+.1f}%"
        delta = "—" if row["delta"] is None else f"{row['delta']:+.3g}"
        note = f"<br><sub>{row['reason']}</sub>" if row["reason"] else ""
        add(f"| {name}<br><sub>`{row['key']}`</sub> "
            f"| {_number(row['baseline'], row['unit'])} "
            f"| {_number(row['current'], row['unit'])} "
            f"| {delta} "
            f"| {relative} "
            f"| {row['tolerance'] * 100:.0f}% / {row['floor']:g} {row['unit']} "
            f"| {VERDICT_MARK[row['verdict']]}{note} |")
    add("")
    counts = comparison["counts"]
    add("Totals: " + ", ".join(f"**{counts.get(name, 0)}** {name}" for name in
                               (IMPROVED, DEGRADED, UNCHANGED, INCOMPARABLE)) + ".")
    add("")
    add("A metric is `unchanged` when it moved by less than its relative "
        "tolerance **or** by less than its absolute floor. The floor is there "
        "because a quantity near zero produces enormous percentages for "
        "changes that mean nothing.")
    add("")
    add("Metrics are measurements, not acceptance criteria. A regression here "
        "does not mean a criterion failed — it means the aircraft is doing the "
        "same thing measurably less well than the baseline did.")
    add("")
    return "\n".join(out)


def write(directory: Path, comparison: dict) -> tuple[Path, Path]:
    """Writes regression.json and regression.md into a run directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    as_json = directory / "regression.json"
    as_text = directory / "regression.md"
    as_json.write_text(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    as_text.write_text(render(comparison), encoding="utf-8")
    return as_json, as_text
