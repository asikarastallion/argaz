"""Experiment analysis: distributions per arm, deltas between them, a verdict.

WHAT THIS LAYER ADDS
--------------------
`campaign.py` can already describe one group of runs: counts, a clean pass
rate, and the mean, spread and range of every metric, with the sample size
beside each. What it cannot do is put two groups next to each other and say how
far apart they are — and that is the only question an experiment exists to ask.

So this module reads the runs of one experiment, aggregates each arm as the
repeatability campaign it actually is, and then does exactly three things
campaign.py does not:

  1. groups metrics by KEY rather than by (key, procedure);
  2. reports the delta between two arms' means, with what that delta is worth;
  3. judges the experiment-level acceptance criteria and says what was not
     judged at all.

WHY METRICS ARE GROUPED BY KEY HERE AND BY IDENTITY EVERYWHERE ELSE
-------------------------------------------------------------------
Everywhere else in this project a metric is identified by `key@procedure`, and
that is right: "time to target altitude" means nothing without saying whose
target, and a regression comparison across two different procedures would be
two unrelated numbers subtracted.

An experiment is the case that inverts it. Its arms deliberately fly *different*
procedures — a nominal climb and the same climb with GPS taken away — and the
whole question is what the same measured quantity did under the two conditions.
Matching on identity would line up nothing at all. So here the identity is the
key, the procedures each number came from are listed beside it, and a reader can
see when a quantity was measured under different scopes.

WHAT THIS MODULE REFUSES TO COMPUTE
-----------------------------------
No p-value, no confidence interval, no effect size, no "significant". A SITL
campaign produces single-digit sample sizes; every one of those figures would
be arithmetic that runs fine and means nothing, and each would read to a
reviewer as though the difference had been established.

What is reported instead is deliberately dull: n on both sides, the two means,
their difference, and whether the two arms' observed ranges overlap at all. An
overlap is not a significance test and the document says so — it is a statement
about the numbers actually seen, which is the only kind this sample supports.

NO DATABASE, AGAIN
------------------
An experiment document is recomputed from the run directories every time, the
same way a campaign document is. Runs carry the experiment stamp; nothing here
keeps an index, so a document and the evidence under it cannot drift apart.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import campaign as campaignlib
from . import experiments as experimentlib
from . import limitations as limitslib
from . import metrics as metricslib
from . import paths

SCHEMA = 1

# Where experiment documents live, under the runs root. A sibling of the run
# directories rather than a parent of them — the same rule campaigns follow, and
# for the same reason: an experiment's runs are ordinary runs and everything
# that reads `runs/` has to keep finding them.
EXPERIMENTS_DIRNAME = "experiments"

# Overall verdicts.
PASSED = "passed"            # every declared criterion held
FAILED = "failed"            # at least one did not
INCOMPLETE = "incomplete"    # arms short of their runs, or criteria unjudged
NOT_JUDGED = "not-judged"    # the experiment declared no criteria at all
NOT_RUN = "not-run"          # no run carries this experiment id
VERDICTS = (PASSED, FAILED, INCOMPLETE, NOT_JUDGED, NOT_RUN)

# What a delta between two arms is worth.
MEASURED = "measured"        # both sides have enough runs for a spread
INDICATIVE = "indicative"    # both sides measured, at least one below that
NONE = "none"                # one side measured nothing


def _iso(when: Optional[datetime] = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------- collection
def runs_of(experiment_run: str, root: Optional[Path] = None) -> list[dict]:
    """Every run directory carrying this experiment run id, in flown order.

    Found by reading the runs, exactly as a campaign is. An experiment
    interrupted after its first arm still produces a document, and a run
    somebody moved is simply not there — which is the truth, rather than a
    dangling reference.
    """
    root = Path(root) if root else paths.RUNS_DIR
    out: list[dict] = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = data.get("experiment") or {}
        if stamp.get("run") != experiment_run:
            continue
        out.append({"dir": path.parent, "data": data,
                    "arm": stamp.get("arm") or "",
                    "index": int(stamp.get("index") or 0),
                    "campaign_id": (data.get("campaign") or {}).get("id") or ""})
    out.sort(key=lambda entry: (entry["arm"], entry["index"],
                                entry["data"].get("started_utc") or ""))
    return out


def list_experiment_runs(root: Optional[Path] = None) -> list[dict]:
    """Every recorded experiment run in the runs root, newest first."""
    root = Path(root) if root else paths.RUNS_DIR
    found: dict[str, dict] = {}
    if not root.is_dir():
        return []
    for path in sorted(root.rglob("result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = data.get("experiment") or {}
        identifier = stamp.get("run")
        if not identifier:
            continue
        entry = found.setdefault(identifier, {
            "run": identifier, "experiment_id": stamp.get("id"),
            "model_id": stamp.get("model_id"), "policy": stamp.get("policy"),
            "arms": [], "recorded_runs": 0,
            "started_utc": data.get("started_utc") or ""})
        entry["recorded_runs"] += 1
        arm = stamp.get("arm")
        if arm and arm not in entry["arms"]:
            entry["arms"].append(arm)
        started = data.get("started_utc") or ""
        if started and (not entry["started_utc"] or started < entry["started_utc"]):
            entry["started_utc"] = started
    return sorted(found.values(), key=lambda e: e["started_utc"], reverse=True)


def previous_run_of(experiment_id: str, before: str,
                    root: Optional[Path] = None) -> Optional[str]:
    """The newest earlier recorded run of the same experiment, or None.

    Used only by the `baseline` policy. A baseline chosen by recency is a
    convenience for a person looking at the interface; a pipeline that needs a
    reproducible answer names the run it wants.
    """
    candidates = [entry for entry in list_experiment_runs(root)
                  if entry["experiment_id"] == experiment_id
                  and entry["run"] != before
                  and entry["run"] < before]
    return candidates[0]["run"] if candidates else None


# ------------------------------------------------------------------- metrics
def _metric_rows(entries: list[dict], keys: list[str]) -> list[dict]:
    """One row per selected metric key, over every run in this arm.

    Grouped by key rather than by `key@procedure` — see the module docstring
    for why an experiment is the one place where that is the right identity.
    """
    values: dict[str, list[float]] = {key: [] for key in keys}
    procedures: dict[str, list[str]] = {key: [] for key in keys}
    meta: dict[str, dict] = {}
    missing: dict[str, int] = {key: 0 for key in keys}

    for entry in entries:
        seen: set = set()
        for metric in entry["data"].get("metrics") or []:
            key = metric.get("key")
            if key not in values:
                continue
            seen.add(key)
            meta.setdefault(key, metric)
            procedure = metric.get("procedure") or ""
            if procedure and procedure not in procedures[key]:
                procedures[key].append(procedure)
            if metric.get("value") is None:
                missing[key] += 1
            else:
                values[key].append(float(metric["value"]))
        for key in keys:
            if key not in seen:
                # The run carried no such metric at all — it was never derived,
                # rather than derived and null. Counted the same way, because
                # both mean "this run contributed no measurement", and reported
                # as `not_measured` beside n.
                missing[key] += 1

    rows: list[dict] = []
    for key in keys:
        spec = metricslib.CATALOGUE.get(key, {})
        stats = campaignlib.statistics(values[key])
        rows.append({
            "key": key,
            "label": metricslib.label_for(key),
            "unit": (meta.get(key) or {}).get("unit", spec.get("unit", "")),
            "better": (meta.get(key) or {}).get("better", spec.get("better", "")),
            "procedures": procedures[key],
            "not_measured": missing[key],
            **stats,
        })
    return rows


def _by_key(rows: list[dict]) -> dict[str, dict]:
    return {row["key"]: row for row in rows}


def _ranges_overlap(left: dict, right: dict) -> Optional[bool]:
    """Do the two arms' observed ranges touch at all?

    Deliberately the crudest possible statement about two samples, and stated
    as such wherever it is printed. It is not a significance test: it says
    whether any value seen on one side was also within the span of the other,
    which is a fact about the numbers actually observed rather than an
    inference about numbers that were not.
    """
    if left["n"] == 0 or right["n"] == 0:
        return None
    return not (left["max"] < right["min"] or right["max"] < left["min"])


def compare_metrics(reference: list[dict], current: list[dict]) -> list[dict]:
    """Per-key delta between two arms' distributions."""
    left, right = _by_key(reference), _by_key(current)
    out: list[dict] = []
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        row: dict[str, Any] = {
            "key": key,
            "label": metricslib.label_for(key),
            "unit": (a or b or {}).get("unit", ""),
            "better": (a or b or {}).get("better", ""),
            "reference": a, "current": b,
            "delta": None, "relative": None, "ranges_overlap": None,
            "basis": NONE, "reason": "",
        }
        if a is None or b is None:
            row["reason"] = "the metric is not present on both sides"
            out.append(row)
            continue
        if a["n"] == 0 or b["n"] == 0:
            side = "reference" if a["n"] == 0 else "current"
            row["reason"] = (f"no run in the {side} arm measured this, so there "
                             f"is nothing to take a difference of")
            out.append(row)
            continue

        delta = b["mean"] - a["mean"]
        row["delta"] = round(delta, 4)
        row["relative"] = (None if not a["mean"]
                           else round(delta / abs(a["mean"]), 4))
        row["ranges_overlap"] = _ranges_overlap(a, b)
        enough = campaignlib.MIN_SAMPLES_FOR_SPREAD
        if a["n"] >= enough and b["n"] >= enough:
            row["basis"] = MEASURED
        else:
            row["basis"] = INDICATIVE
            row["reason"] = (
                f"one arm has fewer than {enough} measured values, so neither "
                f"side has a reported spread and this difference cannot be "
                f"read against one")
        out.append(row)
    return out


