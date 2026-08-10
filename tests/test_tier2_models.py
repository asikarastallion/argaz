"""Tier 2 — the real model set, in Gazebo, headless.

WHAT A GREEN ROW HERE MEANS, AND WHY ONLY THIS TIER MAY CLAIM IT
----------------------------------------------------------------
This is the only place a `models.json` entry is ever flown. The launch
commands come from `session.build_launch_commands`, which is what the START
button uses, so a model that passes here is a model whose button works.

Tier 1 flies SITL's own generic frames. It proves the procedure logic and the
application, and it proves nothing whatsoever about an airframe. Reporting a
tier-1 pass against a model name would put back exactly the unearned tick this
version exists to remove, so `docs/status.md` reads model rows from this file
and from nothing else.

THREE THINGS PER MODEL, AND WHY THOSE THREE
-------------------------------------------
Take off, change mode in flight, land. They are the three claims the status
table makes, and each is judged by measured state: an altitude that was
reached, a mode number that came back in a heartbeat, a disarm that happened.
An ACK is never a pass. Since C.0.5 the takeoff also has to have been flown
inside a declared attitude envelope, because "it reached 20 m" turned out to
be true of an aircraft that was tumbling.

SKIPS ARE NOT PASSES
--------------------
No Gazebo, no assets, no procedure for the airframe: the test skips with a
reason and the model is recorded `untested`. A model that boots and then fails
is recorded `failed`. The two are never merged.
"""
from __future__ import annotations

import json
import time

import pytest

from argazui import paths, procedures as procs
from argazui.procrunner import ProcedureRunner, probe_capabilities
from argazui.runs import RunRecorder

import gazebo
from support import TEST_RUNS_ROOT

pytestmark = pytest.mark.tier2


def _models() -> list[dict]:
    if not paths.MODELS_JSON.is_file():
        return []
    return json.loads(paths.MODELS_JSON.read_text()).get("models", [])


MODELS = _models()


def _ids(model: dict) -> str:
    return model["id"]


@pytest.fixture(scope="session")
def tier2_runs_root():
    root = TEST_RUNS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_procedure(recorder: RunRecorder, sim, procedure, values: dict) -> dict:
    """One attempt, then at most one retry — and the retry is never silent.

    Same rule as tier 1: a procedure that only ever works on the second go is
    recorded `flaky` in docs/status.md, not `passed`.
    """
    runner = ProcedureRunner(sim.link, on_event=recorder.event)
    result = runner.run(procedure, values)
    recorder.add_procedure(procedure, result, values=values, attempt=1)
    if result["outcome"] == "passed":
        return result

    recorder.console(
        f"\n[test] {procedure.id} attempt 1 -> {result['outcome']}: "
        f"{result['text']}\n[test] retrying once\n".encode())
    retry = ProcedureRunner(sim.link, on_event=recorder.event).run(procedure, values)
    recorder.add_procedure(procedure, retry, values=values, attempt=2)
    if retry["outcome"] == "passed":
        recorder.mark_flaky(procedure.id,
                            f"attempt 1 {result['outcome']}: {result['text']}")
    return retry


def _explain(result: dict) -> str:
    lines = [f"{result['procedure']} -> {result['outcome']}: {result['text']}"]
    for step in result["steps"]:
        lines.append(f"    [{step['status']:7s}] {step['label']} — {step['text']}")
    for expect in result["expect"]:
        lines.append(f"    expect [{'OK' if expect['passed'] else 'FAIL'}] "
                     f"{expect['label']} — {expect['text']}")
    lines.append(f"    envelope: {json.dumps(result.get('stability'))}")
    return "\n".join(lines)


