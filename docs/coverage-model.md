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
