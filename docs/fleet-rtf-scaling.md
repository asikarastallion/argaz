# What a fleet costs: real-time factor against vehicle count

**This measurement refuted the formula it was taken to check.** `fleet.max_vehicles`
was `max(2, cores // 2)`, which allows eight vehicles on this machine. It is
now a measured constant of four, because core count turns out not to be the
limit at all.

    measured   2026-08-05
    host       Linux 7.0.0-28-generic, 16 cores
    fleet      N x hexapod_copter, one gz sim, lock_step=1, speedup 1
    method     all N armed and hovering at 10 m, /stats sampled at 1 Hz for 45 s

Hovering rather than idle on purpose: an empty world tells you nothing about
what a fleet costs.

---

## The numbers

| vehicles | RTF mean | RTF median | RTF min | RTF max | sim s / wall s |
|---|---|---|---|---|---|
| 2 | 0.781 | 0.719 | 0.544 | 1.383 | 0.886 |
| 3 | 0.572 | 0.562 | 0.361 | 1.000 | 0.607 |
| 4 | 0.434 | 0.421 | 0.265 | 0.661 | 0.489 |

`sim s / wall s` is computed independently of Gazebo's own reported RTF, from
the change in `sim_time` over the change in wall clock across the window. The
two agree, which is why both are shown.

## The shape

Simulated throughput falls as roughly **1.77 / N**:

    N=2  1.77/2 = 0.885   measured 0.886
    N=3  1.77/3 = 0.590   measured 0.607
    N=4  1.77/4 = 0.443   measured 0.489

That is close to pure serialisation. **Sixteen cores and four vehicles already
halve real-time factor.** Gazebo steps physics on one thread and lockstep makes
the server block on each FDM in turn (`ArduPilotPlugin.cc:1206`), so vehicles
are added to a serial critical path. Adding cores does not buy vehicles.

Extrapolating the fit, eight vehicles would run at about **0.22x** — a fleet
whose every timing measurement describes the host rather than the aircraft.

## What this changed

* `DEFAULT_MAX_VEHICLES = 4`, a measured constant. Not derived from
  `os.cpu_count()`, which the measurement shows is not the constraint.
* The ceiling error message now points here rather than reciting a formula.
* `argaz.toml` documents the curve instead of the old CPU reasoning.

**The ceiling is a guard rail, not a performance guarantee.** What decides
whether a run was viable is the RTF monitor, which measures the world that
actually ran. A ceiling predicts; a monitor observes, and this project prefers
the second.

## A caution about the default threshold

The shipped specs set `max_rtf_drop = 0.35`. At four vehicles the measured
*minimum* RTF is **0.265** — already below it. So a four-vehicle fleet on this
machine will legitimately be marked DEGRADED during its worst moments, and
that is the monitor working, not a fault.

Three vehicles (min 0.361) sit just above the line. The shipped
`hexapod_trio` is three for that reason as well as for being the smallest
fleet that can show a formation.

## What is still unmeasured

* Whether the 1.77/N fit holds past four. Extrapolation is not measurement,
  and the ceiling stops the fleet before the question arises.
* How the curve moves with a heavier or lighter airframe. `hexapod_copter` has
  six motors and a Lua script; a plain quad may be cheaper per vehicle.
* Whether `--speedup > 1` under lockstep changes the shape or only the scale.
* Machines other than this one. **Re-measure before trusting the default on
  different hardware** — the procedure is in the method line at the top, and
  the whole point of this file is that the number came from running it.
