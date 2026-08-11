"""F-14 — a broken simulator is not a broken aircraft, and it says which part.

WHAT THIS FILE HAS TO PROVE, FROM §6 OF THE v1.7 BRIEF
------------------------------------------------------
    1 Gazebo startup failure          -> environment
    2 SITL startup failure            -> environment (vehicle start)
    3 vehicle readiness timeout       -> vehicle_readiness
    4 successful environment startup
    5 successful vehicle readiness
    6 an actual acceptance failure after a valid startup   <- MANDATORY

Six is the one that matters most and is the easiest to lose. A fix that made
every failure look like infrastructure would close this finding and destroy the
tool, so the last case asserts that a measured criterion violation on a working
simulator is still `acceptance` — the one category that means the aircraft did
something wrong.

WHY THE PROBES ARE TESTED AGAINST REAL SOCKETS
-----------------------------------------------
`wait_for_sitl` is asserted against a real listening socket and a real closed
port rather than a patched `connect_ex`. The defect being closed was that a PID
was treated as evidence of a service, and a test that stubbed the service would
be making the same mistake one level up.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from argazui import failures, simlifecycle as lc

pytestmark = pytest.mark.tier1


# ------------------------------------------------------------ the state model
def test_a_new_lifecycle_starts_created_and_has_not_failed():
    lifecycle = lc.Lifecycle(label="probe")
    assert lifecycle.phase == lc.CREATED
    assert lifecycle.failed is False
    assert lifecycle.failure() is None


def test_every_phase_maps_to_something_and_only_one_maps_to_acceptance():
    """The taxonomy gains no category; a failure is reported at its own layer.

    Exactly one phase may produce `acceptance`, because `acceptance` is
    documented as the only verdict about the aircraft and a lifecycle rung is
    by definition below the aircraft.
    """
    for phase in lc.FAILED:
        assert phase in lc.PHASE_FAILURES, phase
        category, code = lc.PHASE_FAILURES[phase]
        assert category in failures.CATEGORIES, category
        assert code
    to_acceptance = [p for p, (c, _) in lc.PHASE_FAILURES.items()
                     if c == failures.ACCEPTANCE]
    assert to_acceptance == [lc.ACCEPTANCE_FAILED]


def test_an_unknown_phase_is_refused_rather_than_recorded():
    lifecycle = lc.Lifecycle()
    with pytest.raises(ValueError):
        lifecycle.enter("environment_probably_fine")
    with pytest.raises(ValueError):
        lifecycle.fail(lc.COMPLETED, "completed is not a failure")


def test_a_terminal_phase_is_not_left_again():
    """A failure that a later success overwrote would be present and invisible.

    That is worse than not recording it: the history would show a clean
    start-up and the run would carry a verdict nothing supports.
    """
    lifecycle = lc.Lifecycle()
    lifecycle.fail(lc.ENVIRONMENT_FAILED, "gazebo died")
    lifecycle.enter(lc.VEHICLE_READY, "this must not take")
    assert lifecycle.phase == lc.ENVIRONMENT_FAILED
    assert not lifecycle.reached(lc.VEHICLE_READY)


# ----------------------------------------------------- 1. Gazebo startup fails
def test_a_gazebo_that_never_serves_a_world_is_an_environment_failure():
    lifecycle = lc.Lifecycle(label="probe")
    lifecycle.enter(lc.ENVIRONMENT_STARTING, "gz sim launched")
    lifecycle.fail(lc.ENVIRONMENT_FAILED,
                   "no Gazebo transport topics — no simulator is serving")

    failure = lifecycle.failure()
    assert failure["category"] == failures.ENVIRONMENT
    assert failure["code"] == failures.CODE_ENVIRONMENT_NOT_READY
    # And through the classifier a run record actually goes through.
    classified = failures.classify_run({"lifecycle": lifecycle.as_dict(),
                                        "procedures": []})
    assert classified.category == failures.ENVIRONMENT
    assert classified.category != failures.ACCEPTANCE


def test_a_dead_simulator_is_diagnosed_rather_than_waited_out():
    """`alive` is what turns a timeout into a sentence somebody can act on.

    Waiting the full budget for a process that exited two seconds in reports
    "it did not become ready", which is true and useless.
    """
    started = time.time()
    ready, detail = lc.wait_for_gazebo(timeout=30.0, poll=0.2,
                                       alive=lambda: False)
    assert ready is False
    assert "exited" in detail or "gone" in detail
    assert time.time() - started < 5.0, (
        "a simulator known to be dead was still waited out")


def test_gazebo_readiness_reads_a_served_world_and_not_a_process():
    """A PID proves `fork` succeeded, and nothing more.

    Gazebo holds one for the several seconds it spends failing to resolve a
    mesh. On this host no simulator is running, so the probe must say so — and
    must not say so because `gz` is missing, which is a different answer it
    also has to be able to give.
    """
    ready, detail = lc.gazebo_serving()
    assert isinstance(ready, bool)
    assert detail, "the probe gave no reason for its answer"
    if not ready:
        assert ("no simulator is serving" in detail
                or "not on PATH" in detail
                or "no world is loaded" in detail
                or "did not answer" in detail), detail


# ------------------------------------------------------ 2. SITL startup fails
def test_sitl_that_never_opens_its_port_is_a_vehicle_start_failure():
    """"The process exists" and "the process is doing its job" are two rungs.

    Probed against a port nothing is listening on, so the negative answer comes
    from the kernel rather than from a stub.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as spare:
        spare.bind(("127.0.0.1", 0))
        closed_port = spare.getsockname()[1]
    # The socket is closed now, so nothing is accepting on `closed_port`.

    ready, detail = lc.wait_for_sitl(closed_port, timeout=1.0, poll=0.2)
    assert ready is False
    assert "not operational" in detail

    lifecycle = lc.Lifecycle()
    lifecycle.enter(lc.ENVIRONMENT_READY, "gazebo is serving")
    lifecycle.enter(lc.VEHICLE_STARTING, "sim_vehicle.py launched")
    lifecycle.fail(lc.VEHICLE_START_FAILED, detail)

    failure = lifecycle.failure()
    assert failure["category"] == failures.ENVIRONMENT
    assert failure["code"] == failures.CODE_VEHICLE_START_FAILED
    assert failure["category"] != failures.ACCEPTANCE


