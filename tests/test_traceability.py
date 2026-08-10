"""Identifiers exist, links resolve, and the chain says which are only positional.

WHY A TRACEABILITY SCHEME NEEDS ITS OWN TESTS
---------------------------------------------
It degrades silently. A criterion loses its id, a metric names a procedure the
run never flew, an evidence reference points at a file that was pruned — and
every one of those still renders a table that looks perfectly correct. Nothing
goes red, nobody notices, and the chain quietly becomes decoration.

So the integrity check is the feature, and these are its tests.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argazui import procedures as procs, trace

pytestmark = pytest.mark.tier1


def criterion(**overrides) -> dict:
    base = {"label": "reached altitude", "condition": {}, "passed": True,
            "text": "", "kind": "eventually", "duration": None,
            "criterion_id": "copter_takeoff#alt-reached", "declared_id": True}
    base.update(overrides)
    return base


def step(**overrides) -> dict:
    base = {"index": 0, "kind": "set_mode", "label": "Switch to GUIDED",
            "status": "passed", "text": "", "seconds": 0.2,
            "step_id": "copter_takeoff#s1"}
    base.update(overrides)
    return base


def run(**overrides) -> dict:
    base = {
        "run_id": "20260810T120000Z_sitl_quad",
        "status": "passed",
        "test_id": "tests/test_x.py::test_y",
        "model": {"id": "sitl_quad"},
        "procedures": [{
            "procedure": "copter_takeoff", "role": "takeoff",
            "result": {"outcome": "passed", "steps": [step()],
                       "expect": [criterion()], "faults": []},
        }],
        "metrics": [{"key": "time_to_target_alt", "procedure": "copter_takeoff",
                     "value": 12.0, "unit": "s",
                     "metric_id": "time_to_target_alt@copter_takeoff"}],
        "evidence": {"complete": True},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------- identifiers
def test_a_declared_id_is_used_and_a_missing_one_is_derived():
    assert trace.criterion_id("copter_takeoff", 0, "alt-reached") == \
        "copter_takeoff#alt-reached"
    assert trace.criterion_id("copter_takeoff", 1, None) == "copter_takeoff#c2"
    assert trace.step_id("copter_takeoff", 2, None) == "copter_takeoff#s3"
    assert trace.step_id("copter_takeoff", 2, "arm") == "copter_takeoff#arm"


def test_a_derived_id_says_it_is_derived():
    """The distinction a reader matching two runs actually needs.

    A derived id would change if somebody inserted a line above it; a declared
    one would not. An identifier whose stability the reader cannot see is worse
    than one they can.
    """
    assert trace.is_derived("copter_takeoff#c2") is True
    assert trace.is_derived("copter_takeoff#s11") is True
    assert trace.is_derived("copter_takeoff#alt-reached") is False
    # A declared id that merely starts with s or c is not derived.
    assert trace.is_derived("copter_takeoff#climb") is False


def test_an_identifier_splits_back_into_its_parts():
    assert trace.split("copter_takeoff#alt-reached") == \
        ("copter_takeoff", "alt-reached")
    assert trace.split("nothing") == ("nothing", "")


def test_a_metric_id_names_its_procedure_only_when_it_has_one():
    assert trace.metric_id("peak_angular_rate") == "peak_angular_rate"
    assert trace.metric_id("time_to_target_alt", "copter_takeoff") == \
        "time_to_target_alt@copter_takeoff"


@pytest.mark.parametrize("bad", ["Alt-Reached", "alt reached", "alt#reached",
                                 "", "a" * 49, 7, None])
def test_a_malformed_declared_id_is_refused(bad):
    """An id is quoted in tables, URLs and shell commands.

    One that needs escaping in any of them is one that will be got wrong
    somewhere, so it is refused at load time rather than sanitised.
    """
    with pytest.raises(trace.TraceError):
        trace.check_declared(bad, "x.yaml")


# ---------------------------------------------------------------- the chain
def test_the_chain_runs_from_intent_to_evidence():
    chain = trace.chain(run())
    assert chain["test_id"] == "tests/test_x.py::test_y"
    assert chain["verdict"] == "passed"
    assert chain["procedures"][0]["procedure_id"] == "copter_takeoff"
    assert chain["procedures"][0]["steps"][0]["step_id"] == "copter_takeoff#s1"
    assert chain["procedures"][0]["criteria"][0]["criterion_id"] == \
        "copter_takeoff#alt-reached"
    assert chain["metrics"][0]["metric_id"] == "time_to_target_alt@copter_takeoff"
    assert chain["procedures"][0]["metric_ids"] == \
        ["time_to_target_alt@copter_takeoff"]


def test_a_run_nothing_asserts_says_so_rather_than_leaving_it_blank():
    """"Flown by hand" is a real answer, and the one that matters most."""
    chain = trace.chain(run(test_id=None))
    assert chain["test_id"] == trace.BY_HAND


def test_only_the_last_attempt_of_a_procedure_is_in_the_chain():
    """A retry buys `flaky`, not two chains for one intent."""
    document = run(procedures=[
        {"procedure": "copter_takeoff", "role": "takeoff", "attempt": 1,
         "result": {"outcome": "failed", "steps": [], "expect": [], "faults": []}},
        {"procedure": "copter_takeoff", "role": "takeoff", "attempt": 2,
         "result": {"outcome": "passed", "steps": [step()],
                    "expect": [criterion()], "faults": []}},
    ])
    chain = trace.chain(document)
    assert len(chain["procedures"]) == 1
    assert chain["procedures"][0]["verdict"] == "passed"


def test_a_criterion_that_was_never_reached_is_not_marked_evaluated():
    """Coverage rests on this: a criterion nobody reached covers nothing."""
    chain = trace.chain(run(procedures=[{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "failed", "steps": [], "faults": [],
                   "expect": [criterion(passed=False,
                                        text="not evaluated — the procedure "
                                             "stopped earlier")]},
    }]))
    assert chain["procedures"][0]["criteria"][0]["evaluated"] is False


def test_a_turkish_not_evaluated_message_is_recognised_too():
    """The run record stores the message in the language the flight was flown in."""
    chain = trace.chain(run(procedures=[{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "failed", "steps": [], "faults": [],
                   "expect": [criterion(passed=False,
                                        text="degerlendirilmedi — prosedur "
                                             "daha once durdu")]},
    }]))
    assert chain["procedures"][0]["criteria"][0]["evaluated"] is False


# ------------------------------------------------------------- integrity
def test_a_sound_chain_reports_no_problems():
    document = run()
    assert trace.integrity(document) == []


def test_a_metric_scoped_to_a_procedure_the_run_never_flew_is_dangling():
    document = run(metrics=[{"key": "time_to_target_alt",
                             "procedure": "plane_takeoff", "value": 1.0,
                             "metric_id": "time_to_target_alt@plane_takeoff"}])
    problems = trace.integrity(document)
    assert any(p["problem"] == "dangling-link" for p in problems)
    assert "plane_takeoff" in problems[0]["detail"]


def test_a_criterion_whose_id_names_another_procedure_is_dangling():
    document = run(procedures=[{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "passed", "steps": [], "faults": [],
                   "expect": [criterion(criterion_id="plane_takeoff#alt-reached")]},
    }])
    problems = trace.integrity(document)
    assert any(p["problem"] == "dangling-link" for p in problems)


def test_two_criteria_sharing_an_identifier_are_reported():
    document = run(procedures=[{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "passed", "steps": [], "faults": [],
                   "expect": [criterion(), criterion()]},
    }])
    assert any(p["problem"] == "duplicate-id" for p in trace.integrity(document))


def test_a_chain_naming_an_artefact_the_manifest_does_not_list_is_reported():
    """The chain must not point at evidence nobody can open."""
    document = run(evidence={"artefacts": [
        {"path": "result.json", "exists": True},
        {"path": "report.md", "exists": False},
    ]})
    document["evidence"]["artefacts"].append({"path": "gone.json", "exists": True})
    chain = trace.chain(document)
    # The chain lists what the manifest says is present; break the manifest
    # underneath it and the mismatch has to surface.
    document["evidence"]["artefacts"] = [
        {"path": "result.json", "exists": True}]
    problems = trace.integrity(document, chain)
    assert any(p["problem"] == "missing-evidence" for p in problems)


def test_a_run_with_no_verdict_cannot_attach_anything_to_a_result():
    problems = trace.integrity(run(status=None))
    assert any(p["problem"] == "missing-verdict" for p in problems)


def test_derived_ids_are_listed_so_a_reader_knows_which_are_positional():
    document = run(procedures=[{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "passed", "faults": [],
                   "steps": [step(step_id="")],
                   "expect": [criterion(criterion_id="")]},
    }])
    derived = trace.derived_ids(trace.chain(document))
    assert derived == ["copter_takeoff#s1", "copter_takeoff#c1"]


# ------------------------------------------------------- the shipped files
def test_every_shipped_criterion_declares_its_own_identifier():
    """A criterion is quoted OUTSIDE its own run — in the coverage report, in
    the "what was not tested" list, in a comparison of two runs months apart.
    Those need a name that survives somebody inserting a criterion above it.
    """
    derived = []
    for pid, procedure in sorted(procs.load_all(force=True).items()):
        for index, expectation in enumerate(procedure.expect):
            identifier = trace.criterion_id(pid, index, expectation.id)
            if trace.is_derived(identifier):
                derived.append(identifier)
    assert derived == [], (
        f"these shipped criteria have no declared id: {derived}")


def test_declared_identifiers_are_unique_within_a_procedure():
    for pid, procedure in sorted(procs.load_all(force=True).items()):
        declared = [e.id for e in procedure.expect if e.id]
        assert len(declared) == len(set(declared)), f"{pid} reuses a criterion id"


def test_a_duplicate_declared_id_is_refused_at_load_time():
    body = """\
schema: 4
id: dupe
name: {en: X, tr: X}
sources: [https://example.invalid/doc]
applies_to: {role: takeoff}
steps:
  - set_mode: GUIDED
expect:
  - id: same
    condition: {armed: true}
  - id: same
    condition: {alt_above: 1}
"""
    with pytest.raises(procs.ProcedureError) as exc:
        procs.parse(body, Path("dupe.yaml"))
    assert "same" in str(exc.value)


def test_trace_identifiers_need_schema_4():
    """The version moves rather than being extended in place — the same rule
    schema 2 and 3 were introduced under."""
    body = """\
schema: 3
id: early
name: {en: X, tr: X}
sources: [https://example.invalid/doc]
applies_to: {role: takeoff}
steps:
  - set_mode: GUIDED
expect:
  - id: too-early
    condition: {armed: true}
"""
    with pytest.raises(procs.ProcedureError, match="schema 4"):
        procs.parse(body, Path("early.yaml"))
