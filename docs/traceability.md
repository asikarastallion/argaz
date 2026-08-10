# Traceability

Every link between an intention and the evidence for it has a name.

```
test intent   test_id        the pytest node, or `manual`
  -> procedure    procedure_id   the YAML file's own id
  -> step         step_id        <procedure>#s3, or a declared name
  -> criterion    criterion_id   <procedure>#alt-reached — always declared
  -> metric       metric_id      key@procedure
  -> run          run_id         the run directory
  -> artefact     the evidence manifest's paths
  -> verdict      the run's status and failure category
```

## Why

Every release up to v1.4 made the *facts* better: measured criteria, temporal
shapes, metrics, fingerprints, campaigns, a failure category. None of them made
it possible to follow one claim backwards. A reviewer holding
[`status.md`](status.md) and asked *"which criterion is that, which run showed
it, and what file proves it"* had to read three documents and join them by eye.

## There is no database

Nothing here is stored. A chain is **computed** from a run's `result.json`
every time it is asked for, exactly as a [campaign](campaigns.md) document is
recomputed from its runs.

A traceability record that could drift from the run it describes would be worse
than none: it would be a second source for the one thing this project keeps
single.

```bash
python3 -m argazui trace runs/<run-id>          # the chain, and any gaps in it
python3 -m argazui trace runs/<run-id> --json
```

| exit | meaning |
|---|---|
| `0` | every link resolves |
| `1` | the chain has a problem — a dangling reference, a duplicate id, an artefact the chain names and the manifest does not list |
| `2` | the run could not be read |

`1` rather than `0` because this is meant for CI. A traceability scheme nobody
verifies degrades silently, and every problem it reports still renders a table
that looks perfectly correct.

## Declared and derived identifiers

A **criterion declares its own id**:

```yaml
schema: 4

expect:
  - id: alt-reached
    condition: {alt_above: "{alt*0.9}"}
    within: 20s
```

A **step derives one from its position** — `copter_takeoff#s3` — unless it
declares one too.

The line between them is not arbitrary:

- A step identifier is only ever read *inside* the run that produced it. The
  report lists the steps; the failure classification names the one that failed.
  Position is a perfectly good name for that.
- A criterion identifier is quoted *outside* its own run: in the
  [coverage report](coverage.md), in the "what was not tested" section of
  [status.md](status.md), in a comparison of two runs months apart. Those need
  a name that survives somebody inserting a criterion above it.

Every criterion in every shipped procedure declares one, and a test asserts it.
A procedure that omits one still works — it gets `<procedure>#c2` — and the
chain **marks that identifier as derived**, because an identifier whose
stability the reader cannot see is worse than one they can.

### The shape of an id

Lower-case letters, digits, `_` and `-`, 1–48 characters, and never `#`. An id
is quoted in tables, URLs and shell commands, and one that needs escaping in
any of them is one that will be got wrong somewhere — so it is refused at load
time rather than sanitised.

Two criteria in one file may not share an id. The coverage report and the "what
was not tested" list would silently merge two different claims into one row.

## `test_id`: what a run was *for*

A run flown by a test carries that test's pytest node id. A run flown by a
person carries `manual`, which is a real answer and the one that matters:
**no test in this repository asserts what it shows.**

The flight report's [non-claims section](runs-and-evidence.md) says so
explicitly for such a run, rather than leaving a reader to infer it from the
absence of a test name.

## What the integrity check catches

| problem | meaning |
|---|---|
| `missing-id` | a recorded procedure or criterion has no identifier |
| `duplicate-id` | two steps or two criteria in one run share one |
| `dangling-link` | a criterion's id names a different procedure, or a metric is scoped to a procedure the run never executed |
| `missing-evidence` | the chain refers to an artefact the [manifest](evidence-manifest.md) does not list as present |
| `missing-verdict` | the run record carries no status, so nothing in it can be attached to a result |

## Where it appears

| | |
|---|---|
| `runs/<id>/result.json` | `test_id`, and `step_id` / `criterion_id` on every step and criterion |
| `runs/<id>/report.md` | section 1 names the intent; section 3 lists every step with its id; section 5 names every failed criterion by id |
| the Flight Runs panel | a **Traceability** block in the run sheet, with any unresolved link |
| `GET /api/runs/<id>/trace` | the chain, its problems, and which ids are derived |
| [`coverage.md`](coverage.md) | uncovered criteria, by id |

## What it is not

This is not a requirements-management system, and v1.5 deliberately did not
build one. There is no requirements document, no bidirectional matrix, no
approval workflow and no tool to import one. What there is: every claim this
project makes can be followed to the file that supports it, in one command.

Traceability identifiers were added in ArgazUI v1.5.
