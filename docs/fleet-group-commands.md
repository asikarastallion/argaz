# Group commands: five outcomes, and how each was induced for real

A group command returns one row per vehicle, and each row carries **two
separate findings** — the acknowledgement, and a confirmation taken from
heartbeats *after* the ack and held for a stated interval. Both are needed
because a real autopilot really does accept a command and then abandon it.

    ACCEPTED   acked, and the state still held after the hold window
    REVERTED   acked, and the state did NOT hold
    DENIED     rejected, carrying the autopilot's own reason text
    TIMEOUT    no acknowledgement inside the window
    NO_LINK    there was nothing to acknowledge it

Group verdict: `PASSED` / `PARTIAL` / `FAILED` / `EMPTY`. `EMPTY` is separate
because "I commanded four vehicles and none obeyed" and "I commanded nothing"
are different events, and a target selector that quietly resolves to nobody
would otherwise report success.

---

## Why REVERTED exists

Phase 3 caught ArduPlane doing exactly this, in a run nobody set up to catch
it (docs/e2e-flight-flake.md):

```
t=6.85  mode  MANUAL -> FBWA     the command was accepted
t=6.99  mode  FBWA   -> MANUAL   and 140 ms later it was not
```

No NAK. No STATUSTEXT. A router that reported only the ACK would have called
that a success. Reported as DENIED it would be a different untruth — an
operator hunting for a rejection reason would find none, because the autopilot
did accept it.

Collapsing REVERTED into either neighbour reintroduces the exact failure v1.1
removed, one level up. So it is its own outcome, and the row records both
halves: `ack: "ACCEPTED"` *and* `confirmed: false`.

---

## Induced for real, not simulated

`tests/test_fleet_router.py` drives all five outcomes through a fake link,
which proves the classifier. That is not evidence that a real autopilot
produces them. `tests/test_fleet_sitl_router.py` induces two against real
SITL.

### DENIED — a genuine pre-arm refusal

Three levers were tried before one worked. The failures are worth recording
because each looked like it should have worked:

| lever | what actually happened |
|---|---|
| `SIM_GPS1_ENABLE=0` then ARM | **v2 armed anyway.** ArduCopter arms in STABILIZE without a position estimate; removing GPS does not stop it. |
| `SIM_GPS1_ENABLE=0` then MODE GUIDED | **both vehicles accepted GUIDED** and held it. Mode entry is lenient while disarmed. |
| any GPS/EKF-flavoured refusal | absorbed by `MavlinkLink._do_arm`'s retry. `TRANSIENT_ARM_HINTS` contains `gps`, `3d fix`, `position`, `ekf`, and it retries for `ARM_RETRY_WINDOW` = 35 s. Measured: `ARM: accepted (on attempt 2, after waiting for the vehicle to become ready)`. |

That retry is **correct v1.2 behaviour** — a user should not have to click ARM
five times while the EKF settles — and v1.3 does not change it. But it means a
transient-looking refusal is not a deterministic probe. The refusal has to be
one the retry logic will not absorb: a battery below the arming voltage is
permanent and its wording matches no transient hint.

Real matrix, `BATT_ARM_VOLT=25.0` on v2 only:

```json
{
  "command": "ARM", "policy": "parallel_ack", "verdict": "PARTIAL",
  "results": [
    {"vehicle": "v1", "outcome": "ACCEPTED", "ack": "ACCEPTED",
     "reason": "ARM: accepted", "t_ms": 172,
     "confirmed": true, "observed": "armed == True held for 1.5s"},
    {"vehicle": "v2", "outcome": "DENIED", "ack": "NAK",
     "reason": "ARM: REJECTED (MAV_RESULT_FAILED) — otopilot: Arm: Battery 1 below minimum arming voltage",
     "t_ms": 5622, "confirmed": null, "observed": ""},
    {"vehicle": "v3", "outcome": "ACCEPTED", "ack": "ACCEPTED",
     "reason": "ARM: accepted", "t_ms": 178,
     "confirmed": true, "observed": "armed == True held for 1.5s"}
  ]
}
```

The refusal text is the autopilot's own. `confirmed` is `null` for the denied
vehicle, not `false` — nothing was confirmed because nothing was attempted.

### REVERTED — acked, then undone

Induced by moving the simulated flight-mode switch during the hold window.