# --------------------------------------------------------------- acceptance
def _criterion_result(criterion, arms: dict[str, dict],
                      lang: str = "en") -> dict:
    """One experiment-level criterion, judged against the arms as flown."""
    row: dict[str, Any] = {
        "criterion_id": criterion.id,
        "kind": criterion.kind,
        "arm": criterion.arm,
        "metric": criterion.metric,
        "label": criterion.label(lang),
        "observed": None,
        "limit": None,
        "passed": False,
        "evaluated": False,
        "text": "",
    }
    arm = arms.get(criterion.arm)
    if arm is None or not arm["recorded_runs"]:
        row["text"] = (f"not judged — the arm '{criterion.arm}' has no recorded "
                       f"run, so nothing was measured for it")
        return row

    if criterion.kind == experimentlib.PASS_RATE:
        rate = arm["pass_rate"]
        row["limit"] = criterion.min_pass_rate
        row["observed"] = rate
        if rate is None:
            row["text"] = "not judged — the arm recorded no runs to rate"
            return row
        row["evaluated"] = True
        row["passed"] = rate >= (criterion.min_pass_rate or 0.0)
        row["text"] = (
            f"{rate * 100:.0f}% clean passes over {arm['recorded_runs']} run(s), "
            f"against the {(criterion.min_pass_rate or 0.0) * 100:.0f}% declared. "
            f"A run that passed on a retry is `flaky` and is not in this rate.")
        return row

    metric = _by_key(arm["metrics"]).get(criterion.metric)
    if metric is None or metric["n"] == 0:
        row["text"] = (f"not judged — no run in '{criterion.arm}' measured "
                       f"`{criterion.metric}`. Nothing was measured, which is "
                       f"not the same as nothing being wrong.")
        return row
    row["observed"] = metric["mean"]

    if criterion.kind == experimentlib.RANGE:
        row["limit"] = {"min": criterion.minimum, "max": criterion.maximum}
        row["evaluated"] = True
        low = criterion.minimum is None or metric["mean"] >= criterion.minimum
        high = criterion.maximum is None or metric["mean"] <= criterion.maximum
        row["passed"] = bool(low and high)
        bounds = []
        if criterion.minimum is not None:
            bounds.append(f"≥ {criterion.minimum:g}")
        if criterion.maximum is not None:
            bounds.append(f"≤ {criterion.maximum:g}")
        row["text"] = (
            f"mean {metric['mean']:.4g} {metric['unit']} over n={metric['n']}, "
            f"against {' and '.join(bounds)} {metric['unit']}")
        return row

    # DELTA — the arm's mean against another arm's mean.
    other = arms.get(criterion.delta_vs)
    reference = (_by_key(other["metrics"]).get(criterion.metric)
                 if other else None)
    if reference is None or reference["n"] == 0:
        row["text"] = (f"not judged — the arm it is measured from "
                       f"('{criterion.delta_vs}') has no measurement of "
                       f"`{criterion.metric}`")
        return row
    delta = metric["mean"] - reference["mean"]
    row["observed"] = round(delta, 4)
    row["limit"] = criterion.max_delta
    row["evaluated"] = True
    row["passed"] = abs(delta) <= (criterion.max_delta or 0.0)
    row["text"] = (
        f"mean moved by {delta:+.4g} {metric['unit']} from '{criterion.delta_vs}' "
        f"({reference['mean']:.4g} -> {metric['mean']:.4g}, n={reference['n']} "
        f"and n={metric['n']}), against the {criterion.max_delta:g} "
        f"{metric['unit']} declared")
    return row


