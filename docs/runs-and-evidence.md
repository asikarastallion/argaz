# Runs & evidence

A **run** is one START … STOP of one model. It leaves
`runs/<UTC-time>_<model_id>/`, containing everything needed to explain
afterwards what happened.

## What is in a run directory

| file | what it is |
|---|---|
| `scenario.yaml` | the procedure files that were executed, **verbatim** |
| `result.json` | step-by-step pass/fail, the acceptance criteria, the metrics, the fingerprint |
| `console.log` | what the simulation terminal showed, ANSI stripped |
| `mavlink_events.jsonl` | mode/arm/ack/statustext, plus a 1 Hz state sample |
| `<NNNNNNNN>.BIN` | the autopilot's own dataflash log |
| `params_full.txt` | every parameter, taken from that log |
| `params_diff.txt` | the ones that differ from the **firmware** default |
| `report.md` / `report.json` | the post-flight report |
| `fingerprint.json` | what produced this result — see [reproducibility](reproducibility.md) |
| `evidence.json` | what this run was **expected** to leave behind, and what it did — see [evidence manifest](evidence-manifest.md) |
| `regression.json` / `.md` | present once the run has been compared to a baseline |
| `versions.txt` | ArduPilot SHA, Gazebo, ArgazUI, interpreter |
| `plots/` | altitude and attitude-tracking PNGs, when matplotlib is installed |

Two fields of `result.json` are worth naming separately, both added in v1.4:

- **`failure`** — why the run did not pass, as one of seven categories rather
  than as a sentence. `null` on a passing run, and deliberately never
  `"category": "none"`. See
  [Failure classification](failure-classification.md).
- **`campaign`** — the repeatability campaign this run is one iteration of, or
  `null`. It is stamped into the run rather than kept in an index file, so a
  campaign is found by reading its runs and a run that was copied still says
  what it belonged to. See [Campaigns](campaigns.md).
- **`test_id`** (v1.5) — what the run was *for*: a pytest node id, or `manual`
  for a flight somebody started by hand. `manual` is a real answer and the one
  that matters — it says no test in this repository asserts what the run shows.
  See [Traceability](traceability.md).
- **`evidence`** (v1.5) — the verdict on the run's own evidence: whether every
  required artefact is present, and what is missing if not. The full manifest
  is in `evidence.json`.

Every step and every criterion inside `procedures` also carries a `step_id` and
a `criterion_id` from v1.5, so a claim can be followed from the status table
back to the file that supports it.

A run that injected a fault also carries, per procedure, a **`faults`** list
holding four separate things: the mechanism exactly as applied (which
parameters, to what, and what they were before), the response (how long it was
actually held, on which clock, and which evidence arrived), the criteria, and
the verdict. None is derived from another, because *a fault that was
successfully injected is not a pass*. See
[Fault injection](fault-injection.md).

A campaign writes one directory of its own,
`runs/campaigns/<campaign-id>/campaign.json` and `.md`. It is an aggregation
over N ordinary runs and adds no fact that cannot be recomputed from them.

## Why the YAML is stored verbatim

That is the single-source rule made checkable. `scenario.yaml` is
byte-for-byte the file the TAKEOFF button ran and the regression test ran, so a
run can be reproduced without guessing which revision of the procedure was in
effect. It is also what the fingerprint's `procedure_hash` is computed from —
not the file on disk, which may have been edited since.

## Why it is not `argazui/run/<model_id>/`

That directory still exists and still is SITL's working directory — it is what
keeps eeprom and logs out of the ArduPilot tree. But it is *reused* by the next
launch of the same model, so nothing in it survives. Artefacts are copied out
of it into a timestamped run directory when the session stops.

## Capture is append-as-you-go

`console.log` and `mavlink_events.jsonl` are written while the run happens, not
buffered until the end. If ArgazUI is killed mid-flight the directory still
holds everything up to that moment, which is exactly when it is most wanted.

## The dataflash log is checked, not assumed

The report is built from a log written by a process ArgazUI terminates. STOP
sends SIGINT first precisely so the autopilot can close its log — but if it
ever needed longer, it would be killed mid-write and the report would quietly
cover a partial flight. *Quietly* is the part that matters, so every archived
log is verified: it must parse end to end, and its last record must carry a
timestamp. A truncated log is still kept and still analysed, and it is reported
as truncated.

## A missing log is explained, not just noted

The usual reason is not a fault at all: ArduPilot ships `LOG_DISARMED=0`, so a
session where the vehicle never armed produces no log. That is different from a
log that was expected and lost, and `artefacts.dataflash_absent_reason` says
which of the two it was.

## Parameter overrides lead the report

If a run reconfigured the aircraft, that is the first thing the report shows —
before any measurement — because every number below it was measured on a
vehicle in that state, not a stock one. A procedure may only change a parameter
it declared in its `overrides:` block, with a reason, and the declared values
are restored when the procedure ends however it ends. Whether each restore
actually succeeded is recorded: a failed restore is a fact about the vehicle's
current state.

## Reading a run without the interface

```bash
python3 -m argazui runs                       # the same listing the panel shows
python3 -m argazui report <run-dir>           # regenerate the post-flight report
python3 -m argazui report <log.BIN>           # analyse a bare log, no run directory
python3 -m argazui compare <run-dir> --baseline <run-dir>
MAVExplorer.py runs/<id>/<NNNNNNNN>.BIN       # the log, in ArduPilot's own tool
```

`runs/` is deliberately not committed to the repository: it is the *output* of
using ArgazUI. CI uploads it as a build artefact instead.
