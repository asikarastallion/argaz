# Fleet run — report_fleet

**FAILED**

> 1 criterion/criteria did not hold. The detail column says what was measured, not merely that a limit was crossed.

## The fleet

| vehicle | sysid | model/frame | role | spawn |
|---|---|---|---|---|
| v1 | 1 | quad | — | -6 E, 6 N |
| v2 | 2 | quad | — | 6 E, 6 N |
| v3 | 3 | quad | — | -6 E, -6 N |

- world: `none (SITL-only)`
- formation: `grid`
- run id: `20260806T000000Z_fleet_report_fleet`

## Acceptance criteria

Threshold criteria are judged on **seconds spent outside** the band against a declared tolerance, never on the worst single sample. A peak is one sample; duration is the signal.

|  | criterion | what was measured |
|---|---|---|
| FAIL | minimum pairwise separation ≥ 5 m | 0.50s below 5 m out of 1.5s observed (simulated time), against a 0.2s tolerance |
| PASS | real-time factor stayed at or above 0.35 | 0.00s below 0.35 out of 2.0s observed (wall-clock time), against a 1s tolerance |
| PASS | every vehicle reached 10 m | v1 12.0 m, v2 11.8 m, v3 12.1 m |
| NOT MEASURED | every vehicle passed its own acceptance criteria | no procedure ran on v3, so the fleet-level claim cannot be made |
| NOT MEASURED | no orphan processes, all port leases released | the fleet was never torn down under supervision, so nothing observed its exit |

### What authorised each claim

- **minimum pairwise separation ≥ 5 m** — /world/runway/pose/info — one world-state message under a single header stamp
- **real-time factor stayed at or above 0.35** — /stats, read from the running physics server
- **every vehicle reached 10 m** — VFR_HUD over each link

## What this run did not claim

The following could not be evaluated. They are **not** passes, and nothing below should be read as evidence about them:

- **every vehicle passed its own acceptance criteria** — no procedure ran on v3, so the fleet-level claim cannot be made
- **no orphan processes, all port leases released** — the fleet was never torn down under supervision, so nothing observed its exit

## Cross-wiring check

Ran before any acceptance criterion. Proves each autopilot drives its own model — without it, every measurement could describe a fleet that does not exist.

**PASS** — 3 vehicles each moved their own model

| commanded | it moved | every other model moved |
|---|---|---|
| v1 | 8.01 m | v2 0.01 m, v3 0.00 m |

## Group commands

An ACK is not a result. Every row carries both the acknowledgement and whether the state it should produce still held afterwards.

### `MODE LOITER` — PARTIAL (policy `parallel_ack`)

| vehicle | outcome | ack | t | detail |
|---|---|---|---|---|
| v1 | ACCEPTED | ACCEPTED | 40 ms | mode -> LOITER |
| v2 | REVERTED | ACCEPTED | 37 ms | acknowledged, then it did not hold |

## Reproducibility

From `versions.environment()`, the one canonical record of which software produced a result.

|  |  |
|---|---|
| ardupilot | ArduPlane V4.8.0-dev @ 0b38722bd5a4 |
| argazui | 1.3.0 |
| gz_sim | Gazebo Sim, version 8.14.0 |
| python | 3.12.3 |

---

Generated 2026-08-06T09:35:48Z from 412 recorded events. A fleet run says nothing about whether any MODEL is supported — `docs/status.md` reads model rows from tier-2 tests alone.