# --------------------------------------------------------------------- report
def _arm_document(arm_id: str, entries: list[dict], keys: list[str],
                  root: Path, declared: Optional[experimentlib.Arm] = None,
                  lang: str = "en") -> dict:
    """One arm, aggregated as the repeatability campaign it actually is."""
    campaign_id = next((e["campaign_id"] for e in entries if e["campaign_id"]), "")
    summary = (campaignlib.aggregate(campaign_id, root) if campaign_id
               else {"counts": {name: 0 for name in campaignlib.VERDICTS},
                     "pass_rate": None, "failure_categories": {},
                     "consistency": {"checked": False, "identical": False,
                                     "differences": []},
                     "runs": [], "runs_recorded": 0})
    stamp = entries[0]["data"].get("experiment") if entries else {}
    return {
        "id": arm_id,
        "label": declared.name(lang) if declared else arm_id,
        "role": (declared.role if declared
                 else (stamp or {}).get("arm_role") or experimentlib.TREATMENT),
        "procedure_id": (declared.procedure_id if declared
                         else (stamp or {}).get("procedure_id")),
        "campaign_id": campaign_id,
        "declared_runs": (declared.runs if declared
                          else (stamp or {}).get("of")),
        "recorded_runs": len(entries),
        "counts": summary["counts"],
        "pass_rate": summary["pass_rate"],
        "failure_categories": summary["failure_categories"],
        "consistency": summary["consistency"],
        "metrics": _metric_rows(entries, keys),
        "runs": [{"run_id": e["data"].get("run_id") or e["dir"].name,
                  "dir": str(e["dir"]),
                  "index": e["index"],
                  "status": e["data"].get("status"),
                  "evidence_complete": (e["data"].get("evidence") or {}).get("complete"),
                  "missing_required": ((e["data"].get("evidence") or {})
                                       .get("missing_required") or [])}
                 for e in entries],
    }


