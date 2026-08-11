# Acceptance criteria

An acceptance criterion is the part of a procedure that decides whether the
flight worked. It is declared in the procedure's `expect:` block, evaluated by
`ProcedureRunner` against measured vehicle state, and it is the only thing that
can turn a run red.

The complete syntax is in
[`argazui/procedures/SCHEMA.md`](../argazui/procedures/SCHEMA.md). This page is
about what the criteria *mean*.

## An ACK is not success

`MAV_RESULT_ACCEPTED` says the autopilot received a command it was willing to
consider. It says nothing about the aircraft. Every criterion in this project
is therefore evaluated against measured state — an altitude that was reached, a
mode number that came back in a heartbeat, a disarm that happened.

## Conditions

| condition | true when |
|---|---|
| `armed: true` / `false` | the armed flag matches |
| `mode: QLOITER` | the current mode matches, by number |
| `mode_in: [QLOITER, QHOVER]` | the current mode is one of these |
| `alt_above: 15` / `alt_below: 1.5` | relative altitude in metres |
| `climb_rate_above` / `climb_rate_below` | `VFR_HUD.climb`, m/s |
| `groundspeed_above: 5` | `VFR_HUD.groundspeed`, m/s |
| `prearm_ok: true` | the `SYS_STATUS` pre-arm health bit is set |
| `param: {name: Q_ENABLE, min: 1}` | the parameter is within bounds |
| `attitude_stable: {...}` | the accumulated attitude envelope held |
| `roll_within: [-20, 20]` | schema 2 — instantaneous roll, degrees |
| `pitch_within: [-20, 20]` | schema 2 — instantaneous pitch, degrees |
| `angular_rate_above: 90` | schema 2 — largest of \|p\|, \|q\|, \|r\|, deg/s |
| `angular_rate_below: 90` | schema 2 — the same quantity, the other way |

Body rates rather than the rate of change of an Euler angle: Euler angles are
degenerate at a vertical attitude, where roll and yaw describe the same
rotation, and a tailsitter spends its entire takeoff there.

## The temporal shapes

Schema 1 had exactly one shape — *is this true now, or does it become true
before a timeout?* That answers where the aircraft ended up and nothing else.
Schema 2 adds three shapes that answer **when** and **for how long**.

```yaml
schema: 2

expect:
  # BECOME true inside a deadline
  - condition: {alt_above: "{alt*0.9}"}
    within: 20s

  # become true, then REMAIN true continuously
  - condition: {alt_above: "{alt*0.9}", armed: true, mode: GUIDED}
    for: 5s

  # NOT become true at any observed moment in a window
  - condition: {angular_rate_above: 180}
    never: 5s
```

At most one temporal key per criterion. Two of them together have no single
evaluation order, and a criterion whose meaning depends on the reader is worse
than one that does not exist.

### Durations must state their unit

`10s`, `500ms`, `2min`. A bare `for: 5` is rejected at load time.

Every other number in a procedure is a metre, a degree, a PWM count or a
parameter value. A duration that looked like any of them would be read wrong
exactly once — silently, in flight, by whoever inherits the file. `m` is
deliberately not a unit here, because in a flight procedure it reads as metres.

### They are measured on the vehicle's clock

Durations are counted on `ATTITUDE.time_boot_ms`, not on `time.time()`. Under
SITL speedup a wall-clock second is not a second of flight, so a `for: 5s`
judged on arrival time would demand five times the flight it says it does — or
a fifth of it, depending which way the speedup goes.

The vehicle's clock only advances while telemetry arrives, so every window also
carries a wall-clock backstop sized from the measured speedup. If that backstop
is what ended the window, the criterion says so in its result: a wall-clock
measurement reported as though it were vehicle time would make every duration
in a run's evidence wrong by the speedup factor.

### `for:` does not restart

A lapse inside the hold window fails the criterion and reports how long it did
hold. A restarting window would let a condition that flickers on and off pass
eventually, which is the opposite of what *continuously* means.

### `never:` is a claim about what was observed

The evaluator samples vehicle state every 0.2 wall-clock seconds. An excursion
shorter than one sampling interval of vehicle time can pass between two samples
unseen, and this is stated rather than hidden: `never` is a claim about what
was observed at that rate.

`attitude_stable` remains the criterion that weighs **every** attitude sample
the vehicle sent, and it is the right tool when the question is how much time
the aircraft spent outside a band.

### Silence is never success

**Every** condition names the telemetry it rests on, and a condition whose
signal has never arrived cannot be satisfied — in any of the four shapes.

| condition | needs |
|---|---|
| `armed`, `mode`, `mode_in` | a vehicle `HEARTBEAT` |
| `alt_above`, `alt_below` | `GLOBAL_POSITION_INT` |
| `climb_rate_above`, `climb_rate_below`, `groundspeed_above` | `VFR_HUD` |
| `roll_within`, `pitch_within`, `angular_rate_*`, `attitude_stable` | `ATTITUDE` |
| `prearm_ok` | `SYS_STATUS` |
| `param` | the vehicle answering the read — it already fails closed |

The reason is that every field on the vehicle state has a default, and a
default is not a measurement. `alt` starts at 0.0 because a float has to start
somewhere; it does **not** mean the aircraft is on the ground, and by value
alone the two are identical. Until the v1.6 corrective release they were also
identical to the evaluator: `alt_below: 3` and `armed: false` — between them
the entire acceptance block of every landing procedure — both evaluated true
against a state nothing had ever written to, and the run said
`on the ground — alt=0.0m` for a flight whose position stream never arrived.

A criterion refused this way is **not evaluated**, which is a third outcome and
not a failure:

| `passed` | `evaluated` | means |
|---|---|---|
| `true` | `true` | the aircraft met the criterion |
| `false` | `true` | the aircraft did not — a verdict about the aircraft |
| `false` | `false` | nothing was measured — **not** a verdict about anything |

The run still does not pass. What changes is what it is reported as: an
unevaluated criterion is classified `evidence`, not `acceptance`, because
`acceptance` is the only category that means the aircraft did something wrong.
See [failure-classification.md](failure-classification.md).

A `for:` or a `never:` is refused **before its window opens**, because it makes
a positive claim about a stretch of time. `within:` and the schema-1 shape are
waits, so they keep waiting — telemetry that starts arriving half way through a
wait is a perfectly good flight — and are refused only if the signal is still
missing when the deadline expires.

## `attitude_stable`, and why it exists

`tailsitter_takeoff` passed three times on an aircraft that was tumbling at up
to 1300 °/s. It reached altitude, stayed armed and reported QHOVER — the only
three things the criteria asked about. Altitude is a side effect of a thrust
vector that happened to point roughly upwards.

`attitude_stable` accumulates the whole procedure's attitude and is judged in
**seconds outside a band**, not in peaks: a peak is one sample, and one sample
is a gust, a mode change or a bad reading. Each procedure declares how many of
those seconds it forgives.

Because it is already an answer about the whole procedure, it cannot also carry
a temporal key. Use the instantaneous conditions for that.

## Backward compatibility

Schema 1 files load and behave exactly as before. Temporal criteria and the
instantaneous attitude conditions require `schema: 2`, and a schema-1 file that
uses them is rejected at load time with a message saying so. Extending schema 1
in place would have been quieter and worse: an older ArgazUI would have read a
`within:` it does not implement, out of a document claiming a version it
satisfies.
