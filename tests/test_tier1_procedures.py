"""Tier 1 — procedure logic against real SITL, without Gazebo.

WHAT A GREEN RUN HERE DOES AND DOES NOT MEAN
--------------------------------------------
It means: the capability probe reads the aircraft correctly, the right
procedure is selected for that class, the declared overrides are applied and
restored, the acceptance criteria are evaluated against measured state, and a
complete run directory comes out that `flightlog.py` can parse.

It does **not** mean any Gazebo model works. These are SITL's own generic
frames. `docs/status.md` therefore never marks a model verified from tier 1 —
only tier 2 can do that. Conflating the two would put back exactly the kind of
unearned tick this version was written to remove.
"""
from __future__ import annotations

import json
import time

import pytest

from argazui import procedures as procs
from argazui.flightlog import analyse
from argazui.procrunner import ProcedureRunner

from support import boot, read_result

pytestmark = pytest.mark.tier1


# SITL's own frames. `expect_*` is the procedure the capability probe must
# choose; asserting it is how "the Plane bug" stays fixed — a regression that
# sent Copter's takeoff to a fixed wing would fail here before it ever flew.
FRAMES = [
    {
        "id": "sitl_quad", "name": "SITL quad frame", "vehicle_class": "Copter",
        "method": "sitl_frame", "vehicle": "ArduCopter", "frame": "quad",
        "expect_takeoff": "copter_takeoff", "expect_land": "copter_land",
        "takeoff_values": {"alt": 15}, "cruise_mode": "LOITER",
    },
    {
        "id": "sitl_plane", "name": "SITL plane frame", "vehicle_class": "Plane",
        "method": "sitl_frame", "vehicle": "ArduPlane", "frame": "plane",
        "expect_takeoff": "plane_takeoff", "expect_land": "plane_land",
        "takeoff_values": {"alt": 60}, "cruise_mode": "LOITER",
    },
    {
        "id": "sitl_quadplane", "name": "SITL quadplane frame", "vehicle_class": "VTOL",
        "method": "sitl_frame", "vehicle": "ArduPlane", "frame": "quadplane",
        "expect_takeoff": "vtol_takeoff", "expect_land": "vtol_land",
        "takeoff_values": {"alt": 25}, "cruise_mode": "QHOVER",
    },
    # THIS FRAME FAILS, AND IS KEPT ANYWAY. See docs/status.md and CHANGELOG.
    #
    # `plane-tailsitter` arms, changes mode, obeys the throttle stick and
    # climbs past 20 m — every step of the procedure passes — while tumbling
    # at up to 1300 °/s. It ships no VTOL attitude tuning at all
    # (Q_A_RAT_RLL_P/Q_A_RAT_PIT_P are left at ArduPilot's 0.25 defaults), and
    # ArduPilot's own test suite lists it as a known-broken frame:
    #
    #     "plane-tailsitter": "unstable in hover; unflyable in cruise"
    #        — ardupilot/Tools/autotest/arduplane.py, FlyEachFrame
    #
    # Upstream skips it. The one alternative, `quadplane-copter_tailsitter`,
    # is properly tuned and rock-steady (peak 0.1 °/s) but produces no lift
    # from stick input at any throttle up to full — upstream flies it only
    # through AUTO missions and excludes it from its pilot-RC test for the
    # same reason.
    #
    # So tier 1 cannot verify the tailsitter takeoff on this checkout. The
    # honest way to say that is a red test, not an xfail: tuning the airframe
    # until our own test passes would prove nothing, and marking it green
    # would put back exactly the unearned tick this version removed.
    {
        "id": "sitl_tailsitter", "name": "SITL tailsitter frame", "vehicle_class": "VTOL",
        "method": "sitl_frame", "vehicle": "ArduPlane", "frame": "plane-tailsitter",
        "expect_takeoff": "tailsitter_takeoff", "expect_land": "tailsitter_land",
        "takeoff_values": {"alt": 20}, "cruise_mode": "QHOVER",
    },
]


def _ids(frame: dict) -> str:
    return frame["id"]


