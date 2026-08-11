# The coverage model

What ArgazUI counts as coverage, and what it refuses to count.

> This page is the reasoning. The **report** is generated from the runs on disk
> and is overwritten by every CI run — see [coverage.md](coverage.md), the same
> relationship [verification-model.md](verification-model.md) has with
> [status.md](status.md).

## Not a test count

A test count goes up when somebody adds a test and never goes down when
somebody adds an aircraft, a procedure or a criterion nobody runs. It measures
effort, not reach, and a project that watches it will eventually be proud of a
suite that covers less than it did last month.

So coverage is measured over **named things that could be exercised**, in five
dimensions, and every dimension lists the items it did not reach.

> A percentage with no list under it is an invitation to stop reading. The list
> is the deliverable.

## The five dimensions

| dimension | covered when |
|---|---|
| **Models** | tier 2 has flown the registry entry in Gazebo |
| **Procedures** | some recorded run executed the procedure file |
| **Criteria** | some run actually **evaluated** the acceptance criterion |
| **Faults** | some run actually **injected** the fault kind or the declared scenario fault |
| **Experiments** | some recorded run carried the experiment's stamp — listed per experiment **and per arm** |

An [experiment](experiments.md)'s arms are listed separately from the
experiment itself, for the same reason a declared scenario fault is listed
separately from the mechanism behind it: an experiment half of whose arms were
flown has answered nothing, and it would otherwise appear as covered. A
comparison needs both sides.

Tier 1 does not count towards model coverage. It flies SITL's own generic
frames and says nothing about an airframe — reading a tier-1 run as model
coverage is exactly the conflation [status.md](status.md) exists to prevent,
pointed at a different table.

A **skipped** tier-2 test is not coverage either. It is the absence of it.

## Two refusals

### A criterion nobody reached is not covered

A criterion the procedure never got to — because an earlier step failed, or
because the telemetry it rests on never arrived — produced no information about
the aircraft. Counting it because it appears in a `result.json` would let a run
that aborted at step two report full criterion coverage.

A criterion that was evaluated and **failed** *is* covered. Covered means "some
run exercised this and produced a result", and a failing criterion produced the
most informative kind. Counting only passes would make coverage a second, worse
pass rate.

### A criterion with no identifier is counted, not guessed

Runs recorded before ArgazUI v1.5 carry no
[criterion identifiers](traceability.md). They are **not** matched to today's
criteria by position: the procedure may have been edited since, and a coverage
figure inflated by a guess is the exact shape of the unearned claim this
project was rebuilt to remove.

They are counted and reported instead, so a 0% first reading after an upgrade
has a stated reason rather than looking like a project that tests nothing. Fly
the procedures once more and the figure fills in.

## Running it

```bash
python3 -m argazui coverage                        # writes docs/coverage.md
python3 -m argazui coverage --runs runs --json
```

Exit code is always `0`. **Coverage is a measurement, not a gate.** A project
with an uncovered procedure has a gap, and turning that into a red build would
make the honest thing to do — declaring a procedure before it can be flown —
the thing that breaks CI.

`python3 -m argazui status` writes `coverage.md` alongside `status.md` from the
same collection, so the "what was not tested" summary in one and the full lists
in the other can never disagree about which runs they read.

## What "covered" does not mean

- Not that the result was a pass — see [status.md](status.md).
- Not that it was exercised recently.
- Not that it was exercised more than once — see [campaigns.md](campaigns.md).

An **uncovered** item is the more useful entry: something this project declares
and has never run, which is exactly the gap a verification claim must not be
read across.

## The mechanism matrix: five answers instead of one bit

A fraction per dimension is the right summary and it cannot answer the question
v1.7 asks: *is the mechanism this project SAYS it has actually executable, and
has anything ever executed it?*

"Covered" is one bit, and there are five distinguishable answers. A fault kind
that exists in `faults.KINDS` with unit tests and no scenario is not the same
as one with a scenario that no run has flown, and neither is the same as one
flown and judged by criteria. Reporting all three as "uncovered" loses the
distinction that says what to do next.

| state | meaning |
|---|---|
| `DEFINED` | the code or a document declares it |
| `EXECUTABLE` | something can actually invoke it — a scenario points at it |
| `EXERCISED` | a recorded run invoked it against a vehicle |
| `VERIFIED` | a recorded run invoked it **and** a criterion judged the result |
| `NOT_EXERCISED` | definable and executable, and nothing has run it |
| `UNSUPPORTED` | declared and known not to be executable here, with a reason |

### `VERIFIED` is the only one that says anything about an aircraft

And it is deliberately hard to reach. A fault that was injected and left
unjudged is `EXERCISED`, not `VERIFIED`, because *the mechanism worked* and
*the aircraft handled it* are two different claims — the same distinction
`FaultResult` enforces with four separate fields. A procedure whose every
criterion was refused for missing evidence has been exercised and has verified
nothing.

`VERIFIED` means **judged**, not **passed**. A criterion that was measured and
did not hold has verified exactly as much as one that passed: the mechanism ran
and produced a verdict about the aircraft. Requiring a pass would make the
matrix reward green rather than evidence.

### Nothing may be promoted without a run directory

Every cell above `EXECUTABLE` names the run ids behind it, so a claim in the
matrix can be opened and checked. A mechanism that cannot be exercised here is
marked `UNSUPPORTED` with the reason and is **not** faked — a report that
punished a project for an absent dependency would push somebody to invent the
evidence, which is the failure this matrix exists to make visible.

The matrix is rendered into `docs/coverage.md` beside the dimensions, from the
same run directories, recomputed on every call. It is not a sixth dimension: it
is not a fraction, and forcing it into one would lose the states.
