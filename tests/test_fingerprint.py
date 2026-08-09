"""The environment fingerprint: what it records, and what it refuses to guess.

WHY THE REFUSALS ARE THE POINT
------------------------------
A manifest that quietly omits a field it could not determine reads exactly like
one taken on a machine where that component was fine. Every comparison built on
top of it then rests on an absence nobody can see. So the tests below spend
most of their effort on the unknown path: the field must be `null`, the reason
must be recorded, and the comparison layer must treat it as a difference rather
than as a match.

Needs no vehicle; the `tier1` marker only says which CI job runs them.
"""
from __future__ import annotations

import json

import pytest

from argazui import fingerprint as fp

pytestmark = pytest.mark.tier1


PROCEDURE = {"id": "copter_takeoff", "schema": 2, "file": "copter_takeoff.yaml",
             "text": "schema: 2\nid: copter_takeoff\n"}


def test_a_capture_names_every_component_it_could_identify():
    manifest = fp.capture(model={"id": "iris", "name": "Iris"},
                          procedures=[PROCEDURE],
                          firmware="ArduCopter V4.6.0 (0b38722b)")
    assert manifest["schema"] == fp.SCHEMA
    assert manifest["argaz"]["version"]
    assert manifest["ardupilot"]["firmware"] == "ArduCopter V4.6.0"
    assert manifest["ardupilot"]["firmware_commit"] == "0b38722b"
    assert manifest["runtime"]["python"]
    assert manifest["model"]["id"] == "iris"
    assert manifest["procedures"][0]["id"] == "copter_takeoff"
    assert manifest["procedures"][0]["schema"] == 2
    assert manifest["procedure_hash"].startswith("sha256:")
    assert manifest["config"]["runs_root"]


def test_an_undeterminable_field_is_null_and_carries_its_reason(monkeypatch):
    """"unknown" is an answer. A missing key is not."""
    monkeypatch.setattr(fp, "_VERSION_CACHE", {})
    monkeypatch.setattr(fp, "command_version", lambda *a, **k: ("", "unavailable: no gz"))
    monkeypatch.delenv("ROS_DISTRO", raising=False)

    manifest = fp.capture(model={"id": "iris"}, procedures=[PROCEDURE])
    assert manifest["gazebo"]["version"] is None
    assert manifest["ros"]["distro"] is None

    unknown = {item["field"]: item["reason"] for item in manifest["unknown"]}
    assert "no gz" in unknown["gazebo.version"]
    assert "ROS_DISTRO" in unknown["ros.distro"]


def test_a_run_with_no_procedure_says_that_rather_than_hashing_nothing_quietly():
    manifest = fp.capture(model={"id": "iris"}, procedures=[])
    assert [i["field"] for i in manifest["unknown"] if i["field"] == "procedures"]
    assert manifest["procedures"] == []


def test_a_missing_firmware_string_is_recorded_as_unknown_with_the_usual_cause():
    """A vehicle that never armed writes no log to carry a firmware string."""
    manifest = fp.capture(model={"id": "iris"}, procedures=[PROCEDURE], firmware="")
    reasons = {i["field"]: i["reason"] for i in manifest["unknown"]}
    assert "LOG_DISARMED" not in reasons.get("ardupilot.firmware", "")  # not the claim
    assert "never armed" in reasons["ardupilot.firmware"]
    assert manifest["ardupilot"]["firmware"] is None


# ------------------------------------------------------------------- hashing
def test_the_procedure_hash_follows_the_text_that_actually_ran():
    """Not the file on disk, which may already have been edited."""
    one = fp.capture(procedures=[PROCEDURE])["procedure_hash"]
    edited = fp.capture(procedures=[{**PROCEDURE, "text": PROCEDURE["text"] + "# x\n"}])
    assert edited["procedure_hash"] != one


