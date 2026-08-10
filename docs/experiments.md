# Experiments

An **experiment** is a controlled comparison declared in a file: one model, one
or more *arms* — a procedure flown a stated number of times — a set of
measurements, acceptance criteria that can only be said about a group of runs,
and the limits of what the answer covers.

## Why the layers below were not enough

Every layer this project has built answers a question about *one thing*.

| layer | answers |
|---|---|
| [procedure](acceptance-criteria.md) | what to fly, and what counts as having worked |
| [run](runs-and-evidence.md) | what happened this time |
| [campaign](campaigns.md) | does it happen the same way N times |
| [regression](regression.md) | is it worse than a named baseline |
| [fault injection](fault-injection.md) | what does it do when something is broken |

What none of them can say is the question an engineer actually turns up with:

> Does losing GPS during the climb change how this aircraft holds altitude,
> compared with the same climb when nothing is wrong?

Answering it needs a *controlled* set of runs: the same model, the same
configuration, a nominal group and a faulted group, a stated number of
repetitions, a named set of measurements and a criterion decided in advance.
Every one of those pieces already existed. What did not exist was a place to
write down which combination of them is being run — so that the combination
itself is reviewable, versionable and repeatable.

## It composes; it does not extend

An experiment adds no new capability to the aircraft, no new step type, and no
new way of judging a flight.

- an arm names a procedure that **already exists**; it cannot describe a flight
  of its own, and there is no step list in an experiment file;
- an arm is executed by `campaign.CampaignRunner`, driving the same
  `ProcedureRunner` the interface drives — there is no second execution engine;
- every iteration leaves an **ordinary run directory** with the ordinary
  evidence in it: `result.json`, the dataflash log, the fingerprint, the
  evidence manifest, the flight report;
- there is no expression language, no conditional and no loop.

## Why it is called an experiment and not a scenario

The v1.6 architecture calls this object a *scenario*. This repository has used
that word since v1.4 for something else: `applies_to.role: scenario` is an
off-nominal **procedure**, every run directory contains a `scenario.yaml`
holding the procedures that executed, and the environment fingerprint has a
`scenario` block listing the faults they declared.

Reusing the word would make three existing artefacts ambiguous, and the one
that matters most — the file a reviewer opens to see what actually ran — is the
one that would break. So the word here is `experiment`. An off-nominal
procedure is still a scenario, and an experiment may *use* one; that is exactly
what a faulted arm is.

## What an experiment file says

