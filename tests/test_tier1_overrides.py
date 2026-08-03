"""Tier 1 — declared parameter overrides, including the failure path.

The rule these tests defend: a procedure may change the vehicle's
configuration only if it declared the change with a reason, and the change is
undone when the procedure ends — *however* it ends. Until v1.1 phase 4 the
"however it ends" half had never actually been executed, because every
procedure that had been flown happened to succeed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argazui import procedures as procs
from argazui.procrunner import ProcedureRunner

from support import boot

pytestmark = pytest.mark.tier1

PLANE = {
    "id": "sitl_plane_overrides", "name": "SITL plane frame (override tests)",
    "vehicle_class": "Plane", "method": "sitl_frame",
    "vehicle": "ArduPlane", "frame": "plane",
}

SELFTEST = Path(__file__).parent / "procedures" / "selftest_override_restore.yaml"


def _read_param(link, name: str) -> float:
    value = link.submit(lambda l: {"ok": True, "value": l._param_get(name)},
                        timeout=10.0, label=f"read {name}")["value"]
    assert value is not None, f"{name} could not be read from the vehicle"
    return value


def test_override_is_restored_after_a_mid_procedure_failure(request, runs_root):
    """The procedure aborts half way through; the parameter still goes back.

    This is the path that matters most and was never exercised: a takeoff that
    fails must not leave the aircraft configured differently from how it was
    found, or the next attempt is running on a vehicle the operator did not
    configure.
    """
    vehicle = boot(request, runs_root, PLANE, PLANE["frame"])
    procedure = procs.parse(SELFTEST.read_text(encoding="utf-8"), SELFTEST)

    before = _read_param(vehicle.link, "TKOFF_ALT")
    assert before != 123, (
        "the test's sentinel value is the vehicle's real value; pick another")

    runner = ProcedureRunner(vehicle.link, on_event=vehicle.recorder.event)
    result = runner.run(procedure, {})
    vehicle.recorder.add_procedure(procedure, result, values={})

    # The procedure must have failed — if it passed, the test proves nothing.
    assert result["outcome"] == "failed", (
        f"the self-test procedure was supposed to fail, got {result['outcome']}: "
        f"{result['text']}")

    record = result["params_changed"]["TKOFF_ALT"]
    assert record["applied"] is True, "the override was never applied"
    assert record["set_to"] == 123
    assert record["restore_to"] == before
    assert record["restored"] is True, (
        f"TKOFF_ALT was not restored after the failure: {record}")

    after = _read_param(vehicle.link, "TKOFF_ALT")
    assert after == before, (
        f"the vehicle still reports TKOFF_ALT={after}, expected {before}. "
        f"A failed procedure left the aircraft reconfigured.")


def test_override_reason_reaches_the_run_record(request, runs_root):
    """The justification is recorded, not just the value.

    An override whose reason lives only in a YAML comment is invisible in the
    artefacts, and the artefacts are what someone reads six months later.
    """
    vehicle = boot(request, runs_root, PLANE, PLANE["frame"])
    procedure = procs.parse(SELFTEST.read_text(encoding="utf-8"), SELFTEST)

    runner = ProcedureRunner(vehicle.link, on_event=vehicle.recorder.event)
    result = runner.run(procedure, {})
    vehicle.recorder.add_procedure(procedure, result, values={})

    record = result["params_changed"]["TKOFF_ALT"]
    assert "123" in record["reason"] or "recognisable" in record["reason"], record

    flattened = vehicle.recorder.overrides()
    assert any(item["param"] == "TKOFF_ALT" and item["reason"]
               for item in flattened), flattened


def test_shipped_procedures_declare_every_parameter_they_write():
    """No SITL needed: the validator is the guarantee, so check it holds.

    `load_all` runs the strict parser over every shipped procedure. A
    `set_param` for an undeclared parameter, or an override without a reason,
    raises here rather than in flight.
    """
    loaded = procs.load_all(force=True)
    assert loaded, "no procedures were loaded"

    for procedure in loaded.values():
        declared = {o.param for o in procedure.overrides}
        for step in procedure.steps:
            if step.kind == "set_param":
                name = str(step.value["name"]).upper()
                assert name in declared, (
                    f"{procedure.id} writes {name} without declaring it")
        for override in procedure.overrides:
            assert override.reason_text("en"), (
                f"{procedure.id}: override of {override.param} has no English reason")
            assert override.reason_text("tr"), (
                f"{procedure.id}: override of {override.param} has no Turkish reason")
