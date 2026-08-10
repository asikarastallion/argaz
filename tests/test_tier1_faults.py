"""Tier 1 — a fault actually injected into a real SITL, and cleared again.

WHAT A GREEN RUN HERE MEANS
---------------------------
The mechanism works against a real ArduPilot: the parameter exists, the write
is accepted, the aircraft is degraded for the window the scenario declared, and
the value is put back afterwards. The run record separates the injected
condition from the vehicle's response from the verdict.

WHAT IT DOES NOT MEAN
---------------------
Nothing about any Gazebo model. These are SITL's own generic frames, so
`docs/status.md` never marks a model verified from anything here — the same
rule the nominal tier-1 tests live under.

It also does not mean "a multirotor handles GPS loss". It means *this* frame,
on *this* firmware, with the criteria in `copter_gps_loss.yaml`, did what that
file says it must. The claim is exactly as wide as the criteria and no wider.
"""
from __future__ import annotations

import pytest

from argazui import faults, procedures as procs
from argazui.procrunner import ProcedureRunner

from support import boot, read_result

pytestmark = pytest.mark.tier1

QUAD = {
    "id": "sitl_quad_scenario", "name": "SITL quad frame", "vehicle_class": "Copter",
    "method": "sitl_frame", "vehicle": "ArduCopter", "frame": "quad",
}


def _explain(result: dict) -> str:
    lines = [f"{result['procedure']} -> {result['outcome']}: {result['text']}"]
    for step in result["steps"]:
        lines.append(f"  [{step['status']:7s}] {step['label']} — {step['text']}")
    for fault in result.get("faults") or []:
        lines.append(f"  fault {fault['id']}: applied={fault['applied']} "
                     f"cleared={fault['cleared']} passed={fault['passed']} "
                     f"held={fault['held_s']}s — {fault['text']}")
        for judged in fault["expect"] + fault["recovery"]:
            lines.append(f"      [{'OK' if judged['passed'] else 'FAIL'}] "
                         f"{judged['label']} — {judged['text']}")
    for expect in result["expect"]:
        lines.append(f"  expect [{'OK' if expect['passed'] else 'FAIL'}] "
                     f"{expect['label']} — {expect['text']}")
    return "\n".join(lines)


def _run_scenario(request, runs_root, scenario_id: str) -> tuple[dict, object]:
    vehicle = boot(request, runs_root, QUAD, QUAD["frame"])
    assert vehicle.wait_prearm(), (
        f"the quad frame never passed pre-arm checks\n{vehicle.sitl.tail()}")
    scenario = procs.get(scenario_id)
    assert scenario is not None, f"{scenario_id} is not in argazui/procedures/"

    runner = ProcedureRunner(vehicle.link, on_event=vehicle.recorder.event)
    result = runner.run(scenario, scenario.default_values())
    vehicle.recorder.add_procedure(scenario, result,
                                   values=scenario.default_values())
    return result, vehicle


# --------------------------------------------------------------- GPS loss
def test_gps_loss_is_injected_held_and_restored(request, runs_root):
    """The mechanism, end to end, on the aircraft's own parameters."""
    result, vehicle = _run_scenario(request, runs_root, "copter_gps_loss")
    assert result["faults"], f"no fault was recorded\n{_explain(result)}"
    fault = result["faults"][0]

    assert fault["applied"] is True, (
        f"the scenario ran without its fault — that is a nominal flight "
        f"wearing the wrong name\n{_explain(result)}")
    assert fault["cleared"] is True, (
        f"the GPS was left degraded\n{_explain(result)}")
    assert fault["injected_at_s"], "the injection was not timestamped"
    assert fault["held_s"] > 0, "the fault was never actually held"

    # The mechanism is recorded well enough to reproduce the run, not just
    # named: which parameter, to what, and what it was before.
    assert fault["changed"], f"nothing was recorded as changed\n{fault}"
    for name, record in fault["changed"].items():
        assert name.startswith("SIM_GPS")
        assert record["restore_to"] is not None
        assert record["restored"] is True

    # And the aircraft's own state agrees: the parameter is back.
    for name, record in fault["changed"].items():
        current = vehicle.link.submit(
            lambda l, n=name: {"ok": True, "value": l._param_get(n)},
            timeout=8.0, label=f"check {name}").get("value")
        assert current == pytest.approx(float(record["restore_to"])), (
            f"{name} is {current}, not the {record['restore_to']} it was before")


