"""F-16 — the regression layer has a consumer, and it keeps its five answers.

WHAT THIS FILE HAS TO PROVE, FROM §8 OF THE v1.7 BRIEF
------------------------------------------------------
    * CI distinguishes PASS / FAIL / ERROR / SKIPPED / NOT_APPLICABLE
    * a test-infrastructure error is NOT read as a vehicle acceptance failure
    * a real verification failure is capable of blocking a release
    * the evidence answers: what was tested, with what configuration, and why
      did CI decide as it did

The regression logic itself has been right since v1.3 and is tested in
`test_regression.py`. This file is about the layer above it — the one the audit
found had no consumer at all — so every test here is about the GATE's
arithmetic and semantics, not about whether a delta is computed correctly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argazui import failures, regression

pytestmark = pytest.mark.tier1


# ------------------------------------------------------------ run directories
def _fingerprint(**over) -> dict:
    base = {
        "model": {"config_hash": "sha256:model"},
        "procedure_hash": "sha256:proc",
        "ardupilot": {"commit": "a" * 40, "firmware_commit": "b" * 40,
                      "dirty_digest": "clean"},
        "gazebo": {"version": "Gazebo Sim, version 8.14.0"},
        "sitl_models": {"pin": {"identity": "sha256:models"}},
    }
    for dotted, value in over.items():
        node = base
        parts = dotted.split("__")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return base


def _metric(key: str, value, procedure="copter_takeoff") -> dict:
    return {"key": key, "identity": [key, procedure], "procedure": procedure,
            "value": value, "unit": "s", "clock": "vehicle",
            "window": "procedure", "detail": ""}


def _write_run(directory: Path, model: str, run_id: str, metrics: list,
               fingerprint=None, started="20260101T000000Z") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({
        "schema": 6, "run_id": run_id, "status": "passed",
        "started_utc": started,
        "model": {"id": model},
        "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                        "result": {"outcome": "passed", "steps": [],
                                   "faults": [], "expect": []}}],
        "metrics": metrics,
        "fingerprint": fingerprint if fingerprint is not None else _fingerprint(),
    }, indent=2), encoding="utf-8")
    return directory


@pytest.fixture
def workspace(tmp_path: Path):
    runs = tmp_path / "runs"
    baselines = tmp_path / "baselines"
    runs.mkdir()
    baselines.mkdir()
    return runs, baselines


# ------------------------------------------------------------------- PASS
def test_a_run_matching_its_baseline_passes(workspace):
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base", [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 10.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_PASS
    assert document["exit_code"] == 0
    assert document["blocks_release"] is False


# ------------------------------------------------------------------- FAIL
def test_a_degraded_metric_fails_and_may_block_a_release(workspace):
    """The point of the whole layer: a degradation now has a consumer."""
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base", [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 40.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_FAIL
    assert document["exit_code"] == 1
    assert document["blocks_release"] is True, (
        "a measured degradation cannot block a release, so the gate is "
        "decorative")
    row = document["models"][0]
    assert row["degraded"], "the gate failed without naming what degraded"


def test_a_failing_gate_names_the_model_that_degraded(workspace):
    """A red build that does not say which model is a red build nobody can act
    on."""
    runs, baselines = workspace
    for model, value in (("quad", 10.0), ("plane", 10.0)):
        _write_run(baselines / model, model, f"base_{model}",
                   [_metric("time_to_target_alt", value)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 40.0)], started="20260102T000000Z")
    _write_run(runs / "20260102T000000Z_plane", "plane", "20260102T000000Z_plane",
               [_metric("time_to_target_alt", 10.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_FAIL
    failing = [r["model_id"] for r in document["models"]
               if r["outcome"] == regression.GATE_FAIL]
    passing = [r["model_id"] for r in document["models"]
               if r["outcome"] == regression.GATE_PASS]
    assert failing == ["quad"]
    assert passing == ["plane"]


# ------------------------------------------------------------------ ERROR
def test_incomparable_runs_are_an_error_and_not_a_regression(workspace):
    """A test-infrastructure problem must not be read as a vehicle failure.

    Two runs whose fingerprints do not line up have not shown that anything got
    worse. The audit's own reasoning for `compare`'s exit code 2 applies to the
    gate unchanged, and this is the assertion that it survived the aggregation.
    """
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 10.0)],
               fingerprint=_fingerprint(ardupilot__commit="c" * 40),
               started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_ERROR
    assert document["exit_code"] == 2
    assert document["blocks_release"] is False, (
        "an infrastructure error was allowed to block a release as though it "
        "were an aircraft verdict")
    row = document["models"][0]
    assert row["verdict"] == regression.NOT_COMPARABLE
    # And it keeps the classification the taxonomy gives it.
    assert row["failure"]["category"] == failures.EVIDENCE
    assert row["failure"]["category"] != failures.ACCEPTANCE


def test_an_unreadable_baseline_is_an_error_with_its_reason(workspace):
    runs, baselines = workspace
    broken = baselines / "quad"
    broken.mkdir(parents=True)
    (broken / "result.json").write_text("{ this is not json", encoding="utf-8")
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 10.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_ERROR
    assert document["models"][0]["detail"], "an error was reported with no reason"


def test_a_degradation_outranks_an_error_from_another_model(workspace):
    """FAIL beats ERROR deliberately.

    A measured degradation is a fact about an aircraft, and burying it under
    "one of the other models had an unreadable baseline" would lose the
    finding — which is the more expensive mistake of the two.
    """
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 40.0)], started="20260102T000000Z")
    broken = baselines / "plane"
    broken.mkdir(parents=True)
    (broken / "result.json").write_text("nonsense", encoding="utf-8")
    _write_run(runs / "20260102T000000Z_plane", "plane", "20260102T000000Z_plane",
               [_metric("time_to_target_alt", 10.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_FAIL


# --------------------------------------------------------------- SKIPPED
def test_no_runs_at_all_is_skipped_and_never_pass(workspace):
    """A job that flew nothing has verified nothing.

    Reporting PASS here is the false green the whole project is a reaction to:
    a silent evaporation of tier-2 evidence would look like a clean build.
    """
    runs, baselines = workspace
    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_SKIPPED
    assert document["outcome"] != regression.GATE_PASS
    assert document["exit_code"] == 0


# --------------------------------------------------------- NOT_APPLICABLE
def test_a_model_with_no_committed_baseline_is_not_applicable(workspace):
    """Not an error and not a pass. There was nothing to compare against.

    Kept separate so a project adding its first baselines is not either failing
    CI or being told everything is fine.
    """
    runs, baselines = workspace
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 10.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    assert document["outcome"] == regression.GATE_NOT_APPLICABLE
    assert document["exit_code"] == 0
    assert document["blocks_release"] is False
    assert "no baseline" in document["models"][0]["detail"]


def test_the_five_outcomes_are_all_distinct_and_all_have_an_exit_code():
    assert len(set(regression.GATE_OUTCOMES)) == 5
    for outcome in regression.GATE_OUTCOMES:
        assert outcome in regression.GATE_EXIT, outcome
    # Only a real degradation and a broken comparison fail the job.
    failing = {o for o in regression.GATE_OUTCOMES if regression.GATE_EXIT[o]}
    assert failing == {regression.GATE_FAIL, regression.GATE_ERROR}
    # And they do not share a code, so a pipeline can tell them apart.
    assert regression.GATE_EXIT[regression.GATE_FAIL] != \
        regression.GATE_EXIT[regression.GATE_ERROR]


# ---------------------------------------------------------------- evidence
def test_the_gate_writes_the_ordinary_comparison_into_each_run(workspace):
    """Reuse of the evidence architecture, not a CI reporting ecosystem.

    Every pair the gate judges leaves the same `regression.json` a human
    running `argazui compare` would produce, in the run directory, so the
    evidence for a gate decision is an ordinary artefact.
    """
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    run_dir = _write_run(runs / "20260102T000000Z_quad", "quad",
                         "20260102T000000Z_quad",
                         [_metric("time_to_target_alt", 10.0)],
                         started="20260102T000000Z")
    regression.gate(runs, baselines)
    assert (run_dir / "regression.json").is_file()
    assert (run_dir / "regression.md").is_file()


def test_the_gate_document_answers_what_was_tested_and_why_it_decided(workspace,
                                                                      tmp_path):
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 40.0)], started="20260102T000000Z")

    document = regression.gate(runs, baselines)
    as_json, as_text = regression.write_gate(tmp_path, document)
    text = as_text.read_text(encoding="utf-8")

    # what was tested
    assert "quad" in text
    assert "20260102T000000Z_quad" in text
    # with what configuration
    assert str(baselines) in text and str(runs) in text
    # and why it decided
    assert regression.GATE_FAIL in text
    assert "blocks a release" in text
    # machine-readable, for whatever consumes it next
    assert json.loads(as_json.read_text(encoding="utf-8"))["outcome"] == \
        regression.GATE_FAIL


def test_the_newest_run_per_model_is_the_one_compared(workspace):
    """A job that retried a model must not compare its first attempt.

    Sorted by run id, which starts with a UTC timestamp — file mtimes do not
    survive an artefact upload and cannot be used.
    """
    runs, baselines = workspace
    _write_run(baselines / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    _write_run(runs / "20260102T000000Z_quad", "quad", "20260102T000000Z_quad",
               [_metric("time_to_target_alt", 40.0)], started="20260102T000000Z")
    _write_run(runs / "20260103T000000Z_quad", "quad", "20260103T000000Z_quad",
               [_metric("time_to_target_alt", 10.0)], started="20260103T000000Z")

    document = regression.gate(runs, baselines)
    assert document["models"][0]["run_id"] == "20260103T000000Z_quad"
    assert document["outcome"] == regression.GATE_PASS


def test_a_committed_baseline_is_not_itself_treated_as_a_run(workspace):
    """Baselines live under the runs root in CI, and comparing one with itself
    would report a permanent, meaningless PASS."""
    runs, baselines = workspace
    inner = runs / regression.BASELINES_DIRNAME
    _write_run(inner / "quad", "quad", "base",
               [_metric("time_to_target_alt", 10.0)])
    document = regression.gate(runs, inner)
    assert document["outcome"] == regression.GATE_SKIPPED
