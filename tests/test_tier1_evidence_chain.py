"""Procedure -> run -> evidence -> metric -> regression, on a real SITL.

WHAT THIS TEST IS FOR
---------------------
Every stage of v1.3 has its own unit tests, and they all use evidence built by
hand. That is the right way to pin an evaluator down, and it leaves exactly one
thing unproven: that the stages are actually connected to each other. A metric
computed from a hand-written altitude series proves nothing about whether
`RunRecorder` hands `flightlog.py` the context it needs, or whether the numbers
that come out reach `result.json` in the shape `regression.py` reads.

So this flies one real procedure on a real SITL binary and follows the evidence
all the way to a comparison verdict.

WHAT IT CLAIMS, AND WHAT IT DOES NOT
------------------------------------
The **flight** is real: a real `arducopter`, the same YAML the TAKEOFF button
runs, through the same `ProcedureRunner`. The **baseline** is not a second
flight — it is a second, independent analysis of the same archived evidence,
written into its own run directory. That is deliberate and it is stated here
rather than buried: flying twice would double the tier-1 budget to prove
something the unit tests already prove better.

So this test claims the *wiring* is right, in both directions:

  * identical evidence compares as `unchanged`, with a `passed` verdict;
  * evidence that genuinely differs compares as `degraded`, with a `regressed`
    verdict and a non-zero delta.

It claims nothing about the aircraft. Tier 1 never does.
"""
from __future__ import annotations

import json
import shutil

import pytest

from argazui import procedures as procs
from argazui import regression, runs as runlib

from support import boot
from test_tier1_procedures import FRAMES, run_procedure

pytestmark = pytest.mark.tier1

QUAD = FRAMES[0]
TARGET_ALT = 15.0


def _archived_run(request, runs_root):
    """One real takeoff, closed the way STOP closes it, with its report built."""
    vehicle = boot(request, runs_root, QUAD, QUAD["frame"])
    assert vehicle.wait_prearm(), vehicle.sitl.tail()

    takeoff = procs.select("takeoff", vehicle.capabilities)
    assert takeoff is not None
    result = run_procedure(vehicle, takeoff, {"alt": TARGET_ALT})
    assert result["outcome"] == "passed", json.dumps(result, indent=2)[:2000]

    # Same order as the UI's STOP: the dataflash log is only closed when the
    # process exits, and `wait=True` is what makes the report exist before this
    # test looks for it.
    vehicle.link.stop()
    vehicle.sitl.stop()
    vehicle.recorder.finish(wait=True)
    return vehicle.recorder.dir


def _derive_baseline(source, runs_root, run_id="20260101T000000Z_sitl_quad"):
    """A second, independent analysis of the same archived evidence.

    Not a second flight. The point is that `flightlog` -> `metrics` ->
    `result.json` runs again from scratch over a real dataflash log, so the
    comparison that follows is reading two documents that were produced by the
    pipeline rather than written by this test.
    """
    target = runs_root / run_id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    # The copy has to say who it is, or the comparison would report the
    # original run's id on both sides.
    stored = json.loads((target / "result.json").read_text(encoding="utf-8"))
    stored["run_id"] = run_id
    stored["started_utc"] = "2026-01-01T00:00:00Z"
    (target / "result.json").write_text(json.dumps(stored, indent=2) + "\n",
                                        encoding="utf-8")

    outcome = runlib.regenerate_report(run_id, root=runs_root)
    assert outcome["ok"], outcome
    return target


