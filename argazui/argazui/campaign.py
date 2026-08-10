"""Repeatability campaigns — the same flight, N times, aggregated honestly.

WHY ONE RUN IS NOT AN ANSWER
----------------------------
Every layer below this one judges a single flight: the criteria held or they
did not, the metrics were these numbers, the comparison against a baseline said
this. All of it is true of *one* takeoff, and a simulation's failures are
frequently not like that. A procedure that works four times in five is not a
working procedure and not a broken one, and neither a green run nor a red one
says which it is. The tailsitter this project was rebuilt around passed three
times in a row while the aircraft was tumbling — repetition alone would not
have caught that, but a *spread* would have: 24.9 m, 23.6 m, 18.3 m is not the
signature of a controlled climb.

So a campaign flies the same procedure, on the same model, in the same
configuration, N times, and reports the distribution rather than a verdict.

WHAT A CAMPAIGN IS, STRUCTURALLY
--------------------------------
It is a campaign id stamped into N ordinary run directories. There is no new
storage format and no database: each iteration produces exactly the evidence a
single flight produces — its own `result.json`, its own dataflash log, its own
fingerprint — and the campaign document is an aggregation over them that can be
regenerated at any time from the runs alone.

That is deliberate. A campaign summary that could not be recomputed from the
runs would be a fourth kind of claim with no evidence under it.

WHAT IT REFUSES TO SAY
----------------------
Five runs is five runs. This module reports counts, a pass rate, and the mean,
standard deviation, minimum and maximum of each metric — and it states the
sample size beside every one of them. It computes no confidence interval, no
p-value and no "reliability" figure, because none of those means anything at
n=5 and all of them would read as though it did.

A run that passed only on a retry is `flaky` here, exactly as it is in
`docs/status.md`. It is never counted as a clean pass, and the pass rate is
computed on clean passes only — a campaign whose pass rate quietly included
retries would be measuring the harness's patience rather than the aircraft.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import failures as failurelib
from . import fingerprint as fp
from . import metrics as metricslib
from . import paths

SCHEMA = 1

# Where campaign documents live, under the runs root. A sibling of the run
# directories rather than a parent of them: a campaign's runs are ordinary runs
# and everything that reads `runs/` must keep finding them.
CAMPAIGNS_DIRNAME = "campaigns"

# Per-iteration verdicts. The same four words the status table uses, because a
# reader should not have to learn a second vocabulary for the same facts.
PASSED, FAILED, FLAKY, INCOMPLETE = "passed", "failed", "flaky", "incomplete"
VERDICTS = (PASSED, FAILED, FLAKY, INCOMPLETE)

# How many runs a campaign flies unless told otherwise.
DEFAULT_RUNS = 5

# Below this many measured values a metric's standard deviation is not
# reported. Two numbers have a standard deviation and it describes nothing;
# printing one would give a spread of two samples the same visual weight as a
# spread of twenty.
MIN_SAMPLES_FOR_SPREAD = 3

CAMPAIGN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z_[A-Za-z0-9_.-]+$")


def campaign_id(model_id: str, procedure_id: str,
                when: Optional[datetime] = None) -> str:
    """`20260810T124500Z_sitl_quad.copter_takeoff` — sorts by time, reads as prose."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{model_id}.{procedure_id}")
    return f"{stamp}_{safe}"


