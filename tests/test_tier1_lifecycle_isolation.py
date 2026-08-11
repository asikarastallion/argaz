"""Tier 1 integration — launch, readiness, procedure, evidence, verdict, cleanup.

WHY A SEPARATE FILE FROM THE UNIT TESTS
----------------------------------------
`test_sim_lifecycle.py` and `test_isolation.py` assert what the two modules do
in isolation. Neither can say whether the pieces are WIRED: a lifecycle nobody
records, or an ownership check nothing calls, would pass every unit test in
this repository and change nothing about a run.

So this file flies a real SITL, drives the real `ProcedureRunner`, and then
opens the run directory and asserts on what is actually in `result.json` — the
same document `docs/status.md`, the failure classifier and a reviewer all read.

WHAT IT DOES NOT COVER
----------------------
Gazebo. There is none in tier 1 by design, so the environment rung here is the
degenerate one ("this model needs no simulator of its own"). The Gazebo path is
exercised by tier 2, which drives the identical `simlifecycle` code through
`tests/gazebo.py`.
"""
from __future__ import annotations

import os

import pytest

from argazui import failures, isolation, procedures as procs, simlifecycle
from argazui.procrunner import ProcedureRunner

from support import boot, read_result

pytestmark = pytest.mark.tier1

QUAD = {
    "id": "sitl_quad_lifecycle", "name": "SITL quad frame",
    "vehicle_class": "Copter", "method": "sitl_frame",
    "vehicle": "ArduCopter", "frame": "quad",
}


def test_a_flight_records_the_lifecycle_it_actually_went_through(request,
                                                                 runs_root):
    """launch -> readiness -> procedure -> evidence -> verdict -> cleanup.

    The whole chain, in one run directory, asserted from the artefact rather
    than from the objects that produced it.
    """
    vehicle = boot(request, runs_root, QUAD, QUAD["frame"])
    lifecycle = simlifecycle.Lifecycle(label=QUAD["id"])
    resources = isolation.RunResources(label=QUAD["id"], sid=os.getsid(0))

    # -- environment. Tier 1 starts a SITL binary directly, so the simulator
    #    rung is reached by having nothing to bring up, and it says so.
    lifecycle.enter(simlifecycle.ENVIRONMENT_STARTING, "SITL launched directly")
    lifecycle.enter(simlifecycle.ENVIRONMENT_READY,
                    "this model needs no simulator of its own")

    # -- vehicle readiness, through the same probe the browser path uses.
    lifecycle.enter(simlifecycle.VEHICLE_STARTING, "waiting for MAVLink")
    assert vehicle.wait_prearm(), (
        f"the quad frame never passed pre-arm checks\n{vehicle.sitl.tail()}")
    phase, detail = simlifecycle.vehicle_readiness(vehicle.link)
    assert phase == simlifecycle.VEHICLE_READY, detail
    lifecycle.enter(simlifecycle.VEHICLE_READY, detail)

    # -- SITL is SERVING, not merely running. The distinction the audit named
    #    as asymmetric between the test path and the real path; both use this
    #    probe now.
    port = int(vehicle.sitl.connection.rsplit(":", 1)[1])
    ready, detail = simlifecycle.wait_for_sitl(port, timeout=5.0)
    assert ready is True, detail

    # WHAT A TIER-1 RUN ACTUALLY OWNS
    # -------------------------------
    # SITL's serial0, and nothing else. It connects straight to that TCP port
    # and never binds 14550 — MAVProxy's UDP fan-out is the browser path's
    # arrangement, not this one. Declaring the MAVLink ports here would record
    # an ownership claim over sockets this run never touched, which is the
    # opposite of what the ownership boundary is for.
    resources.check_ports({"sitl": (port, isolation.KIND_TCP)})
    held = [h for h in resources.conflicts if h.port == port]
    assert held, "SITL is serving and its own port was not seen as held"

    # -- procedure
    lifecycle.enter(simlifecycle.PROCEDURE_RUNNING, "copter_takeoff")
    takeoff = procs.select("takeoff", vehicle.capabilities, QUAD)
    assert takeoff is not None
    result = ProcedureRunner(vehicle.link,
                             on_event=vehicle.recorder.event).run(takeoff,
                                                                  {"alt": 15})
    vehicle.recorder.add_procedure(takeoff, result, values={"alt": 15})
    lifecycle.enter(simlifecycle.COMPLETED, "procedure finished")

    # -- cleanup, checked rather than assumed
    resources.verify_released()
    vehicle.recorder.record_lifecycle(lifecycle)
    vehicle.recorder.record_isolation(resources)
    vehicle.recorder.finish(wait=True)

    # -- evidence: what a reviewer holding only this directory can see
    record = read_result(vehicle.recorder)
    assert record, "the run wrote no result.json"

    recorded = record["lifecycle"]
    assert recorded["phase"] == simlifecycle.COMPLETED
    assert recorded["clock"] == "wall"
    assert recorded["failure"] is None
    phases = [entry["phase"] for entry in recorded["history"]]
    assert phases[0] == simlifecycle.CREATED
    for rung in (simlifecycle.ENVIRONMENT_READY, simlifecycle.VEHICLE_READY,
                 simlifecycle.PROCEDURE_RUNNING):
        assert rung in phases, f"{rung} is missing from the recorded lifecycle"
    assert recorded["timings_s"]["vehicle_ready"] is not None, (
        "the readiness latency was not measured")

    owned = record["isolation"]
    assert owned["session_id"] == os.getsid(0)
    assert "sitl" in owned["ports"], (
        f"the run record does not say which ports this run owned: {owned}")
    assert owned["ports"]["sitl"] == port

    # -- verdict: still the aircraft's, and still from the criteria
    assert result["outcome"] == "passed", result["text"]
    assert record["status"] == "passed"