@pytest.mark.skipif(not MODELS, reason="no models.json in this installation")
@pytest.mark.parametrize("model", MODELS, ids=_ids)
def test_model_takes_off_changes_mode_and_lands(request, tier2_runs_root, model):
    """The three claims, flown, for one registry model."""
    if model.get("method") == "ros2_launch":
        pytest.skip(
            f"{model['id']} launches through ros2, which needs a built "
            f"ardupilot_gz workspace; this image has ROS 2 but not that "
            f"workspace, so the model is untested rather than failed")

    work_dir = paths.RUN_DIR / model["id"]
    recorder = RunRecorder(model=model, root=tier2_runs_root, work_dir=work_dir,
                           launch_commands=gazebo.launch_commands(model),
                           test_id=request.node.nodeid)

    try:
        sim = gazebo.start(model, log_dir=work_dir, on_event=recorder.event,
                           on_log=lambda text: recorder.console(text.encode()))
    except gazebo.GazeboUnavailable as exc:
        recorder.event({"kind": "skipped", "reason": str(exc)})
        recorder.finish(report=False)
        pytest.skip(str(exc))

    request.addfinalizer(lambda: (sim.stop(), recorder.finish(wait=True)))

    assert sim.wait_prearm(), (
        f"{model['id']} never passed pre-arm checks\n{sim.tail()}")

    caps = probe_capabilities(sim.link, vehicle=model.get("vehicle"))
    takeoff = procs.select("takeoff", caps, model)
    landing = procs.select("land", caps, model)
    if takeoff is None or landing is None:
        # A real answer, not an error: `no-procedure` maps to `untested`.
        recorder.event({"kind": "no_procedure", "capabilities": caps})
        pytest.skip(f"{model['id']}: no procedure matches its probed "
                    f"capabilities {caps} — recorded as untested")

    # ------------------------------------------------------------ takeoff
    altitude = 20.0 if caps.get("quadplane") or caps["autopilot"] == "ArduCopter" else 60.0
    result = _run_procedure(recorder, sim, takeoff, {"alt": altitude})
    assert result["outcome"] == "passed", _explain(result)
    assert sim.link.state.armed, "not armed after a passing takeoff"

    # -------------------------------------------------- mode change in flight
    # Verified against the heartbeat, not against the ACK.
    cruise = ("QHOVER" if caps.get("quadplane")
              else "LOITER" if caps["autopilot"] == "ArduCopter" else "LOITER")
    res = sim.link.send(f"mode {cruise}")
    assert res.get("ok"), f"mode {cruise} was rejected: {res.get('text')}"
    deadline = time.time() + 30
    while time.time() < deadline and sim.link.state.mode != cruise:
        time.sleep(0.5)
    assert sim.link.state.mode == cruise, (
        f"the autopilot acknowledged {cruise} but reports "
        f"{sim.link.state.mode} in its heartbeat")

    # --------------------------------------------------------------- landing
    landed = _run_procedure(recorder, sim, landing, {})
    assert landed["outcome"] == "passed", _explain(landed)
    assert not sim.link.state.armed, "still armed after a passing landing"


# --------------------------------------------------------------- off-nominal
# WHY ONE MODEL AND NOT ALL OF THEM
# ---------------------------------
# A scenario is a second full flight per model, and tier 2 already costs a
# Gazebo boot each. The claim this test makes is narrow on purpose: that fault
# injection works against the real model set in Gazebo, not only against SITL's
# generic frames — which is the one thing tier 1 cannot show.
#
# It is a Copter because both shipped scenarios are Copter scenarios, and a
# scenario is chosen by name rather than by capability. A VTOL or Plane
# equivalent needs a procedure written for it first; inventing criteria for an
# airframe nobody has watched respond would be the unearned claim this project
# exists to remove.
SCENARIO_MODELS = [m for m in MODELS if m.get("vehicle") == "ArduCopter"]


@pytest.mark.skipif(not SCENARIO_MODELS,
                    reason="no ArduCopter model in models.json to fly a "
                           "scenario on; recorded as unverified, not passed")
@pytest.mark.parametrize("model", SCENARIO_MODELS[:1], ids=_ids)
def test_a_model_survives_a_gps_loss_in_the_hover(request, tier2_runs_root, model):
    """One off-nominal scenario, flown on a real airframe in Gazebo."""
    if model.get("method") == "ros2_launch":
        pytest.skip(f"{model['id']} launches through ros2, which needs a built "
                    f"ardupilot_gz workspace")

    scenario = procs.get("copter_gps_loss")
    assert scenario is not None, "copter_gps_loss is missing from procedures/"

    work_dir = paths.RUN_DIR / model["id"]
    recorder = RunRecorder(model=model, root=tier2_runs_root, work_dir=work_dir,
                           launch_commands=gazebo.launch_commands(model),
                           test_id=request.node.nodeid)
    try:
        sim = gazebo.start(model, log_dir=work_dir, on_event=recorder.event,
                           on_log=lambda text: recorder.console(text.encode()))
    except gazebo.GazeboUnavailable as exc:
        recorder.event({"kind": "skipped", "reason": str(exc)})
        recorder.finish(report=False)
        pytest.skip(str(exc))

    request.addfinalizer(lambda: (sim.stop(), recorder.finish(wait=True)))
    assert sim.wait_prearm(), (
        f"{model['id']} never passed pre-arm checks\n{sim.tail()}")

    caps = probe_capabilities(sim.link, vehicle=model.get("vehicle"))
    if not scenario.matches(caps):
        pytest.skip(f"{model['id']}: copter_gps_loss does not apply to its "
                    f"probed capabilities {caps} — recorded as untested")

    result = _run_procedure(recorder, sim, scenario, scenario.default_values())

    # Fail closed: a scenario that ran without its fault is a nominal flight
    # under an off-nominal name, and asserting the outcome without checking
    # this would let that pass.
    assert result["faults"], f"no fault was injected\n{_explain(result)}"
    fault = result["faults"][0]
    assert fault["applied"] is True, _explain(result)
    assert fault["cleared"] is True, (
        f"the GPS was left degraded on {model['id']}\n{_explain(result)}")
    assert not fault["evidence_missing"], (
        f"the criteria rest on telemetry that never arrived, so the verdict "
        f"means nothing\n{_explain(result)}")

    assert result["outcome"] == "passed", _explain(result)