def test_a_sitl_that_is_serving_is_detected_as_operational():
    """The counterweight: a real listening socket answers yes, quickly."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    threading.Thread(target=lambda: None, daemon=True).start()
    try:
        ready, detail = lc.wait_for_sitl(port, timeout=5.0, poll=0.1)
        assert ready is True, detail
        assert str(port) in detail
    finally:
        listener.close()


def test_a_vehicle_process_that_died_is_named_rather_than_timed_out():
    started = time.time()
    ready, detail = lc.wait_for_sitl(1, timeout=30.0, poll=0.2,
                                     alive=lambda: False)
    assert ready is False
    assert "gone" in detail or "exited" in detail
    assert time.time() - started < 5.0


# ------------------------------------------------ 3. vehicle readiness timeout
class _State:
    def __init__(self, heartbeat=False, prearm_known=False, prearm_ok=False):
        self.heartbeat_known = heartbeat
        self.prearm_known = prearm_known
        self.prearm_ok = prearm_ok


class _Link:
    def __init__(self, state):
        self.state = state


def test_a_vehicle_that_reports_itself_unfit_is_vehicle_readiness():
    """NOT `environment`, and NOT `acceptance`.

    This vehicle is running and talking; it says its pre-arm checks do not
    pass. That is a fact about the aircraft's configuration and the taxonomy
    has a category for it that is neither the simulator's fault nor a verdict
    about how it flew. `swan_k1_hwing` is the live example in docs/status.md.
    """
    phase, detail = lc.vehicle_readiness(
        _Link(_State(heartbeat=True, prearm_known=True, prearm_ok=False)))
    assert phase == lc.VEHICLE_NOT_READY
    assert "not passing" in detail

    lifecycle = lc.Lifecycle()
    lifecycle.enter(lc.ENVIRONMENT_READY, "")
    lifecycle.fail(lc.VEHICLE_NOT_READY, detail)
    failure = lifecycle.failure()
    assert failure["category"] == failures.VEHICLE_READINESS
    assert failure["category"] not in (failures.ACCEPTANCE, failures.ENVIRONMENT)


def test_not_yet_observed_is_not_the_same_as_observed_unhealthy():
    """The `known`/`ok` pairs are what make three answers possible.

    A single boolean would report a vehicle that has not spoken yet and one
    that has said it is unfit identically, and only one of those is a problem.
    """
    silent = lc.vehicle_readiness(_Link(_State()))[0]
    talking = lc.vehicle_readiness(_Link(_State(heartbeat=True)))[0]
    unfit = lc.vehicle_readiness(
        _Link(_State(heartbeat=True, prearm_known=True)))[0]
    assert silent == lc.VEHICLE_STARTING
    assert talking == lc.VEHICLE_STARTING
    assert unfit == lc.VEHICLE_NOT_READY


# --------------------------------------------- 4 & 5. the successful path
def test_a_nominal_startup_reaches_every_rung_in_order():
    lifecycle = lc.Lifecycle(label="nominal")
    for phase in lc.NOMINAL[1:]:
        lifecycle.enter(phase, "")
    assert lifecycle.phase == lc.COMPLETED
    assert lifecycle.failed is False
    assert lifecycle.failure() is None
    recorded = [entry.phase for entry in lifecycle.history]
    assert recorded == list(lc.NOMINAL)


def test_a_completed_lifecycle_classifies_a_run_as_nothing():
    """Reaching COMPLETED makes no claim about the aircraft.

    It says the environment came up and the executor got its turn. The verdict
    comes from the procedures, and the classifier must fall straight through to
    them.
    """
    lifecycle = lc.Lifecycle()
    for phase in lc.NOMINAL[1:]:
        lifecycle.enter(phase, "")
    assert failures.classify_run({"lifecycle": lifecycle.as_dict(),
                                  "procedures": []}) is None


def test_a_vehicle_that_is_fit_reports_ready():
    phase, detail = lc.vehicle_readiness(
        _Link(_State(heartbeat=True, prearm_known=True, prearm_ok=True)))
    assert phase == lc.VEHICLE_READY
    assert "pre-arm checks pass" in detail


def test_startup_latency_is_measured_and_labelled_wall_clock():
    """The metrics §11 asks for, and no more than those.

    A rung never reached reports None rather than zero, because "it took no
    time" and "it never happened" are different facts.
    """
    lifecycle = lc.Lifecycle(label="timed")
    lifecycle.enter(lc.ENVIRONMENT_STARTING, "")
    time.sleep(0.05)
    lifecycle.enter(lc.ENVIRONMENT_READY, "")
    document = lifecycle.as_dict()

    assert document["clock"] == "wall"
    assert document["timings_s"]["environment_ready"] >= 0.05
    assert document["timings_s"]["vehicle_ready"] is None, (
        "a rung that was never reached reported a duration")


# ---------------------------------------- 6. MANDATORY: a real acceptance fail
def test_a_measured_criterion_violation_after_a_good_startup_is_acceptance():
    """The release gate this whole finding could otherwise have broken.

    A fix that classified everything as infrastructure would close F-14 and
    remove the tool's only verdict about an aircraft. So: a lifecycle that
    reached the executor cleanly, and a procedure whose criterion was MEASURED
    and did not hold, must still be `acceptance` / `criterion-failed`.
    """
    lifecycle = lc.Lifecycle(label="flew")
    for phase in (lc.ENVIRONMENT_STARTING, lc.ENVIRONMENT_READY,
                  lc.VEHICLE_STARTING, lc.VEHICLE_READY, lc.PROCEDURE_RUNNING,
                  lc.COMPLETED):
        lifecycle.enter(phase, "")

    record = {
        "lifecycle": lifecycle.as_dict(),
        "status": "failed",
        "artefacts": {"dataflash": "00000001.BIN"},
        "procedures": [{
            "procedure": "copter_takeoff", "role": "takeoff",
            "result": {
                "outcome": "failed", "steps": [], "faults": [],
                "expect": [{
                    "criterion_id": "copter_takeoff#alt-reached",
                    "label": "reached at least 85% of the requested altitude",
                    "passed": False, "evaluated": True,
                    "text": "alt=3.2m",
                }],
            },
        }],
    }
    failure = failures.classify_run(record)
    assert failure is not None
    assert failure.category == failures.ACCEPTANCE, (
        f"a measured criterion violation was reported as {failure.category}; "
        f"the aircraft's own verdict has been lost")
    assert failure.code == failures.CODE_CRITERION_FAILED


def test_an_environment_failure_outranks_procedures_that_never_had_a_vehicle():
    """A start-up that stopped is not read from the residue it left behind.

    Steps that timed out against a simulator that was not there used to be the
    only evidence, and reconstructing a cause from them is what made a dead
    Gazebo a `procedure` failure. The layer that launched knows, and it says so.
    """
    lifecycle = lc.Lifecycle()
    lifecycle.enter(lc.ENVIRONMENT_STARTING, "")
    lifecycle.fail(lc.ENVIRONMENT_FAILED, "gazebo never served a world")
    record = {
        "lifecycle": lifecycle.as_dict(),
        "procedures": [{
            "procedure": "copter_takeoff", "role": "takeoff",
            "result": {"outcome": "failed",
                       "steps": [{"kind": "wait_for", "status": "failed",
                                  "label": "climb", "text": "timed out"}],
                       "faults": [], "expect": []},
        }],
    }
    failure = failures.classify_run(record)
    assert failure.category == failures.ENVIRONMENT
    assert failure.code == failures.CODE_ENVIRONMENT_NOT_READY


def test_a_run_recorded_before_lifecycles_existed_still_classifies():
    """Backward compatibility: archived runs carry no `lifecycle` key.

    Refusing to read them, or classifying their absence as a failure, would
    reclassify every run in the repository.
    """
    record = {
        "status": "failed",
        "artefacts": {"dataflash": "00000001.BIN"},
        "procedures": [{
            "procedure": "copter_land", "role": "land",
            "result": {"outcome": "failed", "steps": [], "faults": [],
                       "expect": [{"label": "on the ground", "passed": False,
                                   "evaluated": True, "text": "alt=12.0m"}]},
        }],
    }
    failure = failures.classify_run(record)
    assert failure is not None
    assert failure.category == failures.ACCEPTANCE


# ------------------------------------- the launch commands themselves (F-14)
def test_the_launch_no_longer_asserts_that_six_seconds_was_enough():
    """`sleep 6` was the whole Gazebo handshake, and it asserted rather than
    checked.

    Six seconds is too long on a fast machine — the ten tier-2 models in this
    release were serving at about 2.1 s — and too short on a cold cache, and in
    neither case does it distinguish a simulator that is slow from one that is
    dead.
    """
    from argazui import session

    model = {"id": "probe", "method": "gz_plus_sitl_frame", "vehicle": "ArduPlane",
             "frame": "gazebo-zephyr", "world": "zephyr_runway.sdf",
             "env": "env.sh"}
    lines = session.build_launch_commands(model)
    joined = "\n".join(lines)

    assert "gz sim" in joined, "the probe model does not launch Gazebo at all"
    assert not any(line.strip() == "sleep 6" for line in lines), (
        "the fixed-duration Gazebo handshake is back")

    # The readiness line waits on the simulator DOING ITS JOB.
    wait = next(line for line in lines if "/world/" in line)
    assert "gz topic -l" in wait
    assert "grep -q" in wait


def test_the_readiness_wait_is_bounded_and_says_so_when_it_gives_up():
    """A launch that waits forever is a launch nobody can diagnose.

    And the fallback is stated in the output rather than silent: `gz topic` can
    be absent from a PATH that has `gz sim`, so the vehicle is started anyway
    and the console says why the rung was not reached.
    """
    from argazui import session

    wait = session.gazebo_ready_wait(timeout_s=60, poll_s=2)
    assert "seq 1 30" in wait, "the loop bound does not follow timeout/poll"
    assert "sleep 2" in wait
    assert "did not report a world within 60s" in wait
    assert "starting the vehicle anyway" in wait


def test_a_model_with_no_world_gets_no_gazebo_wait():
    """`sitl_only` has no simulator to wait for, and must not wait for one."""
    from argazui import session

    model = {"id": "probe", "method": "sitl_only", "vehicle": "ArduPlane",
             "frame": "plane", "env": "env.sh"}
    joined = "\n".join(session.build_launch_commands(model))
    assert "gz topic" not in joined
    assert "gz sim" not in joined
