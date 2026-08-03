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
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import paths

SCHEMA = 1

PASSED, FAILED, FLAKY, UNTESTED = "passed", "failed", "flaky", "untested"
RESULTS = (PASSED, FAILED, FLAKY, UNTESTED)

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
class Row:
    model: dict
    result: str = UNTESTED
    reason: str = ""
    procedures: list[str] = field(default_factory=list)
    advisories: Optional[int] = None
    last_run: str = ""
    firmware: str = ""
    tier: str = ""

    @property
    def model_id(self) -> str:
        return self.model.get("id", "?")


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
        row.procedures = [p.get("procedure", "?") for p in data.get("procedures", [])
                          if p.get("procedure")]
        # De-duplicate while keeping order: a retried procedure appears twice.
        row.procedures = list(dict.fromkeys(row.procedures))
        row.advisories = data.get("advisory_count")
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
        "| Model | Class | Launch method | Procedures | Result | Advisories | "
        "Last run (UTC) | Firmware | Tier |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: (RESULTS.index(r.result), r.model_id)):
        result = f"**{row.result}**" if row.result in (FAILED, FLAKY) else row.result
        note = f"{result}<br><sub>{row.reason}</sub>" if row.reason else result
        lines.append(
            f"| `{row.model_id}` | {_cell(row.model.get('vehicle_class'))} "
            f"| `{_cell(row.model.get('method'))}` "
            f"| {_cell(', '.join(f'`{p}`' for p in row.procedures))} "
            f"| {note} "
            f"| {row.advisories if row.advisories is not None else '—'} "
            f"| {_cell(row.last_run)} "
            f"| {_cell(row.firmware)} "
            f"| {_cell(row.tier)} |")

    lines += ["", "Totals: " + ", ".join(
        f"**{tally.get(name, 0)}** {name}" for name in RESULTS) + ".", ""]

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


def generate(runs_roots: list[Path], out: Path, workflow: str = "",
             run_url: str = "") -> str:
    data = collect([Path(r) for r in runs_roots])
    text = render(data, workflow=workflow, run_url=run_url)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
