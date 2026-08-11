# Changelog

## v1.6.1 — 2026-08-11 — corrective release

### What this release is about

Nothing new. An independent engineering audit of v1.6
([docs/FINAL_V1.6_ENGINEERING_AUDIT.md](docs/FINAL_V1.6_ENGINEERING_AUDIT.md))
found two defects that reach the verification result itself, and eight more
beside them. This release closes them and adds no capability.

### The two that mattered

**A criterion could pass on telemetry that never arrived.** The runner had a
guard for exactly this — `_unmeasurable()` — and it was wired into two of the
four criterion shapes, consulting a table that named attitude and pre-arm and
nothing else. So `alt_below: 3` and `armed: false`, which are between them the
*entire* acceptance block of all four landing procedures, both evaluated true
against a `VehicleState` that had never received a message. 0.0 is what a float
starts as; it is not a measurement, and by value alone a landed aircraft and a
dead position stream are identical. A run said `on the ground — alt=0.0m` and
there was no way to tell which one it meant.

Every condition now names the signal it rests on, the guard runs inside
`_check` where all four shapes and every `wait_for:` step pass through it, and
a criterion refused this way is `evaluated: false` — a third outcome that is
neither a pass nor a verdict about the aircraft.

**A broken simulator was reported as a broken aircraft.** `failures.py` opens
by saying `acceptance` is the only category that means the aircraft did
something wrong, and that conflating the categories "is how a broken harness
comes to be reported as a broken aircraft". It then did that: a fault mechanism
absent from the firmware, an operator cancel, the overall timeout, a fault
start condition that never held and a malformed placeholder all classified
`acceptance`. The cause was structural — an abort leaves skipped steps and
unevaluated criteria behind, and the classifier read that residue instead of
the cause. The runner records `result["abort"]` now and the classifier
dispatches on it first.

### Everything else

- **Metric clock.** `mode_transition_latency_max` was host wall-clock seconds
  in a catalogue of vehicle-clock seconds, so two runs flown at different SITL
  speedups reported a regression caused by a command-line argument. It is on
  the vehicle's clock; every metric now states its `clock`, and `argazui
  compare` refuses to subtract two that disagree.
- **Metric window.** `time_outside_attitude_envelope` covered the whole log
  while the `attitude_stable` criterion sharing its name and its bands covered
  one procedure — so a tailsitter parked on a runway was "outside the envelope"
  for every second it sat still. Scoped to the armed interval, with `window`
  stating the difference that remains.
- **Shell quoting.** Registry values reached an interactive bash session
  unquoted, so a model whose `frame` read `quad; touch /tmp/x` ran `touch`.
  Every interpolated value is quoted per path segment, which keeps the
  `$SITL_MODELS` expansion every shipped model depends on. Newlines are
  refused outright.
- **Repeatability initial state.** SITL's working directory is reused, so each
  campaign iteration inherited the previous one's `eeprom.bin` — while the
  fingerprint hashed the `.param` file and could not see it. `sim_vehicle.py
  -w` on every launch; `persist_eeprom: true` to opt out; `initial_state` in
  every run record, read back out of the commands that were actually typed.
- **Fingerprint identity.** `dirty` and `gazebo.version` were captured and
  compared by nothing. `dirty` is now a content digest of the uncommitted work
  rather than a flag, because a boolean cannot tell "two different work states"
  from "the same one twice" — and refusing the second would make the
  regression layer unusable during development.
- **Evaluated state.** Three modules recovered "was this judged" by
  substring-matching translated prose, with three different rules, and
  disagreed: the status table published a criterion refused for missing
  telemetry as an aircraft failure while the traceability chain and the
  coverage report correctly called it unevaluated. It is a boolean field.
- **Environment failures.** A procedure run against a simulator that never came
  up timed out step by step and was classified `procedure`. It now refuses to
  start without a heartbeat and classifies `environment`.
- **Generated artefacts.** `docs/status.md` and `docs/coverage.md` still
  described v1.5; `coverage.md` carried four dimensions against code declaring
  five. Both regenerated, and `tests/test_identity_and_artefacts.py` fails on
  the structural staleness that shipped.

### Tests

Four new files — `test_evidence_guard.py`, `test_abort_classification.py`,
`test_launch_safety.py`, `test_metric_semantics.py`,
`test_identity_and_artefacts.py` — carrying the audit's original probes as
permanent regression tests, including the ones that prove the fixes are not
blunt: a measured criterion still passes, a measured violation is still an
`acceptance` failure, and `sitl_tailsitter` still fails for the right reason.

The shell-quoting tests run the generated line under a real `bash` with
`sim_vehicle.py` replaced by a function that prints its arguments, because
asserting on the generated string only proves it looks like what the author
expected.

### Known limits, unchanged

`sitl_tailsitter` still fails tier 1 deliberately, and three models still fail
tier 2 for the reasons v1.6 recorded. See `docs/status.md`.

## v1.6.0 — 2026-08-11

### What this release is about

v1.3 made a run measurable. v1.4 made it repeatable and its failures
diagnosable. v1.5 made it auditable. Every one of those answers a question
about **one thing** — this flight, these five flights, this claim and the file
under it.

The question an engineer actually turns up with is not shaped like that:

> Does losing GPS during the climb change how this aircraft holds altitude,
> compared with the same climb when nothing is wrong?

Answering it needs a *controlled* set of runs — same model, same configuration,
a nominal group and a faulted group, a stated number of repetitions, a named
set of measurements, and a criterion decided in advance. Every one of those
pieces already existed here. What did not exist was anywhere to write down
**which combination of them is being run**, so that the combination itself
could be reviewed, versioned and repeated.

That file is an experiment.

### It composes; it does not extend

This is the part of the release that is deliberately boring, and it is the
requirement the architecture was most explicit about: **do not create a second
execution engine.**

- an arm names a procedure that already exists — there is no step list in an
  experiment file, no expression language, no conditional and no loop;
- an arm is handed to `campaign.CampaignRunner`, which drives the same
  `ProcedureRunner` the button drives;
- every iteration leaves the **ordinary run directory**: `result.json`, the
  dataflash log, the fingerprint, the evidence manifest, the flight report.

`ExperimentRunner` owns the order of the arms and the identity that ties their
runs together. That is all it owns. `campaign.py` was not modified by this
release.

An arm *is* a campaign, and its runs carry **both** stamps — the campaign one
and the experiment one. A run that dropped its campaign id to carry an
experiment id would have vanished from every campaign tool in the project.

### Why it is called an experiment and not a scenario

The architecture calls this object a *scenario*. This repository has used that
word since v1.4 for something else: `applies_to.role: scenario` is an
off-nominal **procedure**, every run directory contains a `scenario.yaml`
holding the procedures that executed, and the environment fingerprint has a
`scenario` block listing the faults they declared.

Reusing the word would have made three existing artefacts ambiguous, and the
one that matters most — the file a reviewer opens to see what actually ran — is
the one that would have broken. An off-nominal procedure is still a scenario; a
faulted arm is an experiment *using* one.

### What an experiment declares

```yaml
schema: 1
id: copter_gps_loss_vs_nominal
question: {en: "Does losing the position source change how well it tracks...", tr: "..."}
model: iris
values: {alt: 25}
arms:
  - {id: nominal,  procedure: copter_takeoff,  runs: 3, role: reference}
  - {id: gps_loss, procedure: copter_gps_loss, runs: 3, role: treatment}
metrics: [tracking_error_roll_rms, peak_angular_rate]
compare: {policy: arms, reference_arm: nominal}
accept:
  - {id: roll-tracking, arm: gps_loss, metric: tracking_error_roll_rms,
     max_delta: 3.0, delta_vs: nominal}
