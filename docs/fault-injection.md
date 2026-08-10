# Fault injection

Two faults, and only two: the **GPS** degrading or going away, and the **MAVLink
link** to the ground station being interrupted or made lossy.

They exist so a procedure can ask the question a nominal flight cannot — *what
does this aircraft do when something is wrong* — and answer it with the same
evidence chain a nominal flight produces.

## Why so few

A general fault DSL would take a week to write and produce scenarios nobody has
watched a vehicle respond to. These two were chosen because each has:

- a mechanism ArduPilot's own SITL already provides, or that ArgazUI genuinely
  owns;
- an observable that is *measured* rather than assumed;
- a failure mode that occurs in real flying.

Wind, motor loss and arbitrary sensor corruption are deliberately **not**
implemented. They will be if and when there is a scenario somebody wants to run
and a criterion somebody can defend, not because the list looks short.

## The five rules

Each exists because its opposite is dangerous.

### 1. Simulation only

Every mechanism writes a `SIM_*` parameter or changes ArgazUI's own socket
behaviour. Nothing here has a path to hardware — and nothing here is
*conditional* on being in a simulator, which is a stronger guarantee than a
flag: the mechanisms simply do not exist outside one.

### 2. Declared in the procedure

A fault is a `failures:` entry in the YAML that ran. It is therefore in
`scenario.yaml` byte for byte, and it is inside the text that `procedure_hash`
covers in the [environment fingerprint](reproducibility.md). A run cannot have
been degraded by something the archived document does not mention.

`fingerprint.json` also lists the declaration under `scenario`, for a reader.
That section is descriptive and is **not** a second identity field: the
`failures:` block is already part of the procedure text, and a second hash over
the same content could only ever disagree with the first.

### 3. Fail closed

Every declared fault is probed against the vehicle **before the first step**. If
the mechanism is not on this firmware — an ArduPilot without the parameter, a
degradation knob that does not exist — the procedure is **aborted** and the
aircraft never leaves the ground. The run is recorded with an `environment`
failure and the code `fault-not-applied`.

It is never flown nominally. An off-nominal test whose off-nominal condition
never happened is a nominal test wearing the wrong name, and it would report a
pass for a behaviour nobody exercised.

### 4. Cleaned up

Every injector restores what it changed from a `finally`, including when the
procedure fails, errors or is cancelled. Whether each restore actually succeeded
is recorded rather than assumed; a fault that could not be cleared is itself a
classified failure (`fault-not-cleared`), because the simulator is still
degraded and nothing measured after that point means what it says.

The link fault has a second guarantee beyond the injector's own: the runner
clears it from its outer `finally`, and `MavlinkLink.stop()` clears it again, so
it cannot outlive the session that carried it.

### 5. Deterministic

No randomness anywhere. Packet loss drops one in N **by count**, not by
probability, so two runs of the same scenario degrade the link in the same
places. `drop_one_in: 1` is refused — that is a full interruption, and the run
record should say which of the two actually happened.

## The catalogue

| `fault` | `target` | options | mechanism |
|---|---|---|---|
| `gps_loss` | `gps1` | — | `SIM_GPS1_ENABLE = 0`, restored to the value read before injection |
| `gps_degradation` | `gps1` | `satellites` (default 4), `fix_type` (0–6) | `SIM_GPS1_NUMSATS`, `SIM_GPS1_FIXTYPE`, both restored |
| `mavlink_interrupt` | `gcs_link` | — | ArgazUI transmits nothing and discards every received packet unread |
| `mavlink_degradation` | `gcs_link` | `drop_one_in` (default 2, minimum 2) | ArgazUI discards every Nth received message |

Only the **primary** GPS is offered. ArduPilot's SITL simulates a second
receiver only when `SIM_GPS2_ENABLE` is set, so "disable GPS 2" on a normal
model degrades nothing at all — which is exactly the silent no-op rule 3 exists
to prevent.

ArduPilot renamed these parameters when SITL gained multiple simulated
receivers: `SIM_GPS_DISABLE` became `SIM_GPS1_ENABLE`, with the sense inverted.
Both are probed and whichever the connected vehicle answers is used, because
ArgazUI is a front end for a checkout it does not control.

### Why the MAVLink fault is not a `SIM_` parameter

ArduPilot has no parameter for "the ground station went away", and it should
not: the ground station *is this program*. The fault therefore lives where the
fault would live in reality — in the link — and it is honest in both directions,
because ArgazUI genuinely stops hearing the aircraft for the duration rather
than pretending to.

Suppressing ArgazUI's heartbeat is a **complete** model of the condition rather
than an approximation of one. ArduPilot's GCS failsafe keys on
`sysid_mygcs_seen`, which is called from exactly three handlers — `HEARTBEAT`,
`RC_CHANNELS_OVERRIDE` and `MANUAL_CONTROL`
(`ardupilot/libraries/GCS_MAVLink/GCS_Common.cpp`). ArgazUI sends the first two
and never the third, and the fault withholds both.

## The four things a fault test keeps apart

A run's record separates these, and none is derived from another:

| | |
|---|---|
| **the injected condition** | which parameters were written to what, and what they were before |
| **the vehicle response** | how long the fault was actually held, on the vehicle's clock, and which evidence arrived |
| **the criteria** | `expect:` (judged while the fault is held) and `recovery:` (judged after it is cleared) |
| **the verdict** | whether every one of those criteria held |

> **A fault that was successfully injected is not a pass.**

A fault whose declared `evidence:` never arrived is reported as **not judged**,
not as satisfied. Without it the criteria would be evaluated against a state
nothing ever wrote to — an aircraft frozen in amber, which passes anything.

## When criteria can and cannot be judged during a fault

This is not a limitation of the mechanism; it is what the faults *are*.

- **GPS loss** leaves telemetry flowing, so `expect:` criteria are meaningful:
  they are claims about the degraded aircraft, and they would not mean the same
  thing measured after the fix.
- **A full MAVLink interruption** stops telemetry by definition. Every criterion
  in `copter_link_loss.yaml` is therefore a `recovery:` one. The ground station
  finds out what happened afterwards, or not at all.

## Running one

Scenarios appear in their own panel, are started by name, and are never bound to
a quick-command button — a fault must not start because a capability heuristic
decided it applied. Two ship with v1.4:

| | |
|---|---|
| `copter_gps_loss` | climbs to a hover in GUIDED, switches the GPS off for 12 s |
| `copter_link_loss` | climbs to a hover in GUIDED, silences the link for 10 s |

The schema is documented in
[`argazui/procedures/SCHEMA.md`](../argazui/procedures/SCHEMA.md) under
*Scenarios and fault injection*.

## What the scenarios deliberately do not assert

`copter_gps_loss` does **not** require a particular failsafe mode.
`FS_EKF_ACTION` is a parameter, a model may ship any value of it, and a
criterion demanding `LAND` would be testing this repository's assumption rather
than the aircraft. What it does require is the part that is true whatever the
parameter says: an airborne vehicle that loses GPS must not disarm and must not
tumble. The mode it chooses is recorded in the run's mode timeline, as evidence
for a person to read.

Fault injection was added in ArgazUI v1.4.