def run_once(vehicle, procedure, values: dict, attempt: int) -> dict:
    runner = ProcedureRunner(vehicle.link, on_event=lambda e: vehicle.recorder.event(e))
    result = runner.run(procedure, values)
    vehicle.recorder.add_procedure(procedure, result, values=values, attempt=attempt)
    return result


def run_procedure(vehicle, procedure, values: dict) -> dict:
    """Runs a procedure, with at most ONE retry, and never silently.

    SITL genuinely is timing-sensitive on a loaded machine: an EKF that has not
    settled can refuse an arm that would succeed ten seconds later. One retry
    absorbs that. It is not free — `mark_flaky` makes the run report as `flaky`
    in docs/status.md instead of `passed`, so a procedure that only ever works
    on the second go cannot masquerade as a healthy one.
    """
    result = run_once(vehicle, procedure, values, attempt=1)
    if result["outcome"] == "passed":
        return result

    vehicle.recorder.console(
        f"\n[test] {procedure.id} attempt 1 -> {result['outcome']}: "
        f"{result['text']}\n[test] retrying once\n".encode())
    retry = run_once(vehicle, procedure, values, attempt=2)
    if retry["outcome"] == "passed":
        vehicle.recorder.mark_flaky(
            procedure.id, f"attempt 1 {result['outcome']}: {result['text']}")
    return retry


@pytest.mark.parametrize("frame", FRAMES, ids=_ids)
def test_procedure_selection_matches_the_airframe(request, runs_root, frame):
    """The probe reads the vehicle, and the vehicle picks its own procedure.

    models.json is deliberately not consulted: SkyCat TVBS is registered as a
    plain QuadPlane but its parameters make it a tailsitter, so only the
    aircraft can answer this.
    """
    vehicle = boot(request, runs_root, frame, frame["frame"])
    caps = vehicle.capabilities

    assert caps["autopilot"] == frame["vehicle"], caps
    for role, expected in (("takeoff", frame["expect_takeoff"]),
                           ("land", frame["expect_land"])):
        chosen = procs.select(role, caps)
        assert chosen is not None, f"no {role} procedure matches {caps}"
        assert chosen.id == expected, (
            f"{frame['frame']} chose {chosen.id} for {role}, expected {expected}. "
            f"Probed capabilities: {caps}")


@pytest.mark.parametrize("frame", FRAMES, ids=_ids)
def test_takeoff_mode_change_and_land(request, runs_root, frame):
    """The full sequence, judged by measured state rather than by ACKs."""
    vehicle = boot(request, runs_root, frame, frame["frame"])
    assert vehicle.wait_prearm(), (
        f"{frame['frame']} never passed pre-arm checks\n{vehicle.sitl.tail()}")

    caps = vehicle.capabilities
    takeoff = procs.select("takeoff", caps)
    landing = procs.select("land", caps)
    assert takeoff and landing

    # ---------------------------------------------------------------- takeoff
    result = run_procedure(vehicle, takeoff, frame["takeoff_values"])
    assert result["outcome"] == "passed", _explain(result, vehicle)
    assert vehicle.link.state.armed, "the vehicle is not armed after a passing takeoff"

    target = frame["takeoff_values"]["alt"]
    assert vehicle.link.state.alt > target * 0.7, (
        f"takeoff reported passed but the aircraft is at "
        f"{vehicle.link.state.alt:.1f} m, not near {target} m")

    # ------------------------------------------------------------ mode change
    # A mode change in flight, verified by number against the heartbeat. This
    # is the third thing the status table claims per model.
    mode = frame["cruise_mode"]
    res = vehicle.link.send(f"mode {mode}")
    assert res["ok"], f"mode {mode} was refused: {res['text']}"
    assert vehicle.link.state.mode == mode, (
        f"asked for {mode}, the vehicle reports {vehicle.link.state.mode}")

    # ------------------------------------------------------------------- land
    result = run_procedure(vehicle, landing, {})
    assert result["outcome"] == "passed", _explain(result, vehicle)
    assert not vehicle.link.state.armed, "still armed after a passing landing"


