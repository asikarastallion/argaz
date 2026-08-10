# Coverage

<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Generated:  2026-08-10T15:08:01Z
     Source:     artefacts/tier1, artefacts/tier2
     Regenerate: python3 -m argazui coverage --runs runs --out docs/coverage.md
     Any edit here is overwritten by the next CI run. -->

Computed from **33** recorded run(s) and the procedure files in this checkout, at **2026-08-10T15:08:01Z**.

**This is not a test count.** A test count goes up when somebody adds a test and never goes down when somebody adds an aircraft, a procedure or a criterion nobody runs. Every dimension below is measured over named things that could be exercised, and every one of them lists what it did not reach.

| Dimension | Covered | Declared | |
|---|---:|---:|---|
| Model coverage | 10 | 11 | 91% |
| Procedure coverage | 9 | 13 | 69% |
| Acceptance-criterion coverage | 24 | 32 | 75% |
| Fault and scenario coverage | 4 | 6 | 67% |

## Model coverage

Registry entries that tier 2 has flown in Gazebo. Tier 1 does not count: it flies SITL's own generic frames and says nothing about an airframe.

**1 of 11 not covered:**

| Item | What it is |
|---|---|
| `iris` | Iris Quadcopter (ROS2 + RViz) (Copter) |

## Procedure coverage

Procedure files that some recorded run actually executed.

**4 of 13 not covered:**

| Item | What it is |
|---|---|
| `plane_land_rtl` | Plane return (RTL — does not land) [land] |
| `plane_takeoff_auto` | Plane takeoff (AUTO mission) [takeoff] |
| `tailsitter_land` | Tailsitter landing (QLAND) [land] |
| `vtol_takeoff_mission` | VTOL takeoff (AUTO mission) [takeoff] |

## Acceptance-criterion coverage

Acceptance criteria that were actually evaluated. A criterion the procedure never reached is not covered — it produced no information about the aircraft.

**50 evaluated criterion result(s) could not be attributed to a declared criterion.** They come from runs recorded before criterion identifiers existed (ArgazUI v1.5). They are not matched by position — the procedure may have been edited since, and a coverage figure inflated by a guess is the thing this project exists to remove. Fly the procedures once more to cover them.

**8 of 32 not covered:**

| Item | What it is |
|---|---|
| `plane_land_rtl#mode-rtl` | in RTL |
| `plane_land_rtl#still-flying` | still armed and flying — RTL does not land a fixed wing |
| `plane_takeoff_auto#alt-reached` | climbed to at least 85% of the commanded takeoff altitude |
| `plane_takeoff_auto#still-armed` | still armed |
| `tailsitter_land#disarmed` | disarmed after landing |
| `tailsitter_land#on-ground` | on the ground |
| `vtol_takeoff_mission#alt-reached` | reached at least 85% of the commanded altitude |
| `vtol_takeoff_mission#still-armed` | still armed |

## Fault and scenario coverage

Fault kinds the code implements, and the faults scenarios declare, that some run actually injected.

**2 of 6 not covered:**

| Item | What it is |
|---|---|
| `gps_degradation` | mechanism: GPS degradation |
| `mavlink_degradation` | mechanism: MAVLink degradation |

## What a covered item does and does not mean

Covered means *some recorded run exercised this and produced a result*. It does not mean the result was a pass, it does not mean the item was exercised recently, and it does not mean it was exercised more than once — see [status.md](status.md) for verdicts and [campaigns.md](campaigns.md) for repetition.

An **uncovered** item is the more useful entry. It is something this project declares and has never run, which is exactly the gap a verification claim must not be read across.
