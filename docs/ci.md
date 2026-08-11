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

## Coverage is generated with the status table

`python3 -m argazui status` writes `docs/coverage.md` beside `docs/status.md`,
from the same collection of runs. Two passes over the runs could produce two
answers, and the status table's *What was NOT tested* summary and the coverage
report's full lists have to agree — so there is one pass.

`python3 -m argazui coverage` regenerates the coverage document alone. Its exit
code is always `0`: coverage is a measurement, not a gate. Turning an uncovered
procedure into a red build would make the honest thing to do — declaring a
procedure before it can be flown — the thing that breaks CI.

`python3 -m argazui trace runs/<id>` **is** a gate, and exits 1 when a link in
the chain does not resolve. A traceability scheme nobody verifies degrades
silently.

## Stale generated artefacts are a test failure

`docs/status.md` and `docs/coverage.md` are machine output and are committed, so
they can be wrong in a way source code cannot: the code moves and the document
does not. v1.6 shipped with both still describing v1.5 — most visibly,
`coverage.md` carried four dimensions while `coverage.py` declared five, so the
published report told a reader the project measures something it no longer
measures.

A byte-comparison against freshly generated output cannot be the check. Both
documents are computed from whatever runs are on disk, and that differs between
a developer's machine and a CI runner by design. What is deterministic is their
STRUCTURE, and that is exactly what went stale:

* every coverage dimension the code declares has a section in `coverage.md`,
  and `coverage.md` names no dimension the code has dropped;
* `status.md` carries the headings this generator writes;
* the README's `STATUS-SUMMARY` block names the same generation time as
  `status.md`, so a commit cannot stage one and not the other.

These live in `tests/test_identity_and_artefacts.py`, are marked `tier1`, and
therefore run on every push in the job that already exists. No new workflow and
no new CI step.

## The regression gate

Until v1.7 this section described a snippet a reader *could* add. Nothing
invoked `argazui compare`, so a metric degrading past its threshold had no
automated consumer anywhere — a regression system that exists only as code is
not yet a release gate.

`tier2.yml` now runs it, after the models have flown:

```yaml
- name: Regression gate
  if: always()
  run: python3 -m argazui gate --runs runs --baselines runs/baselines
```

It compares the newest run of each model the job flew against the committed
baseline in `runs/baselines/<model_id>/`, and returns one verdict.

### The five outcomes, and why they are five

| outcome | meaning | exit | blocks a release |
|---|---|---:|---|
| `PASS` | every compared metric held its threshold | 0 | no |
| `FAIL` | a metric degraded past its threshold | 1 | **yes** |
| `ERROR` | the comparison could not be made | 2 | no — and it fails the job |
| `SKIPPED` | there were no runs to compare | 0 | no |
| `NOT_APPLICABLE` | this model has no committed baseline yet | 0 | no |

`FAIL` and `ERROR` both fail the job and are deliberately different news. An
unreadable run, or two runs whose fingerprints do not line up, is an
**infrastructure** result: it keeps its `evidence` classification, and nothing
reads it as a verdict about an aircraft. Collapsing the two is how a
mis-specified baseline path comes to be reported as a degraded aircraft.

`SKIPPED` is not `PASS`. A job that flew nothing has verified nothing, and
reporting green for it would be the silent evaporation of evidence this file's
`if-no-files-found` note already warns about.

### Why the gate is a tier-2 step

A comparison needs a flight, and tier 2 is where models fly. What runs on every
push is everything about the comparison that does **not** need an aircraft: the
compatibility rules, the delta arithmetic and its floors, the five outcomes,
and that an infrastructure error is not reported as a degraded aircraft. Those
are pure tests, they take about a second, and `tier1.yml` runs them by name in
a *Deterministic regression verification* step so their result is exposed
rather than buried in a total of six hundred.

```
PR / every push          unit + integration + deterministic regression
nightly / release        the above, plus the models, plus the gate
```

### Baselines

A baseline is an ordinary run directory committed under `runs/baselines/`, not
a format of its own — see [its README](../runs/baselines/README.md). Give the
gate an explicit baselines root. `argazui compare`'s no-baseline form picks the
newest earlier run of the same model, which is a convenience for the interface;
in a pipeline it would make what a comparison was measured against depend on
whatever happened to be on disk that day.

## The model environment is verified before anything flies

`tier2.yml` runs `python3 -m argazui doctor --release` before it launches a
single model. `--release` applies the stricter of the two model-environment
thresholds: the assets must be one immutable revision with no uncommitted
changes, not merely undisputed. See [Reproducibility](reproducibility.md).

A nightly that flew a different `SITL_Models` from the one `argaz.toml`
declares would publish model rows nobody could repeat, and the failure would be
invisible because every row would still be green. So the job fails — as a
**configuration** problem, before any model is launched, so that no model is
ever recorded `failed` for it.

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
