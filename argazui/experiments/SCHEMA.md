# ArgazUI experiment schema — version 1

An **experiment** is a declarative, controlled comparison. It names one model,
one or more *arms* — a procedure flown a stated number of times — a set of
measurements, acceptance criteria that can only be said about a group of runs,
and the limits of what the answer covers.

Experiments live in `argazui/experiments/*.yaml`.

## What an experiment adds, and what it must never become

It adds **one thing**: a place to write down which combination of existing
pieces is being run, so that the combination itself is reviewable and
repeatable.

It composes. It does not extend.

- an arm names a procedure that already exists; it cannot describe a flight of
  its own, and there is no step list here;
- an arm is executed as an ordinary repeatability campaign, by
  `campaign.CampaignRunner`, driving the same `ProcedureRunner` the interface
  drives;
- every iteration leaves an ordinary run directory with the ordinary evidence
  in it — `result.json`, the dataflash log, the fingerprint, the evidence
  manifest, the flight report;
- there is no expression language, no conditional, no loop and no parameter
  arithmetic.

If any of that stops being true, this format has grown into the mission planner
and the simulation DSL that v1.6 was explicitly told not to build.

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

---

## Top level

```yaml
schema: 1                       # required
id: copter_gps_loss_vs_nominal  # required, must equal the filename stem
name:                           # optional, shown in the interface
  en: GPS loss against a nominal climb
  tr: Nominal tirmanisa karsi GPS kaybi
question:                       # REQUIRED — see below
  en: Does losing the position source change how well this aircraft tracks...
  tr: ...
model: iris                     # required: one registry id
values: {alt: 25}               # optional: procedure inputs, applied to every arm
arms: [...]                     # required, 1 to 4
metrics: [...]                  # required, non-empty
compare: {...}                  # required
accept: [...]                   # optional
limitations: {...}              # optional, four named categories
```

