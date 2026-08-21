# Coverage

<!-- GENERATED FILE — DO NOT EDIT BY HAND.
     Generated:  2026-08-21T04:18:49Z
     Source:     artefacts/tier1, artefacts/tier2
     Regenerate: python3 -m argazui coverage --runs runs --out docs/coverage.md
     Any edit here is overwritten by the next CI run. -->

Computed from **57** recorded run(s) and the procedure files in this checkout, at **2026-08-21T04:18:49Z**.

**This is not a test count.** A test count goes up when somebody adds a test and never goes down when somebody adds an aircraft, a procedure or a criterion nobody runs. Every dimension below is measured over named things that could be exercised, and every one of them lists what it did not reach.

| Dimension | Covered | Declared | |
|---|---:|---:|---|
| Model coverage | 10 | 11 | 91% |
| Procedure coverage | 12 | 15 | 80% |
| Acceptance-criterion coverage | 28 | 34 | 82% |
| Fault and scenario coverage | 8 | 8 | 100% |
| Experiment coverage | 0 | 5 | 0% |

## Model coverage

Registry entries that tier 2 has flown in Gazebo. Tier 1 does not count: it flies SITL's own generic frames and says nothing about an airframe.

**1 of 11 not covered:**

| Item | What it is |
|---|---|
| `iris` | Iris Quadcopter (ROS2 + RViz) (Copter) |

## Procedure coverage

Procedure files that some recorded run actually executed.

**3 of 15 not covered:**

| Item | What it is |
|---|---|
| `plane_takeoff_auto` | Plane takeoff (AUTO mission) [takeoff] |
| `tailsitter_land` | Tailsitter landing (QLAND) [land] |
| `vtol_takeoff_mission` | VTOL takeoff (AUTO mission) [takeoff] |

## Acceptance-criterion coverage

Acceptance criteria that were actually evaluated. A criterion the procedure never reached is not covered — it produced no information about the aircraft.

**6 of 34 not covered:**

| Item | What it is |
|---|---|
| `plane_takeoff_auto#alt-reached` | climbed to at least 85% of the commanded takeoff altitude |
| `plane_takeoff_auto#still-armed` | still armed |
| `tailsitter_land#disarmed` | disarmed after landing |
| `tailsitter_land#on-ground` | on the ground |
| `vtol_takeoff_mission#alt-reached` | reached at least 85% of the commanded altitude |
| `vtol_takeoff_mission#still-armed` | still armed |

## Fault and scenario coverage

Fault kinds the code implements, and the faults scenarios declare, that some run actually injected.

All 8 covered.

## Experiment coverage

Declared experiments, and each arm of them, that some recorded run actually flew. An arm is listed on its own because an experiment half of whose arms were flown has answered nothing — a comparison needs both sides.

**5 of 5 not covered:**

| Item | What it is |
|---|---|
| `copter_gps_loss_vs_nominal` | GPS loss against a nominal climb |
| `copter_gps_loss_vs_nominal#nominal` | copter_takeoff × 3 [reference] |
| `copter_gps_loss_vs_nominal#gps_loss` | copter_gps_loss × 3 [treatment] |
| `copter_takeoff_repeatability` | Copter takeoff repeatability |
| `copter_takeoff_repeatability#repeat` | copter_takeoff × 5 [treatment] |

## What a covered item does and does not mean

Covered means *some recorded run exercised this and produced a result*. It does not mean the result was a pass, it does not mean the item was exercised recently, and it does not mean it was exercised more than once — see [status.md](status.md) for verdicts and [campaigns.md](campaigns.md) for repetition.

An **uncovered** item is the more useful entry. It is something this project declares and has never run, which is exactly the gap a verification claim must not be read across.

## Mechanism coverage

What this installation DECLARES it can do, against what a run directory on disk shows it has actually done. `Verified` is the only column that says anything about an aircraft, and it requires a recorded flight in which a criterion judged the result — a mechanism that was invoked and left unjudged is `Exercised`, not `Verified`.

Read from 57 run(s) under `artefacts/tier1`, `artefacts/tier2`.

