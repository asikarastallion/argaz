# Inter-vehicle clock behaviour without Gazebo, measured

**What this constrains:** whether a SITL-only fleet may claim anything about
relative geometry. It may not, and this is the measurement that says so.

    measured   2026-08-05
    method     2x arducopter --model quad, -I0/-I1, --serial0 tcp:0,
               SYSTEM_TIME.time_boot_ms sampled every 5 s for 120 s
    host       Linux 7.0.0-28-generic, 16 cores

---

## The result

| speedup | samples | first | last | spread over 120 s | growth |
|---|---|---|---|---|---|
| 1 | 24 | −0.9045 s | −0.9045 s | 0.0008 s | 0.0000 s/min |
| 5 | 24 | −4.5087 s | −4.5074 s | 0.0092 s | −0.0007 s/min |

Drift is computed with the read ordering corrected out:

    drift = (boot_a − boot_b) − (wall_a − wall_b) × speedup

so a perfectly synchronised pair reads 0 no matter which vehicle is polled
first.

## It is an offset, not a drift — and that matters

The two clocks **do not diverge**. Over two minutes the separation between
them changed by 0.8 ms at speedup 1 and 9 ms at speedup 5. Their *rates*
agree to within 0.0007 s per minute, which is the noise floor of this method.

What exists instead is a **constant offset**, and it scales with speedup:

    4.5087 / 0.9045 = 4.983        speedup ratio = 5

That is the signature of a fixed *startup stagger* in wall-clock terms —
about 0.9 s between the two processes reaching their boot clock — expressed in
vehicle time, which runs `speedup` times faster. It is not two clocks pulling
apart; it is two clocks that started at different moments and have kept
perfect step ever since.

The distinction is practical. A drift could be bounded by shortening the run
or resynchronising periodically. An offset that scales with speedup cannot:
running the suite at speedup 5 does not shrink it, it multiplies it by five.

## What follows for the separation monitor

`time_boot_ms` is **not a shared time base across vehicles in SITL-only mode.**
Two positions carrying the same `time_boot_ms` were recorded 0.9 s apart at
speedup 1, and 4.5 s apart at speedup 5.

For a fleet whose acceptance criterion is a 5 m minimum separation, that is
disqualifying. A multirotor climbing at 3 m/s covers 13.5 m in 4.5 s of
vehicle time. A "distance" computed from two such positions is not a distance
with a large error bar — it is two snapshots of different instants subtracted
from one another, and its error is bounded by nothing the fleet controls.

So, implemented in `fleet/separation.py`:

* `SeparationMonitor(min_separation_m, time_base_valid=False, reason=...)`
  **emits nothing**. Every `sample()` returns `measured=False` with the reason.
* `separation.csv` is written empty, with the reason recorded beside it.
* `verdict()["passed"]` is **`None`**, never `True`. A criterion that was not
  evaluated has no verdict, and reporting one as passed is exactly how an
  unearned tick reaches a table.
* The fleet report prints, in place of the separation section:
  *"no relative-geometry claim was made"* and the reason.

There is deliberately **no override flag**. A caller who wants numbers from an
undefined time base is asking for the precise failure this refusal exists to
prevent, and `SeparationMonitor` raises if constructed to refuse without a
stated reason.

    "we did not measure this"  and  "we measured it and it was fine"
    are the two answers this project exists to keep apart.

## Under Gazebo lockstep — measured, and it is NOT zero

Phase 5 re-ran the measurement with three vehicles in one Gazebo world, as the
condition for lifting the refusal. Lockstep helps a great deal. It does not
deliver a common time base.

| measurement | speedup | vehicles | max abs pair drift | mean |
|---|---|---|---|---|
| SITL-only (phase 3) | 1 | 2 | 0.9045 s | 0.9045 s |
| lockstep, `SYSTEM_TIME` | 1 | 3 | 0.1995 s | 0.0983 s |
| lockstep, newest `ATTITUDE` (10 Hz, drained) | 1 | 3 | **0.3225 s** | 0.1905 s |

The second and third rows measure the same fleet two ways. The first used
`SYSTEM_TIME`, a low-rate stream, so part of what it saw was message
staleness. The third drains a 10 Hz stream and keeps the newest sample — and
reports a *larger* number, which settles the question: the residual is not a
sampling artefact that better sampling removes.

It is also structured rather than random. Against Gazebo's own `sim_time`,
each vehicle sat at a stable offset for the whole run:

```
behind_sim_s   v1: +0.28    v2: -0.03    v3: -0.30
```

v1 consistently lags the world clock, v3 consistently leads it, and the spread
between them does not converge. **Lockstep synchronises the physics stepping,
not the vehicles' reported clocks.**

### So the refusal stands for MAVLink-derived separation

0.32 s of skew against a 5 m limit is not a rounding error. A multirotor
moving at 3 m/s covers about a metre in that time — a fifth of the criterion.
A 5.5 m true separation could read as 4.5 m, or the reverse.

Per the rule this file exists to enforce: the measurement did not show
agreement, so the monitor does not get to emit on that source.

### What authorised the monitor instead

Gazebo publishes the whole world state in a single message:

    /world/<name>/pose/info    one header.stamp, every model's position under it

Those positions are simultaneous **by construction** — one world state at one
simulated instant — rather than by an assumption about three clocks. There is
no gap to correct for because there is only one read.

So separation under Gazebo is sourced from `pose/info` and
`time_base_valid=True` is justified by *that*, not by the presence of Gazebo.
The run record names which measurement authorised it. Two practical notes,
both learned the hard way:

* it must be `pose/info`, **not** `dynamic_pose/info`. The dynamic variant
  carries only entities whose pose changed, so a vehicle that lands and
  settles silently drops out — measured: a wiring check lost a vehicle the
  moment it stopped moving and read that as "position unknown" rather than
  "exactly where it was".
* this measures where the vehicles **are**, not where their EKFs believe they
  are. That is the right quantity for a physical separation criterion, and it
  is a different question from "does each vehicle know where the others are",
  which v1.3 does not answer.

The switch remains one constructor argument, on purpose: which mode a fleet is
in is a property of the fleet, decided once at bring-up, not something each
caller decides per sample.

## What is still unmeasured

* Whether the offset stays constant across a longer run (hours) or under load
  from 8 vehicles rather than 2. Two minutes and two vehicles is what the gate
  needed.
* The lockstep case. Phase 5 must confirm that a shared clock really does make
  the offset zero rather than merely smaller — the same measurement, run under
  Gazebo, is the honest way to earn `time_base_valid=True`.