def _evidence_rollup(arms: list[dict]) -> dict:
    """Whether the runs this document rests on actually left their evidence."""
    rows = [run for arm in arms for run in arm["runs"]]
    incomplete = [run["run_id"] for run in rows
                  if run["evidence_complete"] is False]
    unknown = [run["run_id"] for run in rows
               if run["evidence_complete"] is None]
    missing = sorted({name for run in rows for name in run["missing_required"]})
    return {"runs": len(rows), "complete": len(rows) - len(incomplete) - len(unknown),
            "incomplete": incomplete, "unknown": unknown,
            "missing_required": missing}


def collect(experiment_run: str, root: Optional[Path] = None,
            experiment: Optional[experimentlib.Experiment] = None,
            lang: str = "en", compare: bool = True) -> dict:
    """The experiment document, recomputed from the run directories.

    `experiment` is the definition as it is on disk now. It is optional: a
    document can still be produced for an experiment whose file has been
    removed or renamed, from the stamps the runs carry — with fewer facts in
    it, and saying which ones are missing, rather than refusing to answer.

    `compare=False` collects the distributions and skips the comparison. It is
    used for exactly one thing: the `baseline` policy collects the earlier run
    to measure this one against, and that earlier run has a baseline of its
    own. Left to recurse, a long history would be walked end to end — once per
    document — for numbers no reader asked for.
    """
    root = Path(root) if root else paths.RUNS_DIR
    entries = runs_of(experiment_run, root)

    if experiment is None:
        stamp = entries[0]["data"].get("experiment") if entries else {}
        identifier = (stamp or {}).get("id")
        experiment = experimentlib.get(identifier) if identifier else None

    keys = list(experiment.metrics) if experiment else sorted(
        {metric.get("key") for entry in entries
         for metric in (entry["data"].get("metrics") or [])
         if metric.get("key")})

    by_arm: dict[str, list[dict]] = {}
    for entry in entries:
        by_arm.setdefault(entry["arm"], []).append(entry)

    declared_arms = {arm.id: arm for arm in (experiment.arms if experiment else [])}
    order = list(declared_arms) + [name for name in by_arm
                                   if name not in declared_arms]
    arms = [_arm_document(name, by_arm.get(name, []), keys, root,
                          declared_arms.get(name), lang)
            for name in order if name in by_arm or name in declared_arms]

    by_id = {arm["id"]: arm for arm in arms}
    policy = (experiment.policy if experiment
              else ((entries[0]["data"].get("experiment") or {}).get("policy")
                    if entries else experimentlib.REPEATS))

    comparisons = (_comparisons(experiment, policy, by_id, keys, root,
                                experiment_run) if compare else [])

    criteria = [_criterion_result(criterion, by_id, lang)
                for criterion in (experiment.accept if experiment else [])]
    acceptance = {
        "declared": len(criteria),
        "passed": sum(1 for row in criteria if row["passed"]),
        "failed": sum(1 for row in criteria
                      if row["evaluated"] and not row["passed"]),
        "not_evaluated": sum(1 for row in criteria if not row["evaluated"]),
        "criteria": criteria,
    }

    short = [arm["id"] for arm in arms
             if arm["declared_runs"] and arm["recorded_runs"] < arm["declared_runs"]]
    verdict = _verdict(entries, arms, acceptance, short)

    return {
        "schema": SCHEMA,
        # The language the language-tagged parts of this document were resolved
        # in. Stored rather than passed to the renderer separately, so a
        # document collected in one language cannot be rendered with another's
        # headings — which is a mismatch nothing else would notice.
        "lang": lang,
        "id": experiment_run,
        "experiment_id": (experiment.id if experiment
                          else ((entries[0]["data"].get("experiment") or {})
                                .get("id") if entries else None)),
        "generated_utc": _iso(),
        "definition": (experiment.as_dict(lang) if experiment else None),
        # Stated plainly rather than left to be inferred from a null: a document
        # produced without its definition can report what was flown and cannot
        # report what was asked.
        "definition_available": experiment is not None,
        "policy": policy,
        "reference_arm": (experiment.reference_arm if experiment else ""),
        "runs_recorded": len(entries),
        "arms_short": short,
        "arms": arms,
        "comparisons": comparisons,
        "acceptance": acceptance,
        "evidence": _evidence_rollup(arms),
        "verdict": verdict,
        "limitations": limitslib.statements(
            experiment.limitations if experiment else None, lang),
        "limitations_declared": limitslib.declared_count(
            experiment.limitations if experiment else None),
    }


