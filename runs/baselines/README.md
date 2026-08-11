# Regression baselines

## Status: empty, deliberately

No baseline is committed yet, so `argazui gate` reports `NOT_APPLICABLE` for
every model and exits 0. That is a real outcome rather than a placeholder — one
of the five the gate distinguishes — and it is the correct one until a
release-clean flight exists to seed it from.

v1.7's own tier-2 run could have seeded it and was not used, because the
machine that flew it reports the model environment as `modified`: the
`SITL_Models` checkout carries one uncommitted line
(`Q_ENABLE 1` in `Gazebo/config/alti_transition_quad.param`). Committing
numbers measured in that environment would put a reference nobody can reproduce
at the centre of the release gate, which is the defect the pin exists to
prevent — and it would break rule 1 below on the first day.

The first nightly whose `doctor --release` passes is what should populate this
directory.

*(Separately: an edit that a model genuinely needs belongs in that model's
`sitl_param_overrides` in `argazui/config/models.json`, which `model.config_hash`
covers, rather than as an undeclared change to a third-party checkout that no
hash can see.)*

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
