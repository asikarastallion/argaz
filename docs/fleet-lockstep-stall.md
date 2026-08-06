# The lockstep stall, induced on purpose

**The headline diagnostic of v1.3, and the only honest way to build it was to
make the failure happen deliberately.** Every number here comes from holding a
real SITL under `SIGSTOP` in a real three-vehicle Gazebo world.

    measured   2026-08-05
    fleet      3x hexapod_copter, one gz sim, lock_step=1
    method     SIGSTOP one vehicle's SITL, observe, SIGCONT

---

## Why it needs a diagnosis and not just a detector

`<lock_step>1</lock_step>` is set in every `ardupilot_gazebo` model. The server
steps physics, sends state to every FDM, and **blocks** until each one
answers:

```cpp
while (!this->ReceiveServoPacket() && this->dataPtr->arduPilotOnline)
{
    if (this->dataPtr->signal != 0) { break; }
}
```
`ArduPilotPlugin.cc:1206`

So one silent vehicle freezes the world. The symptom is "everything stopped",
which points at nobody: every vehicle is motionless and every link is equally
quiet, because none of them is being stepped. Naming the one that stopped is
the whole value.

---

## Two assumptions, both wrong, both corrected by measurement

### 1. It does not stop cleanly — it crawls, then it goes silent

The first detector tested whether simulated time was **exactly flat**. That
detected nothing at all:

```
"during": null            <- 25 s of SIGSTOP, no stall reported
sim_time 111.053 -> 113.213 over ~50 s wall   (effective RTF ~0.04)
```

Sim time kept creeping, because the plugin drains FDM packets that were
already in the socket buffer when the process froze — one per physics step.
An exact-flatness test never fires.

Replaced with a **rate** test: below 0.1x for longer than 3 s is a stall.
Healthy runs measured 0.45–1.12x with three vehicles, so the threshold has an
order of magnitude of clearance on both sides.

### 2. When it really stalls, `/stats` stops answering — and that IS the signal

The rate test still missed it, for a reason that inverts the obvious reading:

```
t+ 4.0s  no reply on /stats; the physics server is not publishing statistics
t+ 9.5s  no reply on /stats; the physics server is not publishing statistics
...      (for the whole 60 s of SIGSTOP)
```

The `gz` process is blocked *inside the plugin's wait loop*, so it stops
servicing gz-transport too. `gz topic -e -t /stats` times out.

The first version treated that as "no measurement available" and reported
`stalled=False`. **A physics server that is running but has stopped answering
is the strongest stall signal there is, not the absence of one.** The detector
now distinguishes:

| `/stats` | server process | verdict |
|---|---|---|
| answering, rate ≥ 0.1x | alive | healthy |
| answering, rate < 0.1x for ≥3 s | alive | **stalled** (crawl) |
| silent for ≥3 s | alive | **stalled** (blocked) |
| silent | gone | crash, not a stall |

---

## What it produces now

```json
{
  "stalled": true,
  "stalled_for_s": 5.51,
  "suspect_vehicles": ["v2"],
  "reason": "the physics server has not answered /stats for 5.5s while still
             running — it is blocked waiting for an FDM. v2 is frozen (process
             state T), so its FDM cannot answer and lockstep is waiting for it.
             v1, v3 are silent as a consequence, not as a cause."
}
```

`SIGCONT` recovers within ~2 s and the detector reports the world advancing
again.

### Attribution: process state outranks heartbeat silence

An intermediate version listed **all three** vehicles as suspects. That is the
useless "everything stopped" answer wearing a detector's clothes, and it comes
from treating heartbeat silence as evidence. During a frozen world *no*
vehicle sends heartbeats, because none of them is being stepped — silence is
universal and therefore says nothing.

So the ranking is:

1. **process state `T`** (`/proc/<pid>/stat`) — definitive, and the only
   usable evidence during a full freeze;
2. **process gone** — nothing will ever answer for it;
3. **heartbeat silence** — used only when the server is still answering, i.e.
   when one vehicle went quiet while the others kept talking;
4. **nothing** — reported as "no vehicle could be singled out", with the
   reason, rather than blaming whichever was checked first.

When a frozen vehicle is identified, the others are named explicitly as
consequences so nobody chases them.

---

## What this does not cover

* A vehicle that is running and scheduled but wedged inside its own loop. Its
  process state is `S`/`R` and the world is frozen, so heartbeat age cannot
  separate it from its victims. The detector says so rather than guessing.
* Multiple simultaneous freezes — one is reported per process in state `T`,
  which is correct, but has not been exercised.
* Whether the crawl-then-silence sequence looks the same at higher vehicle
  counts or under `--speedup`. Measured at three vehicles, speedup 1.