def test_the_procedure_hash_is_stable_regardless_of_execution_order():
    """Takeoff-then-land and land-then-takeoff are the same set of procedures."""
    other = {"id": "copter_land", "schema": 1, "file": "copter_land.yaml",
             "text": "schema: 1\nid: copter_land\n"}
    forward = fp.capture(procedures=[PROCEDURE, other])["procedure_hash"]
    backward = fp.capture(procedures=[other, PROCEDURE])["procedure_hash"]
    assert forward == backward


def test_two_procedures_swapping_files_do_not_collide():
    """The id is hashed alongside the text, so the pairing itself is covered."""
    a = {"id": "one", "schema": 1, "file": "one.yaml", "text": "AAA"}
    b = {"id": "two", "schema": 1, "file": "two.yaml", "text": "BBB"}
    swapped_a = {**a, "text": "BBB"}
    swapped_b = {**b, "text": "AAA"}
    assert (fp.capture(procedures=[a, b])["procedure_hash"]
            != fp.capture(procedures=[swapped_a, swapped_b])["procedure_hash"])


def test_the_model_hash_covers_its_parameter_files(tmp_path):
    """A changed .param changes the aircraft without changing any commit."""
    params = tmp_path / "iris.param"
    params.write_text("Q_ENABLE,1\n", encoding="utf-8")
    model = {"id": "iris", "param_file": [str(params)]}

    before = fp.capture(model=model)["model"]["config_hash"]
    params.write_text("Q_ENABLE,0\n", encoding="utf-8")
    after = fp.capture(model=model)["model"]["config_hash"]
    assert before != after, "editing a parameter file did not change the model hash"


def test_a_parameter_file_the_model_names_but_does_not_have_is_reported(tmp_path):
    manifest = fp.capture(model={"id": "iris",
                                 "param_file": [str(tmp_path / "gone.param")]})
    assert any(i["field"] == "model.param_file" for i in manifest["unknown"])


# ---------------------------------------------------------------- comparison
def test_differences_name_the_field_and_what_it_means():
    left = {"model": {"config_hash": "a"}, "procedure_hash": "p",
            "ardupilot": {"commit": "c", "firmware_commit": "f"}}
    right = json.loads(json.dumps(left))
    right["ardupilot"]["commit"] = "different"

    found = fp.differences(left, right)
    assert [d["field"] for d in found] == ["ardupilot.commit"]
    assert found[0]["reason"] == "changed"
    assert "ArduPilot" in found[0]["what"]


def test_identical_fingerprints_produce_no_differences():
    left = {"model": {"config_hash": "a"}, "procedure_hash": "p",
            "ardupilot": {"commit": "c", "firmware_commit": "f"}}
    assert fp.differences(left, json.loads(json.dumps(left))) == []


def test_an_unknown_field_counts_as_a_difference():
    """Not a claim that they differ — a statement that nothing shows they match."""
    left = {"model": {"config_hash": "a"}, "procedure_hash": "p",
            "ardupilot": {"commit": None, "firmware_commit": "f"}}
    right = {"model": {"config_hash": "a"}, "procedure_hash": "p",
             "ardupilot": {"commit": "c", "firmware_commit": "f"}}
    found = fp.differences(left, right)
    assert [d["field"] for d in found] == ["ardupilot.commit"]
    assert found[0]["reason"] == "unknown on at least one side"


def test_a_run_recorded_before_fingerprints_reads_as_empty_rather_than_failing(tmp_path):
    assert fp.read(tmp_path) == {}


def test_write_then_read_round_trips(tmp_path):
    manifest = fp.capture(model={"id": "iris"}, procedures=[PROCEDURE])
    fp.write(tmp_path, manifest)
    assert fp.read(tmp_path)["procedure_hash"] == manifest["procedure_hash"]


@pytest.mark.parametrize("dotted,expected", [
    ("ardupilot.commit", "c"),
    ("model.config_hash", "a"),
    ("nothing.here", None),
    ("ardupilot.commit.deeper", None),
])
def test_field_lookup_tolerates_what_is_not_there(dotted, expected):
    manifest = {"model": {"config_hash": "a"}, "ardupilot": {"commit": "c"}}
    assert fp.field(manifest, dotted) == expected
