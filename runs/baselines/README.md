# Regression baselines

## Status: seven baselines, from one clean flight

| model | procedures | metrics | source run |
|---|---|---:|---|
| `alti_transition_quad` | `vtol_takeoff`, `vtol_land` | 8 | `20260812T073525Z_alti_transition_quad` |
| `bicopter` | `copter_takeoff`, `copter_land` | 9 | `20260812T073659Z_bicopter` |
| `hexapod_copter` | `copter_takeoff`, `copter_land` | 9 | `20260812T073904Z_hexapod_copter` |
| `mini_talon_vtail` | `plane_takeoff`, `plane_land` | 8 | `20260812T075504Z_mini_talon_vtail` |
| `skywalker_x8` | `plane_takeoff`, `plane_land` | 9 | `20260812T074209Z_skywalker_x8` |
| `skywalker_x8_quad` | `vtol_takeoff`, `vtol_land` | 8 | `20260812T074514Z_skywalker_x8_quad` |
| `wsc_aircraft` | `plane_takeoff`, `plane_land` | 9 | `20260812T075216Z_wsc_aircraft` |

All seven were flown in one tier-2 suite run whose environment was:

```
SITL_Models   25bc38ed8c6c0345840159a8cbc0b02781d52f3c   state: pinned
              identity sha256:811fa669b5cf854c1db9da9771fbdfff
ArduPilot     0b38722bd5a46099dbe7d50074624680f58ce584   firmware 0b38722b
Gazebo        Sim 8.14.0
```

`python3 -m argazui doctor --release` passed on that machine, which is the
threshold this directory requires: one immutable revision, clean working tree.

### The four models with no baseline, and why

| model | why not |
|---|---|
| `zephyr` | verdict `failed` — a hand-launched wing against a runway takeoff. A baseline is a statement about how an aircraft *should* fly; a partial flight's numbers are not one. |
| `skycat_tvbs` | verdict `failed` — the tailsitter band is not held. Same reason. |
| `swan_k1_hwing` | never passes pre-arm, so it produced no metrics at all. `compare` hard-blocks a run with no metrics, so a baseline could not be used even if one existed. |
| `iris` | skipped — needs a built `ardupilot_gz` workspace, so it has never flown here. |

For all four the gate reports `NOT_APPLICABLE`, which is the accurate answer:
there is nothing to compare against, and that is not a pass and not a failure.
Their verdicts are tracked by [status.md](../../docs/status.md), which is where
a *verdict* belongs; this directory tracks *metrics*.

### Read this before gating on them

The gate returned `PASS 7, NOT_APPLICABLE 3` immediately after these baselines
were created — but each run was being compared against a baseline copied from
itself, so that PASS was arithmetic rather than evidence.

An **independent second tier-2 flight**, same machine, same pinned environment,
minutes later, against these same baselines, returned `PASS 3, FAIL 4`. The
comparisons were valid — `fingerprint.differences()` reports no drift — so the
movement is run-to-run variance of the simulation, and its direction confirms
that: some metrics improved and some degraded.

Measured across all seven pairs, against the 10 % default tolerance:

| metric | max \|Δ\| | gateable today |
|---|---:|---|
| `peak_angular_rate` | 113.4 % | **no** |
| `tracking_error_roll_max` | 50.0 % | **no** |
| `tracking_error_pitch_max` | 15.0 % | **no** |
| `tracking_error_roll_rms` | 7.1 % | yes |
| `time_outside_attitude_envelope` | 2.9 % | yes |
| `tracking_error_pitch_rms` | 2.2 % | yes |
| `time_to_target_alt` | 1.6 % | yes |
| `mode_transition_latency_max` | 0.0 % | yes |

Every unstable metric is a **maximum**; every stable one is an RMS, a total or
a time. A maximum is decided by one sample out of thousands and inherits the
variance of the noisiest instant in the flight.

**The thresholds were deliberately not tuned to make this green.** Two runs are
not a distribution — `campaign.py` refuses to report a spread from fewer than
three samples, and a tolerance chosen to fit one comparison is a number
pretending to be a measurement. A repeatability campaign per model is what
would justify setting `[regression.tolerance]` for the three max-metrics.

Until then these baselines are sound and the gate is honest, and the nightly
will report `FAIL` on those metrics.
[docs/V1.7_ENGINEERING_VERIFICATION.md](../../docs/V1.7_ENGINEERING_VERIFICATION.md)
§16.5 carries the full numbers.

---

One directory per model, named exactly as the model's `id` in
`argazui/config/models.json`:

```
runs/baselines/
  skywalker_x8/
    result.json
    fingerprint.json
    versions.txt
    scenario.yaml
```

`python3 -m argazui gate --runs runs --baselines runs/baselines` compares the
newest run of each model this job flew against the directory that bears its
name, and returns one verdict. `.github/workflows/tier2.yml` runs it.

## A baseline is a run, not a file format

There is deliberately no schema of its own. A baseline directory is an
ordinary run directory, and `regression.load_run` reads it with the same code
that reads any other — so a baseline can be opened, re-reported and traced
exactly like the flight it came from, and inventing a summary format for it
would have been a claim with no flight underneath.

## What is committed, and what is left out

Committed: `result.json` (the metrics and the verdict), `fingerprint.json` (the
environment those metrics were measured in), `versions.txt` and
`scenario.yaml`.

Left out: the dataflash `.BIN`, the plots and the console log. They are
megabytes each, `git` is not where they belong, and nothing in a comparison
reads them — `compare` works from `result.json`'s metrics and the fingerprint.
The run they came from is named in `result.json`, and the tier-2 workflow keeps
its full artefacts for 30 days.

The consequence is stated rather than hidden: a baseline in this directory
cannot have its metrics re-derived from its own log. It is a record of a
measurement, not a re-runnable flight.

## Adding or replacing one

A baseline is a claim that this is how the aircraft *should* fly, so it is
replaced deliberately and never automatically:

1. Fly the model, on a machine or an image whose model environment is
   `pinned` — `python3 -m argazui doctor --release` must pass, or the baseline
   records numbers nobody can reproduce.
2. Copy the four files above out of the run directory.
3. Commit, with the run id and the reason in the message.

## Why a comparison may refuse

`compare` blocks on a different model or a different procedure set, and reports
configuration drift for any of `fingerprint.IDENTITY_FIELDS` — the model
configuration hash, the procedure hash, the ArduPilot commit and working tree,
the Gazebo version, and the model assets. That is not the gate being awkward: a
baseline flown on a different airframe or a different autopilot has not shown
that anything got worse, and the gate reports `ERROR` rather than `FAIL` so
nobody reads it as a verdict about the aircraft.

Replacing a baseline is therefore the correct response to a deliberate
firmware or model change, and `--ignore-config-drift` is the wrong one for CI.
