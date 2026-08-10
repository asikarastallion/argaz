# Failure investigation

A run went red. This page is the path from that to the file that explains it.

## Start with the category, not the message

Open `runs/<run-id>/result.json` and read one field:

```json
"failure": {
  "category": "vehicle_readiness",
  "code": "arm-refused",
  "detail": "Arm the motors: ARM: REJECTED (MAV_RESULT_FAILED) — autopilot: PreArm: AHRS: waiting for home",
  "source": "steps[1]",
  "procedure": "copter_takeoff"
}
```

The same field is in the **Why** column of [`docs/status.md`](status.md), on a
chip beside the verdict in the Flight Runs panel, and at the top of `report.md`.
It tells you which of seven investigations this is —
see [Failure classification](failure-classification.md) for what each means.

`"failure": null` means the run passed. There is no "none" category.

## Then follow the category

### `environment` — the simulation never got into the right state

```bash
head -40 runs/<run-id>/console.log     # the launch commands are at the top
python3 -m argazui doctor              # every prerequisite, with a fix per failure
```

The launch commands in the run's `console.log` are the exact lines that were
typed. Paste them into a terminal: whatever goes wrong there goes wrong the same
way here, and it is usually a missing world file, a missing parameter file or an
environment script that did not source.

If the code is `fault-not-applied`, the simulator refused a declared fault — see
[Fault injection](fault-injection.md). ArgazUI aborted rather than flying
nominally, which is the intended behaviour, not a second bug.

If the code is `override-not-applied`, the vehicle refused a parameter the
procedure declared in `overrides:`. The aircraft was never in the configuration
the procedure requires, so nothing after that point is meaningful.

### `vehicle_readiness` — the aircraft would not become ready

The autopilot said why. It is in the failure `detail`, and in full in:

```bash
grep -i "prearm\|arm:" runs/<run-id>/console.log
python3 - <<'PY'
import json, pathlib
for line in pathlib.Path("runs/<run-id>/mavlink_events.jsonl").read_text().splitlines():
    event = json.loads(line)
    if event.get("kind") == "statustext":
        print(event["t"], event["text"])
PY
```

ArgazUI already retries three specific transient refusals for up to 35 s (see
the README's *Automatic ARM recovery*). A `vehicle_readiness` failure means the
refusal was not one of those, or it did not clear.

### `procedure` — a step did not do what it asked

`source` names the step. Read it in `result.json`, then read the procedure
itself — which is archived verbatim, so you are reading the revision that ran
and not whatever the file says today:

```bash
python3 -c "import json;d=json.load(open('runs/<run-id>/result.json'));\
print(*(f\"{s['status']:8s} {s['label']}: {s['text']}\" for s in d['procedures'][0]['result']['steps']),sep='\n')"
less runs/<run-id>/scenario.yaml
```

A `step-timeout` on a `wait_for` is usually the aircraft doing something slowly
rather than not at all — the mode timeline in `report.md` and the altitude plot
will show which.

### `acceptance` — the flight ran and a criterion did not hold

This is the only category that is a verdict about the aircraft.

Every criterion records **what was actually measured**, not just that it failed:

```bash
python3 -c "import json;d=json.load(open('runs/<run-id>/result.json'));\
print(*(f\"{'OK ' if e['passed'] else 'FAIL'} [{e['kind']}] {e['label']}: {e['text']}\" for e in d['procedures'][0]['result']['expect']),sep='\n')"
```

Then `runs/<run-id>/report.md` and its plots, which are built from the
autopilot's own dataflash log at full rate rather than from telemetry.

If the code is `criterion-not-judged`, the criterion was never evaluated because
the telemetry it rests on never arrived. That is a different problem from the
aircraft misbehaving, and it usually points at a stream that was not requested
or a link that dropped — check `stability.samples` in the same document.

### `evidence` — it flew and the proof is incomplete

```bash
python3 -c "import json;print(json.load(open('runs/<run-id>/result.json'))['artefacts'])"
```

`dataflash_absent_reason` states why there is no log. The common one is not a
fault at all: ArduPilot ships `LOG_DISARMED=0`, so a session where the vehicle
never armed writes no log, and nothing was lost.

`dataflash-truncated` means SITL was killed before it closed the file. STOP
sends SIGINT first precisely so this does not happen; if it did, something else
killed the process group.

`runs-not-comparable` comes from a regression comparison rather than a flight —
see [Regression](regression.md), and the `configuration_drift` list in
`regression.json`, which names the field that moved.

### `regression` — nothing failed and something got worse

```bash
less runs/<run-id>/regression.md
```

It names the baseline, every metric, the delta, the threshold and the verdict.
Remember what a metric is: a measurement with no threshold of its own
([Metrics](metrics.md)). A regression does not mean a criterion failed — it
means the aircraft is doing the same thing measurably less well than the
baseline did.

### `infrastructure` — ArgazUI or the link broke

Not a verdict about the aircraft, and it must never be reported as one. The
`text` field carries the exception; the browser console and the terminal
ArgazUI was started from carry the rest.

## Is it one failure or a pattern?

A single red run does not distinguish "this is broken" from "this fails
sometimes". Fly it repeatedly:

```bash
# from the interface: Repeatability campaign -> pick the procedure -> RUN CAMPAIGN
python3 -m argazui campaign <campaign-id>
```

The campaign document reports the pass rate, the spread of every metric, and
`failure_categories` — how many of each kind occurred across the runs. Three
`environment` failures out of five is a different diagnosis from three
`acceptance` ones, and the counts are the fastest way to tell.

See [Repeatability campaigns](campaigns.md).

## Is it this build, or was it always like this?

```bash
python3 -m argazui compare runs/<current> --baseline runs/<a-known-good-run>
```

The comparison refuses to run across a changed model, procedure, ArduPilot
commit or firmware unless told to in so many words — which is itself the answer
some of the time. See [Regression](regression.md) and
[Reproducibility](reproducibility.md).

## What not to do

- **Do not weaken a criterion to make a run green.** A test tool that adjusts
  the aircraft or its limits until its own test passes proves nothing. Every
  parameter change a procedure makes has to be declared with a reason, and that
  rule exists for this exact temptation.
- **Do not read a skip as a pass.** A skipped test records the model as
  `untested`, which means nothing was proven — not that nothing is wrong.
- **Do not treat an advisory as the cause.** Advisories are health findings from
  the dataflash log and never change a verdict. A noisy airframe is not why a
  criterion failed.
