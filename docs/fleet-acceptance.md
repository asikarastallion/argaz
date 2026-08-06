# Fleet acceptance: three outcomes, judged on time

Two rules, both inherited from v1.1 and applied one level up.

---

## 1. Three outcomes, never two

    passed         evaluated, and it held
    failed         evaluated, and it did not
    not-measured   it could not be evaluated at all

**A criterion that could not be evaluated must never render as a pass.** That
is the same untruth as a skipped test counted green, and at fleet level it is
easier to commit: six criteria showing a tidy column of ticks reads as a
healthy run whether or not anything was observed.

`not-measured` carries a **mandatory** reason — `Criterion` raises without one
— and every report has a section that exists solely to list them:

```
## What this run did not claim

The following could not be evaluated. They are **not** passes, and nothing
below should be read as evidence about them:

- **minimum pairwise separation ≥ 5 m** — SITL-only fleet: the vehicles do not
  share a clock, so positions carry no common time base
- **real-time factor stayed at or above 0.35** — SITL-only fleet: there is no
  physics server to report a real-time factor
```

If a run measured nothing, that section *is* the report.

### The verdict has a third value too

    PASSED       every criterion evaluated, and every one held
    FAILED       at least one criterion did not hold
    INCOMPLETE   nothing failed, but something could not be judged

INCOMPLETE is not a pass. A run where everything measured held but half the
criteria were unevaluated has not passed — it has not been tested. A
Gazebo-free fleet is structurally INCOMPLETE, and that is the correct answer
rather than a defect.

---

## 2. Judged on time outside, not on the worst sample

v1.1 settled this for attitude: a peak is one sample, one sample is noise, and
what separates a manoeuvre from a loss of control is how LONG the aircraft
stays outside its band. `StabilityWatch` has counted seconds-outside on the
vehicle's own clock ever since.

The fleet's own data makes the same case. A three-vehicle run measured **RTF
min 0.265, median 0.42**. A run that touched 0.265 for a fraction of a second
and a run that sat there are different animals, and a criterion keyed on the
minimum cannot tell them apart — it fails both or passes both, depending only
on where the line is drawn.

So every threshold criterion asks: **how many seconds outside, against how
many seconds of forgiveness the spec declared?**

```
| PASS | real-time factor stayed at or above 0.35 | 0.00s below 0.35 out of
         39.5s observed (wall-clock time), against a 1s tolerance |
| FAIL | minimum pairwise separation ≥ 11.983 m  | 36.49s below 11.983 m out of
         36.5s observed (simulated time), against a 1s tolerance |
```

The detail column states **which clock it counted on**, because the two
criteria deliberately differ:

| criterion | clock | why |
|---|---|---|
| separation | simulated | the stamp on the world state the positions came from — what the aircraft experienced |
| RTF | wall | real-time factor *is* the ratio of simulated to wall time, so "how long was it degraded" is a wall-clock question |

Each sample is weighted by the gap to the previous one, capped at
`MAX_GAP_S`. Same method and same two reasons as `StabilityWatch`: samples do
not arrive evenly, and a gap in the data must be able neither to manufacture
nor to excuse time outside a band. A 600 s dropout contributes at most one
`MAX_GAP_S`, which is asserted by test.

### "It did not do it" and "nobody watched" are different

A vehicle with no altitude data makes the fleet-level altitude criterion
**not-measured**, not failed. A vehicle that ran no procedure contributes
not-measured, never a pass. One missing observation withdraws the fleet-level
claim rather than converting into a verdict about the aircraft.

---

## Every claim names what authorised it

Separation was allowed to speak because `/world/<w>/pose/info` carries every
model's position under one header stamp — not because Gazebo happened to be
running. That distinction is the whole of phase 5 and it is worthless if a
reader cannot see it without opening the source, so it is in the report:

```
### What authorised each claim

- **minimum pairwise separation ≥ 5 m** — /world/runway/pose/info — one
  world-state message carries every model's position under a single header
  stamp, so the positions are simultaneous by construction
- **real-time factor stayed at or above 0.35** — /stats, read from the running
  physics server
```

The same record goes into `fleet.json` under `authorisations`.

---

## The report is the last artefact written

Criterion 6 is "no orphan processes, all port leases released" — a fact about
the **end** of the run, which does not exist until teardown has happened. A
report written before teardown can only mark it not-measured, which is honest
but needlessly incomplete.

So teardown-then-report is an explicit, idempotent call rather than something
hidden in a finalizer whose ordering is subtle. The first version relied on
pytest finalizer ordering and read the report before it was written.

---

## Versions come from `versions.environment()` and nowhere else

There is exactly one answer to "which software produced this result". v1.1
phase 3 had two, they disagreed, and no two runs could be lined up. The report
reads that record; it does not assemble a second one.

---

## A fleet run is never a model claim

`docs/status.md` reads model rows from `tier2`-marked tests and nothing else.
Now that `hexapod_copter` flies in a fleet under Gazebo, the risk of a fleet
result leaking into the model table is real and new — a fleet test's id
legitimately names the model.

Asserted directly in `tests/test_status_table.py`:

* a fleet suite record cannot create a model row, even when its nodeid names
  the model;
* a passing fleet run cannot overturn a failing tier-2 verdict — the dangerous
  direction;
* a fleet run directory beside model runs stays inert;
* fleet markers are not counted in the tier-1 summary either.

Verified by mutation: making `fleet_gazebo` feed model rows fails exactly the
first two.

Every report also ends by saying so in plain words.

---

## The three report shapes, all produced from real data

| run | verdict | how it was induced |
|---|---|---|
| the recorded 3-vehicle Gazebo flight | **PASSED** | flown |
| one vehicle fails its own criteria | **FAILED** | v2 reported `failed` at 2.4 m against a 5 m target |
| a fleet criterion fails | **FAILED** | asked the recorded run for 11.98 m of separation when it held 9.98 m |
| a Gazebo-free fleet | **INCOMPLETE** | separation and RTF genuinely unmeasurable |

The second failure needed no vehicles flown at each other and nothing
fabricated: the flight happened, the distances are the ones Gazebo reported,
and the criterion was simply asked a stricter question than the run can answer
yes to. Examples are under `runs/example_failed_vehicle/`,
`runs/example_failed_separation/` and `runs/example_sitl_only/`.
