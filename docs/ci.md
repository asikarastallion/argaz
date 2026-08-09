# CI/CD

Three workflows, and the boundary between them is the same boundary the whole
project rests on: **only tier 2 may say anything about a model.**

| workflow | when | what it proves |
|---|---|---|
| `tier1.yml` | every push and pull request | procedure logic, the HTTP/WebSocket layer, the page. Nothing about any model. |
| `tier2.yml` | nightly at 03:00 UTC, and on demand | the real model set, in Gazebo. The only source of model rows in [status.md](status.md). |
| `status.yml` | after a tier run | regenerates `docs/status.md` from the artefacts and commits it |

## Images are pulled, never built

Compiling ArduPilot on every push would put tier 1 an hour past its budget. The
tier-2 image is 10.3 GB (Gazebo Harmonic + ROS 2 Jazzy + ArduPilot +
SITL_Models + ardupilot_gazebo) and a hosted runner has about 14 GB free before
the reclaim step — pulling it is close to the limit and building it there is
closer still. Both images are built by a separate `images` workflow.

The checkout is mounted over the copy baked into the image, so the code under
test is the commit that triggered the run.

## What is uploaded, and why even on failure

Every run leaves a directory: dataflash log, parameter dump, post-flight
report, environment fingerprint, and the `suite.json` that `docs/status.md` is
generated from. It is uploaded whether the job passed or failed, **because a
failure is a result too** — and because a red run is the one somebody actually
needs to read.

## docs/status.md is generated, and the loop is deliberately broken

`status.yml` regenerates the table and commits it. Two guards keep that from
starting an endless cycle:

- `tier1.yml` ignores pushes that only touch `docs/**`;
- the bot's commit carries `[skip ci]`, because it also rewrites the
  `STATUS-SUMMARY` block in `README.md`, which is **not** under `docs/`. A
  human editing the README should still run the tests, so the exemption is
  scoped to that one commit rather than to the file.

## Adding a regression gate

`argazui compare` is built for this: exit `0` for no regression, `1` for a
degradation, `2` for runs that could not be compared. See
[Regression](regression.md).

```yaml
- name: Compare against the baseline
  run: |
    python3 -m argazui compare "runs/$CURRENT" --baseline "runs/$BASELINE"
```

Give it an explicit baseline. The no-baseline form picks the newest earlier run
of the same model, which is a convenience for the interface — in a pipeline it
would make what a comparison was measured against depend on whatever happened
to be on disk that day.

## If tier 2 cannot run on a hosted runner

Point it at your own machine; nothing else changes.

1. Settings → Actions → Runners → New self-hosted runner
2. Change `runs-on: ubuntu-latest` to `runs-on: self-hosted` in `tier2.yml`
3. The machine needs Docker and ~30 GB free. No display is required — ArgazUI
   launches Gazebo server-only when it finds none.

A tier 2 that cannot run is reported as `untested`. A tier 2 that reported
green without flying anything would be worse than no tier 2 at all.

## Running the tiers locally

See [Development/Testing](testing.md).
