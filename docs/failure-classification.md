# Failure classification

Every failure ArgazUI records carries **one machine-readable category**, and the
category is stored in the run rather than worked out by whoever reads it.

## Why

Until v1.4 a failed run had a verdict and a sentence. `failed` plus *"the
expected state did not arrive within 60 s"* is true and almost useless: it does
not say whether the aircraft misbehaved, whether SITL never started, whether the
dataflash log was lost, or whether ArgazUI itself broke. Those are four
different investigations, and working out which one applies by reading a
sentence is exactly the judgement a machine should not be leaving to a person in
a hurry.

## The seven categories

The set is **closed**. A taxonomy that grows a category whenever something new
goes wrong stops being a diagnosis and becomes a second copy of the error
message. Each name below is a *different investigation*.

| category | what it means | look at first |
|---|---|---|
| `environment` | The simulation could not be brought into the state the run needed: SITL or Gazebo did not start, an asset was missing, a declared override or fault could not be applied. | `console.log`, the launch commands at the top of it, `argazui doctor` |
| `vehicle_readiness` | The aircraft would not be made ready: pre-arm never passed, or an arm was refused. | the autopilot's own messages in `console.log` and `mavlink_events.jsonl` |
| `procedure` | A step of the flow did not do what it asked — a mode refused, a command rejected, a wait timed out. The acceptance criteria were never reached. | the failing step in `result.json`, and `scenario.yaml` |
| `acceptance` | The flow ran to the end and a declared criterion did not hold. | the `expect` block in `result.json`, and the plots in `report.md` |
| `evidence` | It flew and the proof is incomplete: no dataflash log, a truncated one, or two runs that cannot be compared. | `artefacts.dataflash_check` in `result.json` |
| `regression` | Nothing failed. A measured quantity moved past its threshold against a named baseline. | `regression.md` and the baseline it names |
| `infrastructure` | ArgazUI, the link or the CI job broke. | the traceback in the run's `text`, and the workflow log |

> **Only `acceptance` is a verdict about an aircraft.**
>
> The other six say the simulation, the tooling or the evidence went wrong.
> Conflating them is how a broken harness comes to be reported as a broken
> aircraft — which is the same class of untruth as an unearned tick, pointed the
> other way.

## Codes

A code is finer than a category and coarser than a message: it is what two runs
that failed *the same way* have in common. The category answers "who
investigates"; the code answers "is this the same thing as last time".

| code | category |
|---|---|
| `prearm-never-passed` | `vehicle_readiness` |
| `arm-refused` | `vehicle_readiness` |
| `step-failed`, `step-timeout` | `procedure` |
| `criterion-failed` | `acceptance` |
| `criterion-not-judged` | `acceptance` |
| `override-not-applied` | `environment` |
| `fault-not-applied`, `fault-not-cleared` | `environment` |
| `dataflash-missing`, `dataflash-truncated` | `evidence` |
| `runs-not-comparable` | `evidence` |
| `metric-degraded` | `regression` |
| `runner-error` | `infrastructure` |
| `iteration-launch-failed` | `environment` |

## The order of investigation

A run that could not arm never reached its acceptance criteria, so reporting the
unevaluated criteria would name a symptom and hide the cause. The classifier
therefore reports **the first thing that went wrong**, in this order:

1. a runner error — everything after it was recorded by a run that was already
   broken;
2. a declared override that would not apply — the vehicle is not in the
   configuration the procedure requires;
3. a declared fault that could not be injected or cleared;
4. the first failing step;
5. the first criterion that did not hold;
6. the run's evidence.

Step 6 is why a run whose procedures all passed can still fail: a flight nobody
can prove happened is worth exactly as much as one that did not.

## `criterion-not-judged` is not `criterion-failed`

A criterion whose telemetry never arrived is reported as *not judged*. It is
still an `acceptance` failure — the procedure did not establish what it claimed
to — but the code says the criterion was never actually evaluated. "Nothing was
measured" and "something was wrong" are the two answers this project exists to
keep apart, and collapsing them in either direction invents a result.

## Where it appears

| | |
|---|---|
| `runs/<id>/result.json` | `failure` — `null` on a passing run, never `"none"` |
| each procedure inside it | its own `failure`, so a two-procedure run says which one |
| `runs/<id>/report.md` | a **Why this run did not pass** section |
| `runs/<id>/regression.json` | the comparison's own classification |
| `docs/status.md` | a **Why** column, plus a per-category tally |
| the Flight Runs panel | a chip beside the verdict, with the code and detail on hover |
| `campaign.json` | `failure_categories`, counted across the campaign |

A passing run has `"failure": null`. There is deliberately no `"category":
"none"`: a reader scanning for the word *failure* would otherwise find one on
every run in the directory.

## Language

The **category label** is a user-visible string and exists in English and
Turkish, in the interface and in the API (`GET /api/failure-categories`).

The **`detail` field is English, on purpose.** It is part of a machine-readable
record that CI reads and that a comparison between two runs has to be able to
match, so it must not change with whichever language the interface happened to
be in when the flight was flown. Most of it is the autopilot's own wording in
any case, which is English regardless.

## Where the code is

`argazui/failures.py` is the single implementation. Nothing else in the code
base decides a category — `procrunner.py`, `runs.py`, `regression.py`,
`status.py` and `campaign.py` all call into it — because a second
implementation would disagree with the first the moment a step type was added.

Failure classification was added in ArgazUI v1.4.