def test_a_completed_lifecycle_does_not_touch_the_aircraft_verdict(request,
                                                                   runs_root):
    """The lifecycle is a record, not a judgement.

    A run that came up cleanly and then failed a criterion must still be an
    `acceptance` failure. Asserted on a real flight rather than a hand-built
    dict, because the hand-built version is what let F-02 survive.
    """
    vehicle = boot(request, runs_root, QUAD, QUAD["frame"])
    assert vehicle.wait_prearm(), vehicle.sitl.tail()

    lifecycle = simlifecycle.Lifecycle(label=QUAD["id"])
    for phase in (simlifecycle.ENVIRONMENT_STARTING,
                  simlifecycle.ENVIRONMENT_READY,
                  simlifecycle.VEHICLE_STARTING, simlifecycle.VEHICLE_READY,
                  simlifecycle.PROCEDURE_RUNNING, simlifecycle.COMPLETED):
        lifecycle.enter(phase, "")

    takeoff = procs.select("takeoff", vehicle.capabilities, QUAD)
    result = ProcedureRunner(vehicle.link,
                             on_event=vehicle.recorder.event).run(takeoff,
                                                                  {"alt": 15})
    vehicle.recorder.add_procedure(takeoff, result, values={"alt": 15})
    vehicle.recorder.record_lifecycle(lifecycle)
    vehicle.recorder.finish(wait=True)
    record = read_result(vehicle.recorder)

    # The real flight passed, so there is no failure to classify — and the
    # lifecycle did not invent one.
    assert record["failure"] is None, record["failure"]

    # Now the counterweight, on the SAME clean lifecycle: a measured criterion
    # violation must reach `acceptance` through it rather than be masked by it.
    doctored = dict(record)
    doctored["procedures"] = [{
        "procedure": "copter_takeoff", "role": "takeoff",
        "result": {"outcome": "failed", "steps": [], "faults": [],
                   "expect": [{"criterion_id": "copter_takeoff#alt-reached",
                               "label": "reached the requested altitude",
                               "passed": False, "evaluated": True,
                               "text": "alt=1.1m"}]},
    }]
    failure = failures.classify_run(doctored)
    assert failure.category == failures.ACCEPTANCE
    assert failure.code == failures.CODE_CRITERION_FAILED


def test_a_run_leaves_no_owned_process_and_no_held_port(request, runs_root):
    """5 and 6 from §7, against a real SITL rather than a `sleep`.

    `boot` registers teardown with `addfinalizer`, so the cleanup this asserts
    is the one every tier-1 test relies on. If it leaked, the whole suite would
    accumulate SITL instances — which is the failure mode `_free_instance`
    exists to work around rather than to hide.
    """
    vehicle = boot(request, runs_root, QUAD, QUAD["frame"])
    assert vehicle.wait_prearm(), vehicle.sitl.tail()

    port = int(vehicle.sitl.connection.rsplit(":", 1)[1])
    assert isolation.port_free(port, "tcp") is False, (
        "SITL is running and its serial0 port is not held; the probe is wrong")

    sid = os.getsid(vehicle.sitl.process.pid)
    resources = isolation.RunResources(label=QUAD["id"], sid=sid)
    resources.ports = {"sitl": port}

    # Stop it the way teardown does, then ask the kernel rather than assuming.
    vehicle.link.stop()
    vehicle.sitl.stop()

    import time
    for _ in range(100):
        released = resources.verify_released()
        if released["released"]:
            break
        time.sleep(0.1)

    assert released["released"] is True, (
        f"the run left something behind: {released}")
    assert released["survivors"] == []
    assert released["ports_still_held"] == {}
