# Verification and validation

Two words that get used interchangeably and mean different things. ArgazUI does
one of them.

| | question it answers | ArgazUI |
|---|---|---|
| **Verification** | Did the implementation satisfy the criteria somebody declared? | **yes, this is what it does** |
| **Validation** | Are the model, the criteria and the scenario representative of the behaviour anyone actually cares about? | **no** |

Every green result in this repository is a verification result. It says a
procedure ran and the criteria in it held. It says nothing about whether those
were the right criteria, whether the simulated aircraft resembles the real one,
or whether the scenario is one that ever happens.

## Why this page exists

Because the gap closes by itself in a reader's head.

A page of passing checks, a coverage figure, a run directory full of hashed
artefacts and a traceability chain that resolves — all of it reads as *this
aircraft works*. None of it says that. The whole apparatus of this project is
built to make verification claims precise, and precision is exactly what makes
them easy to over-read.

So the flight report's last section is
[**Limitations and non-claims**](runs-and-evidence.md), and this page is what it
points at.

## What SITL is evidence about

SITL is evidence about **software behaviour under a simulated physics model**.
That is genuinely useful and genuinely limited.

It can show:

- that the autopilot's logic does what the procedure asked — a mode was
  entered, a command was accepted, an altitude was reached and held;
- that ArgazUI's own layers work — the procedure runner, the criteria, the
  evidence chain;
- that a change made something measurably worse than a named baseline;
- that behaviour repeats, or does not, across N runs.

It cannot show:

- that the airframe flies. The dynamics model is a model. A tailsitter that
  hovers perfectly in SITL may be untrimmable in air, and one that tumbles in
  SITL may be fine.
- that the sensors behave. Simulated GPS, IMU and barometer noise are models of
  noise, chosen for plausibility rather than measured from a device.
- that the timing holds. SITL runs at a speedup on a general-purpose OS; a real
  flight controller runs a real scheduler on real hardware.
- that anything about power, temperature, vibration, EMI, airframe flex, or any
  of the things that actually break aircraft, is true.

> **No dynamics model, however good, is evidence about hardware.**

## What would count as validation

Not this tool. Validation of a flight-control claim needs, at minimum:

- flight test on the real airframe, instrumented;
- a comparison between what the simulation predicted and what the aircraft did;
- criteria derived from what the aircraft is *for*, reviewed by somebody who
  knows the mission — rather than from what the simulator can measure.

ArgazUI can contribute to the second of those: a run directory is a complete,
hashed, reproducible record of what the simulation predicted, and comparing it
against a real flight is a reasonable thing to want to do. It does not perform
that comparison and it makes no claim to.

## Where the criteria come from, and what that means

A criterion in this project is written by whoever wrote the procedure. Its
threshold is defended in a comment and, where it comes from ArduPilot's own
documentation, cited — see [acceptance-criteria.md](acceptance-criteria.md).

That is an honest engineering practice and it is **not** the same as a
requirement. Nothing here traces to a stated operational need, because there is
no requirements document to trace to and v1.5 deliberately did not invent one.
[Traceability](traceability.md) links a claim to its evidence; it does not link
it to a purpose.

The consequence is worth stating plainly: **a criterion this project satisfies
was chosen by this project.** A green run means the aircraft did what somebody
here decided to ask of it.

## The honest summary

ArgazUI answers: *what was executed, under exactly which configuration, what
did the vehicle do, what criteria were evaluated, what evidence proves the
result, and how does it compare with a known baseline?*

It does not answer: *is that the right thing to have asked, and would the real
aircraft agree?*

Keeping those two apart is the point of the whole tool. A verification platform
that let the second question be answered by the first would be a more
convincing version of the hand-written support table v1.0 shipped with — which
is the thing this project exists to have replaced.