@pytest.mark.parametrize("frame", FRAMES[:2], ids=_ids)
def test_run_directory_is_complete_and_parseable(request, runs_root, frame):
    """A run must leave artefacts another tool can actually read.

    Restricted to two frames because it re-flies a takeoff purely to produce a
    directory; the assertion is about the artefacts, not the airframe.
    """
    vehicle = boot(request, runs_root, frame, frame["frame"])
    assert vehicle.wait_prearm(), vehicle.sitl.tail()
    takeoff = procs.select("takeoff", vehicle.capabilities)
    run_procedure(vehicle, takeoff, frame["takeoff_values"])

    # Close the run the way the UI's STOP does, in the same order.
    vehicle.link.stop()
    vehicle.sitl.stop()
    result = vehicle.recorder.finish(report=False)

    directory = vehicle.recorder.dir
    for name in ("console.log", "mavlink_events.jsonl", "scenario.yaml",
                 "result.json", "versions.txt", "fingerprint.json"):
        assert (directory / name).is_file(), f"{name} is missing from {directory}"

    assert result["schema"] == 3
    assert result["status"] in ("passed", "failed", "error")
    assert result["procedures"], "the procedure was not recorded in result.json"

    # The environment manifest is written before the report, so that a session
    # that produced no dataflash log still says what it ran on.
    manifest = json.loads((directory / "fingerprint.json").read_text(encoding="utf-8"))
    assert manifest["procedure_hash"], manifest
    assert manifest["procedures"] and manifest["procedures"][0]["id"] == takeoff.id
    for field in ("argaz", "ardupilot", "runtime", "model"):
        assert manifest[field], f"the fingerprint has no {field} section"

    # scenario.yaml has to be the procedure verbatim — that is the single
    # source rule made checkable.
    scenario = (directory / "scenario.yaml").read_text(encoding="utf-8")
    assert takeoff.raw_text.strip() in scenario, (
        "scenario.yaml does not contain the procedure that ran verbatim")

    dataflash = result["artefacts"]["dataflash"]
    assert dataflash, f"no dataflash log was archived\n{vehicle.sitl.tail()}"
    report = analyse(directory / dataflash, directory,
                     meta={"run_id": result["run_id"],
                           "overrides": result["overrides"]}, plots=False)
    assert report["params"]["total"] > 100, "the log carried no parameter dump"
    assert (directory / "params_full.txt").is_file()
    assert (directory / "params_diff.txt").is_file()
    # Advisories are health findings and must never be a verdict.
    assert isinstance(report["advisory_count"], int)
    assert result["status"] != "error"


def _explain(result: dict, vehicle) -> str:
    lines = [f"{result['procedure']} -> {result['outcome']}: {result['text']}"]
    for step in result["steps"]:
        lines.append(f"  [{step['status']:7s}] {step['label']} — {step['text']}")
    for expect in result["expect"]:
        lines.append(f"  expect [{'OK' if expect['passed'] else 'FAIL'}] "
                     f"{expect['label']} — {expect['text']}")
    lines.append(vehicle.sitl.tail(15))
    return "\n".join(lines)


def test_the_link_measures_the_simulators_speedup(request, runs_root):
    """The RC keepalive is derived from this number, so it must be real.

    Nothing tells a ground station the SITL speedup — it is an argument to a
    process ArgazUI only sees the output of. The link derives it from the
    vehicle's own timestamps, and the whole keepalive calculation rests on
    that being right rather than plausible.
    """
    import sitl as sitl_mod
    from argazui.mavlink_link import keepalive_interval

    frame = FRAMES[0]
    vehicle = boot(request, runs_root, frame, frame["frame"])

    deadline = time.time() + 60
    while time.time() < deadline and vehicle.link.speedup == 1.0:
        time.sleep(1.0)

    expected = sitl_mod.DEFAULT_SPEEDUP
    assert vehicle.link.speedup == pytest.approx(expected, rel=0.35), (
        f"SITL was started at speedup {expected} but the link measured "
        f"{vehicle.link.speedup:.2f}")

    # And the interval that follows from it is short enough to outrun the
    # override timeout at that speedup.
    interval = vehicle.link.keepalive_interval()
    budget = 3.0 / vehicle.link.speedup
    assert interval * 2 <= budget, (
        f"a {interval:.3f}s keepalive does not fit twice into a {budget:.3f}s "
        f"budget at speedup {vehicle.link.speedup:.1f}")
