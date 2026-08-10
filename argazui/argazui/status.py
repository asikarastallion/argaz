"""Generate `docs/status.md` from test output. Never from an opinion.

WHY THIS FILE IS GENERATED
--------------------------
v1.0's README carried a hand-written table of supported models with ticks
against them. Nothing produced those ticks except somebody's belief, and at
least one of them was wrong for a year: Plane TAKEOFF never worked. The whole
of v1.1 exists to replace that belief with machine output, and this module is
where the replacement happens.

THE ONE RULE THAT MATTERS MOST
------------------------------
**Tier 1 makes no claim about any model.** It flies SITL's own generic frames
and proves the procedure logic, the API and the page. A model it never touched
stays `untested`, and the Tier column says which tier — if any — actually flew
the airframe in the row. If that distinction ever blurs, the table becomes the
thing it was written to replace.

WHAT EACH RESULT MEANS
----------------------
    passed     flown in tier 2; every acceptance criterion held
    failed     flown in tier 2; a step or a criterion did not hold
    flaky      flown in tier 2; passed only on the retry
    untested   not yet verified by a machine — NOT "broken"

`no-procedure`, a skipped test and a model absent from the run all collapse to
`untested`, because they are the same statement: nothing was proven here.

A ROW IS NOT A CLAIM ABOUT A MODEL
----------------------------------
`passed` in the table above means "every procedure this model was flown with
met every criterion it declared". That is narrower than it looks, and the gap
is where an unearned claim grows back: nobody flew this aircraft through a
mission, in wind, near its limits, or twice in a row. So the table is not the
finest thing this generator produces — `verification claims` are. Each one names
one procedure or one acceptance criterion, its result and the run that proves
it, and the section that renders them says plainly that anything not listed was
not verified.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import failures as failurelib
from . import paths

# 2 (v1.3): rows carry `claims` — what was verified, at procedure and
#           acceptance-criterion granularity, with the run that proves each.
# 3 (v1.4): a failing row carries the classified failure category, and an
#           injected fault is a claim of its own kind.
SCHEMA = 3

PASSED, FAILED, FLAKY, UNTESTED = "passed", "failed", "flaky", "untested"
RESULTS = (PASSED, FAILED, FLAKY, UNTESTED)

# What a single claim can say. `not evaluated` is its own word and not a
# failure: a criterion the procedure never reached says nothing about the
# aircraft, and collapsing it into `failed` would be an invented result in the
# opposite direction from an invented pass.
CLAIM_PASSED, CLAIM_FAILED, CLAIM_UNEVALUATED = "passed", "failed", "not evaluated"

# The kinds of thing a run can prove, coarsest first.
CLAIM_PROCEDURE = "procedure"
CLAIM_MODE = "mode transition"
CLAIM_CRITERION = "acceptance criterion"
# An off-nominal claim: a fault was injected and the aircraft's response was
# judged. Its own kind because it is a different sort of statement from the
# other three — it says what happened when something was WRONG, and reading it
# as a nominal claim would overstate what the run showed.
CLAIM_FAULT = "fault response"

# A test outcome recorded by tests/conftest.py, mapped to a table result.
# `skipped` is deliberately UNTESTED and never PASSED: a machine that did not
# run something has not verified it.
FROM_TEST_OUTCOME = {
    "passed": PASSED,
    "failed": FAILED,
    "error": FAILED,
    "skipped": UNTESTED,
}


@dataclass
class Claim:
    """One thing a run actually verified, and the evidence for it."""

    subject: str
    kind: str
    procedure: str
    result: str
    detail: str = ""
    run_id: str = ""


@dataclass
class Row:
    model: dict
    result: str = UNTESTED
    reason: str = ""
    procedures: list[str] = field(default_factory=list)
    advisories: Optional[int] = None
    last_run: str = ""
    firmware: str = ""
    tier: str = ""
    claims: list[Claim] = field(default_factory=list)
    # The classified reason the model's latest run did not pass, or None.
    # Read from the run rather than derived here: `failures.py` is the one
    # implementation of that judgement.
    failure: Optional[dict] = None

    @property
    def model_id(self) -> str:
        return self.model.get("id", "?")

    @property
    def claims_passed(self) -> int:
        return sum(1 for c in self.claims if c.result == CLAIM_PASSED)


def claims_of(result: dict) -> list[Claim]:
    """Every claim one stored run supports, from the run's own record.

    Only the LAST attempt of each procedure is read, for the same reason
    `aggregate_status` reads only the last: the suite is allowed one retry, and
    that leniency is paid for in the `flaky` marker rather than by counting a
    failed first attempt twice.

    Nothing is inferred here. A criterion that was never evaluated is reported
    as never evaluated, and a run with no procedures produces no claims at all
    — which is exactly what "flown by hand" is worth.
    """
    run_id = result.get("run_id", "")
    last: dict[str, dict] = {}
    for entry in result.get("procedures") or []:
        if entry.get("procedure"):
            last[entry["procedure"]] = entry

    out: list[Claim] = []
    for procedure, entry in last.items():
        outcome = entry.get("result") or {}
        role = entry.get("role") or "procedure"
        verdict = (CLAIM_PASSED if outcome.get("outcome") == "passed"
                   else CLAIM_FAILED)
        out.append(Claim(subject=role, kind=CLAIM_PROCEDURE, procedure=procedure,
                         result=verdict, detail=entry.get("name") or procedure,
                         run_id=run_id))

        # A mode change confirmed by heartbeat number is a claim in its own
        # right — it is one of the three things this project says it verifies,
        # and it is buried inside a procedure's steps rather than stated.
        for step in outcome.get("steps") or []:
            if step.get("kind") != "set_mode":
                continue
            out.append(Claim(
                subject=CLAIM_MODE, kind=CLAIM_MODE, procedure=procedure,
                result=(CLAIM_PASSED if step.get("status") == "passed"
                        else CLAIM_UNEVALUATED if step.get("status") == "skipped"
                        else CLAIM_FAILED),
                detail=f"{step.get('label', 'set_mode')} — {step.get('text', '')}"[:120],
                run_id=run_id))

        # A fault the run injected, and whether the aircraft's response met the
        # criteria the scenario declared. A fault that was applied and never
        # judged — because its evidence never arrived — is `not evaluated`, not
        # a pass: injecting a fault successfully proves nothing about the
        # aircraft.
        for fault in outcome.get("faults") or []:
            if not fault.get("applied"):
                verdict_f = CLAIM_UNEVALUATED
            elif fault.get("evidence_missing"):
                verdict_f = CLAIM_UNEVALUATED
            else:
                verdict_f = CLAIM_PASSED if fault.get("passed") else CLAIM_FAILED
            out.append(Claim(
                subject=f"{fault.get('fault')} → {fault.get('id')}",
                kind=CLAIM_FAULT, procedure=procedure, result=verdict_f,
                detail=(f"{fault.get('target')}, held "
                        f"{fault.get('held_s', 0)}s — "
                        f"{fault.get('text', '')}")[:160],
                run_id=run_id))

        for criterion in outcome.get("expect") or []:
            text = criterion.get("text") or ""
            unevaluated = "not evaluated" in text or "degerlendirilmedi" in text
            out.append(Claim(
                subject=criterion.get("label") or "criterion",
                kind=CLAIM_CRITERION, procedure=procedure,
                result=(CLAIM_PASSED if criterion.get("passed")
                        else CLAIM_UNEVALUATED if unevaluated else CLAIM_FAILED),
                detail=(f"[{criterion['kind']} "
                        f"{criterion.get('duration')}s] {text}"[:160]
                        if criterion.get("kind") and criterion["kind"] != "eventually"
                        else text[:160]),
                run_id=run_id))
    return out


@dataclass
class Suite:
    """One `suite.json`, as written by tests/conftest.py."""

    path: Path
    environment: str = "unknown"
    generated_utc: str = ""
    tests: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Suite":
        doc = json.loads(path.read_text(encoding="utf-8"))
        return cls(path=path, environment=doc.get("environment", "unknown"),
                   generated_utc=doc.get("generated_utc", ""),
                   tests=doc.get("tests") or [])

    def by_marker(self, marker: str) -> list[dict]:
        return [t for t in self.tests if marker in (t.get("markers") or [])]


def _model_id_from_nodeid(nodeid: str) -> Optional[str]:
    """`...[skywalker_x8_quad]` -> `skywalker_x8_quad`."""
    if "[" not in nodeid or not nodeid.rstrip().endswith("]"):
        return None
    return nodeid.rsplit("[", 1)[1].rstrip("]").strip() or None


def _runs_under(root: Path) -> list[dict]:
    """Every finished run directory below `root`, newest last."""
    out = []
    for result in sorted(root.rglob("result.json")):
        try:
            out.append({"dir": result.parent,
                        "data": json.loads(result.read_text(encoding="utf-8"))})
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda r: r["data"].get("started_utc") or "")
    return out


def _latest_run_for(runs: list[dict], model_id: str) -> Optional[dict]:
    matching = [r for r in runs
                if (r["data"].get("model") or {}).get("id") == model_id]
    return matching[-1] if matching else None


def collect(runs_roots: list[Path], registry: Optional[dict] = None) -> dict:
    """Read every suite record and run directory, and decide one row per model.

    Nothing here consults a human-maintained list of what works. The registry
    supplies the ROWS; the test output supplies every RESULT.
    """
    registry = registry or json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
    models = registry.get("models", [])

    suites: list[Suite] = []
    runs: list[dict] = []
    for root in runs_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for suite_file in sorted(root.rglob("suite.json")):
            try:
                suites.append(Suite.load(suite_file))
            except (OSError, json.JSONDecodeError):
                continue
        runs.extend(_runs_under(root))

    tier2_tests: dict[str, dict] = {}
    for suite in suites:
        for test in suite.by_marker("tier2"):
            model_id = _model_id_from_nodeid(test["nodeid"])
            if model_id:
                tier2_tests[model_id] = test

    rows = [_row_for(model, tier2_tests, runs) for model in models]
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
        "suites": suites,
        "tier1": _tier1_summary(suites),
        "unverified_here": _unverified(suites),
    }


def _row_for(model: dict, tier2_tests: dict[str, dict], runs: list[dict]) -> Row:
    row = Row(model=model)
    model_id = row.model_id
    test = tier2_tests.get(model_id)
    run = _latest_run_for(runs, model_id)

    if test is None:
        # Tier 2 never ran this model. Tier 1 may have run all day; it still
        # says nothing about an airframe.
        row.result, row.reason = UNTESTED, "not flown by tier 2"
    else:
        row.result = FROM_TEST_OUTCOME.get(test.get("outcome", ""), UNTESTED)
        if row.result is UNTESTED or row.result == UNTESTED:
            row.reason = (test.get("reason") or "").strip().split("\n")[0][:160]
        if row.result == PASSED:
            row.tier = "tier 2"

    if run is not None:
        data = run["data"]
        # Claims are read from the run whether the row passed or failed. A
        # failed model still verified something — it took off and then did not
        # land — and hiding that would leave the reader with less than the run
        # record actually holds.
        row.claims = claims_of(data)
        row.procedures = [p.get("procedure", "?") for p in data.get("procedures", [])
                          if p.get("procedure")]
        # De-duplicate while keeping order: a retried procedure appears twice.
        row.procedures = list(dict.fromkeys(row.procedures))
        row.advisories = data.get("advisory_count")
        row.failure = data.get("failure") or (
            lambda f: f.as_dict() if f else None)(failurelib.classify_run(data))
        row.last_run = data.get("started_utc") or ""
        row.firmware = ((data.get("build") or {}).get("text") or "").strip()
        if row.result == PASSED and data.get("flaky"):
            row.result = FLAKY
        # `no-procedure` demotes a PASS to `untested`: the run asserted
        # nothing, so it proved nothing.
        #
        # It must NOT touch a failure. A model that never reached pre-arm also
        # never ran a procedure, so its run record says `no-procedure` too —
        # and an earlier version of this let that overwrite the verdict, so
        # swan_k1_hwing appeared as `untested` when tier 2 had flown it and
        # watched it fail. Reporting a failure as "not yet verified" is the
        # same class of untruth this table exists to remove, pointed the other
        # way.
        if row.result == PASSED and data.get("status") == "no-procedure":
            row.result, row.reason = UNTESTED, "no procedure matched this airframe"
        if row.result in (PASSED, FLAKY, FAILED):
            row.tier = "tier 2"
    return row


def _tier1_summary(suites: list[Suite]) -> dict:
    """What tier 1 verified — deliberately reported without any model name."""
    tests = [t for s in suites for t in s.by_marker("tier1")]
    if not tests:
        return {}
    counts: dict[str, int] = {}
    for test in tests:
        counts[test["outcome"]] = counts.get(test["outcome"], 0) + 1
    environments = sorted({s.environment for s in suites if s.by_marker("tier1")})
    when = sorted(s.generated_utc for s in suites if s.by_marker("tier1"))
    return {"counts": counts, "total": len(tests),
            "environments": environments, "generated_utc": when[-1] if when else "",
            "failed": sorted(t["nodeid"] for t in tests
                             if t["outcome"] in ("failed", "error"))}


def _unverified(suites: list[Suite]) -> list[dict]:
    """Tests that could only be exercised elsewhere, and so were not."""
    out = []
    for suite in suites:
        for test in suite.by_marker("container_only"):
            if test.get("outcome") == "skipped":
                out.append({"nodeid": test["nodeid"], "environment": suite.environment,
                            "reason": (test.get("reason") or "").strip()[:160]})
    return out


# --------------------------------------------------------------------- render
def _cell(text: str) -> str:
    return (text or "—").replace("|", r"\|")


def render(data: dict, workflow: str = "", run_url: str = "") -> str:
    rows: list[Row] = data["rows"]
    tally: dict[str, int] = {}
    for row in rows:
        tally[row.result] = tally.get(row.result, 0) + 1

    produced = workflow or "an unrecorded workflow"
    lines = [
        "# Model verification status",
        "",
        "<!-- GENERATED FILE — DO NOT EDIT BY HAND.",
        f"     Produced by: {produced}",
        f"     Generated:   {data['generated_utc']}",
        "     Source:      runs/**/suite.json and the run directories beside them.",
        "     Regenerate:  python3 -m argazui status --runs runs --out docs/status.md",
        "     Any edit here is overwritten by the next CI run. -->",
        "",
        f"Generated by `{produced}` at **{data['generated_utc']}**"
        + (f" ([run]({run_url}))" if run_url else "") + ".",
        "",
        "**This table is machine output.** No entry in it is a human assertion. "
        "`untested` means *not yet verified by a machine* — it does not mean "
        "broken, and it does not mean working.",
        "",
        "| Model | Class | Launch method | Procedures | Result | Why | "
        "Advisories | Last run (UTC) | Firmware | Tier |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: (RESULTS.index(r.result), r.model_id)):
        result = f"**{row.result}**" if row.result in (FAILED, FLAKY) else row.result
        note = f"{result}<br><sub>{row.reason}</sub>" if row.reason else result
        # The category, not the message. "acceptance" and "environment" send a
        # reader to two different files, and that is the whole reason this
        # column exists rather than a longer sentence in the one before it.
        why = "—"
        if row.failure:
            why = (f"`{row.failure.get('category')}`"
                   f"<br><sub>{_cell(row.failure.get('code', ''))}</sub>")
        lines.append(
            f"| `{row.model_id}` | {_cell(row.model.get('vehicle_class'))} "
            f"| `{_cell(row.model.get('method'))}` "
            f"| {_cell(', '.join(f'`{p}`' for p in row.procedures))} "
            f"| {note} "
            f"| {why} "
            f"| {row.advisories if row.advisories is not None else '—'} "
            f"| {_cell(row.last_run)} "
            f"| {_cell(row.firmware)} "
            f"| {_cell(row.tier)} |")

    lines += ["", "Totals: " + ", ".join(
        f"**{tally.get(name, 0)}** {name}" for name in RESULTS) + ".", ""]

    categories: dict[str, int] = {}
    for row in rows:
        if row.failure:
            key = row.failure.get("category", "")
            categories[key] = categories.get(key, 0) + 1
    if categories:
        lines += [
            "Failures by category: " + ", ".join(
                f"**{count}** {failurelib.label_for(name)} (`{name}`)"
                for name, count in sorted(categories.items())) + ".",
            "",
            "Only `acceptance` is a verdict about an aircraft. The others say "
            "the simulation, the tooling or the evidence went wrong — see "
            "[failure-classification.md](failure-classification.md).",
            "",
        ]

    # ------------------------------------------------------------- tier 1
    tier1 = data.get("tier1") or {}
    lines += ["## What tier 1 verified", ""]
    if not tier1:
        lines.append("No tier-1 suite record was available when this was generated.")
    else:
        counts = ", ".join(f"{n} {k}" for k, n in sorted(tier1["counts"].items()))
        lines += [
            f"{tier1['total']} tests, {counts} — in "
            f"{', '.join(tier1['environments'])}, at {tier1['generated_utc']}.",
            "",
            "Tier 1 flies SITL's own generic frames. It verifies that the right "
            "procedure is chosen for an airframe, that acceptance criteria are "
            "evaluated against measured state, that the server and the page work "
            "in a browser, and that a complete run directory comes out.",
            "",
            "**It verifies nothing about any model above.** That is why a model "
            "tier 2 has not flown stays `untested` no matter how green tier 1 is.",
        ]
        if tier1.get("failed"):
            lines += ["", "Failing tier-1 tests:", ""]
            lines += [f"- `{nodeid}`" for nodeid in tier1["failed"]]
    lines.append("")

    # ------------------------------------------------------ what was verified
    lines += _claims_section(rows)

    # ------------------------------------------------- environment-restricted
    unverified = data.get("unverified_here") or []
    if unverified:
        lines += ["## Not verified in the environment that ran", "",
                  "These tests can only be exercised elsewhere, so they were "
                  "skipped rather than passed:", ""]
        for item in unverified:
            lines.append(f"- `{item['nodeid']}` — skipped in {item['environment']}"
                         + (f": {item['reason']}" if item["reason"] else ""))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


CLAIM_MARK = {CLAIM_PASSED: "passed", CLAIM_FAILED: "**failed**",
              CLAIM_UNEVALUATED: "*not evaluated*"}


def _claims_section(rows: list[Row]) -> list[str]:
    """What each model actually proved, one claim at a time.

    Deliberately separate from the table. A table row is a summary and reads
    like a property of the aircraft; a claim names the one procedure or the one
    criterion behind it, and is the granularity at which this project is
    willing to say something was verified.
    """
    with_claims = [row for row in rows if row.claims]
    lines = ["## What was actually verified", ""]
    if not with_claims:
        lines += ["No run record available when this was generated, so there is "
                  "nothing to claim.", ""]
        return lines

    lines += [
        "Every row below is one thing a machine observed, and the run that "
        "observed it. **Anything not listed here was not verified** — not by "
        "this project, and not by the table above. In particular, no model has "
        "been flown through a mission, in wind, at the edges of its envelope, "
        "or repeatedly enough to say anything about reliability.",
        "",
    ]
    for row in sorted(with_claims, key=lambda r: r.model_id):
        runs = sorted({claim.run_id for claim in row.claims if claim.run_id})
        lines += [
            f"### `{row.model_id}` — {row.claims_passed} of {len(row.claims)} "
            f"claim(s) passed",
            "",
            f"Evidence: {', '.join(f'`{r}`' for r in runs) or '—'}",
            "",
            "| Claim | Kind | Procedure | Result |",
            "|---|---|---|---|",
        ]
        for claim in row.claims:
            detail = f"<br><sub>{_cell(claim.detail)}</sub>" if claim.detail else ""
            lines.append(
                f"| {_cell(claim.subject)}{detail} | {claim.kind} "
                f"| `{_cell(claim.procedure)}` "
                f"| {CLAIM_MARK.get(claim.result, claim.result)} |")
        lines.append("")
    return lines


SUMMARY_START = "<!-- STATUS-SUMMARY: generated by argazui status; do not edit between the markers -->"
SUMMARY_END = "<!-- /STATUS-SUMMARY -->"


def summary_line(data: dict) -> str:
    """One sentence for the README, counted rather than claimed."""
    tally: dict[str, int] = {}
    for row in data["rows"]:
        tally[row.result] = tally.get(row.result, 0) + 1
    counts = ", ".join(f"**{tally.get(name, 0)}** {name}"
                       for name in RESULTS if tally.get(name))
    return (f"*Verification status: {counts} of {len(data['rows'])} models "
            f"([docs/status.md](docs/status.md), generated "
            f"{data['generated_utc']}).*")


def update_readme(readme: Path, data: dict) -> bool:
    """Rewrite the marked block in README.md. Returns True if it changed.

    Markers rather than a whole generated README: the rest of that file is
    prose a person maintains, and only the one line that makes a factual claim
    about support is machine-written.
    """
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return False
    if SUMMARY_START not in text or SUMMARY_END not in text:
        return False
    head, rest = text.split(SUMMARY_START, 1)
    _, tail = rest.split(SUMMARY_END, 1)
    updated = f"{head}{SUMMARY_START}\n{summary_line(data)}\n{SUMMARY_END}{tail}"
    if updated == text:
        return False
    readme.write_text(updated, encoding="utf-8")
    return True


def generate(runs_roots: list[Path], out: Path, workflow: str = "",
             run_url: str = "", readme: Optional[Path] = None) -> str:
    data = collect([Path(r) for r in runs_roots])
    text = render(data, workflow=workflow, run_url=run_url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    if readme is not None:
        update_readme(Path(readme), data)
    return text
