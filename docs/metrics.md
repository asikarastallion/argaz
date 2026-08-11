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

| key | unit | clock | window | scope | derived from |
|---|---|---|---|---|---|
| `time_to_target_alt` | s | vehicle | armed | procedure | `POS.RelHomeAlt` against the altitude the procedure asked for, measured from arming |
| `tracking_error_roll_max` | deg | vehicle | log | run | `ATT.DesRoll - ATT.Roll` |
| `tracking_error_pitch_max` | deg | vehicle | log | run | `ATT.DesPitch - ATT.Pitch` |
| `tracking_error_roll_rms` | deg | vehicle | log | run | the same difference, root mean square |
| `tracking_error_pitch_rms` | deg | vehicle | log | run | the same difference, root mean square |
| `peak_angular_rate` | deg/s | vehicle | log | run | `IMU.GyrX/GyrY/GyrZ`, largest magnitude on any axis |
| `time_outside_attitude_envelope` | s | vehicle | armed | run | `ATT.Roll`/`ATT.Pitch` against the envelope the procedure declared, over the armed interval(s) |
| `mode_transition_latency_max` | s | vehicle | procedure | procedure | the duration of each `set_mode` step **on the vehicle's own clock**, ending when the heartbeat confirms the new mode by number |

Every one of these reads better lower, but the direction is recorded explicitly
per metric rather than assumed: a comparator that hard-codes "smaller is
better" reports the wrong verdict the first time a metric like "altitude held"
is added.

### Why this small set

Each entry answers a question someone actually asks of a flight, and each names
the signal it came from. A module that computed everything computable would
produce a wall of numbers with no stated meaning, and the first regression
comparison would drown in noise from quantities nobody chose to watch.

## Clock and window

Two numbers of seconds are the same quantity only if they were taken on the
same clock, over the same stretch of the flight. Both are stated per metric and
both travel with the value in `result.json`, so a comparison written later does
not have to resolve them against whatever the code says today.

| clock | |
|---|---|
| `vehicle` | the aircraft's own clock — the dataflash `TimeUS`, or `ATTITUDE.time_boot_ms` live. Every published metric is on this one. |
| `wall` | this process's clock. Recorded only as an honest fallback when the vehicle's clock was not running during the measurement. |

Under SITL speedup a wall-clock second is not a second of flight, so the two
differ by the speedup factor. `mode_transition_latency_max` was on the host
clock until the v1.6 corrective release — the only metric derived from a
recorded step rather than from the log — so comparing two runs flown at
different speedups reported a regression caused by a command-line argument.

| window | |
|---|---|
| `procedure` | from the first step of a procedure to its last criterion |
| `armed` | the armed interval(s) the dataflash log records — the flight |
| `log` | every record in the log, including time on the ground |

`time_outside_attitude_envelope` and the `attitude_stable` acceptance criterion
share a name and a set of bands and **do not share a window**: the criterion is
scoped to its own procedure, the metric to the log's armed interval(s). Before
the corrective release the metric covered the whole log, so a tailsitter parked
on a runway with a [55,115]° pitch band was "outside the envelope" for every
second it sat still — and the two could report 0.0 s and 40 s for one flight
with nothing saying they answered different questions. They are now close
enough to read together, and `window` states the difference that remains.

`argazui compare` refuses to subtract two metrics that disagree on either
field, and says which.

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
