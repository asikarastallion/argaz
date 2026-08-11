# Regression

A run says whether its acceptance criteria held. That is a verdict about one
flight against limits somebody declared, and it cannot see the thing that
actually happens to a simulation project over months: **every criterion still
passes, and the aircraft is quietly getting worse at flying.** Tracking error
creeps up, the climb takes four seconds longer, a mode change that used to
confirm in 100 ms now takes two.

Nothing fails, and something is wrong. Comparing a run's [metrics](metrics.md)
against a named baseline is how that becomes visible.

## Running one

```bash
# explicit baseline — this is what CI should do
python3 -m argazui compare runs/20260809T101500Z_iris \
        --baseline runs/20260801T090000Z_iris

# convenience: the newest earlier run of the same model
python3 -m argazui compare runs/20260809T101500Z_iris

# compare anyway, across a firmware or procedure change
python3 -m argazui compare <current> --baseline <baseline> --ignore-config-drift
```

It writes `regression.json` and `regression.md` into the current run's
directory. The interface exposes the same thing through
`GET /api/runs/<id>/compare`.

## Exit codes

| code | meaning |
|---|---|
| `0` | no metric degraded past its threshold |
| `1` | at least one did — **this is the regression signal** |
| `2` | the runs could not be compared, or could not be read |

`2` is separate from `1` on purpose. "These runs do not line up" is not the
same news as "this build got worse", and a pipeline that treated them alike
would eventually report a mis-specified baseline as a regression.

## Two runs are not comparable just because they exist

This is the strict part, and it is the reason
[the environment fingerprint](reproducibility.md) exists. A comparison across a
different model, a different procedure, a different ArduPilot or an edited
parameter file is not a measurement of anything — it is two unrelated numbers
subtracted.

**Hard incomparable**, with no flag to override it:

- a different model,
- a different set of procedures,
- either side having no metrics at all (a run from before v1.3, or one whose
  flight report was never generated — `argazui report <run>` fixes that).

**Configuration drift** — reported field by field, and `incomparable` by
default:

- the procedure content hash changed,
- the model configuration or one of its parameter files changed,
- the ArduPilot checkout or the firmware binary changed,
- any of those is unknown on either side.

`--ignore-config-drift` compares anyway and still prints what changed, because
"I changed the firmware and I want to see what that did to the numbers" is a
real question. It just has to be asked out loud.

Nothing is ever compared silently.

## Verdicts

Per metric: `improved`, `degraded`, `unchanged`, `incomparable`.
Overall: `passed`, `regressed`, `incomparable`.

A metric is `unchanged` when it moved by less than its **relative tolerance**
*or* by less than its **absolute floor**.

### Why there is a floor as well as a percentage

An RMS tracking error of 0.02° that becomes 0.04° is +100% and means nothing:
both numbers are noise. Judging purely on the relative change would fill CI
with red for quantities that are, in engineering terms, identical. The floor is
roughly the resolution at which each measurement means anything.

A baseline of exactly zero has no percentage at all, and the floor is then the
only test there is — which is the case it was added for.

## Thresholds

Defaults: 10% relative, and a per-metric floor. 10% is not a law of nature; it
is the point below which SITL's own run-to-run scatter dominates, measured on
repeated tier-1 takeoffs of the same frame.

| metric | floor |
|---|---|
| `time_to_target_alt` | 0.5 s |
| `tracking_error_roll_max` / `_pitch_max` | 1.0° |
| `tracking_error_roll_rms` / `_pitch_rms` | 0.1° |
| `peak_angular_rate` | 2.0 °/s |
| `time_outside_attitude_envelope` | 0.2 s |
| `mode_transition_latency_max` | 0.1 s |

Override in `argaz.toml`:

```toml
[regression]
default_tolerance = 0.10

[regression.tolerance]
peak_angular_rate = 0.25

[regression.floor]
time_to_target_alt = 1.0
```

## No database

A baseline is a run directory. Comparisons read `result.json` and write
`regression.json` beside the current run. That is the whole storage design, and
it is deliberate: the evidence for a comparison should be readable with the
same tools as the evidence for a flight.

## What a regression is not

Metrics are measurements, not acceptance criteria. A regression here does not
mean a criterion failed. It means the aircraft is doing the same thing
measurably less well than the baseline did — which is a reason to look, and
sometimes a reason to move the baseline.

## The CI gate

`argazui compare` answers one question about one pair of runs. What CI needs is
the question one level out — *did anything this job flew get worse than its
committed baseline* — with a single verdict and the outcomes kept apart.

```
python3 -m argazui gate --runs runs --baselines runs/baselines
```

The audit's finding was that nothing consumed this layer at all: the exit-code
contract above was documented and no workflow invoked it. `tier2.yml` now does,
after the models have flown.

| outcome | meaning | exit | blocks a release |
|---|---|---:|---|
| `PASS` | every compared metric held its threshold | 0 | no |
| `FAIL` | a metric degraded past its threshold | 1 | **yes** |
| `ERROR` | the comparison could not be made | 2 | no — and it fails the job |
| `SKIPPED` | there were no runs to compare | 0 | no |
| `NOT_APPLICABLE` | this model has no committed baseline yet | 0 | no |

`FAIL` outranks `ERROR` when models disagree, deliberately: a measured
degradation is a fact about an aircraft, and burying it under "one of the other
models had an unreadable baseline" is the more expensive mistake of the two.

`SKIPPED` is not `PASS`, for the same reason a skipped test is not a passing
one. A job that flew nothing has verified nothing.

Every pair the gate judges still writes the ordinary `regression.json` and
`regression.md` into the run directory, so the evidence for a gate decision is
an artefact anybody can open — there is no separate CI reporting format.

A baseline is an ordinary run directory committed under `runs/baselines/`; see
[its README](../runs/baselines/README.md) for what is kept and why.
