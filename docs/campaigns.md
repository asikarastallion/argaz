# Repeatability campaigns

A campaign flies **the same procedure, on the same model, in the same
configuration, N times** and reports the distribution rather than a verdict.

## Why one run is not an answer

Every other layer in this project judges a single flight: the criteria held or
they did not, the metrics were these numbers, the comparison against a baseline
said this. All of it is true of *one* takeoff, and a simulation's failures are
frequently not like that. A procedure that works four times in five is neither a
working procedure nor a broken one, and neither a green run nor a red one says
which it is.

The case this project was rebuilt around makes the point. `tailsitter_takeoff`
passed three times at 24.9 m, 23.6 m and 18.3 m. Each run passed its criteria.
The *spread* is the signature of an aircraft that was not in control of its
climb — and no single run could show it.

## What a campaign is, structurally

A campaign id stamped into N ordinary run directories.

There is no new storage format and no database. Each iteration produces exactly
the evidence a single flight produces — its own `result.json`, its own dataflash
log, its own fingerprint, its own report — and the campaign document is an
aggregation over them that is recomputed from the runs every time it is asked
for.

That is deliberate: a campaign summary that could not be recomputed from the
runs would be a fourth kind of claim with no evidence underneath it.

```
runs/
├── 20260810T124500Z_iris/        result.json  ->  "campaign": {"id": ..., "index": 1, "of": 5}
├── 20260810T125130Z_iris/        result.json  ->  "campaign": {"id": ..., "index": 2, "of": 5}
├── …
└── campaigns/
    └── 20260810T124500Z_iris.copter_takeoff/
        ├── campaign.json
        └── campaign.md
```

## Running one

From the interface — **Repeatability campaign**, under the scenarios panel: pick
a procedure, pick a count, press RUN CAMPAIGN. The campaign owns START and STOP
for as long as it runs, because "each run gets independent evidence" means a
real launch and a real shutdown per iteration, not one session with the
procedure sent five times.

From the shell, to aggregate what has already been flown:

```bash
python3 -m argazui campaign                       # list the campaigns on disk
python3 -m argazui campaign <campaign-id>         # recompute and write the document
python3 -m argazui campaign <campaign-id> --json  # the same, machine-readable
```

Exit codes, because this is meant for CI:

| code | meaning |
|---|---|
| `0` | the campaign was aggregated and every run passed cleanly |
| `1` | the campaign exists and one or more runs failed, was flaky, or is incomplete |
| `2` | there is no such campaign |

`2` is kept separate from `1` for the same reason `argazui compare` keeps it:
"there is no such campaign" is different news from "the aircraft failed".

## What the document reports

| | |
|---|---|
| pass / fail / flaky / incomplete counts | one per iteration |
| clean pass rate | **clean passes only** — see below |
| per-metric mean, standard deviation, min, max | with the sample size beside each |
| failures by category | using the [failure taxonomy](failure-classification.md) |
| consistency check | did every iteration really fly the same thing? |
| per-run verdict | with a link to each run's own directory |

### A retry never becomes a pass

A run that passed only on a retry is `flaky`, exactly as it is in
[`docs/status.md`](status.md). It is not counted in the pass rate. A pass rate
that quietly included retries would be measuring the harness's patience rather
than the aircraft.

### What it refuses to say

Five runs is five runs. The document reports counts, a rate, and four summary
statistics per metric — and states the sample size next to every one of them. It
computes **no confidence interval, no p-value and no reliability figure**,
because none of them means anything at n=5 and all of them would read as though
it did.

A standard deviation is reported only from **three measured values upwards**.
Below that the cell reads `—`, which means *not enough runs to say* — not *no
variation*. Two numbers have a standard deviation and it describes nothing.

### The consistency check

A campaign's whole claim is "the same thing, N times", and that claim is
checkable: every run carries an [environment fingerprint](reproducibility.md).
The document compares them, and if the model configuration, the procedure text,
the ArduPilot commit or the firmware moved between iterations it says so at the
top of the metrics section — because a spread caused by an edit halfway through
is not a spread caused by the aircraft.

## What a campaign does not do

- It does not decide anything. A wide spread fails nothing; metrics are
  measurements, not acceptance criteria ([Metrics](metrics.md)).
- It does not compare against a baseline. That is
  [regression comparison](regression.md), which is a different question asked of
  two runs rather than one question asked of N.
- It does not fly more than one model or more than one procedure. A campaign
  over two different things has no meaningful spread.

## Where the code is

| | |
|---|---|
| `argazui/campaign.py` | the id, the executor, the statistics, the rendering |
| `argazui/app.py` | the server's launcher, which drives the ordinary START/STOP path |
| `argazui/runs.py` | the `campaign` stamp in `result.json` |

The executor takes a *launcher callable* rather than owning one, because
bringing an aircraft up genuinely differs between the server, tier 1 and tier 2.
What is identical in all three — one run directory per iteration, the same
`ProcedureRunner`, the same stamp, one aggregation at the end — is what the
class exists to keep identical.

Campaigns were added in ArgazUI v1.4.
