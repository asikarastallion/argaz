"""A run and a report regenerated from it must describe themselves identically.

THE DEFECT THIS FILE EXISTS FOR
-------------------------------
`argazui report <run>` re-analyses an archived flight, months later, from the
evidence in its directory. Everything it writes has to line up with what the
flight itself wrote, because `regression.py` refuses to compare two runs whose
environment fingerprints disagree — and it cannot tell "somebody changed the
firmware" from "our own two code paths disagree about how to hash a file".

They did disagree. The live path hashed the model dict it had in memory and the
YAML as loaded; the regeneration path hashed the trimmed model record from
`result.json` and the YAML with its comment block stripped. Both produced
perfectly plausible hashes, and a regenerated run silently became incomparable
with the flight it was regenerated from.

Nothing about a vehicle is exercised here; the `tier1` marker only says which
CI job runs it.
"""
from __future__ import annotations

import json

import pytest

from argazui import fingerprint as fp
from argazui import procedures as procs
from argazui.runs import MODEL_RECORD_KEYS, RunRecorder, _recorded_procedures

pytestmark = pytest.mark.tier1

MODEL = {
    "id": "sitl_quad", "name": "SITL quad", "vehicle_class": "Copter",
    "method": "sitl_frame", "vehicle": "ArduCopter", "frame": "quad",
    "param_file": [], "world": None, "env": None, "has_ros2": False,
    # Fields a run does not archive. They must not reach the hash, or the
    # regenerated report could never reproduce it.
    "image": "/static/models/quad.png",
    "docs": "https://example.invalid/quad",
}


def _record(tmp_path, procedure) -> RunRecorder:
    recorder = RunRecorder(model=MODEL, root=tmp_path,
                           launch_commands=["# pytest"])
    recorder.add_procedure(procedure, {"outcome": "passed", "values": {"alt": 15},
                                       "steps": [], "expect": []},
                           values={"alt": 15})
    recorder.finish(report=False)
    return recorder


def test_the_recorded_yaml_hashes_the_same_as_the_yaml_that_flew(tmp_path):
    """scenario.yaml has to round-trip to the procedure's own text.

    Procedures begin with their own comment block explaining where the flow
    comes from. An extractor that dropped every `#` line looked correct and
    produced a different digest for the same file.
    """
    procedure = procs.load_all()["copter_takeoff"]
    recorder = _record(tmp_path, procedure)

    result = json.loads((recorder.dir / "result.json").read_text(encoding="utf-8"))
    recovered = _recorded_procedures(recorder.dir, result)

    assert [entry["id"] for entry in recovered] == ["copter_takeoff"]
    assert recovered[0]["schema"] == procedure.schema
    assert fp.normalise(recovered[0]["text"]) == fp.normalise(procedure.raw_text), (
        "the YAML read back out of scenario.yaml is not the YAML that ran")


def test_a_regenerated_fingerprint_matches_the_one_the_flight_wrote(tmp_path):
    procedure = procs.load_all()["copter_takeoff"]
    recorder = _record(tmp_path, procedure)

    flown = fp.read(recorder.dir)
    result = json.loads((recorder.dir / "result.json").read_text(encoding="utf-8"))
    regenerated = fp.capture(
        model=result["model"],
        procedures=_recorded_procedures(recorder.dir, result))

    assert regenerated["procedure_hash"] == flown["procedure_hash"]
    assert regenerated["model"]["config_hash"] == flown["model"]["config_hash"]
    # Nothing may read as *changed*. Fields that are unknown on both sides —
    # here the firmware, because this session produced no dataflash log — are
    # still reported as differences, and that is the correct answer: nothing
    # shows the two match. Only "changed" would mean the code paths disagree.
    assert [d["field"] for d in fp.differences(flown, regenerated)
            if d["reason"] == "changed"] == [], (
        "a run and a report regenerated from it describe themselves differently")


def test_only_the_archived_model_fields_reach_the_hash(tmp_path):
    """A field the run does not store cannot be part of what identifies it.

    Read from `MODEL_RECORD_KEYS` rather than restated, so adding a field to
    the archive cannot leave this test asserting the old set — which is exactly
    what would hide the reverse defect below.
    """
    procedure = procs.load_all()["copter_takeoff"]
    recorder = _record(tmp_path, procedure)
    flown = fp.read(recorder.dir)

    changed = {**MODEL, "image": "/static/models/something-else.png"}
    assert (fp.capture(model={k: changed.get(k) for k in MODEL_RECORD_KEYS},
                       procedures=[])["model"]["config_hash"]
            == flown["model"]["config_hash"])


def test_a_declared_parameter_override_changes_the_configuration_identity():
    """...and a field that changes the AIRCRAFT must be stored.

    `sitl_param_overrides` is written into a second `--add-param-file` at every
    launch: `swan_k1_hwing` gets `EK3_ENABLE=1` that way and
    `alti_transition_quad` gets the `Q_ENABLE=1` upstream's own file omits. It
    was applied and not archived, so two runs flown with different overrides —
    a quadplane and the fixed wing the same file describes without them —
    carried the same `model.config_hash` and compared as one configuration.
    """
    assert "sitl_param_overrides" in MODEL_RECORD_KEYS

    def config_hash(overrides):
        model = {k: MODEL.get(k) for k in MODEL_RECORD_KEYS}
        model["sitl_param_overrides"] = overrides
        return fp.capture(model=model, procedures=[])["model"]["config_hash"]

    on, off, absent = (config_hash({"Q_ENABLE": 1}),
                       config_hash({"Q_ENABLE": 0}),
                       config_hash(None))
    assert on != off, "a changed override did not change the configuration identity"
    assert on != absent, "declaring an override did not change it either"
    assert config_hash({"Q_ENABLE": 1}) == on, "the hash is not stable"


def test_a_retried_procedure_is_hashed_once(tmp_path):
    """The suite is allowed one retry; the same file did not become two."""
    procedure = procs.load_all()["copter_takeoff"]
    recorder = RunRecorder(model=MODEL, root=tmp_path)
    for attempt in (1, 2):
        recorder.add_procedure(procedure,
                               {"outcome": "passed", "values": {}, "steps": [],
                                "expect": []}, values={}, attempt=attempt)
    recorder.finish(report=False)

    manifest = fp.read(recorder.dir)
    assert len(manifest["procedures"]) == 1
    # And both attempts are still in the record — the retry is never hidden.
    result = json.loads((recorder.dir / "result.json").read_text(encoding="utf-8"))
    assert len(result["procedures"]) == 2


def test_a_session_with_no_dataflash_still_leaves_a_fingerprint(tmp_path):
    """A vehicle that never armed writes no log. It still ran on something."""
    recorder = RunRecorder(model=MODEL, root=tmp_path)
    recorder.finish(report=False)

    manifest = fp.read(recorder.dir)
    assert manifest["argaz"]["version"]
    assert any(item["field"] == "procedures" for item in manifest["unknown"])
