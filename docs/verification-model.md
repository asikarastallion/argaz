# Verification model

This page states what a green result in ArgazUI claims, and — at greater
length, because it matters more — what it does not.

## The one rule everything else follows from

**Nothing is reported as verified unless a machine observed it.** Not a
plausible inference, not "it worked last week", not an ACK. A model that has
never been flown by tier 2 is `untested`, and `untested` means *not yet
verified by a machine*. It does not mean broken and it does not mean working.

This project exists because the alternative was tried. v1.0's README carried a
hand-written table of ticks; nothing produced those ticks except somebody's
belief, and at least one of them was wrong for a year — Plane takeoff had
never worked.

## Three kinds of output, and they are not interchangeable

| | produced by | can fail a run? | threshold comes from |
|---|---|---|---|
| **Acceptance criteria** | the `expect:` block of a procedure | **yes** | the procedure, declared per flight |
| **Advisories** | `flightlog.py`, from the dataflash log | no | ArduPilot's own documentation |
| **Metrics** | `metrics.py`, from the same log and the run record | no | nothing, until compared to a baseline |

Conflating the first two would mean either a noisy airframe marking a working
takeoff as broken, or a genuine acceptance failure hiding among health
warnings. Metrics are separated from both for a different reason: they carry no
threshold at all on their own, so giving them one here would quietly create a
second acceptance system with limits nobody declared in a procedure. See
[Metrics](metrics.md) and [Regression](regression.md).

## Three outcomes, and the third one is not about the aircraft

| outcome | meaning |
|---|---|
| `passed` | every step ran and every acceptance criterion held |
| `failed` | a step or a criterion did not hold. A real result about the aircraft. CI goes red. |
| `error` | the procedure could not be evaluated at all — a malformed step, a dropped link, a bug in the runner. **Says nothing about the aircraft.** |

A run's own status adds a fourth, `no-procedure`: the model was started and
stopped without running anything, so nothing was asserted. It is reported as
`untested`, never as a pass.

Since v1.4 a failed run also carries **one category saying which kind of
failure it was** — of which only `acceptance` is a verdict about the aircraft.
The outcome above says whether the flight passed; the category says who should
look at it. See [Failure classification](failure-classification.md).

## An off-nominal result is four facts, not one

A scenario injects a fault ([Fault injection](fault-injection.md)). Its record
keeps four things apart, and none is derived from another:

| | |
|---|---|
| the injected condition | what was actually done to the simulator |
| the vehicle response | what the aircraft did while it was done |
| the criteria | what the procedure said counts as acceptable |
| the verdict | whether they held |

**A fault that was successfully injected is not a pass.** The verdict comes
from the criteria and from nothing else — and a fault whose evidence never
arrived is reported as *not judged*, which is neither a pass nor a claim that
the aircraft misbehaved.

## One run is not a repeatability claim

A green run says a flight met its criteria once. It does not say the procedure
works, and this project has a case of its own where the difference mattered:
`tailsitter_takeoff` passed three times at 24.9 m, 23.6 m and 18.3 m. Each run
was green; the spread was the evidence.

A [campaign](campaigns.md) is where that claim can be made, and it is still
bounded: five runs is five runs, so the document reports counts and a spread
with the sample size beside them and computes no confidence interval from it.

## Two tiers, and only one of them may name a model

**Tier 1** flies SITL's own generic frames with no Gazebo. It verifies that the
capability probe reads the aircraft correctly, that the right procedure is
selected, that declared overrides are applied and restored, that acceptance
criteria are evaluated against measured state, and that a complete, parseable
run directory comes out.

**Tier 1 makes no claim about any Gazebo model.** A green tier-1 run does not
mean "Skywalker X8 works"; it means the plane procedure works on SITL's plane
frame.

**Tier 2** flies the real model set in Gazebo. It is the only tier whose
results may appear against a model in [docs/status.md](status.md).

A skip is not a pass. Missing binary, missing Gazebo, missing model: the test
skips with a stated reason and the model is recorded `untested`.

## Claims are narrower than rows

A `passed` row in the status table means "every procedure this model was flown
with met every criterion it declared". That is narrower than it looks, and the
gap is exactly where an unearned claim grows back.

So the status generator also emits **verification claims**: one row per
procedure, per confirmed mode transition, and per acceptance criterion, each
with its result and the run that proves it. The rule for reading them is
printed above the section itself — *anything not listed there was not
verified*.

In particular, no model in this project has been flown:

- through a mission with waypoints,
- in wind or any other disturbance,
- at the edges of its flight envelope,
- with an injected fault,
- repeatedly enough to support any statement about reliability.

## Retries cost something

The suites are allowed exactly one retry per procedure, because SITL genuinely
is timing-sensitive on a loaded machine. The retry is never silent: it is
recorded in the run's `flaky` list, every attempt stays in `procedures`, and
the status table reports the run as `flaky` rather than `passed`. Without that
visible cost the retry rule would simply be a way to hide failures.

## Where each of these lives

| | |
|---|---|
| Acceptance criteria | `argazui/procedures/*.yaml`, evaluated by `procrunner.py` |
| Outcome of one run | `runs/<id>/result.json` |
| Advisories and metrics | `runs/<id>/report.json`, summarised in `report.md` |
| What produced the result | `runs/<id>/fingerprint.json` |
| Comparison to a baseline | `runs/<id>/regression.json` |
| Model rows and claims | `docs/status.md`, generated by `argazui status` |
