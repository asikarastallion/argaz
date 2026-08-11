"""Tier 1 — the two fault mechanisms nothing had ever executed.

WHY THIS FILE EXISTS
--------------------
`gps_degradation` and `mavlink_degradation` have been in `faults.KINDS` since
v1.4 with unit tests behind them, and no scenario named either, so nothing
could point them at an aircraft. The v1.6 audit recorded that as F-19 and the
mechanism coverage matrix reported both as DEFINED — declared in code and
unreachable from any procedure.

`copter_gps_degradation.yaml` and `copter_link_degradation.yaml` made them
executable. This file is what makes them EXERCISED and then VERIFIED, and the
distinction is the whole point: a mechanism is not verified because it exists,
and it is not verified because a scenario names it. It is verified when a
recorded flight injected it, the aircraft responded, a criterion judged the
response, and the run directory can be opened to check.

WHAT EACH TEST PROVES, IN THE ORDER §9 OF THE v1.7 BRIEF ASKS FOR
-----------------------------------------------------------------
    1 the fault starts                  `applied`, `injected_at_s`
    2 the condition is observable       `changed` / `link_fault`, read back
    3 the expected response occurs      the criteria the scenario declared
    4 a criterion evaluates it          `expect` + `recovery`, `evaluated`
    5 evidence is generated             the run directory and its manifest
    6 the verdict is correct            `passed` == all(criteria)
    7 cleanup restores the environment  `cleared`, and the parameter read back

WHAT IT DOES NOT PROVE
----------------------
Nothing about any Gazebo model — these are SITL's own generic frames, the same
rule every tier-1 test lives under. And nothing about multirotors in general:
it is *this* frame, on *this* firmware, against the criteria in those two YAML
files, and the claim is exactly as wide as the criteria.
"""
from __future__ import annotations

import pytest

from argazui import procedures as procs
from argazui.procrunner import ProcedureRunner

from support import boot, read_result

pytestmark = pytest.mark.tier1