Every user-visible string (`name`, `question`, an arm's `label` and `note`, a
criterion's `message`, every limitation) is a map with `en` and `tr` keys. A
bare string is accepted and used for both languages; new files should supply
both, because both languages are release artefacts.

### `question` is required

An experiment with no stated question is a batch of runs, and the document it
produces is a table of numbers with nothing to read them against. It is the one
field here that no tool can derive, check or default, which is exactly why it
has to be written.

### `model`

One registry id, from `argazui/config/models.json`. One, because a controlled
comparison across two aircraft is not a controlled comparison. The id is
checked against the registry when the experiment is *started*, not when it is
loaded — a definition stays readable on a checkout whose registry has not been
scanned yet.

### `values`

Procedure inputs, applied to every arm, with the arm's own `values` on top.

Every name must be an input the arm's procedure declares, or the file is
rejected at load time. A typo here is silent and expensive: the procedure would
fly its default altitude, every number in the report would be about that
flight, and the document would say the experiment configured something else.

---

## `arms`

```yaml
arms:
  - id: nominal                 # required: lower case, digits, '_' or '-'
    procedure: copter_takeoff   # required: must exist in argazui/procedures/
    runs: 3                     # required: 1 to 50
    role: reference             # optional: reference | treatment (default)
    values: {alt: 25}           # optional: overrides the experiment's values
    label: {en: ..., tr: ...}   # optional
    note: {en: ..., tr: ...}    # optional
```

An arm is *"this procedure, this many times"*, and it is executed as a
repeatability campaign — so an arm **is** a campaign, findable and aggregatable
by every tool that already reads campaigns. The experiment is the statement
that these particular campaigns belong to one question.

At most **four** arms. Beyond that the document stops being a controlled
comparison and becomes a matrix nobody checks.

`runs: 1` is allowed and is honest: the analysis reports `n=1`, refuses to print
a standard deviation, and marks any delta computed from that arm as
**indicative** rather than measured.

Exactly one arm carries `role: reference` under the `arms` policy — it is the
side every delta is measured from.

---

## `metrics`

```yaml
metrics:
  - tracking_error_roll_rms
  - peak_angular_rate
```

Keys from the metric catalogue in `argazui/argazui/metrics.py`; an unknown key
is rejected with the list of known ones. Only these are reported, and **only
these may be judged** — a criterion may not rest on a number the document does
not show.

Within an experiment a metric is identified by its **key alone**, not by
`key@procedure` as everywhere else in this project. That is deliberate and it
is the one place the rule inverts: the arms deliberately fly different
procedures, and the whole question is what the same quantity did under the two
conditions. The procedures each number came from are listed beside it in the
report.

---

## `compare`

```yaml
compare:
  policy: arms                  # arms | baseline | repeats
  reference_arm: nominal        # required under 'arms', refused under the others
```

| policy | what it compares | shape |
|---|---|---|
| `arms` | every other arm against the reference arm | 2 to 4 arms, one `role: reference` |
| `baseline` | each arm against its own earlier run of this experiment | any number of arms, no reference arm |
| `repeats` | nothing — distributions only | exactly one arm |

The policy is stated rather than inferred from the arm count. "Two arms and no
comparison" is a real and honest thing to run — two independent repeatability
measurements — and guessing that it must be a controlled comparison would
invent a claim nobody made.

---

## `accept`

Acceptance criteria **about a group of runs**. Criteria about a single flight
already exist in the procedure and are not repeated here.

```yaml
accept:
  - id: nominal-reliable        # optional; derived as a1, a2, ... when absent
    arm: nominal                # required: an arm of this experiment
    min_pass_rate: 1.0          # shape 1
    message: {en: ..., tr: ...}

  - id: climb-not-slower
    arm: gps_loss
    metric: time_to_target_alt  # shape 2: bounds on the arm's mean
    min: 0
    max: 40

  - id: roll-tracking
    arm: gps_loss
    metric: tracking_error_roll_rms
    max_delta: 3.0              # shape 3: distance from another arm's mean
    delta_vs: nominal
```

Exactly one of the three shapes per criterion:

| shape | keys | judged on |
|---|---|---|
| pass rate | `min_pass_rate` | the arm's **clean** pass rate — a retry counts as `flaky`, never as a pass |
| range | `min` and/or `max` + `metric` | the arm's mean of that metric |
| delta | `max_delta` + `delta_vs` + `metric` | the absolute distance between two arms' means |

A criterion that judges two things at once has no single reason for its
verdict, so combining them is refused at load time.

**There is no `significant`, no `within_one_stdev` and no `95%`.** Every one of
those is a statistical claim, and at the sample sizes a SITL campaign produces
none of them would mean what it says. The document reports `n` beside every
number instead.

A criterion that could not be judged — because no run measured the metric, or
because the arm it is measured from has none — is reported as **not judged**,
and the experiment's verdict becomes `incomplete`. It is never counted as a
pass.

---

## `limitations`

Four named categories, each a list of statements. All four are optional.

```yaml
limitations:
  assumptions:
    - en: GPS loss is simulated by switching the SITL receiver off...
      tr: GPS kaybi, SITL alicisi kapatilarak simule edilir...
  model_limitations: [...]
  unverified_effects: [...]
  out_of_scope: [...]
```

| category | what belongs in it |
|---|---|
| `assumptions` | what had to be true for the numbers to mean anything — the one kind of limit a reader can go and check |
| `model_limitations` | what the simulated aircraft is **not**; this bounds the claim |
| `unverified_effects` | physics that was absent, or present and never compared against anything real |
| `out_of_scope` | conditions the experiment deliberately did not enter |

They are separate because a reader does something different with each. An
assumption can be checked; a model limitation bounds the claim; an unverified
effect is a reason not to extrapolate; something out of scope is a reason to
run something else. Collapsing them into one "notes" field turns four
actionable statements into a paragraph nobody reads.

An unknown category is rejected rather than kept: a statement filed under a
name the report does not print is a limit somebody wrote down and nobody ever
read, which is worse than not writing it — the author believes it was stated.

**Standing limitations are added automatically** and cannot be dropped by a
definition. They are the ones true of every experiment this tool can run, and
they are marked *(standing)* in the report so a reader can tell them from the
ones somebody wrote for this question. See
`argazui/argazui/limitations.py`.

---

## What the run directories carry

Every iteration of every arm is an ordinary run. Its `result.json` gains one
block (result schema 6):

```json
"experiment": {
  "schema": 1,
  "id": "copter_gps_loss_vs_nominal",
  "run": "20260810T124500Z_copter_gps_loss_vs_nominal",
  "arm": "gps_loss",
  "arm_role": "treatment",
  "index": 2,
  "of": 3,
  "model_id": "iris",
  "procedure_id": "copter_gps_loss",
  "policy": "arms"
}
```

The existing `campaign` block stays beside it, because the arm really is a
campaign. Stamped into the run rather than kept in an index for the same reason
a campaign is: an experiment is found by *reading its runs*, so a run that was
copied out of the tree still says what it belonged to, and a document can never
name a run that is not there.

## Producing the document

```bash
python3 -m argazui experiment                     # what is declared, what has run
python3 -m argazui experiment copter_gps_loss_vs_nominal   # newest run of it
python3 -m argazui experiment 20260810T124500Z_copter_gps_loss_vs_nominal
```

It writes `runs/experiments/<experiment-run-id>/experiment.json` and
`experiment.md`, recomputed from the run directories every time. Exit codes:
`0` the experiment was aggregated and nothing declared failed, `1` a declared
criterion did not hold, `2` there is nothing by that name.