def test_a_flight_becomes_evidence_becomes_metrics_becomes_a_verdict(request, runs_root):
    directory = _archived_run(request, runs_root)

    # ------------------------------------------------------------- evidence
    for name in ("result.json", "report.json", "report.md", "fingerprint.json"):
        assert (directory / name).is_file(), f"{name} is missing from {directory}"

    stored = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert stored["schema"] == runlib.RESULT_SCHEMA

    # -------------------------------------------------------------- metrics
    measured = {m["key"]: m for m in stored["metrics"] if m["value"] is not None}
    assert "time_to_target_alt" in measured, (
        f"the climb to {TARGET_ALT:g} m produced no time-to-target metric; "
        f"the run's context did not reach flightlog. All metrics: "
        f"{json.dumps(stored['metrics'], indent=2)}")
    assert "peak_angular_rate" in measured, "no IMU-derived metric came out of the log"
    assert measured["time_to_target_alt"]["procedure"] == "copter_takeoff", (
        "a procedure-scoped metric lost the procedure it belongs to")
    assert measured["time_to_target_alt"]["unit"] == "s"

    # ---------------------------------------------------------- fingerprint
    manifest = stored["fingerprint"]
    assert manifest["procedure_hash"].startswith("sha256:")
    assert manifest["procedures"][0]["id"] == "copter_takeoff"
    from argazui.procedures import SCHEMA_VERSION
    assert manifest["procedures"][0]["schema"] == SCHEMA_VERSION, (
        "the executed procedure's declared schema did not reach the manifest")

    # ----------------------------------------------------------- comparison
    baseline_dir = _derive_baseline(directory, runs_root)
    baseline = regression.load_run(baseline_dir)
    current = regression.load_run(directory)

    comparison = regression.compare(baseline, current)
    assert comparison["verdict"] == regression.PASSED, json.dumps(
        comparison["compatibility"], indent=2)
    assert not comparison["compatibility"]["configuration_drift"], (
        "two analyses of the same evidence disagreed about the environment")

    compared = [row for row in comparison["metrics"]
                if row["verdict"] != regression.INCOMPARABLE]
    assert compared, "nothing was actually compared; every metric was skipped"
    assert all(row["verdict"] == regression.UNCHANGED for row in compared), (
        "identical evidence produced a change: "
        + json.dumps([r for r in compared if r["verdict"] != regression.UNCHANGED],
                     indent=2))

    # ------------------------------------------------ and it can go red, too
    # The same real evidence, with one measured number moved past its
    # threshold. A chain that can only ever report "unchanged" would satisfy
    # every assertion above and be worthless.
    worse = json.loads(json.dumps(current))
    for row in worse["metrics"]:
        if row["key"] == "peak_angular_rate" and row["value"] is not None:
            row["value"] = float(row["value"]) * 3.0 + 50.0
            break
    else:
        pytest.fail("no peak_angular_rate to perturb; the log carried no IMU records")

    regressed = regression.compare(baseline, worse)
    assert regressed["verdict"] == regression.REGRESSED
    assert "peak_angular_rate" in regressed["degraded"]
    row = next(r for r in regressed["metrics"] if r["key"] == "peak_angular_rate")
    assert row["delta"] > 0 and row["relative"] > 0

    # The comparison is written beside the run, as `argazui compare` writes it.
    as_json, as_text = regression.write(directory, regressed)
    assert json.loads(as_json.read_text(encoding="utf-8"))["verdict"] == "regressed"
    assert "REGRESSION" in as_text.read_text(encoding="utf-8")


def test_the_report_states_the_metrics_and_the_environment(request, runs_root):
    """The human-readable artefact carries the same facts as the JSON.

    A report that quietly lost a section would leave the machine-readable
    record right and every person reading the run wrong.
    """
    directory = _archived_run(request, runs_root)
    report = (directory / "report.md").read_text(encoding="utf-8")

    # The ten reviewer-oriented sections, in order. Asserted as a sequence
    # rather than by membership: the ORDER is the contract — a reviewer
    # reading two runs must not have to hunt for the same fact in two places.
    sections = [
        "## 1. Scope", "## 2. Configuration", "## 3. Procedure",
        "## 4. Verdict", "## 5. Failed criteria",
        "## 6. Quantitative metrics", "## 7. Evidence manifest",
        "## 8. Environment", "## 9. Regression comparison",
        "## 10. Limitations and non-claims",
    ]
    positions = []
    for heading in sections:
        assert heading in report, f"{heading} is missing from the report"
        positions.append(report.index(heading))
    assert positions == sorted(positions), "the report's sections are out of order"

    assert "measurements, not criteria" in report
    assert "Model configuration" in report and "sha256:" in report
    # Advisories and metrics must stay visibly separate: one has thresholds
    # from ArduPilot's documentation, the other deliberately has none.
    assert "### Advisories" in report
    assert report.index("### Advisories") < report.index("### Metrics")

    # Section 10 is the one a verification document is least likely to have.
    tail = report[report.index("## 10. Limitations and non-claims"):]
    assert "verification" in tail and "validation" in tail
    assert "would behave this way in the air" in tail, (
        "the report does not say that a simulation is not evidence about "
        "hardware")
    assert "One run is one run" in tail

    # Section 7 has to be able to say the evidence is incomplete, so it must
    # actually be rendered from the manifest rather than described in prose.
    manifest = report[report.index("## 7. Evidence manifest"):
                      report.index("## 8. Environment")]
    assert "result.json" in manifest and "fingerprint.json" in manifest
    assert "Produced by" in manifest