QUAD = {
    "id": "sitl_quad_degradation", "name": "SITL quad frame",
    "vehicle_class": "Copter", "method": "sitl_frame",
    "vehicle": "ArduCopter", "frame": "quad",
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


def _fly(request, runs_root, scenario_id: str):
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


def _assert_fault_is_verified(result: dict, fault: dict) -> None:
    """The six properties that separate EXERCISED from VERIFIED.

    Shared because they are the same six for both mechanisms — which is itself
    the argument for asserting them here rather than trusting each scenario to
    have been written carefully.
    """
    # 1 — the fault started.
    assert fault["applied"] is True, (
        f"the scenario ran without its fault, which is a nominal flight "
        f"wearing an off-nominal name\n{_explain(result)}")
    assert fault["injected_at_s"], "the injection was not timestamped"
    assert fault["held_s"] > 0, "the fault was never actually held"

    # 4 — criteria evaluated it, and were not merely present.
    judged = fault["expect"] + fault["recovery"]
    assert judged, f"no criterion was evaluated\n{_explain(result)}"
    assert not fault["evidence_missing"], (
        f"the criteria rest on telemetry that never arrived, so the verdict "
        f"means nothing\n{_explain(result)}")

    # 6 — the verdict follows from the criteria and from nothing else. This is
    # the rule that stops "the fault was injected" becoming "the aircraft
    # handled it", and it is asserted rather than assumed.
    assert fault["passed"] == all(j["passed"] for j in judged), (
        f"the verdict does not follow from the criteria\n{_explain(result)}")

    # 7 — cleanup restored the environment.
    assert fault["cleared"] is True, (
        f"the simulator was left degraded after the run\n{_explain(result)}")


# ------------------------------------------------------------ gps_degradation
def test_gps_degradation_is_injected_judged_and_restored(request, runs_root):
    """`gps_degradation` against a real ArduPilot, end to end.

    The mechanism writes SIM_GPS1_NUMSATS and SIM_GPS1_FIXTYPE (or the older
    family, whichever this firmware exposes), so the injected CONDITION is
    readable back off the vehicle rather than merely asserted here — which is
    what makes step 2 of the list in the module docstring a measurement.
    """
    result, vehicle = _fly(request, runs_root, "copter_gps_degradation")
    assert result["faults"], f"no fault was recorded\n{_explain(result)}"
    fault = result["faults"][0]
    _assert_fault_is_verified(result, fault)

    # 2 — the condition is observable: which parameter, to what, and what it
    # was before. A fault that cannot say what it changed cannot be reproduced.
    assert fault["changed"], f"nothing was recorded as changed\n{fault}"
    for name, record in fault["changed"].items():
        assert name.startswith("SIM_GPS"), name
        assert record["restore_to"] is not None, (
            f"{name} was unreadable before the write, so nothing can be put "
            f"back and the run says so rather than claiming a restore")
        assert record["restored"] is True

    # 7 again, from the aircraft's own answer rather than from our record.
    for name, record in fault["changed"].items():
        current = vehicle.link.submit(
            lambda l, n=name: {"ok": True, "value": l._param_get(n)},
            timeout=8.0, label=f"check {name}").get("value")
        assert current == pytest.approx(float(record["restore_to"])), (
            f"{name} is {current}, not the {record['restore_to']} it was before")

    # 3 and 6 — the aircraft did what the scenario says it must.
    assert result["outcome"] == "passed", _explain(result)


def test_a_degraded_fix_is_not_the_same_mechanism_as_a_lost_one(request, runs_root):
    """The two GPS scenarios inject different things, and the record says so.

    Worth asserting because the failure mode is silent: a degradation whose
    knobs did not exist would fall back to nothing, the flight would be nominal,
    and the run would read as a passing off-nominal scenario. `faults.py`
    refuses that at probe time ("nothing would be degraded"), and this is the
    flight-level check that the refusal is not needed because the mechanism is
    really doing something different from `gps_loss`.
    """
    result, _ = _fly(request, runs_root, "copter_gps_degradation")
    fault = result["faults"][0]
    assert fault["fault"] == "gps_degradation"

    changed = set(fault["changed"])
    # gps_loss writes the enable parameter. Degradation must not.
    assert not any(name.endswith(("_ENABLE", "_DISABLE")) for name in changed), (
        f"a degradation switched the receiver off; that is gps_loss\n{changed}")
    assert changed, "a degradation that changed no parameter degraded nothing"


# -------------------------------------------------------- mavlink_degradation
def test_link_degradation_is_injected_judged_and_lifted(request, runs_root):
    """`mavlink_degradation` against a real ArduPilot, end to end.

    The one fault in the catalogue whose window can be judged from inside
    itself: three received messages in four still arrive, so `for` and `never`
    criteria have samples to work with. `copter_link_loss` cannot do this and
    says why in its own header.
    """
    result, vehicle = _fly(request, runs_root, "copter_link_degradation")
    assert result["faults"], f"no fault was recorded\n{_explain(result)}"
    fault = result["faults"][0]
    _assert_fault_is_verified(result, fault)
    assert fault["fault"] == "mavlink_degradation"

    # 4 — and specifically, judged DURING the window. This is the property
    # that distinguishes this scenario from copter_link_loss, whose criteria
    # are all `recovery:` ones because there is no telemetry mid-blackout.
    assert fault["expect"], (
        f"every criterion was deferred to recovery, so nothing was measured "
        f"while the link was degraded — which is the one thing this scenario "
        f"exists to do\n{_explain(result)}")

    # 7 — the link fault must not outlive the procedure. The runner clears it
    # from a `finally` and `MavlinkLink.stop` clears it again; if either had
    # failed, whatever runs next in this process would be silently degraded.
    assert vehicle.link._link_fault is None, (
        "the link was left degraded after the scenario finished")

    assert result["outcome"] == "passed", _explain(result)


# ------------------------------------------------------------------ evidence
def test_a_degradation_run_leaves_the_evidence_its_verdict_rests_on(request,
                                                                    runs_root):
    """5 — evidence is generated, and it names the mechanism that was used.

    A verdict whose evidence is missing is not a verdict, and a scenario that
    passed without archiving what it did is indistinguishable from one that
    never ran. Checked through the ordinary artefacts, because a special path
    for scenarios would be a second source of truth.
    """
    result, vehicle = _fly(request, runs_root, "copter_gps_degradation")
    vehicle.recorder.finish(wait=True)
    record = read_result(vehicle.recorder)
    assert record, "the run wrote no result.json"

    # The declared scenario is in the fingerprint, so a reader knows this run
    # was off-nominal without opening the procedure.
    manifest = record.get("fingerprint") or {}
    declared = (manifest.get("scenario") or {}).get("faults") or []
    assert declared, "the fingerprint records no scenario"
    assert declared[0]["id"] == "gps_degraded_in_hover", declared

    # And the YAML that ran is archived verbatim — the single-source rule,
    # which a scenario must not be an exception to.
    scenario = (vehicle.recorder.dir / "scenario.yaml").read_text(encoding="utf-8")
    assert "failures:" in scenario
    assert "gps_degradation" in scenario
    assert "gps_degraded_in_hover" in scenario

    # The result document carries the injected condition, not only the verdict.
    recorded = record["procedures"][-1]["result"]["faults"][0]
    assert recorded["fault"] == "gps_degradation"
    assert recorded["applied"] is True
    assert recorded["changed"], "the run record does not say what was changed"
