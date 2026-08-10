# Validation limits

Four named categories in which an experiment states, explicitly, what its result
does not establish.

[Verification vs validation](verification-vs-validation.md) says why the
distinction matters. This page is the mechanism: where the statements are
written, what belongs in each category, and which ones are added whether an
author writes them or not.

## Why an experiment needed this and a run did not

Every flight report has carried a **Limitations and non-claims** section since
v1.5, and it works. But those limits are the ones true of *any* run this tool
produces. They are written by the tool, about the tool.

An experiment is where that stops being enough. It states a question, controls a
comparison and produces a number — and the moment a document says

> GPS loss cost 4.7° of RMS roll tracking error

it is being read as a fact about an aircraft rather than about a simulation of
one. That gap cannot be closed by better measurement. It is closed, if at all,
by somebody writing down what the simulation assumed, what its model does not
contain, which physical effects were never in it, and which conditions the test
deliberately did not enter.

So an experiment declares its own limits, in the file, beside the criteria — and
they are part of the document rather than a footnote to it.

## The four categories

| category | what belongs in it | what a reader does with it |
|---|---|---|
| `assumptions` | what had to be true for the numbers to mean anything | **checks it** |
| `model_limitations` | what the simulated aircraft is *not* | **bounds the claim** |
| `unverified_effects` | physics that was absent, or present and never compared against anything real | **does not extrapolate** |
| `out_of_scope` | conditions the experiment deliberately did not enter | **runs something else** |

They are separate because a reader does something different with each.
Collapsing them into one `notes:` field — which is what every project does
eventually — turns four actionable statements into a paragraph nobody reads.

An unknown category is **rejected at load time** rather than kept. A statement
filed under a name the report does not print is a limit somebody wrote down and
nobody ever read, which is worse than not writing it: the author believes it was
stated.

## Declaring them

```yaml
limitations:
  assumptions:
    - en: >-
        GPS loss is simulated by switching the SITL receiver off with SIM_GPS
        parameters. The autopilot sees the receiver stop reporting; it does not
        see one that is jammed, spoofed, or reporting a plausible wrong position.
      tr: >-
        GPS kaybi, SIM_GPS parametreleriyle SITL alicisi kapatilarak simule edilir...
  model_limitations:
    - en: The EKF's behaviour without GPS depends on which other sensors the
          model provides and on parameters such as EK3_SRC1_POSXY...
  unverified_effects: [...]
  out_of_scope: [...]
```

All four are optional. A statement is a string or an `{en, tr}` map; both
languages are release artefacts, so new files should supply both.

## Standing limitations

Some limits are true of every experiment this tool can run, whatever the file
says. They are added automatically, printed alongside the declared ones, and
marked *(standing)* so a reader can tell them apart from the ones somebody wrote
for this particular question.

A definition **cannot drop one.** That is the point: a document that could omit
"nothing here was measured on hardware" by leaving a key out would omit it, and
the person who read that document would not know it was missing.

The current standing set — see `argazui/argazui/limitations.py` for the text,
which is the authority:

| category | what is always said |
|---|---|
| `assumptions` | everything is SITL, nothing was measured on hardware; the arms are assumed to have flown the same configuration, and the fingerprint is what makes that checkable; simulated time is the vehicle's clock |
| `model_limitations` | a SITL frame is a generic airframe of its class; a Gazebo model reproduces what its author declared and has never been compared against a measurement of a real aircraft |
| `unverified_effects` | battery sag, ESC and motor dynamics, propeller efficiency, structural flexibility and wear are absent or idealised; real sensors fail in ways no parameter reproduces |
| `out_of_scope` | HITL, real flight controllers and real airframes; more than one vehicle; anything done outside the recorded procedures |

## An experiment that declares none

It is allowed, and the document says so in as many words:

> **This experiment declared no limitations of its own**, so only the standing
> ones below apply. That is allowed and it is worth noticing: the limits that
> matter most to a particular question are usually the ones only its author
> knows.

That is a nudge, not a gate. A rule that forced every experiment to declare a
limitation would produce a repository full of limitations written to satisfy the
rule, which is worse than an honest blank.

## Where they appear

| | |
|---|---|
| `experiment.md` §10 | declared first, then standing, grouped by category |
| `experiment.json` | `limitations` — one row per statement, with its `source` |
| the Experiments panel | the same list, under the comparison |
| `GET /api/limitations` | the four categories, what belongs in each, and the standing statements |

Served from the module rather than duplicated in the interface, for the same
reason the fault and metric catalogues are: a standing limitation added to the
code must not be able to go missing from the page that shows them.

## What this is not

It is not a risk register, a hazard analysis or a safety case. It records what a
simulation result does not establish. Deciding what to *do* about that — whether
the gap matters, what evidence would close it, whether the aircraft may fly — is
engineering judgement that belongs to a person, and nothing in this repository
attempts it.

Validation limits were added in ArgazUI v1.6.