def _comparisons(experiment: Optional[experimentlib.Experiment], policy: str,
                 by_id: dict[str, dict], keys: list[str], root: Path,
                 experiment_run: str) -> list[dict]:
    """The deltas this experiment's policy asked for, and nothing else."""
    out: list[dict] = []

    if policy == experimentlib.ARMS:
        reference = experiment.reference_arm if experiment else ""
        base = by_id.get(reference)
        if base is None:
            return out
        for arm in by_id.values():
            if arm["id"] == reference:
                continue
            out.append({
                "kind": experimentlib.ARMS,
                "reference": reference, "current": arm["id"],
                "reference_label": base["label"], "current_label": arm["label"],
                "metrics": compare_metrics(base["metrics"], arm["metrics"]),
            })
        return out

    if policy == experimentlib.BASELINE:
        experiment_id = experiment.id if experiment else None
        earlier = (previous_run_of(experiment_id, experiment_run, root)
                   if experiment_id else None)
        if earlier is None:
            return out
        before = collect(earlier, root, experiment, compare=False)
        for arm in by_id.values():
            other = next((a for a in before["arms"] if a["id"] == arm["id"]), None)
            if other is None:
                continue
            out.append({
                "kind": experimentlib.BASELINE,
                "reference": f"{earlier}:{arm['id']}", "current": arm["id"],
                "reference_label": earlier, "current_label": arm["label"],
                "baseline_run": earlier,
                "metrics": compare_metrics(other["metrics"], arm["metrics"]),
            })
        return out

    return out                      # REPEATS compares nothing, on purpose


def _verdict(entries: list[dict], arms: list[dict], acceptance: dict,
             short: list[str]) -> str:
    """The one word, and the order it is decided in.

    not-run    nothing carries this experiment id
    failed     a declared criterion was judged and did not hold
    incomplete an arm is short of its runs, or a criterion was never judged
    not-judged the experiment declared no criteria, so nothing was asserted
    passed     every declared criterion held, over the runs that were declared

    `failed` is decided before `incomplete` because a criterion that was judged
    and did not hold is a result, and one that came from three runs instead of
    five is still that result — the document prints n beside it. `incomplete`
    is decided before `not-judged` so that an experiment which measured nothing
    cannot report the same word as one that deliberately asserts nothing.
    """
    if not entries:
        return NOT_RUN
    if acceptance["failed"]:
        return FAILED
    if short or acceptance["not_evaluated"]:
        return INCOMPLETE
    if not acceptance["declared"]:
        return NOT_JUDGED
    return PASSED


# ------------------------------------------------------------------ rendering
def _number(value: Any, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):.4g}{(' ' + unit) if unit else ''}"


VERDICT_HEADLINE = {
    PASSED: "**Every declared criterion held.**",
    FAILED: "**At least one declared criterion did not hold.**",
    INCOMPLETE: "**This experiment is incomplete.** Some of what it declared "
                "was never flown or never measured, so its verdict covers less "
                "than it was asked to.",
    NOT_JUDGED: "**Nothing was asserted.** This experiment declares no "
                "acceptance criteria, so the numbers below were measured and "
                "not judged.",
    NOT_RUN: "**No run carries this experiment id.** Nothing was flown.",
}