def test_the_gps_loss_verdict_comes_from_the_criteria(request, runs_root):
    """A fault that was successfully injected is not a pass.

    The verdict has to be the conjunction of the declared criteria and nothing
    else — including the recovery criteria, which are judged after the GPS is
    back.
    """
    result, _ = _run_scenario(request, runs_root, "copter_gps_loss")
    fault = result["faults"][0]
    judged = fault["expect"] + fault["recovery"]
    assert judged, f"no criterion was evaluated\n{_explain(result)}"

    if fault["evidence_missing"]:
        assert fault["passed"] is False, (
            "a fault whose evidence never arrived reported a pass")
    else:
        assert fault["passed"] == all(j["passed"] for j in judged), (
            f"the verdict does not follow from the criteria\n{_explain(result)}")

    # The evidence the scenario declared has to have actually arrived, or the
    # criteria were judged against a state nothing wrote to.
    assert fault["evidence_required"] == ["attitude"]
    assert not fault["evidence_missing"], (
        f"attitude telemetry never arrived, so nothing here was judged"
        f"\n{_explain(result)}")

    assert result["outcome"] == "passed", _explain(result)


def test_the_run_record_carries_the_scenario_and_its_fault(request, runs_root):
    """The evidence chain a scenario leaves behind, checked as a whole."""
    result, vehicle = _run_scenario(request, runs_root, "copter_gps_loss")
    assert result["outcome"] in ("passed", "failed"), _explain(result)

    vehicle.link.stop()
    vehicle.sitl.stop()
    vehicle.recorder.finish(report=False)
    stored = read_result(vehicle.recorder)

    assert stored["schema"] == 4
    recorded = stored["procedures"][0]["result"]["faults"]
    assert recorded and recorded[0]["id"] == "gps_off_in_hover"
    assert recorded[0]["fault"] == faults.GPS_LOSS

    # The declaration is in the fingerprint for a reader, and the `failures:`
    # block is inside the procedure text the procedure hash covers.
    manifest = stored["fingerprint"]
    assert manifest["scenario"]["faults"], "the fingerprint records no scenario"
    assert manifest["scenario"]["faults"][0]["id"] == "gps_off_in_hover"
    assert manifest["procedure_hash"]

    # And the archived YAML is the file that ran, verbatim — the single-source
    # rule, which a scenario must not be an exception to.
    scenario = (vehicle.recorder.dir / "scenario.yaml").read_text(encoding="utf-8")
    assert "failures:" in scenario and "gps_off_in_hover" in scenario


# ---------------------------------------------------------- link interruption
def test_the_link_interruption_is_survived_and_the_link_comes_back(request, runs_root):
    """The one fault whose criteria cannot be judged while it is happening.

    Every criterion in `copter_link_loss.yaml` is a `recovery:` one, so a pass
    here means ArgazUI heard the aircraft again and found it where it left it —
    which is the only thing a ground station can honestly assert about a
    blackout.
    """
    result, vehicle = _run_scenario(request, runs_root, "copter_link_loss")
    fault = result["faults"][0]

    assert fault["applied"] is True, _explain(result)
    assert fault["cleared"] is True, _explain(result)
    assert not fault["expect"], (
        "this scenario declares no criteria for the blackout window; judging "
        "any would mean judging the last state that arrived before it")
    assert fault["recovery"], _explain(result)

    assert "heartbeat" in fault["evidence_required"]
    assert not fault["evidence_missing"], (
        f"the link never came back, so nothing was judged\n{_explain(result)}")
    assert result["outcome"] == "passed", _explain(result)

    # The fault is a flag in this process and must not outlive the procedure.
    assert vehicle.link.link_fault is None, "the link was left degraded"