The full reference is
[`argazui/experiments/SCHEMA.md`](#docs=experiment-schema). In outline:

```yaml
schema: 1
id: copter_gps_loss_vs_nominal
question:                         # required — see below
  en: Does losing the position source change how well this aircraft tracks...
model: iris                       # one registry entry
values: {alt: 25}                 # procedure inputs, applied to every arm
arms:
  - {id: nominal,  procedure: copter_takeoff,  runs: 3, role: reference}
  - {id: gps_loss, procedure: copter_gps_loss, runs: 3, role: treatment}
metrics: [tracking_error_roll_rms, peak_angular_rate]
compare: {policy: arms, reference_arm: nominal}
accept:
  - {id: nominal-reliable, arm: nominal, min_pass_rate: 1.0}
  - {id: roll-tracking, arm: gps_loss, metric: tracking_error_roll_rms,
     max_delta: 3.0, delta_vs: nominal}
limitations:
  assumptions: [...]
  model_limitations: [...]
  unverified_effects: [...]
  out_of_scope: [...]
```

**`question` is required.** An experiment with no stated question is a batch of
runs, and the document it produces is a table of numbers with nothing to read
them against. It is the one field no tool can derive, check or default, which is
exactly why it has to be written.

## Structurally: an arm is a campaign

An experiment run id stamped into N ordinary run directories, and the arm's own
campaign id stamped beside it.

```
runs/
├── 20260810T124500Z_iris/   result.json → "campaign":   {"id": …-copter_takeoff-nominal, "index": 1}
│                                        → "experiment": {"run": …, "arm": "nominal", "index": 1}
├── …
├── campaigns/
│   ├── 20260810T124500Z_iris.copter_takeoff-nominal/    campaign.json / .md
│   └── 20260810T124500Z_iris.copter_gps_loss-gps_loss/  campaign.json / .md
└── experiments/
    └── 20260810T124500Z_copter_gps_loss_vs_nominal/
        ├── experiment.json
        └── experiment.md
```

Both stamps, not one. An arm really *is* a repeatability campaign, so every tool
that already reads campaigns keeps finding it, and the campaign document for
each arm is produced by the code that already produced them.

Stamped into the runs rather than kept in an index for the same reason a
campaign is: an experiment is found by **reading its runs**, so a run that was
copied out of the tree still says what it belonged to, and a document can never
name a run that is not there.

## Running one

From the interface — the **Experiments** panel: pick a declared experiment,
press RUN EXPERIMENT. It flies every arm in order, each as a campaign, each
iteration a real launch and a real shutdown.

From the shell, to see what is declared and what has actually been flown:

```bash
python3 -m argazui experiment                              # both lists
python3 -m argazui experiment copter_gps_loss_vs_nominal   # newest run of it
python3 -m argazui experiment 20260810T124500Z_copter_gps_loss_vs_nominal
```

Exit codes, because this is meant for CI:

| code | meaning |
|---|---|
| `0` | the experiment was aggregated and nothing declared failed |
| `1` | a declared criterion did not hold |
| `2` | there is no such experiment, or nothing has been flown under that name |

An **incomplete** experiment exits `0`. Arms short of their runs are a reason to
fly more, not a reason to fail a build — and a project whose CI went red for
declaring an experiment before it could be flown would learn to stop declaring
them. The same reasoning [coverage](coverage-model.md) is built on.

## The document

Ten fixed, numbered sections, in the same order and for the same reason the
[flight report](runs-and-evidence.md) has had since v1.5 — a reviewer reading
two experiments should not have to hunt for the same fact in two places.

1. Question and scope
2. Configuration
3. Execution — every arm, its campaign, its counts
4. Verdict
5. Failed criteria, and what was **not judged**
6. Measured quantities, by arm
7. Comparison — the deltas the policy asked for
8. Evidence — every run, and whether it left everything behind
9. How to reproduce this document
10. Limitations and non-claims

### Comparing by metric key, not by identity

Everywhere else in this project a metric is identified by `key@procedure`, and
that is right: "time to target altitude" means nothing without saying whose
target, and a regression comparison across two different procedures would be two
unrelated numbers subtracted.

An experiment is the case that inverts it. Its arms deliberately fly *different*
procedures — a nominal climb and the same climb with GPS taken away — and the
whole question is what the same measured quantity did under the two conditions.
Matching on identity would line up nothing at all. So within an experiment the
identity is the **key**, and the procedures each number came from are listed
beside it.

### What the analysis refuses to compute

**No p-value, no confidence interval, no effect size, no "significant".** At the
sample sizes a SITL campaign produces, every one of them would be arithmetic
that runs fine and means nothing, and each would read to a reviewer as though
the difference had been established.

What is reported instead is deliberately dull:

| | |
|---|---|
| `n` | on both sides, beside every number |
| the two means | and their difference |
| Δ% | relative to the reference arm's mean |
| ranges overlap | whether the two arms' observed spans touch at all |
| basis | `measured`, `indicative` or `none` |

An overlap is **not a significance test**. It is a statement about the numbers
actually seen, which is the only kind this sample supports.

A delta is `measured` only when both arms have at least three measured values —
the same threshold campaigns use before printing a standard deviation. Below
that it is `indicative`, and the document says so in the row.

### Verdicts

| verdict | meaning |
|---|---|
| `passed` | every declared criterion held, over the runs that were declared |
| `failed` | a criterion was judged and did not hold |
| `incomplete` | an arm is short of its runs, or a criterion was never judged |
| `not-judged` | the experiment declares no acceptance criteria — nothing was asserted |
| `not-run` | nothing carries this experiment id |

`failed` is decided before `incomplete` because a criterion that was judged and
did not hold is a result, and one that came from three runs instead of five is
still that result — the document prints `n` beside it.

A criterion that could not be judged is **never counted as a pass**. "No run
measured this" and "this held" are different facts, and only one of them is an
answer.

## Acceptance criteria about a group

Criteria about a single flight already live in the procedure and are not
repeated here. Exactly three shapes are available, and no more:

| shape | keys | judged on |
|---|---|---|
| pass rate | `min_pass_rate` | the arm's **clean** pass rate — a retry is `flaky`, never a pass |
| range | `min` / `max` + `metric` | the arm's mean of that metric |
| delta | `max_delta` + `delta_vs` + `metric` | the absolute distance between two arms' means |

A criterion may only judge a metric that is in the experiment's `metrics:` list,
or its verdict would rest on a number the report does not show.

## Limitations are part of the result

Four named categories — simulation assumptions, model limitations, unverified
physical effects, conditions outside the test scope — declared in the file and
printed as section 10, with the standing ones that apply to every experiment
this tool can run.

They are separate categories because a reader does something different with
each. See [Validation limits](validation-limits.md) for what belongs in which,
and [Verification vs validation](verification-vs-validation.md) for why an
experiment is the point at which that distinction stops being academic.

## Coverage

Experiments are the fifth [coverage](coverage-model.md) dimension, and each arm
is listed on its own — because an experiment half of whose arms were flown has
answered nothing. A comparison needs both sides.

## Where the code is

| | |
|---|---|
| `argazui/experiments.py` | the definition, its validation, and the runner that hands each arm to a campaign |
| `argazui/analysis.py` | distributions per arm, deltas between them, the verdict, the document |
| `argazui/limitations.py` | the four categories and the standing statements |
| `argazui/campaign.py` | executes every arm — unchanged by this release |
| `argazui/runs.py` | the `experiment` stamp in `result.json` (schema 6) |

Experiments were added in ArgazUI v1.6.