BASIS_NOTE = {
    MEASURED: "both arms have enough measured values for a spread to be "
              "reported",
    INDICATIVE: "**indicative only** — at least one arm has fewer measured "
                "values than a spread can be reported from",
    NONE: "not computed",
}


def render(document: dict, lang: Optional[str] = None) -> str:
    """The experiment as a document a reviewer reads, in ten fixed sections.

    The same ten-section discipline the flight report has had since v1.5, and
    for the same reason: a reviewer reading two experiments should not have to
    hunt for the same fact in two places, and a fixed order is checkable.

    The prose is English; what follows `lang` is the language-tagged content
    the definition supplied — the question, the arm labels, the criteria and
    the limitations. It defaults to the language the document was collected in,
    because those are the only two that can disagree.
    """
    lang = lang or document.get("lang") or "en"
    out: list[str] = []
    add = out.append
    definition = document.get("definition") or {}

    add(f"# Experiment — {document['id']}")
    add("")
    add(f"Generated {document['generated_utc']}.")
    add("")

    # ----------------------------------------------------- 1. Question, scope
    add("## 1. Question and scope")
    add("")
    if definition:
        add(f"> {definition.get('question', '')}")
        add("")
        add("| | |")
        add("|---|---|")
        add(f"| Experiment | `{document.get('experiment_id')}` — "
            f"{definition.get('name', '')} |")
        add(f"| Model | `{definition.get('model_id', '?')}` |")
        add(f"| Comparison policy | `{document.get('policy')}` |")
        if document.get("reference_arm"):
            add(f"| Reference arm | `{document['reference_arm']}` |")
        add(f"| Runs declared | {definition.get('total_runs', '—')} |")
        add(f"| Runs recorded | {document['runs_recorded']} |")
        add("")
    else:
        add(f"The definition of `{document.get('experiment_id')}` is not in "
            f"this checkout, so this document reports what the runs record and "
            f"not what was asked. The question, the acceptance criteria and the "
            f"declared limitations are all in the file, and none of them can be "
            f"recovered from the runs.")
        add("")

    add(VERDICT_HEADLINE.get(document["verdict"], document["verdict"]))
    add("")

    # ------------------------------------------------------ 2. Configuration
    add("## 2. Configuration")
    add("")
    if definition and definition.get("values"):
        add(f"Inputs applied to every arm: "
            f"`{json.dumps(definition['values'], sort_keys=True)}`.")
        add("")
    inconsistent = [arm for arm in document["arms"]
                    if arm["consistency"].get("checked")
                    and not arm["consistency"].get("identical")]
    if inconsistent:
        add("**The runs within an arm were not identical.** An arm claims the "
            "same aircraft, the same procedure and the same configuration every "
            "time, and these runs disagree — so any spread below measures the "
            "difference as much as it measures the aircraft:")
        add("")
        for arm in inconsistent:
            for item in arm["consistency"].get("differences") or []:
                add(f"- `{arm['id']}` — **{item['what']}** "
                    f"(`{item['field']}`, {item['reason']})")
        add("")
    else:
        add("Every run within each arm agrees with the others on its "
            "environment fingerprint: same firmware, same model configuration, "
            "same procedure text.")
        add("")

    # ----------------------------------------------------------- 3. Execution
    add("## 3. Execution")
    add("")
    add("Each arm was flown as an ordinary repeatability campaign, through the "
        "same procedure runner the interface drives. Every iteration below is "
        "a complete run directory with its own evidence.")
    add("")
    add("| Arm | Role | Procedure | Campaign | Declared | Recorded | passed | "
        "failed | flaky | incomplete |")
    add("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for arm in document["arms"]:
        counts = arm["counts"]
        add(f"| **{arm['id']}** — {arm['label']} | {arm['role']} "
            f"| `{arm['procedure_id']}` | `{arm['campaign_id'] or '—'}` "
            f"| {arm['declared_runs'] or '—'} | {arm['recorded_runs']} "
            f"| {counts.get(campaignlib.PASSED, 0)} "
            f"| {counts.get(campaignlib.FAILED, 0)} "
            f"| {counts.get(campaignlib.FLAKY, 0)} "
            f"| {counts.get(campaignlib.INCOMPLETE, 0)} |")
    add("")
    if document["arms_short"]:
        add(f"**{', '.join('`' + name + '`' for name in document['arms_short'])} "
            f"flew fewer runs than declared.** Everything computed from those "
            f"arms rests on a smaller sample than the experiment asked for.")
        add("")

    # ------------------------------------------------------------- 4. Verdict
    add("## 4. Verdict")
    add("")
    acceptance = document["acceptance"]
    if not acceptance["declared"]:
        add("This experiment declares no acceptance criteria. It measures and "
            "reports; it asserts nothing, and no part of this document should "
            "be read as a pass.")
        add("")
    else:
        add(f"{acceptance['passed']} of {acceptance['declared']} declared "
            f"criteria held, {acceptance['failed']} did not, and "
            f"{acceptance['not_evaluated']} could not be judged at all.")
        add("")
        add("| Criterion | Arm | Judged | Result |")
        add("|---|---|---|---|")
        for row in acceptance["criteria"]:
            mark = ("passed" if row["passed"]
                    else "**FAILED**" if row["evaluated"] else "*not judged*")
            add(f"| {row['label']}<br><sub>`{row['criterion_id']}`</sub> "
                f"| `{row['arm']}` | {'yes' if row['evaluated'] else 'no'} "
                f"| {mark}<br><sub>{row['text']}</sub> |")
        add("")

    # ----------------------------------------------------- 5. Failed criteria
    add("## 5. Failed criteria")
    add("")
    failed = [row for row in acceptance["criteria"]
              if row["evaluated"] and not row["passed"]]
    unjudged = [row for row in acceptance["criteria"] if not row["evaluated"]]
    if not failed:
        add("None." if acceptance["declared"] else
            "None were declared, so none failed. That is not a pass.")
        add("")
    for row in failed:
        # The observation first and the declaration second. A reviewer reading
        # this section already knows something failed; what they need next is
        # the number, not the sentence somebody wrote about it beforehand.
        add(f"- **`{row['criterion_id']}`** — {row['text']}.")
        add(f"  Declared as: *{row['label']}*")
    if failed:
        add("")
    if unjudged:
        add("Not judged, which is not the same as passing:")
        add("")
        for row in unjudged:
            add(f"- **`{row['criterion_id']}`** — {row['text']}")
        add("")

    # ------------------------------------------------ 6. Measured quantities
    add("## 6. Measured quantities, by arm")
    add("")
    for arm in document["arms"]:
        add(f"### `{arm['id']}` — {arm['label']}")
        add("")
        if not arm["metrics"]:
            add("No metric was selected for this experiment.")
            add("")
            continue
        add("| Metric | n | Mean | Std dev | Min | Max | Not measured |")
        add("|---|---:|---:|---:|---:|---:|---:|")
        for row in arm["metrics"]:
            spread = ("—" if row["stdev"] is None
                      else _number(row["stdev"], row["unit"]))
            add(f"| {row['label']}<br><sub>`{row['key']}`"
                + (f" — {', '.join(row['procedures'])}" if row["procedures"] else "")
                + f"</sub> | {row['n']} | {_number(row['mean'], row['unit'])} "
                f"| {spread} | {_number(row['min'], row['unit'])} "
                f"| {_number(row['max'], row['unit'])} | {row['not_measured']} |")
        add("")
    add(f"A standard deviation is reported only from "
        f"{campaignlib.MIN_SAMPLES_FOR_SPREAD} measured values upwards; below "
        f"that it is `—`, which means *not enough runs to say* and not *no "
        f"variation*.")
    add("")

    # ---------------------------------------------------------- 7. Comparison
    add("## 7. Comparison")
    add("")
    if not document["comparisons"]:
        if document["policy"] == experimentlib.REPEATS:
            add("This experiment repeats one arm and compares nothing. The "
                "distributions in section 6 are the whole result.")
        elif document["policy"] == experimentlib.BASELINE:
            add("No earlier run of this experiment was found, so there is "
                "nothing to compare this one against. Run it again to produce "
                "a baseline.")
        else:
            add("No comparison could be made — the reference arm has no "
                "recorded run.")
        add("")
    for comparison in document["comparisons"]:
        add(f"### `{comparison['current']}` against `{comparison['reference']}`")
        add("")
        add("| Metric | Reference | Current | Δ of means | Δ% | Ranges overlap "
            "| Basis |")
        add("|---|---|---|---:|---:|---|---|")
        for row in comparison["metrics"]:
            left, right = row["reference"], row["current"]
            relative = ("—" if row["relative"] is None
                        else f"{row['relative'] * 100:+.1f}%")
            delta = "—" if row["delta"] is None else f"{row['delta']:+.4g}"
            overlap = {True: "yes", False: "**no**", None: "—"}[row["ranges_overlap"]]
            note = f"<br><sub>{row['reason']}</sub>" if row["reason"] else ""
            add(f"| {row['label']}<br><sub>`{row['key']}`</sub> "
                f"| {_number((left or {}).get('mean'), row['unit'])} "
                f"(n={(left or {}).get('n', 0)}) "
                f"| {_number((right or {}).get('mean'), row['unit'])} "
                f"(n={(right or {}).get('n', 0)}) "
                f"| {delta} | {relative} | {overlap} "
                f"| {row['basis']}{note} |")
        add("")

    if document["comparisons"]:
        add("**No p-value, confidence interval or effect size is computed "
            "here.** At the sample sizes a SITL campaign produces, every one of "
            "them would be arithmetic that runs fine and means nothing, and "
            "each would read as though the difference had been established. "
            "What is reported instead is n on both sides, the two means, their "
            "difference, and whether the two arms' observed ranges overlap at "
            "all — which is a statement about the numbers actually seen, not a "
            "significance test.")
        add("")

    # ------------------------------------------------------------ 8. Evidence
    add("## 8. Evidence")
    add("")
    evidence = document["evidence"]
    add(f"{evidence['complete']} of {evidence['runs']} run(s) left every "
        f"required artefact behind.")
    add("")
    if evidence["incomplete"]:
        add("**Incomplete evidence** — these runs are missing something a claim "
            "rests on: "
            + ", ".join(f"`{name}`" for name in evidence["incomplete"]) + ".")
        add("")
        if evidence["missing_required"]:
            add("Missing artefacts: "
                + ", ".join(f"`{name}`" for name in evidence["missing_required"])
                + ".")
            add("")
    if evidence["unknown"]:
        add("These runs carry no evidence manifest, so whether they are "
            "complete is unknown: "
            + ", ".join(f"`{name}`" for name in evidence["unknown"]) + ".")
        add("")
    add("| Arm | Run | Status | Evidence |")
    add("|---|---|---|---|")
    for arm in document["arms"]:
        for run in arm["runs"]:
            state = {True: "complete", False: "**incomplete**",
                     None: "*no manifest*"}[run["evidence_complete"]]
            add(f"| `{arm['id']}` | `{run['run_id']}` | {run['status']} "
                f"| {state} |")
    add("")
    add("Every row is an ordinary run directory: `result.json`, the dataflash "
        "log, the environment fingerprint, the evidence manifest and the flight "
        "report. This document adds no fact that is not recomputable from them.")
    add("")

    # ---------------------------------------------------------- 9. Provenance
    add("## 9. How to reproduce this document")
    add("")
    add("```")
    add(f"python3 -m argazui experiment {document['id']}")
    add("```")
    add("")
    add("It is recomputed from the run directories every time and nothing about "
        "it is cached, so this document and the evidence under it cannot drift "
        "apart.")
    add("")

    # -------------------------------------------------------- 10. Limitations
    add("## 10. Limitations and non-claims")
    add("")
    for line in _limitation_lines(document, lang):
        add(line)
    return "\n".join(out)


def _limitation_lines(document: dict, lang: str) -> list[str]:
    lines: list[str] = []
    rows = document.get("limitations") or []
    count = document.get("limitations_declared") or 0

    lines.append(
        "Everything above is **verification** — an implementation met criteria "
        "somebody declared. None of it is **validation**: nothing here shows "
        "the criteria, the model or the question are representative of anything "
        "that happens outside a simulator. See "
        "[verification-vs-validation.md](../../docs/verification-vs-validation.md).")
    lines.append("")
    if not count:
        lines.append(
            "**This experiment declared no limitations of its own**, so only "
            "the standing ones below apply. That is allowed and it is worth "
            "noticing: the limits that matter most to a particular question are "
            "usually the ones only its author knows.")
        lines.append("")

    for category in limitslib.CATEGORIES:
        entries = [row for row in rows if row["category"] == category]
        if not entries:
            continue
        lines.append(f"### {limitslib.label_for(category, lang)}")
        lines.append("")
        lines.append(limitslib.what_for(category, lang))
        lines.append("")
        for row in entries:
            mark = "" if row["source"] == limitslib.DECLARED else " *(standing)*"
            lines.append(f"- {row['text']}{mark}")
        lines.append("")
    return lines


# -------------------------------------------------------------------- storage
def directory_for(experiment_run: str, root: Optional[Path] = None) -> Path:
    root = Path(root) if root else paths.RUNS_DIR
    return root / EXPERIMENTS_DIRNAME / experiment_run


def write(experiment_run: str, document: dict,
          root: Optional[Path] = None) -> tuple[Path, Path]:
    """Writes experiment.json and experiment.md, and returns both paths."""
    directory = directory_for(experiment_run, root)
    directory.mkdir(parents=True, exist_ok=True)
    as_json = directory / "experiment.json"
    as_text = directory / "experiment.md"
    as_json.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    as_text.write_text(render(document), encoding="utf-8")
    return as_json, as_text
