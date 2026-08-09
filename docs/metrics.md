# Metrics

A metric is a number derived from evidence a flight already produced. It is
**not** an acceptance criterion and it cannot fail a run.

That separation is the same one advisories already have:

| | decided by | can fail a run? | threshold from |
|---|---|---|---|
| acceptance criteria | the procedure's `expect:` block | **yes** | the procedure |
| advisories | `flightlog.py` | no | ArduPilot's documentation |
| metrics | `metrics.py` | no | nothing, until compared |

A metric acquires a threshold only when it is compared against a baseline — see
[Regression](regression.md). Giving it one here would have turned this into a
second acceptance system with limits nobody declared in a procedure.

## The catalogue

| key | unit | scope | derived from |
|---|---|---|---|
| `time_to_target_alt` | s | procedure | `POS.RelHomeAlt` against the altitude the procedure asked for, measured from arming |
| `tracking_error_roll_max` | deg | run | `ATT.DesRoll - ATT.Roll` |
| `tracking_error_pitch_max` | deg | run | `ATT.DesPitch - ATT.Pitch` |
| `tracking_error_roll_rms` | deg | run | the same difference, root mean square |
| `tracking_error_pitch_rms` | deg | run | the same difference, root mean square |
| `peak_angular_rate` | deg/s | run | `IMU.GyrX/GyrY/GyrZ`, largest magnitude on any axis |
| `time_outside_attitude_envelope` | s | run | `ATT.Roll`/`ATT.Pitch` against the envelope the procedure declared |
| `mode_transition_latency_max` | s | procedure | the recorded duration of each `set_mode` step, which ends when the heartbeat confirms the new mode **by number** |

Every one of these reads better lower, but the direction is recorded explicitly
per metric rather than assumed: a comparator that hard-codes "smaller is
better" reports the wrong verdict the first time a metric like "altitude held"
is added.

### Why this small set

Each entry answers a question someone actually asks of a flight, and each names
the signal it came from. A module that computed everything computable would
produce a wall of numbers with no stated meaning, and the first regression
comparison would drown in noise from quantities nobody chose to watch.

## Identity

A metric is identified by its `key` plus its `procedure`.

- **Run-scoped** metrics come from the dataflash log, which covers the whole
  session, and carry no procedure.
- **Procedure-scoped** metrics name the procedure they belong to. "Time to
  target altitude" means nothing without saying whose target.

## What the log knows and what it does not

The dataflash log knows what the aircraft did. It does not know what the
aircraft was *told* to do. Target altitudes, the declared attitude envelope and
the measured mode-change durations all come from the run's own `result.json`,
and that is the only coupling between `flightlog.py` and the procedure system.

## Absent is not zero

A metric that cannot be derived is emitted with `value: null` and a stated
reason — "no procedure in this run declared a target altitude", "the log
carries no IMU records" — rather than left out. An absent key and a measurement
that could not be made look identical to a reader, and only one of them is a
fact.

## Where they appear

| | |
|---|---|
| `runs/<id>/report.json` | the full list, alongside the series it was computed from |
| `runs/<id>/report.md` | a table, under **Metrics** |
| `runs/<id>/result.json` | the same list, copied so a comparison reads one document per run |
| `runs/<id>/regression.json` | baseline against current, with a verdict per metric |

Metrics were added in ArgazUI v1.3. A run recorded before that has none;
`argazui report <run>` regenerates them from the log it already archived.
