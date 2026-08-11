# Simulation lifecycle

What has to come up before an aircraft can be judged, in what order, and which
kind of failure each rung produces when it does not.

This is the page to read when a run failed and you do not yet know whether to
look at the simulator, the autopilot or the aircraft.
[Process/session lifecycle](lifecycle.md) covers the processes themselves —
what is launched and how it is shut down. This page is about the *states* they
pass through.

## The ladder

```
CREATED
   ↓
ENVIRONMENT_STARTING     the simulator process was launched
   ↓
ENVIRONMENT_READY        it is serving a world — not merely running
   ↓
VEHICLE_STARTING         the autopilot process was launched
   ↓
VEHICLE_READY            it is talking, and it says it is fit to fly
   ↓
PROCEDURE_RUNNING        the executor has it
   ↓
COMPLETED                with a verdict that is about the aircraft
```

with failure branches:

```
ENVIRONMENT_FAILED       the simulator did not come up
VEHICLE_START_FAILED     the simulator did, and the autopilot did not
VEHICLE_NOT_READY        the autopilot is running and reports itself unfit
PROCEDURE_FAILED         the flow ran and did not get where it was going
ACCEPTANCE_FAILED        the aircraft was operational and did the wrong thing
```

## Why "started" and "ready" are two different rungs

A PID proves that `fork` succeeded, and nothing more.

Gazebo holds a PID for the several seconds it spends failing to resolve
`model://runway`, printing *Unable to find uri*, and exiting. SITL holds one
while it waits forever for a physics backend that is not answering. Before
v1.7, `gz sim … &` followed by `sleep 6` was the entire handshake: six seconds
is too long on a fast machine and too short on a cold cache, and in neither
case does it distinguish a simulator that is slow from one that is dead.

So each rung is reached by the component doing its job, not by a clock:

| Rung | How it is established |
|---|---|
| `ENVIRONMENT_READY` | `gz topic -l` lists a topic under `/world/…`. Gazebo's transport only advertises those once a world is loaded and the server is stepping it. |
| `VEHICLE_STARTING` → operational | SITL's serial0 TCP port accepts a connection. The binary opens it once it is past initialisation and ready for a ground station. |
| `VEHICLE_READY` | A heartbeat has arrived **and** `SYS_STATUS` reports the pre-arm check bit healthy. |

The launch commands wait for the first of these in the terminal, visibly:

```bash
gz sim -v4 -r -s alti_transition_runway.sdf &
for i in $(seq 1 30); do
  gz topic -l 2>/dev/null | grep -q "^/world/" && { echo "[argaz] gazebo is serving a world"; break; }
  sleep 2
done
```

That stays a shell line rather than moving into Python for the same reason every
other launch line is one: the commands in the terminal are the commands you
could have typed.

### The fallback, stated rather than hidden

`gz topic` can be absent from a `PATH` that has `gz sim`. A launch that refused
to proceed on a missing diagnostic tool would fail a simulation that was
working, so the vehicle is started anyway and the rung is recorded as not
reached. If no heartbeat then arrives, the run says *Gazebo never reported a
served world, and no vehicle heartbeat arrived* — which is a different sentence
from *the simulator came up but no vehicle appeared*, and they are two
different investigations.

## What each rung produces when it fails

Every failure branch maps onto the [seven-category
taxonomy](failure-classification.md). **No category was added.** The point is
that a failure is reported at the layer it happened in, not that there is a new
vocabulary for layers.

| Stopped at | Category | Code |
|---|---|---|
| `ENVIRONMENT_FAILED` | `environment` | `environment-not-ready` |
| `VEHICLE_START_FAILED` | `environment` | `vehicle-start-failed` |
| `VEHICLE_NOT_READY` | `vehicle_readiness` | `prearm-never-passed` |
| `PROCEDURE_FAILED` | `procedure` | `step-failed` |
| `ACCEPTANCE_FAILED` | `acceptance` | `criterion-failed` |

Exactly one row is `acceptance`, because `acceptance` is
[documented](failure-classification.md) as the only category that means the
aircraft did something wrong — and a lifecycle rung is by definition below the
aircraft.

`VEHICLE_START_FAILED` is `environment` and not `vehicle_readiness` on purpose.
SITL failing to start is the simulator not coming up. `vehicle_readiness` is
reserved for a vehicle that *is* running and reports itself unfit, which is a
fact about the aircraft's configuration — `swan_k1_hwing` in
[status.md](status.md) is the live example: it never passes pre-arm because it
has no airspeed sensor.

## Where it is driven from

Nothing here is an orchestrator. `simlifecycle.Lifecycle` is a record and a
classifier: it starts nothing, launches nothing and owns no process.

* `TerminalSession` still owns the processes.
* `MavlinkLink` still owns readiness.
* `ProcedureRunner` is still the only executor.

Two places drive it, because they are the two that already know what was
started: `Manager` for the browser path, and `tests/gazebo.py` for tier 2. Both
record the result into the run through `RunRecorder.record_lifecycle`.

A tier-1 run records no lifecycle at all. It starts a SITL binary directly, so
there is no Gazebo to bring up and no pty session to own, and `lifecycle: null`
is the honest answer rather than an empty one.

## What a run records

```json
"lifecycle": {
  "phase": "completed",
  "clock": "wall",
  "history": [
    {"phase": "created",               "since_start_s": 0.0,  "detail": ""},
    {"phase": "environment_starting",  "since_start_s": 0.1,  "detail": "6 launch line(s)"},
    {"phase": "environment_ready",     "since_start_s": 8.4,  "detail": "Gazebo is serving world(s): alti_transition_runway"},
    {"phase": "vehicle_starting",      "since_start_s": 8.4,  "detail": "waiting for MAVLink"},
    {"phase": "vehicle_ready",         "since_start_s": 31.2, "detail": "pre-arm checks pass"},
    {"phase": "procedure_running",     "since_start_s": 31.3, "detail": "vtol_takeoff"},
    {"phase": "completed",             "since_start_s": 96.0, "detail": "session stopped"}
  ],
  "timings_s": {"environment_ready": 8.4, "vehicle_ready": 31.2, "total": 96.0},
  "failure": null
}
```

### About the timings

They are **wall clock** and are labelled as such in the record. They measure
how long the host took to bring an environment up, which is a fact about the
host — not about the aircraft, and not a [metric](metrics.md). Nothing derived
from them can reach a verdict.

A rung that was never reached reports `null`, not `0`. "It took no time" and
"it never happened" are different facts, and this project does not let them
look the same.

### A terminal phase is not left again

Once a lifecycle has failed, a later success does not overwrite it. A history
in which the failure is present but invisible is worse than no history: it
would show a clean start-up under a run that carries a verdict nothing
supports.

## Reading a failure

Open `result.json` and look at `lifecycle.failure` first. If it is not `null`,
the run never got far enough for its procedures to mean anything, and
`classify_run` will already have reported the environment rather than the
flight — before it looks at a single step.

If it *is* `null`, the environment came up and the executor got its turn. The
verdict is in the procedures, and [failure investigation](failure-investigation.md)
is the page for it.
