"""Shared fixtures for the ArgazUI regression suite.

WHAT THESE TESTS ARE FOR
------------------------
They run the *same* procedure YAML the UI buttons run, through the *same*
`ProcedureRunner`, against a *real* SITL binary, and they record their results
into the *same* `runs/` directories the UI produces. There is no second
implementation of a takeoff and no simulated autopilot, so a green test means
a working button. That equivalence is the whole reason the suite exists.

TIERS
-----
`tier1`  SITL's own frames, no Gazebo. Verifies procedure logic: capability
         probing picks the right procedure, acceptance criteria are evaluated
         against measured state, declared overrides are applied and restored,
         and a run directory comes out complete and parseable.

         **Tier 1 makes no claim about any Gazebo model.** A green tier-1 run
         does not mean "Skywalker X8 works"; it means the plane procedure works
         on SITL's plane frame. Blurring that would make the status table a
         lie, which is the exact failure this whole version exists to fix.

`tier2`  Gazebo + the real model set. This is the only tier whose results may
         be reported against a model in `docs/status.md`.

SKIPS ARE NOT PASSES
--------------------
Missing binary, missing Gazebo, missing model: the test skips, and the status
generator records the model as `untested`. Nothing here ever reports success
for something it did not fly.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from support import SUITE_REPORT, TEST_RUNS_ROOT      # noqa: F401


def pytest_addoption(parser: pytest.Parser) -> None:
    """Options the suite understands.

    `--regenerate-golden` rewrites the characterisation record in
    tests/golden/. It lives here because pytest reads pytest_addoption from
    conftest files and plugins only — declaring it in the test module that
    uses it silently does nothing.
    """
    parser.addoption(
        "--regenerate-golden", action="store_true", default=False,
        help="rewrite tests/golden/single_vehicle.json from current behaviour")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "tier1: real SITL, no Gazebo — verifies procedure logic only")
    config.addinivalue_line(
        "markers", "tier2: real SITL + Gazebo — the only tier that verifies a model")
    config.addinivalue_line(
        "markers", "container_only: can only be exercised inside the tier image; "
                   "skipped elsewhere and reported as unverified, never as passed")
    # WHY THE FLEET TIERS DO NOT REUSE tier1/tier2
    # --------------------------------------------
    # `status.py` builds the model table from tests carrying the `tier2`
    # marker, taking the model id out of the test's parametrise id. A fleet
    # test marked tier2 would be read as a claim about a model — and the
    # Gazebo-free fleet tier touches no model at all. Separate markers keep
    # "this fleet flew" and "this model works" from ever being the same
    # sentence, which is the same separation tier1/tier2 already enforce.
    config.addinivalue_line(
        "markers", "fleet_sitl: N real SITLs without Gazebo — verifies fleet "
                   "logic (ports, supervisor, teardown) and never a model")
    config.addinivalue_line(
        "markers", "fleet_gazebo: N real SITLs in a real world — the only "
                   "fleet tier that may verify a model")


# --------------------------------------------------------------- suite record
_RESULTS: dict[str, dict] = {}


def _environment_label() -> str:
    """Where this suite ran, in the terms the status table uses."""
    if os.environ.get("ARGAZ_TEST_ENV"):
        return os.environ["ARGAZ_TEST_ENV"]
    if Path("/.dockerenv").exists():
        return "container"
    return "host"


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record every phase, because a skip in setup is still a non-result.

    Collapsing to `report.passed` would count a test skipped during setup —
    which is what an unavailable SITL binary produces — as nothing at all, and
    "nothing at all" is exactly the gap a status table fills in with a guess.
    """
    entry = _RESULTS.setdefault(report.nodeid, {
        "nodeid": report.nodeid, "outcome": "passed", "reason": "",
        "duration": 0.0, "markers": []})
    entry["duration"] += report.duration
    # Every marker the status generator knows about. A marker missing here is
    # recorded as no marker at all, so the test disappears from every summary
    # — which is how the fleet tiers first rendered as "no suite record" after
    # they had actually run.
    entry["markers"] = sorted(
        name for name in ("tier1", "tier2", "fleet_sitl", "fleet_gazebo",
                          "e2e", "container_only")
        if name in report.keywords)

    if report.failed:
        entry["outcome"] = "error" if report.when == "setup" else "failed"
        entry["reason"] = str(report.longrepr)[-2000:] if report.longrepr else ""
    elif report.skipped and entry["outcome"] == "passed":
        entry["outcome"] = "skipped"
        # ("path", lineno, "Skipped: reason") for a skip, a string for an xfail.
        reason = report.longrepr
        entry["reason"] = reason[2] if isinstance(reason, tuple) else str(reason)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    from datetime import datetime, timezone

    tests = sorted(_RESULTS.values(), key=lambda item: item["nodeid"])
    counts: dict[str, int] = {}
    for test in tests:
        counts[test["outcome"]] = counts.get(test["outcome"], 0) + 1
    document = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": _environment_label(),
        "exit_status": int(exitstatus),
        "counts": counts,
        "tests": tests,
    }
    try:
        SUITE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SUITE_REPORT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        # Never fail a suite over its own bookkeeping, but never hide it either.
        print(f"\nCould not write the suite record to {SUITE_REPORT}: {exc}")


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Name what this environment did NOT verify, before anyone reads a total.

    A green summary line is read as "everything works". Tests that can only run
    inside the tier image are skipped on a developer machine, and saying so
    here is the difference between an honest total and a misleading one.
    """
    unverified = [t for t in _RESULTS.values()
                  if "container_only" in t["markers"] and t["outcome"] == "skipped"]
    terminalreporter.write_line("")
    terminalreporter.write_line(
        f"suite record: {SUITE_REPORT} (environment: {_environment_label()})")
    if unverified:
        terminalreporter.write_line(
            f"NOT verified in this environment — only in the tier image "
            f"({len(unverified)}):", yellow=True)
        for test in unverified:
            terminalreporter.write_line(f"  - {test['nodeid']}")


@pytest.fixture(scope="session")
def runs_root() -> Path:
    TEST_RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    return TEST_RUNS_ROOT