limitations: {assumptions: [...], model_limitations: [...], ...}
```

**`question` is required.** An experiment with no stated question is a batch of
runs, and the document it produces is a table of numbers with nothing to read
them against. It is the one field no tool can derive, check or default, which
is exactly why it has to be written.

The validator is strict for a specific reason: every mistake it lets through
becomes a sentence in a reviewed document that is confidently wrong, and none
of them crash. An input the procedure does not declare would let the arm fly
its default altitude while the document said otherwise. A criterion judging a
metric outside `metrics:` would rest its verdict on a number the report never
shows. A `reference_arm` disagreeing with `role: reference` would give the file
two answers to which side a delta is measured from. All three are refused at
load time.

### Comparison, and the statistics that are not here

Within an experiment a metric is identified by its **key alone**, not by
`key@procedure` as everywhere else. That is the one place this project's metric
identity inverts, and it inverts on purpose: the arms deliberately fly
different procedures, and the whole question is what the same quantity did
under the two conditions. Matching on identity would line up nothing at all.

What the analysis reports is deliberately dull — `n` on both sides, the two
means, their difference, the relative change, and whether the two arms'
observed ranges overlap at all.

> **No p-value, no confidence interval, no effect size, no "significant".**

At the sample sizes a SITL campaign produces every one of them would be
arithmetic that runs fine and means nothing, and each would read to a reviewer
as though the difference had been established. An overlap is not a significance
test; it is a statement about the numbers actually seen.

A delta is `measured` only when both arms have at least three measured values —
the same threshold campaigns use before printing a standard deviation. Below
that it is **`indicative`**, and the row says so.

### Verdicts, and the one that is not a pass

| verdict | meaning |
|---|---|
| `passed` | every declared criterion held, over the runs that were declared |
| `failed` | a criterion was judged and did not hold |
| `incomplete` | an arm is short of its runs, or a criterion was never judged |
| `not-judged` | the experiment declares no criteria — nothing was asserted |
| `not-run` | nothing carries this experiment id |

`failed` is decided before `incomplete`: a criterion that was judged and did not
hold is a result, and one from three runs instead of five is still that result —
the document prints `n` beside it.

A criterion that could not be judged is **never counted as a pass**. "No run
measured this" and "this held" are different facts, and only one is an answer.

### Limitations, declared per experiment

Four named categories — simulation assumptions, model limitations, unverified
physical effects, conditions outside the test scope — written in the file,
beside the criteria, and printed as section 10 of the document.

They are separate because a reader does something different with each: an
assumption can be **checked**, a model limitation **bounds** the claim, an
unverified effect is a reason not to **extrapolate**, and something out of scope
is a reason to **run something else**. Collapsing them into one `notes:` field
— which is what every project does eventually — turns four actionable
statements into a paragraph nobody reads. An unknown category is rejected at
load time, because a limit filed under a name the report never prints is one
the author believes was stated and nobody ever read.

**Standing limitations cannot be dropped by a definition.** A document that
could omit *"nothing here was measured on hardware"* by leaving a key out would
omit it, and its reader would not know it was missing. They are marked
*(standing)* so they are distinguishable from the ones somebody wrote for this
particular question.

An experiment that declares none is allowed, and the document says so in as many
words. A rule forcing every experiment to declare a limitation would produce a
repository full of limitations written to satisfy the rule.

### The document

Ten fixed, numbered sections, in the same discipline the flight report has had
since v1.5: question and scope, configuration, execution, verdict, failed
criteria, measured quantities by arm, comparison, evidence, how to reproduce
this document, and limitations and non-claims.

It is recomputed from the run directories every time — there is no index and no
cache, so a document and the evidence under it cannot drift apart. A document
can still be produced for an experiment whose **file has been renamed or
deleted**: it reports what the runs record and states plainly that it cannot
report what was asked.

```bash
python3 -m argazui experiment                              # declared beside flown
python3 -m argazui experiment copter_gps_loss_vs_nominal   # its newest run
```

Exit `0` aggregated and nothing failed, `1` a declared criterion did not hold,
`2` nothing by that name. An **incomplete** experiment exits `0`: arms short of
their runs are a reason to fly more, not a reason to fail a build — the same
reasoning `argazui coverage` is built on.

### Coverage grew a fifth dimension

Experiments, with **each arm listed on its own**. An experiment half of whose
arms were flown has answered nothing, and it would otherwise appear as covered:
a comparison needs both sides.

### What is in this release

| | |
|---|---|
| `argazui/experiments.py` | the definition, its validation, and the runner that hands each arm to a campaign |
| `argazui/analysis.py` | distributions per arm, deltas between them, acceptance, the ten-section document |
| `argazui/limitations.py` | the four categories, the standing statements, both languages |
| `argazui/experiments/*.yaml` | two shipped experiments, and `SCHEMA.md` |
| `runs.py` | result schema **6** — the `experiment` stamp, beside `campaign` |
| `trace.py` | the chain now carries the experiment, run and arm a run belonged to |
| `coverage.py` | the fifth dimension |
| the interface | an **Experiments** panel, in English and Turkish |
| `docs/experiments.md`, `docs/validation-limits.md` | and their Turkish twins |

### Tests

`tests/test_experiments.py` — the validator, mostly its refusals, because every
one of them is a case that would otherwise render a correct-looking document
that is wrong. `tests/test_experiment_analysis.py` — the arithmetic, the
verdict order, and what the document refuses to print.
`tests/test_tier1_experiment.py` — **a real two-arm experiment, flown**, which
is the only way to check that what comes out is two ordinary run directories
carrying both stamps. `tests/e2e/test_experiment_panel.py` — the panel in a
real browser, in both languages, with the console read after every assertion.

### Known limits

- **An experiment is still verification.** It compares two simulations of an
  aircraft, and a delta between them is a fact about the simulation. Nothing in
  this release moves the boundary described in
  `docs/verification-vs-validation.md`; it makes the *unanswered* part visible
  and specific instead of leaving it to a reader's generosity.
- **The `baseline` policy picks its baseline by recency.** That is a
  convenience for a person; a pipeline that needs a reproducible answer should
  name the experiment run it wants.
- **Nothing schedules or parallelises arms.** They are flown in file order, one
  aircraft at a time, because that is what a single-vehicle harness can honestly
  do.

## v1.5.0 — 2026-08-10

### What this release is about

v1.3 made a run measurable. v1.4 made it repeatable and made its failures
diagnosable. This one is about a question neither could answer: **can somebody
who did not run it check any of it?**

Three gaps, each of which lets a correct-looking document be read as more than
it is:

1. **A claim could not be followed backwards.** A reviewer holding
   `docs/status.md` and asked *"which criterion is that, which run showed it,
   and what file proves it"* had to read three documents and join them by eye.
2. **Nothing checked that the evidence was actually there.** A report that was
   never generated, an empty plot directory, a parameter dump the analysis
   skipped — each leaves a run directory that looks fine, and each means a
   claim rests on something nobody can open.
3. **Nothing said what had never been run.** Every table in the project was
   about things that were tested. None of them could distinguish a project with
   four procedures that all pass from one with forty of which four were run.

And one thing the whole apparatus made worse rather than better: the more
precise the claims got, the easier they became to over-read.

### Traceability — a name on every link

```
test intent -> procedure -> step -> criterion -> metric -> run -> artefact -> verdict
```

```bash
python3 -m argazui trace runs/<run-id>     # exit 1 if a link does not resolve
```

There is no database. A chain is **computed** from a run's `result.json` every
time it is asked for, exactly as a campaign document is recomputed from its
runs. A traceability record that could drift from the run it describes would be
worse than none: it would be a second source for the one thing this project
keeps single.

**A criterion declares its own id; a step derives one from its position.** The
line is not arbitrary. A step identifier is only ever read inside the run that
produced it — the report lists the steps, the failure classification names the
one that failed — and position is a good enough name for that. A criterion
identifier is quoted *outside* its own run: in the coverage report, in the
"what was not tested" list, in a comparison of two runs months apart. Those
need a name that survives somebody inserting a criterion above it.

Every criterion in all thirteen shipped procedures now declares one
(`id: alt-reached`), and a test asserts it. A procedure that omits one still
works and gets `<procedure>#c2` — and the chain **marks that identifier as
derived**, because an identifier whose stability the reader cannot see is worse
than one they can.

`test_id` is the start of the chain: a pytest node id, or `manual` for a flight
somebody started by hand. `manual` is a real answer and the one that matters —
it says no test in this repository asserts what the run shows, and the report's
non-claims section says so in as many words.

The integrity check is the feature, not the identifiers. A traceability scheme
nobody verifies degrades silently: a criterion loses its id, a metric names a
procedure the run never flew, an evidence reference points at a file that was
pruned — and every one of those still renders a table that looks perfectly
correct.

### Evidence manifest

Every run writes `evidence.json`: what it was **expected** to leave behind, and
what happened to each artefact — path, type, existence, size, hash, and the
module and schema version that produced it.

Three levels, and the middle one is the point:

| | |
|---|---|
| `required` | the run is not evidence without it. Absent → an `evidence` failure. |
| `conditional` | required only when a stated condition held — the dataflash log is required *if the vehicle armed*, because `LOG_DISARMED=0` means a session that never armed writes none and nothing was lost |
| `optional` | absent is fine — **but only with a stated reason** |

> "There are no plots because matplotlib is not installed" and "there are no
> plots" are different facts, and only the first is an answer.

An optional artefact absent with no explanation is reported as `unexplained` —
the same rule this project applies to a metric that could not be measured and a
fingerprint field that could not be read.

**Two things are deliberately not hashed**, and both for the same reason: a
document cannot contain a correct digest of itself. `result.json` is rewritten
when the report completes, so a hash taken at any one moment is wrong at the
others — and a hash that is *sometimes* wrong would fail an integrity check for
a run that is perfectly intact. The copy embedded in the flight report carries
no digests at all; they live in exactly one place, `evidence.json`, which is
captured after the report and once more after section 7 is filled in.

`failures.classify_run` now takes the manifest, so "a required artefact is
missing" is the general rule and the dataflash-specific checks are the special
case rather than the only one.

### Coverage that names what it did not reach

Four dimensions — models, procedures, acceptance criteria, faults — each
listing the items no run exercised, **by name**.

> A percentage with no list under it is an invitation to stop reading. The list
> is the deliverable.

Deliberately **not a test count**: that number goes up when somebody adds a test
and never goes down when somebody adds an aircraft, a procedure or a criterion
nobody runs. And deliberately **not a gate** — `argazui coverage` always exits
0, because turning an uncovered procedure into a red build would make the
honest thing to do, declaring a procedure before it can be flown, the thing
that breaks CI.

Two refusals to flatter itself:

- **A criterion nobody reached is not covered.** It produced no information
  about the aircraft, and counting it would let a run that aborted at step two
  report full criterion coverage. A criterion that was evaluated and *failed*
  **is** covered — counting only passes would make coverage a second, worse
  pass rate.
- **A criterion recorded before identifiers existed is counted, not guessed.**
  Attributing it by position would require assuming the procedure has not been
  edited since. It is reported instead, so a 0% first reading after this
  upgrade has a stated reason rather than looking like a project that tests
  nothing.

`docs/status.md` gained a **What was NOT tested** section from the same
collection, so the summary and the full lists can never disagree about which
runs they read.

### The flight report, restructured

Ten fixed, numbered sections: scope, configuration, procedure, verdict, failed
criteria, quantitative metrics, evidence manifest, environment, regression, and
**limitations and non-claims**.

The order is the point. A reviewer reading two runs should not have to hunt for
the same fact in two places, and a fixed order is checkable — a test asserts
the ten headings appear in sequence.

Section 10 is the one a verification document is least likely to contain. A
reader who finishes a green report and is not told where its claims stop will
decide for themselves, and they will decide generously; that is what a page of
passing checks is for. So every report now states that it does not claim the
aircraft would behave this way in the air, that anything not in section 5 was
recorded rather than judged, and that one run is one run — plus, conditionally,
that the run was flown by hand, that its evidence is incomplete, or that its
environment could not be fully identified.

### Verification is not validation

A new page, because the distinction closes by itself in a reader's head.

ArgazUI does **verification**: it shows an implementation met criteria somebody
declared. It does not do **validation**: nothing here shows those were the
right criteria, that the simulated aircraft resembles the real one, or that the
scenario is one that ever happens.

Stated as plainly as it can be: *no dynamics model, however good, is evidence
about hardware* — and *a criterion this project satisfies was chosen by this
project.*

### Schemas

| | from | to | added |
|---|---|---|---|
| procedure | 3 | **4** | `id:` on a step and on an `expect:` entry |
| `result.json` | 4 | **5** | `test_id`, `evidence`, and `step_id` / `criterion_id` on every step and criterion |
| `report.json` | 2 | **3** | the ten-section structure and the non-claims section |
| `docs/status.md` | 3 | **4** | the coverage document, and the "what was NOT tested" section |

Older documents load unchanged, and a file that uses a later schema's feature
than it declares is refused at load time.

### Known limits

- **Declaring criterion identifiers changed every shipped procedure's text**,
  which changes its `procedure_hash`. Baselines recorded before v1.5 are
  `incomparable` against runs after it — correctly, and by the design
  `regression.py` already had. `--ignore-config-drift` compares anyway and
  still reports what differed.
- **Criterion coverage reads 0% until the procedures are flown again.** Runs
  recorded before v1.5 carry no criterion identifiers and are counted as
  unattributable rather than matched by position. The report says so.
- **Traceability is not requirements management.** There is no requirements
  document, no bidirectional matrix and no approval workflow, and v1.5
  deliberately did not build one. The chain links a claim to its *evidence*; it
  does not link it to a *purpose*.
- **Nothing tests the manifest against a dismantled real run.** The manifest
  tests build directories rather than removing a file from one a flight
  produced, and the two are not quite the same thing — it is on the manual
  checklist.
- **A non-claims section nobody reads against a flight they watched is a
  paragraph.** So is a coverage list nobody checks against their own beliefs.
  Both exist to be disagreed with, and no test can do that.
- Nothing here changes what tier 2 can claim, and no new model was flown.

## v1.4.0 — 2026-08-10

### What this release is about

v1.3 made a single run measurable and comparable. This one is about the two
things a single nominal run still cannot tell you:

1. **Does it work, or did it work once?** Every layer up to now judges one
   flight. A procedure that works four times in five is neither a working
   procedure nor a broken one, and neither a green run nor a red one says
   which. This project already has the case: `tailsitter_takeoff` passed three
   times at 24.9 m, 23.6 m and 18.3 m — each run met its criteria, and the
   *spread* was the evidence.
2. **What happens when something is wrong?** Every procedure in the repository
   asks whether the aircraft does what it was told. None of them asks what it
   does when the GPS goes away.

And one thing that made both harder to act on: a failed run said `failed` plus
a sentence, which does not distinguish a misbehaving aircraft from a simulator
that never started from a dataflash log that was lost — three different
investigations.

Nothing in the existing architecture was replaced. `models.json` → launch →
MAVLink → `ProcedureRunner` → `result.json` → run evidence → DataFlash report →
regression → CI/status is the same path; each piece below hangs off a point on
it.

### Repeatability campaigns

A campaign flies **the same procedure, on the same model, in the same
configuration, N times** and reports the distribution rather than a verdict.

Structurally it is a campaign id stamped into N ordinary run directories. There
is no new storage format and no database: each iteration produces exactly the
evidence a single flight produces, and the campaign document is an aggregation
over them that is recomputed from the runs every time it is asked for. A
summary that could not be recomputed from the runs would be a fourth kind of
claim with no evidence underneath it.

```bash
python3 -m argazui campaign                    # list the campaigns on disk
python3 -m argazui campaign <campaign-id>      # 0 clean, 1 unclean, 2 no such campaign
```

In the browser it is a panel: pick a procedure, pick a count, press RUN
CAMPAIGN. The campaign owns START and STOP while it runs, because "each run
gets independent evidence" means a real launch and a real shutdown per
iteration — not one session with the procedure sent five times.

**What it refuses to say** is as much of the design as what it reports. Counts,
a clean pass rate, and the mean, standard deviation, minimum and maximum of
every metric — each with its sample size beside it. No confidence interval, no
p-value, no reliability figure, because none of them means anything at n=5 and
all of them would read as though it did. A standard deviation is printed only
from three measured values upwards; below that the cell is `—`, which means
*not enough runs to say* and not *no variation*.

A run that passed only on a retry is `flaky` and is not in the pass rate — the
same rule `docs/status.md` has. A pass rate that quietly included retries would
be measuring the harness's patience rather than the aircraft.

A campaign also **checks its own premise**. Every run carries a fingerprint, so
the document compares them and says so when the model configuration, the
procedure text, the ArduPilot commit or the firmware moved between iterations:
a spread caused by an edit half way through is not a spread caused by the
aircraft.

An iteration that could not be started is recorded as an `environment` failure
and the campaign continues. "Three of five starts failed" is a repeatability
result, and stopping at the first one would hide exactly what the campaign was
run to measure.

### Failure classification — seven categories, and only one is about the aircraft

Every failure now carries one machine-readable category, stored in the run
rather than worked out by whoever reads it:

| | |
|---|---|
| `environment` | the simulation never got into the state the run needed |
| `vehicle_readiness` | the aircraft would not be made ready — pre-arm, arming |
| `procedure` | a step of the flow did not do what it asked |
| `acceptance` | the flow ran and a declared criterion did not hold |
| `evidence` | it flew, and the proof of what happened is missing |
| `regression` | nothing failed; a measured quantity got worse |
| `infrastructure` | ArgazUI, the link or CI broke |

**Only `acceptance` is a verdict about an aircraft.** The other six say the
simulation, the tooling or the evidence went wrong, and conflating them is how
a broken harness comes to be reported as a broken aircraft — the same class of
untruth as an unearned tick, pointed the other way.

The set is closed on purpose. A taxonomy that grows a category whenever
something new goes wrong stops being a diagnosis and becomes a second copy of
the error message.

Two decisions worth stating:

- **The first thing that went wrong is what gets classified.** A run that could
  not arm never reached its criteria, so reporting the unevaluated criteria
  would name a symptom and hide the cause.
- **A run whose procedures all passed can still fail**, on `evidence`. A flight
  nobody can prove happened is worth what one that did not is.

`failures.py` is the only implementation; `procrunner`, `runs`, `regression`,
`status` and `campaign` all call into it. A second implementation would
disagree with the first the moment a step type was added.

The category appears in `result.json`, in a **Why** column in
`docs/status.md`, at the top of `report.md`, on a chip in the Flight Runs
panel, and counted per campaign.

### Controlled fault injection — procedure schema 3

`failures:` left the reserved list. A scenario declares a fault, an injection
point, a start condition, a duration, what should be observed *in words*, the
criteria that decide the verdict, and the telemetry the verdict rests on.

```yaml
schema: 3

failures:
  - id: gps_off_in_hover
    fault: gps_loss
    target: gps1
    inject_after_step: 5
    start: {condition: {alt_above: 20, armed: true}, within: 60s}
    duration: 12s
    expected: {en: "The EKF loses its position source and …", tr: "…"}
    expect:    [{condition: {armed: true}, for: 8s}]      # while it is held
    recovery:  [{condition: {angular_rate_above: 150}, never: 5s}]  # after
    evidence:  [attitude]
```

Four faults in two families, and no more: `gps_loss`, `gps_degradation`,
`mavlink_interrupt`, `mavlink_degradation`. **Wind, motor failure, arbitrary
sensor corruption and a general fault DSL are deliberately absent.** A DSL
would take a week and produce scenarios nobody has watched a vehicle respond
to; these two families each have a mechanism ArduPilot's SITL already provides
or that ArgazUI genuinely owns, an observable that is measured rather than
assumed, and a failure mode that occurs in real flying.

Five rules, each because its opposite is dangerous:

1. **Simulation only.** Every mechanism writes a `SIM_*` parameter or changes
   ArgazUI's own socket behaviour. Nothing has a path to hardware, and nothing
   is *conditional* on being in a simulator — the mechanisms do not exist
   outside one, which is stronger than a flag.
2. **Declared in the procedure**, so it is in `scenario.yaml` verbatim and
   inside the text `procedure_hash` covers. A run cannot have been degraded by
   something the archived document does not mention.
3. **Fail closed.** The mechanism is probed before the first step. If this
   ArduPilot has no such parameter the procedure is **aborted** and the
   aircraft never leaves the ground. A scenario whose fault never happened is a
   nominal test wearing the wrong name, and it would report a pass for a
   behaviour nobody exercised.
4. **Cleaned up**, from a `finally`, on failure, error and cancellation alike —
   and whether the restore succeeded is recorded, not assumed. A fault that
   could not be cleared is a classified failure of its own, because the
   simulator is still degraded and nothing measured afterwards means what it
   says.
5. **Deterministic.** Packet loss drops one in N by count rather than by
   chance. `drop_one_in: 1` is refused: that is an interruption, and the record
   should say which of the two happened.

**A fault that was successfully injected is not a pass.** The record keeps four
things apart — the injected condition, the vehicle's response, the criteria and
the verdict — and none is derived from another. A fault whose declared
`evidence:` never arrived is reported as *not judged*.

The MAVLink fault is not a `SIM_` parameter, and should not be: ArduPilot has
no parameter for "the ground station went away" because the ground station is
this program. Suppressing ArgazUI's heartbeat is a *complete* model of the
condition rather than an approximation — ArduPilot's GCS failsafe keys on
`sysid_mygcs_seen`, called from exactly `HEARTBEAT`, `RC_CHANNELS_OVERRIDE` and
`MANUAL_CONTROL`, of which ArgazUI sends the first two and the fault withholds
both.

Two Copter scenarios ship with it, in the new `scenario` role — listed by name,
never bound to a button, never auto-selected, because injecting a fault must
not happen because a capability heuristic decided it applied:

| | |
|---|---|
| `copter_gps_loss` | hover in GUIDED, GPS off for 12 s, judged during and after |
| `copter_link_loss` | hover in GUIDED, link silent for 10 s, judged only *after* |

`copter_link_loss` has no criteria for the blackout window and that is the
point: during a full interruption there is no telemetry, so any criterion
judged inside it would be judged against the last state that arrived before it
— an aircraft frozen in amber, which passes anything. A ground station finds
out what happened afterwards, or not at all.

`copter_gps_loss` deliberately does **not** require a particular failsafe mode.
`FS_EKF_ACTION` is a parameter, a model may ship any value of it, and a
criterion demanding `LAND` would test this repository's assumption rather than
the aircraft. What it requires is true whatever the parameter says: an airborne
vehicle that loses GPS must not disarm and must not tumble.

### Two timing defects the fault work exposed and fixed

Both were latent in v1.3 and only became routine once a fault could stop
telemetry on purpose.

**A clock that freezes was not detected.** `_Window` asked whether the vehicle's
clock had gone backwards or never started. `time_boot_ms` does neither when
telemetry stops — it keeps its last value. So a window measured `now - start` =
0 for its whole duration and then reported `clock: "vehicle"`: a dead stream
described as a healthy measurement of no seconds at all. A window now notices a
clock that has not moved for two wall-clock seconds, falls back to the wall
clock **scaled by the speedup it opened with** so the number still means
vehicle time, says so in the result text, and keeps the fallback for the rest
of the window — a duration whose unit changed half way through is not a
measurement.

**A cleared fault is not a recovered one.** The moment a fault is lifted, every
field of the vehicle state still holds what arrived before it, so
`{armed: true} within: 15s` passed "after 0 ms" against a reading the blackout
itself had frozen. That is silence reported as success. The vehicle's clock
also resumes with a jump of however long the fault lasted, which could put the
first sample of the next window straight past its budget — producing a
`never: 5s` that collected one reading and honestly reported it could not judge
anything from it. The runner now waits for fresh telemetry before evaluating
any `recovery:` criterion, and reports *not judged* if none arrives.

Both are fixed in the runner rather than in either scenario, because both
follow from what a fault is and not from which fault it was.

### Schemas

| | from | to | added |
|---|---|---|---|
| procedure | 2 | **3** | `failures:`, the `scenario` role |
| `result.json` | 3 | **4** | `failure`, `campaign`, and `faults` per procedure |
| `docs/status.md` | 2 | **3** | the failure category per row, fault-response claims |

Older documents load and behave exactly as before, and a file that uses a
feature from a later schema than it declares is refused at load time with a
message saying so. `fingerprint.json` gains a `scenario` section listing the
declared faults — descriptive, and explicitly **not** a second identity field,
because the `failures:` block is already inside the text `procedure_hash`
covers and a second hash over the same content could only ever disagree with
the first.

### Documentation

Four new pages, each with a Turkish twin, plus a new section of `SCHEMA.md`:
[campaigns](docs/campaigns.md), [fault
injection](docs/fault-injection.md), [failure
classification](docs/failure-classification.md) and [failure
investigation](docs/failure-investigation.md) — the last of which is the path
from a red run to the file that explains it, category by category.

### Known limits

- **Two faults, and a scenario for one airframe class.** Both shipped scenarios
  are Copter scenarios. A VTOL or Plane equivalent needs criteria written for
  it, and inventing them for an airframe nobody has watched respond would be
  the unearned claim this project exists to remove.
- **`gps_degradation` and `mavlink_degradation` are implemented and unflown.**
  Their mechanisms are unit-tested and no shipped scenario uses them, so
  nothing in `docs/status.md` claims an aircraft's response to either.
- **Only the primary GPS.** ArduPilot's SITL simulates a second receiver only
  when `SIM_GPS2_ENABLE` is set, so degrading it on a normal model would be a
  silent no-op — which is what the fail-closed rule exists to prevent.
- **A fault window is a minimum, not an exact duration.** Criteria are
  evaluated inside it, and a criterion that takes longer holds the fault longer.
  The record states what actually happened rather than repeating the
  declaration.
- **Campaign statistics are descriptive only.** Mean, standard deviation and
  range over N runs, with N stated. Nothing here supports a reliability claim,
  and the document says so in as many words.
- **A campaign is one model and one procedure.** A campaign over two different
  things has no meaningful spread, so it is not offered.
- The tier-1 campaign test flies two iterations, not five. It shows the runs are
  independent; it is not a repeatability measurement.
- Nothing here changes what tier 2 can claim about the nominal flights it
  already covers, and no new model was added.

## v1.3.0 — 2026-08-10

### What this release is about

v1.1 made a run produce evidence. v1.2 let you watch one happen. This one is
about the two questions evidence still could not answer:

1. **When, and for how long?** An acceptance criterion could only ask whether
   something was true — now or before a timeout. A takeoff that reaches
   altitude and then sinks back satisfied exactly the same criteria as one that
   held it.
2. **Compared to what?** A run said whether its own criteria held. It could not
   see the failure that actually happens to a simulation project over months:
   every criterion still passes, and the aircraft is quietly getting worse at
   flying.

Nothing in the existing architecture was replaced. `models.json` → launch →
MAVLink → `ProcedureRunner` → `result.json` → run evidence → DataFlash report →
CI/status is the same path it was; each of the pieces below hangs off a point
on it.

### Temporal acceptance criteria — procedure schema 2

```yaml
schema: 2

expect:
  - condition: {alt_above: "{alt*0.9}"}
    within: 20s                    # must BECOME true inside a deadline

  - condition: {alt_above: "{alt*0.9}", armed: true, mode: GUIDED}
    for: 5s                        # then REMAIN true, continuously

  - condition: {angular_rate_above: 180}
    never: 5s                      # and this must not be observed at all
```

Four instantaneous conditions came with them — `roll_within`, `pitch_within`,
`angular_rate_above`, `angular_rate_below` — because `attitude_stable` is
accumulated over the whole procedure and cannot sensibly be asked to hold "for
five seconds". Asking it to is a load-time error that points at the
alternatives.

**They are measured on the vehicle's clock**, not on `time.time()`. Under SITL
speedup a wall-clock second is not a second of flight, so a `for: 5s` judged on
arrival time would demand five times the flight it says it does. Each window
also carries a wall-clock backstop sized from the measured speedup — the
vehicle's clock stops advancing when telemetry stops, and a criterion waiting
on a dead stream is a hang rather than a verdict. When the backstop is what
ended a window, the result says so, because reporting a wall-clock measurement
as vehicle time would make every duration in a run's evidence wrong by the
speedup factor.

**Durations must carry a unit.** `for: 5` is rejected at load time. Every other
number in a procedure is a metre, a degree, a PWM count or a parameter value,
and a duration that looked like one of those would be read wrong exactly once,
silently, in flight, by whoever inherits the file. `m` is deliberately not a
unit — in a flight procedure it reads as metres.

**`for:` does not restart on a lapse**, and a `for`/`never` whose telemetry
never arrived is reported as *not judged* rather than passed. Both are the same
rule this project keeps returning to: nothing measured is not the same as
nothing wrong.

The schema moved from 1 to 2 rather than being extended in place. Schema-1
files load and behave exactly as before; a schema-1 file using a schema-2
feature is refused with a message saying so. Extending in place would have been
quieter and worse — an older ArgazUI would have read a `within:` it does not
implement, out of a document claiming a version it satisfies.

`copter_takeoff.yaml` uses all three shapes. A capability with no procedure
behind it is a claim, and this project's whole subject is the difference
between a claim and evidence.

### Quantitative metrics

Eight derived numbers, computed from evidence a flight already produced: time
to target altitude, peak and RMS roll/pitch tracking error, peak angular rate,
time outside the declared attitude envelope, and the slowest mode transition.
Each carries its unit, the log message or recorded step it came from, and
whether it belongs to the run or to one procedure.

They are a **third kind of output** and cannot fail a run:

| | decided by | can fail a run? | threshold from |
|---|---|---|---|
| acceptance criteria | the procedure's `expect:` | **yes** | the procedure |
| advisories | `flightlog.py` | no | ArduPilot's documentation |
| metrics | `metrics.py` | no | nothing, until compared |

Giving a metric a threshold here would have created a second acceptance system
with limits nobody declared in a procedure. A metric that cannot be derived is
written as `null` with a stated reason — "no procedure in this run declared a
target altitude", "the log carries no IMU records" — rather than omitted: an
absent row and a measurement that could not be made look identical to a reader,
and only one of them is a fact.

The dataflash log knows what the aircraft did and nothing about what it was
told to do, so target altitudes, the declared envelope and the measured
mode-change durations are read out of the run's own `result.json`. That is the
only coupling between `flightlog.py` and the procedure system.

### Environment fingerprint

`versions.txt` answered "which software?" as a flat list for a human to read.
That is enough to look at and not enough to compare, so every run now also
writes `fingerprint.json`: ArgazUI and ArduPilot commits, the firmware identity
and whether it matches the checkout, SITL_Models, Gazebo, ROS, the interpreter,
the resolved configuration — and content hashes of **the procedures that ran**
and **the model's registry entry plus its parameter files**.

Those two hashes exist because they are what changes most often while moving no
version number at all: an edited acceptance criterion, a changed `.param`.

**Unknown is an answer and it comes with a reason.** A component that cannot be
identified is `null`, and the reason is recorded — `"/opt/SITL_Models is not a
git checkout"`, `"unavailable: [Errno 2] ... 'gz'"`. A manifest that quietly
omitted the field would read exactly like one taken on a machine where the
component was fine, and the whole point is that those two must not look alike.

### Run-to-run regression comparison

```bash
python3 -m argazui compare runs/<current> --baseline runs/<baseline>
```

Exit `0` for no regression, `1` for a degradation, `2` for runs that could not
be compared. `2` is separate from `1` on purpose: "these runs do not line up"
is not the same news as "this build got worse", and a pipeline that merged them
would eventually report a mis-specified baseline as a regression. The interface
exposes the same thing on a run's report as **⇄ compare with the previous run**.

The strict part is what it refuses. A different model or a different set of
procedures is refused outright. A changed procedure hash, model configuration,
ArduPilot commit or firmware makes the comparison `incomparable` and names the
field; so does one of those being *unknown* on either side, which is not
evidence that they match. `--ignore-config-drift` compares anyway and still
prints what differed — "I changed the firmware and I want to see what that did
to the numbers" is a real question that has to be asked out loud.

A metric is `unchanged` when it moved by less than its relative tolerance
(10% by default) **or** less than an absolute floor. The floor is not a
convenience: an RMS tracking error of 0.02° that becomes 0.04° is +100% and
means nothing, and judging on the percentage alone would fill CI with red for
quantities that are identical in engineering terms. Both are configurable per
metric under `[regression]` in `argaz.toml`.

No database. A baseline is a run directory; comparisons read `result.json` and
write `regression.json` beside the current run.

### Claim-scoped verification

A `passed` row in `docs/status.md` means "every procedure this model was flown
with met every criterion it declared". That is narrower than it looks, and the
gap is where an unearned claim grows back — so the status generator now also
emits **verification claims**: one row per procedure, per heartbeat-confirmed
mode change and per acceptance criterion, each with its result and the run that
proves it. A criterion that never ran is reported as *not evaluated*, which is
its own word: collapsing it into `failed` would be an invented result pointing
the other way from an invented pass.

The section says plainly that anything not listed was not verified, and names
what no model here has been flown through: a mission, wind, the edges of its
envelope, an injected fault, or enough repetitions to support any statement
about reliability.

### Engineering documentation portal

**DOCS** in the top bar: twenty-two pages in a persistent tree, a search that
matches page titles *and* every heading inside them, and deep links
(`#docs=metrics`, `#docs=regression/exit-codes`).

**It holds no prose.** Every page is a file in this repository or one named
section of one, and each page names its source. Writing the documentation into
the interface produces a second source of truth within a week: the page says
one thing, `README.md` says another, and the one a developer edits is whichever
they happen to open. The only generated page is the landing index, which is a
table of contents and states no technical fact of its own.

Ten new canonical documents were written for the subjects that had no home —
verification model, acceptance criteria, metrics, regression, reproducibility,
runs and evidence, lifecycle, CI/CD, diagnostics, testing — each with a Turkish
twin at `docs/<name>.tr.md`.

The markdown renderer escapes before it transforms, so a document cannot inject
markup into the page. The cost is that a deliberate `<sub>` shows as text, which
is a trade worth making for files anyone with a checkout can edit.

### Restored with the fleet withdrawal: the mode-settle gate

The commit that withdrew the multi-vehicle release took a genuine
single-vehicle fix with it, and its own commit message said so might be worth
re-applying. It turned out to be worth re-applying immediately: the flake it
had fixed reappeared in the very next full-suite run.

ArduPlane reads its flight-mode switch shortly after RC input first becomes
valid, and overwrites any mode commanded in that window — with **no NAK and no
STATUSTEXT**, so the command silently does nothing. Measured:

```
Throttle failsafe off  t=6.75
FBWA commanded         t=6.85   accepted
back to MANUAL         t=6.99   140 ms later, with no explanation
```

The interface enabled its command buttons as soon as the link reported
connected, which is before that window closes, so the race was real for a
person too — click a mode button in the first fraction of a second after a
vehicle appears and the mode reverts silently. The buttons now wait for the
mode to have stopped moving on its own for `MODE_SETTLE_S`, counted on the
vehicle's clock, and say why while they are waiting.

`docs/e2e-flight-flake.md` carries the diagnosis, including how it was traced
without changing any code. It is kept in the repository rather than left in a
commit message precisely because the second occurrence cost minutes instead of
an afternoon.

Still not done, and stated: `_do_mode` reports success for a mode change that
is accepted and then reverted. The gate prevents that here; it does not make it
visible everywhere else.

### Turkish

The portal's chrome, navigation, summaries and notices are translated, and
every document v1.3 added exists in both languages. The pages that are sections
of `README.md` or `USAGE.md` have no Turkish source; in Turkish mode the portal
shows the canonical English text with a notice, in Turkish, explaining exactly
that. Forking every repository document into a second language would recreate
the duplicate-source problem the portal was built to avoid, and a stale
translation of a technical page is worse than an honest English one.

### Verified

- **`tests/test_temporal_criteria.py`** — 31 cases pinning the evaluator down:
  pass, timeout, a lapse mid-hold, a single observed excursion, the boundary at
  the deadline, the vehicle-clock measurement at speedup 10, the wall-clock
  fallback when the clock stalls, and the refusal to judge without telemetry.
- **`tests/test_metrics.py`**, **`tests/test_regression.py`**,
  **`tests/test_fingerprint.py`**, **`tests/test_docs.py`** — the derivations,
  the classifier and its refusals, the manifest and its unknowns, the section
  extractor.
- **`tests/test_run_record.py`** — that a run and a report regenerated from it
  describe themselves identically. See *What this release got wrong first*.
- **`tests/test_tier1_evidence_chain.py`** — a real `arducopter`, the shipped
  `copter_takeoff` procedure, and the evidence followed all the way to a
  comparison verdict, in both directions: identical evidence compares as
  `unchanged` with a `passed` verdict, and perturbed evidence as `degraded`
  with a `regressed` one.
- **`tests/e2e/test_docs_portal.py`** — the portal in headless Chromium: every
  page in the tree resolves, tables and code blocks render, search matches
  headings, a deep link scrolls to its heading, Turkish says when a page has no
  Turkish source, and the console stays clean throughout.
- **`tests/e2e/test_compare_panel.py`** — the compare button in the same
  browser: a verdict and a table come back, the reader is told metrics are not
  criteria, a run with nothing behind it says so instead of showing an empty
  table, and opening another run clears the previous comparison rather than
  leaving one run's numbers under another run's name.
- **Tier 2, on the real model set in Gazebo: 7 passed, 3 failed, 1 skipped** —
  identical to the results recorded before this release. `zephyr`,
  `skycat_tvbs` and `swan_k1_hwing` failed exactly as they did at v1.2, and
  `iris` skipped for the same missing ROS 2 workspace. Nothing here changes
  what tier 2 can claim about any model, and this is the evidence for that
  rather than an assurance.

**Not verified by anything:** that the documentation is *correct*. No test can
read prose. What the tests check is that every page the tree offers resolves to
a file — the failure that would otherwise surface months later as a blank page
after somebody renamed a heading in `README.md`.

`docs/status.md` is unchanged in what it claims about any model. Everything
here is application-level.

### What this release got wrong first

The evidence-chain test caught a defect that had already shipped in this
release's own working tree, and it is the reason that test exists.

`argazui report <run>` re-analyses an archived flight months later. Its output
has to line up with what the flight itself wrote, because the comparison layer
refuses to compare runs whose fingerprints disagree — and it cannot tell
"somebody changed the firmware" from "our own two code paths disagree about how
to hash a file".

They disagreed, twice. The live path hashed the full model dict it held in
memory; the regeneration path could only see the trimmed record in
`result.json`. And the live path hashed the procedure YAML as loaded, while the
regeneration path recovered it from `scenario.yaml` by dropping every `#` line
— which also dropped the comment block every procedure begins with.

Both produced perfectly plausible hashes. A regenerated run silently became
incomparable with the flight it was regenerated from, and the message would
have blamed a configuration change that never happened. The fix is that the
hash covers exactly what the run archives, `scenario.yaml` is parsed by its
fence rather than by stripping comments, and hashed text is normalised.

A second, smaller one: `GET /api/runs/<id>/compare` first answered `404` when a
run had no earlier run to compare against. The endpoint existed and had
answered; the answer was "this is the first run of this model". A 404 made the
browser log an error for an ordinary outcome, on a page whose first promise is
a clean console — which is how the e2e test found it. It returns `200` with
`ok: false` now, and 404 is kept for a run id that does not exist.

### Known limits

- `never:` samples vehicle state every 0.2 wall-clock seconds. An excursion
  shorter than one sampling interval of vehicle time can pass between two
  samples unseen; it is a claim about what was observed at that rate.
  `attitude_stable` remains the criterion that weighs every attitude sample.
- The default regression tolerance is 10%, chosen from SITL's own run-to-run
  scatter on repeated tier-1 takeoffs of the same frame. It is a starting point
  for a project's own baselines, not a property of any aircraft.
- The portal renders a known subset of markdown — headings, fenced code, lists,
  tables, blockquotes, links, inline code. Anything outside it renders as the
  literal text it is.
- A mode change that the autopilot accepts and then reverts still reports as a
  success from `_do_mode`. The mode-settle gate prevents the case that was
  actually biting; it does not make the class of failure visible.
- Nothing here changes what tier 2 can claim, and no new model was flown.

## v1.2.0 — 2026-08-04

### Live telemetry to PlotJuggler

Until now the only numbers you could see *during* a flight were MAVProxy's
console text; everything graphical came after it, from the dataflash report. A
running session now mirrors its telemetry to a loopback UDP port that
PlotJuggler plots in real time. The port opens when you press START and closes
when you press STOP, so the stream belongs to a session rather than to the
server.

- **Config key `plotjuggler_port`** (`argaz.toml`, `ARGAZ_PLOTJUGGLER_PORT`,
  `--plotjuggler-port`), default **14552** — next in the same block as 14550
  and 14551. `0` switches the mirror off.
- **A LIVE PLOT line under Quick Commands** with the address, a copy button for
  the port, and a running count of the messages that have actually left it —
  the count rather than an "open" badge, because one is a measurement and the
  other is a claim.
- Nothing is launched or bundled: ArgazUI opens the port, you connect
  PlotJuggler to it.

**It sends JSON, not MAVLink, and that was not the original plan.** The plan
was a raw MAVLink mirror for "PlotJuggler's MAVLink plugin". That plugin does
not exist. Checked against the installed build (3.17.2): PlotJuggler's live
data sources are UDP Server, WebSocket, ZMQ, MQTT, serial, ROS 2 and the
Foxglove bridge, and its parsers are JSON/CBOR/BSON/MessagePack, Protobuf, ROS
1/2, DataTamer and InfluxDB line protocol. ArduPilot's own PlotJuggler plugin
(`plotjuggler-apbin-plugins`) is a dataflash `.BIN` loader — offline, and a
different problem. A raw mirror would have had no reader, so the mirror emits
one JSON object per MAVLink message instead, which PlotJuggler flattens into
`ATTITUDE/roll`, `VFR_HUD/alt` and so on. Raw MAVLink to a third consumer
already exists and needed nothing new: another `sim_vehicle.py --out`.

No second MAVLink implementation was added. The mirror decodes nothing — it is
fed from `MavlinkLink._absorb`, the one place every received message already
passes through, and only serialises objects pymavlink has already parsed. It
also sits *after* that method's ground-station heartbeat filter, so MAVProxy's
own HEARTBEAT cannot overwrite the aircraft's mode in the plot.

Two field types are dropped on the way out. Text, because nothing plots a
string and it is already in `mavlink_events.jsonl`. And `NaN`/infinity, which
ArduPilot really does send in unpopulated fields: `json.dumps` writes them as
bare literals that are not JSON, and PlotJuggler answers a message it cannot
parse by *stopping the stream* — so one of them would have ended the live plot
rather than spoiled one point. There is a test for exactly that.

### Verified

- Tier 1 (`tests/test_telemetry_mirror.py`): a real SITL quad, a listener bound
  to the mirror port, and an assertion that a `HEARTBEAT` arrives as valid JSON
  with its fields intact — plus that *every* datagram parses, and that the port
  goes silent when the session stops. Encoder tests pin the NaN and text rules
  without needing a vehicle.
- Measured, on that session: 34 message types, roughly 250 series, about 130
  datagrams (26 KB) per second of flight.
- **Not verified by anything: that PlotJuggler draws the graph.** No test in
  this project can see a rendered window. It is a new ✗ row in
  [docs/manual-checklist.md](docs/manual-checklist.md).

`argazui doctor` deliberately does **not** check this port. It checks that
14550 and 14551 are free to *bind*; 14552 is supposed to be held — by
PlotJuggler — so a bind check would report FAIL exactly when the feature works.

`docs/status.md` is unchanged: this is an application-level capability and
makes no claim about any vehicle model.

### Closeout — three things manual testing found

**The Address box, and a warning dialog that lies.** Connecting PlotJuggler
produced *"Couldn't bind to IPv4 UDP server at (127.0.0.1:14552, 14552)"* —
while the data was arriving perfectly. Pressing OK on it stopped the stream;
ignoring it did not. Root-caused against the real snap build (3.17.2) and
upstream's `plotjuggler_plugins/DataStreamUDP/udp_server.cpp`:

```cpp
QHostAddress address(address_str);      // "127.0.0.1:14552" -> a NULL address
bool success = true;
success &= !address.isNull();           // false already, from the text box
success &= _udp_socket->bind(address, port);   // but this SUCCEEDS: null means "any"
connect(_udp_socket, &QUdpSocket::readyRead, this, &UDP_Server::processMessage);
if (!success) { QMessageBox::warning(...); shutdown(); }
```

The flag comes from the text someone typed, not from the socket. `readyRead`
is connected before it is consulted and a modal `QMessageBox` runs a nested
event loop, so telemetry keeps arriving while the dialog sits there; OK returns
into `shutdown()`, which destroys a socket that was working. Confirmed at the
Qt API level (`bind()` returns true for both `127.0.0.1:14552` and an empty
box) and by `ss` showing the complaining process holding `0.0.0.0:14552`.

Nothing ArgazUI sends is involved — the bind happens before the first datagram
is read. It is still our bug: the LIVE PLOT strip displayed `127.0.0.1:14552`
as one selectable token, and **USAGE.md told the user to leave Address blank,
which produces the same null address and the same dialog.** Fixed by never
presenting a `host:port` token again — Address and Port are two separately
labelled, separately copyable values — and by documenting the exact field
values in both languages, in the app and in USAGE.md, including what to do if
you have already hit the dialog (close it with ✕; do not press OK). An e2e test
asserts the combined form appears nowhere in the strip except inside that
warning.

**The Flight Runs panel is capped at 5.** With real usage history it rendered
every run and became an endless scroll. It now shows the five most recent with
a control that reveals the rest and collapses again. Display only: `/api/runs`
still returns every run and nothing under `runs/` changed. `#run=<id>` deep
links keep working — the list expands automatically when the target is below
the fold, because a panel that hides data is fine and a link that silently does
nothing is not.

**Removed the v1.1 handover note from `docs/`.** It listed what was still
missing when v1.1 closed — chiefly that `docs/status.md` and this file did not
yet exist. Both do, and the roles it filled are covered by
[docs/status.md](docs/status.md),
[docs/manual-checklist.md](docs/manual-checklist.md) and this changelog. It is
in the git history if anyone wants it.

---

## v1.1.0 — 2026-08-03

v1.0 was a control panel. v1.1 is a control panel that can prove its own
claims, and the first thing that proof did was contradict v1.0's README.

### Two things v1.0 got wrong, stated plainly

**Plane TAKEOFF never worked.** Every fixed-wing model in v1.0 — Zephyr,
Skywalker X8, Mini Talon, the Weight-Shift Aircraft — was listed as fully
tested, and the TAKEOFF button was wired to a copter's flow: switch to GUIDED,
arm, send `MAV_CMD_NAV_TAKEOFF`. A plane in GUIDED does not take off from that
command; it loiters at its current altitude, and ArduPlane rejects the copter
takeoff outright. There was one takeoff path for every airframe, and it was a
multirotor's. Nothing noticed because nothing checked the aircraft afterwards
— the button reported the ACK it received and stopped there.

Fixed by making the flow a property of the *airframe*: procedures are
declarative YAML per vehicle class, chosen from capabilities probed off the
vehicle over MAVLink (`Q_ENABLE`, `Q_TAILSIT_ENABLE`, `Q_OPTIONS`), never from
what `models.json` claims the model is.

**v1.0's README carried unverified support claims.** It listed eleven models
with green ticks and the sentence "Every model below was tested by actually
flying it". Nothing produced those ticks except somebody's belief. The table
is gone; [docs/status.md](docs/status.md) is generated from test output by CI
and any hand edit to it is overwritten. Expect it to be smaller than the list
it replaced — that is the correction, not a regression.

### The tailsitter: a weak criterion showed green for a tumble

The best story in this release, because it is the failure mode the whole
version exists to catch, caught in our own work.

`tailsitter_takeoff` passed three times, at 24.9 m, 23.6 m and 18.3 m. It
reached altitude, stayed armed and reported QHOVER, and those were the only
three things the acceptance criteria asked about.

When the criteria were tightened to measure *attitude* as well, the same
procedure on the same frame recorded peak body rates of **1263–1306 °/s** —
three and a half revolutions per second — with a median of 183–399 °/s, roll
spanning ±180° and control outputs saturated for the entire flight. The
aircraft had been tumbling the whole time. Altitude was a side effect of a
thrust vector that happened to point roughly upwards; nothing in the old
criteria could tell a controlled climb from a fall in the wrong direction.

Diagnosis, which turned out to be upstream's: `plane-tailsitter` ships no VTOL
attitude tuning at all, and ArduPilot's own test suite lists it as a
known-broken frame — *"unstable in hover; unflyable in cruise"* — and skips it
(`Tools/autotest/arduplane.py`, `FlyEachFrame`). Rebooting SITL first, as
upstream does for tailsitters, improves the peak from 1263 to 235 °/s but does
not stabilise it. The only alternative frame,
`quadplane-copter_tailsitter`, is properly tuned and rock-steady at 0.1 °/s
but produces no lift from stick input at any throttle up to full.

So tier 1 cannot verify this procedure on this checkout. **It is left red.**
Tuning the airframe until our own test passes would prove nothing, and an
`xfail` would paint it green.

### What is new

- **Procedures.** Takeoff and landing for copter, plane, quadplane and
  tailsitter as declarative YAML in `argazui/procedures/`, with a versioned
  schema. The button and the regression test execute the *same file*.
- **Acceptance criteria that measure state.** `expect:` blocks judge altitude,
  mode, arm state, parameters — and, since this release, the attitude envelope
  the aircraft flew through, in seconds spent outside a declared band rather
  than in peaks. An ACK is never a pass.
- **Declared parameter overrides.** A procedure may only change a parameter it
  declares, with a reason in both languages; the values are restored when it
  ends, including when it fails. Upstream `.param` files are never edited.
- **Installable elsewhere.** `argaz.toml`, `ARGAZ_*` variables or CLI flags;
  no absolute path is baked into anything. `argazui doctor` checks the
  installation, and every fix it prints runs verbatim when pasted.
- **Run artefacts.** `runs/<UTC>_<model>/` per flight: dataflash log, full and
  differential parameter dumps, the procedure verbatim, MAVLink event stream,
  console log, and a post-flight report with advisories (vibration, EKF
  innovations, attitude tracking) that never change a verdict.
- **A test suite that flies.** Real SITL, a real FastAPI server, a real
  browser; no mocks anywhere. Tier 1 runs on every push in under six minutes;
  tier 2 flies the model set in Gazebo nightly.
- **Version-drift detection.** The page compares the identity of the server
  answering it against the files it was served, names which layer changed
  (server code vs interface files), and prints a restart command that runs.
- **`sitl_only` launch method.** SITL's own physics, no Gazebo, no display —
  for working on procedures, CI, or a machine with no graphics stack.
- **Headless launching.** Gazebo runs server-only and MAVProxy opens no
  windows when there is no display, so the same launch commands work over SSH
  and in a container.

### Fixed

- The takeoff flow was a multirotor's for every airframe (above).
- The procedure runner let any exception other than an abort escape into its
  thread, freezing the interface with no message.
- A failing panel took the whole page down: one 404 left the startup chain
  rejected before the WebSocket was ever connected. Panels are isolated now
  and each reports its own failure.
- `start.sh` chose `/usr/bin/python3` because `"${VIRTUAL_ENV:-}/bin/python3"`
  expands to exactly that when the variable is unset, then tried to install
  into a PEP 668 interpreter. It now explains every candidate it rejected and
  never uses `--break-system-packages`.
- Recovery commands printed by the interface contained `<pid>` and produced
  `bash: syntax error near unexpected token 'newline'` when pasted. Every
  command any part of this project prints is now runnable as-is, and a test
  parses them.
- ArgazUI refused to start on any machine without Gazebo and ROS 2, because
  the startup preflight ran the full doctor profile. A missing simulator stops
  some models from flying, not the application from running.
- A fresh clone logged eleven 404s in the browser console: `models.json` names
  a preview image for every model, but `static/models/` is fetched separately.
- The post-flight report was generated on a daemon thread, so the last flight
  of a test session lost its report every time — a complete dataflash log and
  nothing that had read it.
- `RC_KEEPALIVE_INTERVAL` was a constant, though both terms of the budget it
  approximates are variables. It is derived now: `RC_OVERRIDE_TIME` is read
  from the vehicle and the SITL speedup is measured from the vehicle's own
  clock.

### Known limits

- **`plane-tailsitter` fails tier 1** and will keep CI red until either
  upstream tunes the frame or the procedure is proven on hardware. See above.
- **Three models fail tier 2**: `zephyr` (hand-launched wing; the plane
  takeoff procedure expects a runway roll, and "needs hand launch" is not yet
  a probed capability), `skycat_tvbs` (outside the tailsitter pitch band,
  though measured rates are calm — whether that is the aircraft or the band
  has not been established), `swan_k1_hwing` (never passes pre-arm: no
  airspeed sensor).
- **`iris` is `untested`**: it launches through `ros2 launch`, which needs a
  built `ardupilot_gz` workspace that the tier-2 image does not contain.
- **Tier 2 runs on GitHub's hosted runners** — verified, roughly 24 minutes
  for eleven models — but the image is 10.3 GB and close to a runner's free
  disk. `tier2.yml` carries self-hosted instructions if that stops working.
- **No test has ever looked at a rendered Gazebo frame.** Models are flown
  headless, so a model loaded upside-down or at the wrong scale would fly its
  procedure and pass. See [docs/manual-checklist.md](docs/manual-checklist.md)
  for this and the other gaps.
- Mission scripts on port 14551 are configured by the launch commands and
  exercised by no test at all.

### Not in this version

Deliberately out of scope and not started: multi-vehicle/swarm simulation,
HITL, scenario YAML (the `mission:` and `failures:` keys are reserved in the
procedure schema and rejected until then), failure injection through `SIM_*`,
regression comparison between runs, authentication and remote access.

---

## v1.0.0

First release. Model registry, two terminal sessions, quick command buttons
over MAVLink, ARM recovery, mission script support.