def _iso(when: Optional[datetime] = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------- record
@dataclass
class Definition:
    """What a campaign is repeating. Written into every run it produces."""

    id: str
    model_id: str
    procedure_id: str
    runs: int = DEFAULT_RUNS
    values: dict = field(default_factory=dict)
    note: str = ""

    def stamp(self, index: int) -> dict:
        """The block one run carries so it can be found again without an index."""
        return {"schema": SCHEMA, "id": self.id, "index": index,
                "of": self.runs, "model_id": self.model_id,
                "procedure_id": self.procedure_id,
                "values": dict(self.values), "note": self.note}

    def as_dict(self) -> dict:
        return {"schema": SCHEMA, "id": self.id, "model_id": self.model_id,
                "procedure_id": self.procedure_id, "runs": self.runs,
                "values": dict(self.values), "note": self.note}


# ------------------------------------------------------------------ execution
class CampaignRunner:
    """Flies one procedure N times through a caller-supplied launcher.

    WHY A LAUNCHER CALLABLE AND NOT A LAUNCHER
    ------------------------------------------
    Bringing an aircraft up is genuinely different in the three places this is
    driven from: the server starts Gazebo and MAVProxy in a pty, tier 1 starts
    a bare SITL binary over TCP, tier 2 starts the full stack. What is the SAME
    in all three, and what this class exists to keep the same, is everything
    after that — one run directory per iteration, the same `ProcedureRunner`,
    the campaign id on every run, and one aggregation at the end.

    `launch` is called once per iteration and must return an object with:

        run(procedure_id, values) -> (result: dict, run_dir: Path)
        close()                   -> tear the iteration down

    Anything raised by `launch` is caught and recorded as an `environment`
    failure for that iteration; the campaign continues, because "three of five
    starts failed" is a result about repeatability and stopping at the first
    one would hide it.
    """

    def __init__(self, definition: Definition,
                 launch: Callable[[int], Any],
                 on_progress: Optional[Callable[[dict], None]] = None) -> None:
        self.definition = definition
        self.launch = launch
        self.on_progress = on_progress or (lambda event: None)
        self._cancel = False
        self.iterations: list[dict] = []

    def cancel(self) -> None:
        self._cancel = True

    def _emit(self, event: str, **payload) -> None:
        try:
            self.on_progress({"type": "campaign", "event": event,
                              "campaign": self.definition.id, **payload})
        except Exception:
            pass

    def run(self) -> list[dict]:
        """Flies every iteration. Returns one summary row per attempt."""
        self._emit("start", definition=self.definition.as_dict())
        for index in range(1, self.definition.runs + 1):
            if self._cancel:
                self._emit("cancelled", index=index)
                break
            self._emit("iteration_start", index=index, of=self.definition.runs)
            row = self._one(index)
            self.iterations.append(row)
            self._emit("iteration_done", index=index, of=self.definition.runs,
                       row=row)
        self._emit("done", iterations=len(self.iterations))
        return self.iterations

    def _one(self, index: int) -> dict:
        row: dict[str, Any] = {"index": index, "run_id": None, "dir": None,
                               "verdict": INCOMPLETE, "failure": None,
                               "started_utc": _iso()}
        session = None
        try:
            session = self.launch(index)
            result, directory = session.run(self.definition.procedure_id,
                                            dict(self.definition.values))
            row["run_id"] = result.get("run_id")
            row["dir"] = str(directory) if directory else None
        except Exception as exc:
            # A launcher that could not bring the aircraft up. Recorded as an
            # environment failure for this iteration and nothing more: it says
            # nothing about the procedure, and it must not be allowed to.
            row["failure"] = failurelib.Failure(
                failurelib.ENVIRONMENT, "iteration-launch-failed",
                detail=f"{type(exc).__name__}: {exc}",
                source="campaign.launch").as_dict()
            row["text"] = str(exc)
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
        row["finished_utc"] = _iso()
        return row


# ---------------------------------------------------------------- statistics
def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _stdev(values: list[float]) -> Optional[float]:
    """Sample standard deviation, or None when the sample is too small.

    None rather than 0.0 for a single value. A spread of zero is a claim that
    the quantity does not vary, and one measurement cannot support it.
    """
    if len(values) < MIN_SAMPLES_FOR_SPREAD:
        return None
    average = sum(values) / len(values)
    variance = sum((v - average) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def statistics(values: list[float]) -> dict:
    """Mean, spread and range of one metric across a campaign."""
    clean = [float(v) for v in values if v is not None]
    return {
        "n": len(clean),
        "mean": None if not clean else round(_mean(clean), 4),
        "stdev": (None if _stdev(clean) is None else round(_stdev(clean), 4)),
        "min": min(clean) if clean else None,
        "max": max(clean) if clean else None,
        # Stated so the reader never has to work out whether a missing spread
        # means "identical every time" or "not enough runs to say".
        "spread_reported": len(clean) >= MIN_SAMPLES_FOR_SPREAD,
    }


# ----------------------------------------------------------------- collection
def _verdict_for(result: dict) -> str:
    if not result:
        return INCOMPLETE
    status = result.get("status")
    if status == "passed" and result.get("flaky"):
        return FLAKY
    if status == "passed":
        return PASSED
    if status in ("failed", "error"):
        return FAILED
    return INCOMPLETE


def runs_of(campaign: str, root: Optional[Path] = None) -> list[dict]:
    """Every run directory carrying this campaign id, in iteration order.

    Found by reading the runs rather than by trusting an index file. A campaign
    interrupted half way still aggregates, and a run somebody moved is simply
    not there — which is the truth, rather than a dangling reference.
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
        stamp = data.get("campaign") or {}
        if stamp.get("id") != campaign:
            continue
        out.append({"dir": path.parent, "data": data,
                    "index": int(stamp.get("index") or 0)})
    out.sort(key=lambda entry: (entry["index"], entry["data"].get("started_utc") or ""))
    return out


def list_campaigns(root: Optional[Path] = None) -> list[dict]:
    """Every campaign present in the runs root, newest first."""
    root = Path(root) if root else paths.RUNS_DIR
    found: dict[str, dict] = {}
    if not root.is_dir():
        return []
    for path in sorted(root.rglob("result.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = data.get("campaign") or {}
        identifier = stamp.get("id")
        if not identifier:
            continue
        entry = found.setdefault(identifier, {
            "id": identifier, "model_id": stamp.get("model_id"),
            "procedure_id": stamp.get("procedure_id"),
            "declared_runs": stamp.get("of"), "recorded_runs": 0,
            "started_utc": data.get("started_utc") or ""})
        entry["recorded_runs"] += 1
        started = data.get("started_utc") or ""
        if started and (not entry["started_utc"] or started < entry["started_utc"]):
            entry["started_utc"] = started
    return sorted(found.values(), key=lambda e: e["started_utc"], reverse=True)


def aggregate(campaign: str, root: Optional[Path] = None,
              definition: Optional[Definition] = None) -> dict:
    """The campaign document: counts, pass rate, per-metric spread, per-run row.

    Everything here is recomputed from the run directories every time. There is
    no cached total anywhere, so a campaign document and the runs under it
    cannot drift apart.
    """
    entries = runs_of(campaign, root)
    rows: list[dict] = []
    metric_values: dict[tuple, list[float]] = {}
    metric_meta: dict[tuple, dict] = {}
    failure_counts: dict[str, int] = {}
    fingerprints: list[dict] = []

    for entry in entries:
        data = entry["data"]
        verdict = _verdict_for(data)
        failure = failurelib.classify_run(data)
        if failure is not None:
            failure_counts[failure.category] = \
                failure_counts.get(failure.category, 0) + 1
        manifest = data.get("fingerprint") or fp.read(entry["dir"])
        if manifest:
            fingerprints.append(manifest)

        for metric in data.get("metrics") or []:
            identity = (metric.get("key"), metric.get("procedure") or "")
            metric_meta.setdefault(identity, metric)
            if metric.get("value") is not None:
                metric_values.setdefault(identity, []).append(float(metric["value"]))
            else:
                metric_values.setdefault(identity, [])

        rows.append({
            "index": entry["index"],
            "run_id": data.get("run_id") or entry["dir"].name,
            "dir": str(entry["dir"]),
            "verdict": verdict,
            "status": data.get("status"),
            "started_utc": data.get("started_utc"),
            "seconds": data.get("seconds"),
            "advisory_count": data.get("advisory_count"),
            "flaky": data.get("flaky") or [],
            "failure": failure.as_dict() if failure else None,
            # Faults are listed per run so an off-nominal campaign says which
            # iterations actually had their fault injected.
            "faults": [f.get("id") for entry_ in (data.get("procedures") or [])
                       for f in ((entry_.get("result") or {}).get("faults") or [])],
        })

    counts = {name: sum(1 for r in rows if r["verdict"] == name)
              for name in VERDICTS}
    # Clean passes only. A retry is paid for here exactly as it is in the
    # status table: it buys a `flaky`, never a `passed`.
    pass_rate = (counts[PASSED] / len(rows)) if rows else None

    metrics = []
    for identity in sorted(metric_values, key=lambda i: (i[0], i[1])):
        key, procedure = identity
        meta = metric_meta.get(identity, {})
        stats = statistics(metric_values[identity])
        metrics.append({
            "key": key, "procedure": procedure,
            "label": metricslib.label_for(key),
            "unit": meta.get("unit", ""), "better": meta.get("better", ""),
            "not_measured": len(rows) - stats["n"],
            **stats,
        })

    return {
        "schema": SCHEMA,
        "id": campaign,
        "generated_utc": _iso(),
        "definition": (definition.as_dict() if definition
                       else _definition_from(entries)),
        "runs_recorded": len(rows),
        "counts": counts,
        "pass_rate": None if pass_rate is None else round(pass_rate, 4),
        "failure_categories": failure_counts,
        "consistency": consistency(fingerprints),
        "metrics": metrics,
        "runs": rows,
    }


def _definition_from(entries: list[dict]) -> dict:
    for entry in entries:
        stamp = entry["data"].get("campaign") or {}
        if stamp:
            return {"schema": SCHEMA, "id": stamp.get("id"),
                    "model_id": stamp.get("model_id"),
                    "procedure_id": stamp.get("procedure_id"),
                    "runs": stamp.get("of"), "values": stamp.get("values") or {},
                    "note": stamp.get("note", "")}
    return {}


def consistency(fingerprints: list[dict]) -> dict:
    """Did every iteration really fly the same thing?

    A campaign's whole claim is "same model, same procedure, same
    configuration, N times". That claim is checkable — the runs each carry a
    fingerprint — and checking it is not optional, because a campaign that
    silently spanned an edited procedure would report a spread caused by the
    edit as though it were caused by the aircraft.
    """
    if len(fingerprints) < 2:
        return {"checked": bool(fingerprints), "identical": bool(fingerprints),
                "differences": []}
    baseline = fingerprints[0]
    differences: list[dict] = []
    for manifest in fingerprints[1:]:
        for item in fp.differences(baseline, manifest):
            if item["field"] not in {d["field"] for d in differences}:
                differences.append(item)
    return {"checked": True, "identical": not differences,
            "differences": differences}


# ------------------------------------------------------------------ rendering
VERDICT_MARK = {PASSED: "passed", FAILED: "**failed**", FLAKY: "**flaky**",
                INCOMPLETE: "*incomplete*"}


def _number(value: Any, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):.4g}{(' ' + unit) if unit else ''}"


def render(document: dict) -> str:
    """The campaign as a document a person reads. Same facts, no new ones."""
    out: list[str] = []
    add = out.append
    definition = document.get("definition") or {}

    add(f"# Repeatability campaign — {document['id']}")
    add("")
    add(f"Generated {document['generated_utc']}.")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Model | `{definition.get('model_id', '?')}` |")
    add(f"| Procedure | `{definition.get('procedure_id', '?')}` |")
    add(f"| Runs declared | {definition.get('runs', '—')} |")
    add(f"| Runs recorded | {document['runs_recorded']} |")
    if definition.get("values"):
        add(f"| Inputs | `{json.dumps(definition['values'], sort_keys=True)}` |")
    if definition.get("note"):
        add(f"| Note | {definition['note']} |")
    add("")

    counts = document["counts"]
    rate = document["pass_rate"]
    add("## Outcome")
    add("")
    add("| passed | failed | flaky | incomplete | clean pass rate |")
    add("|---:|---:|---:|---:|---:|")
    add(f"| {counts[PASSED]} | {counts[FAILED]} | {counts[FLAKY]} "
        f"| {counts[INCOMPLETE]} "
        f"| {'—' if rate is None else f'{rate * 100:.0f}%'} |")
    add("")
    add(f"The pass rate counts **clean passes only**, over "
        f"{document['runs_recorded']} run(s). A run that passed on a retry is "
        f"`flaky` and is not in it.")
    add("")
    add(f"**{document['runs_recorded']} run(s) is {document['runs_recorded']} "
        f"run(s).** No confidence interval, reliability figure or p-value is "
        f"computed from this sample, because none of them would mean anything "
        f"at this size and all of them would read as though they did.")
    add("")

    if document.get("failure_categories"):
        add("### Failures by category")
        add("")
        for category, count in sorted(document["failure_categories"].items()):
            add(f"- **{failurelib.label_for(category)}** (`{category}`) — {count}")
        add("")

    consistent = document.get("consistency") or {}
    if consistent.get("checked") and not consistent.get("identical"):
        add("### The iterations were not identical")
        add("")
        add("A campaign claims the same aircraft, the same procedure and the "
            "same configuration every time. These runs disagree, so any spread "
            "below measures the difference as much as it measures the "
            "aircraft:")
        add("")
        for item in consistent.get("differences") or []:
            add(f"- **{item['what']}** (`{item['field']}`, {item['reason']})")
        add("")

    add("## Metrics across the campaign")
    add("")
    if not document["metrics"]:
        add("No run in this campaign carried metrics. Run "
            "`python3 -m argazui report <run>` on each to derive them from the "
            "dataflash logs that were archived.")
        add("")
    else:
        add("| Metric | n | Mean | Std dev | Min | Max | Not measured |")
        add("|---|---:|---:|---:|---:|---:|---:|")
        for row in document["metrics"]:
            name = row["label"] + (f" — `{row['procedure']}`"
                                   if row["procedure"] else "")
            spread = ("—" if row["stdev"] is None
                      else _number(row["stdev"], row["unit"]))
            add(f"| {name}<br><sub>`{row['key']}`</sub> | {row['n']} "
                f"| {_number(row['mean'], row['unit'])} | {spread} "
                f"| {_number(row['min'], row['unit'])} "
                f"| {_number(row['max'], row['unit'])} "
                f"| {row['not_measured']} |")
        add("")
        add(f"A standard deviation is reported only from "
            f"{MIN_SAMPLES_FOR_SPREAD} measured values upwards; below that it "
            f"is `—`, which means *not enough runs to say* and not *no "
            f"variation*.")
        add("")
        add("Metrics are measurements, not acceptance criteria. A wide spread "
            "here fails nothing — it says the aircraft did not do the same "
            "thing twice, which is exactly what a campaign is for.")
        add("")

    add("## Per-run result")
    add("")
    add("| # | Run | Verdict | Failure | Advisories | Seconds |")
    add("|---:|---|---|---|---:|---:|")
    for row in document["runs"]:
        failure = row.get("failure")
        detail = ("—" if not failure else
                  f"`{failure['category']}`<br><sub>{failure['code']}</sub>")
        advisories = "—" if row.get("advisory_count") is None \
            else row["advisory_count"]
        seconds = "—" if row.get("seconds") is None else f"{row['seconds']:.0f}"
        add(f"| {row['index']} | `{row['run_id']}` "
            f"| {VERDICT_MARK.get(row['verdict'], row['verdict'])} "
            f"| {detail} | {advisories} | {seconds} |")
    add("")
    add("Each row is an ordinary run directory with its own evidence: "
        "`result.json`, the dataflash log, the fingerprint and the flight "
        "report. This document adds no fact that is not recomputable from "
        "them.")
    add("")
    return "\n".join(out)


# -------------------------------------------------------------------- storage
def directory_for(campaign: str, root: Optional[Path] = None) -> Path:
    root = Path(root) if root else paths.RUNS_DIR
    return root / CAMPAIGNS_DIRNAME / campaign


def write(campaign: str, document: dict,
          root: Optional[Path] = None) -> tuple[Path, Path]:
    """Writes campaign.json and campaign.md, and returns both paths."""
    directory = directory_for(campaign, root)
    directory.mkdir(parents=True, exist_ok=True)
    as_json = directory / "campaign.json"
    as_text = directory / "campaign.md"
    as_json.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    as_text.write_text(render(document), encoding="utf-8")
    return as_json, as_text