```json
{
  "command": "MODE LOITER", "verdict": "FAILED",
  "results": [
    {"vehicle": "v1", "outcome": "REVERTED", "ack": "ACCEPTED",
     "reason": "acknowledged, then mode == LOITER did not hold — vehicle is in 'STABILIZE' after 1.5s. The autopilot accepted the command and did not stay in the state it produces.",
     "t_ms": 37, "confirmed": false,
     "observed": "mode == LOITER did not hold — vehicle is in 'STABILIZE' after 1.5s"}
  ]
}
```

**This is not the phase-3 startup race, and the claim is narrower than it may
look.** That race lives in a ~100 ms window right after RC input becomes valid
and cannot be hit on demand. What is induced here is a *different real cause*
of the same observable: a pilot's mode switch overriding a commanded mode. The
router cannot tell the two apart and should not — its job is to notice that
the state did not hold, whatever moved it.

So what this establishes is: **REVERTED is a real outcome that a real
autopilot really produces, and the router really classifies it.** It is not a
claim that the phase-3 race was reproduced on demand.

---

## The hold window interacts with speedup, and that bit once

The confirmation window is 1.5 s of **wall clock**. The suite runs at speedup
5, so from the aircraft's point of view it is **7.5 seconds** — three quarters
of ArduCopter's 10 s `DISARM_DELAY`.

Measured consequence: a vehicle armed, stayed armed for the whole window
(`confirmed: true`), and had auto-disarmed by the time the next line of the
test looked at live state. The matrix row was correct; the second look was a
race against the aircraft's own timer.

The rule that follows: **the matrix entry is the durable evidence.** Re-reading
live state after a command to "double-check" is racing whatever timers the
autopilot runs, and at speedup those timers arrive N times sooner in wall
clock.

---

## Ordering: the router's clock, never the vehicle's

`timeline.jsonl` is sorted on `time.monotonic()` in the router process. Vehicle
time is kept as a field on every event and is never the sort key.

This is not fastidiousness. Two free-running SITLs carry a constant clock
offset of boot-stagger × speedup — 0.9 s at speedup 1, 4.5 s at speedup 5
(docs/fleet-clock-drift.md). Keyed on vehicle time, an event on v2 that
happened *after* an event on v1 sorts *before* it, and a timeline that
reorders cause and effect does not lose precision — it asserts something false
about what led to what. A takeoff would appear to precede the arm that caused
it.

`monotonic()` rather than `time()` because a wall clock can step backwards
(NTP, suspend/resume), and a timeline that goes backwards is worse than one
that is merely offset. The absolute UTC start is recorded once so a monotonic
offset can still be resolved to a real timestamp.

---

## No sysid=0, by construction

Every command goes to one vehicle over that vehicle's own link, and
`MavlinkLink` targets `self._conn.target_system` — learned from the heartbeat
on that connection. A fleet of N links is N distinct addresses with no
broadcast available anywhere in the path. A broadcast cannot be ACKed and
therefore cannot be confirmed, which makes it unusable here by construction
rather than by policy.

Verified against real vehicles: `test_every_command_is_addressed_and_never_broadcast`.

---

## Policies

| policy | behaviour | why |
|---|---|---|
| `parallel_ack` | all at once, one thread per vehicle, ACKs collected together | mode changes, where simultaneity is the point |
| `staggered` | one at a time with `start_delay_s` between | prevents the RTF spike of N simultaneous takeoffs and prop-wash interaction |
| `gated` | vehicle *i+1* only starts once *i* meets a gate (e.g. `alt > 3 m`) | safest, slowest; a vehicle that misses its gate stops the sequence rather than committing the rest |

Matrix rows always follow the **target order**, never the finish order — a
matrix whose rows moved between runs would be unreadable.

## Targets

`all` | `selected` | `["v1","v3"]` | `role:leader`. An unknown id **raises**
rather than being dropped: a group command that silently commands three of the
four vehicles it was given is precisely the ambiguity explicit targeting
exists to remove.

## The abort is fallible, and says so

`abort_fleet` returns the same five-outcome matrix as any other command,
because an abort that reaches nobody has aborted nothing. **"Commanded down"
and "confirmed down" are different claims**, and the run status is derived
from the verdict rather than from having sent the command.