| Mechanism | Kind | Defined | Executable | Exercised | Verified | Evidence | State |
|---|---|:-:|:-:|:-:|:-:|---|---|
| `gps_degradation` | fault | yes | yes | yes | yes | `20260813T102704Z_sitl_quad_degradation`, `20260813T102728Z_sitl_quad_degradation` | **VERIFIED** |
| `gps_loss` | fault | yes | yes | yes | yes | `20260813T102957Z_sitl_quad_scenario`, `20260813T103021Z_sitl_quad_scenario` | **VERIFIED** |
| `mavlink_degradation` | fault | yes | yes | yes | yes | `20260813T102752Z_sitl_quad_degradation` | **VERIFIED** |
| `mavlink_interrupt` | fault | yes | yes | yes | yes | `20260813T103106Z_sitl_quad_scenario` | **VERIFIED** |
| `copter_gps_degradation` | procedure | yes | yes | yes | yes | `20260813T102704Z_sitl_quad_degradation`, `20260813T102728Z_sitl_quad_degradation` | **VERIFIED** |
| `copter_gps_loss` | procedure | yes | yes | yes | yes | `20260813T102957Z_sitl_quad_scenario`, `20260813T103021Z_sitl_quad_scenario` | **VERIFIED** |
| `copter_land` | procedure | yes | yes | yes | yes | `20260812T073659Z_bicopter`, `20260812T073904Z_hexapod_copter` | **VERIFIED** |
| `copter_link_degradation` | procedure | yes | yes | yes | yes | `20260813T102752Z_sitl_quad_degradation` | **VERIFIED** |
| `copter_link_loss` | procedure | yes | yes | yes | yes | `20260813T103106Z_sitl_quad_scenario` | **VERIFIED** |
| `copter_takeoff` | procedure | yes | yes | yes | yes | `20260101T000000Z_sitl_quad`, `20260812T073659Z_bicopter` | **VERIFIED** |
| `plane_land` | procedure | yes | yes | yes | yes | `20260812T074209Z_skywalker_x8`, `20260812T075216Z_wsc_aircraft` | **VERIFIED** |
| `plane_land_rtl` | procedure | yes | yes | yes | yes | `20260813T103544Z_sitl_plane` | **VERIFIED** |
| `plane_takeoff` | procedure | yes | yes | yes | yes | `20260812T074209Z_skywalker_x8`, `20260812T075216Z_wsc_aircraft` | **VERIFIED** |
| `tailsitter_takeoff` | procedure | yes | yes | yes | yes | `20260813T103412Z_sitl_tailsitter`, `20260821T040044Z_skycat_tvbs` | **VERIFIED** |
| `vtol_land` | procedure | yes | yes | yes | yes | `20260812T073525Z_alti_transition_quad`, `20260812T074514Z_skywalker_x8_quad` | **VERIFIED** |
| `vtol_takeoff` | procedure | yes | yes | yes | yes | `20260812T073525Z_alti_transition_quad`, `20260812T074514Z_skywalker_x8_quad` | **VERIFIED** |
| `tailsitter_land` | procedure | yes | yes | — | — | — | **NOT_EXERCISED** |
| `plane_takeoff_auto` | procedure | yes | — | — | — | — | **UNSUPPORTED** |
| `vtol_takeoff_mission` | procedure | yes | — | — | — | — | **UNSUPPORTED** |

Counts: VERIFIED 16, NOT_EXERCISED 1, UNSUPPORTED 2.

### Declared and unproven

Named rather than left to be discovered. None of these is a defect on its own; each is a claim this project has not earned yet, and publishing the list is the point.

* **`tailsitter_land`** (NOT_EXERCISED) — needs a tailsitter airframe. The only one in this suite is SITL's generic `plane-tailsitter`, which ArduPilot's own test suite lists as unstable in hover and unflyable in cruise — `tailsitter_takeoff` already fails on it deliberately, at 1882°/s. Flying a landing procedure on an aircraft that is tumbling would produce a verdict about the frame and record it against the procedure. Tier 2's `skycat_tvbs` is the real tailsitter, and it does not currently reach a hover to land from
* **`plane_takeoff_auto`** (UNSUPPORTED) — declares an `upload_mission` step; no tier in this suite flies a mission, so nothing here has ever executed it
* **`vtol_takeoff_mission`** (UNSUPPORTED) — declares an `upload_mission` step; no tier in this suite flies a mission, so nothing here has ever executed it
