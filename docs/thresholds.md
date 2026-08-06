# No threshold is a constant

**The rule:** in this system no threshold may be a fixed number of wall-clock
seconds or a fixed number of absolute metres. Every one is either

1. **measured from a floor** taken under the same conditions,
2. **expressed in vehicle time** and converted using a measured rate, or
3. **replaced by waiting on a condition**.

This is not a style preference. It was learned three separate times in a
single phase, each time by a fixed constant producing a confident, wrong
answer — and in two of the three cases the wrong answer was an accusation
against a working system.

---

## The three

### A fixed 0.30 m band accused a healthy fleet of being mis-wired

The cross-wiring check asserts that when one vehicle is commanded, no other
model moves "beyond noise". Noise was 0.30 m.

A vehicle still hovering from its own earlier check drifted **0.47 m** in
eight seconds while station-keeping. That is real movement, caused by the
aircraft holding position — and the check reported a mis-wire.

"Stationary" is not a constant. It depends on whether the vehicle is on the
ground, hovering, or descending. **Fix:** measure each model's movement over
the same window with no command given; that is the floor for those
conditions, and a stray is judged against it.

### A fixed 8 s settle accused another one

The same check waited 8 s after commanding a climb, then compared poses. A
vehicle moved only 0.84 m against a 1.0 m requirement and was read as
possibly mis-wired.

At three vehicles the world runs at ~0.6x, so 8 wall seconds is under 5
seconds of vehicle time. The vehicle was fine; the look was short.

**Fix:** wait on the vehicle's own altitude instead of on a clock. A
condition is independent of simulation rate; a wall-clock wait is not.

### A fixed 1.5 s hold was wrong in *both* directions

The router confirms a command by watching the state hold for 1.5 s after the
ACK. That constant was simultaneously too long and too short:

| context | 1.5 s wall is… | consequence |
|---|---|---|
| SITL-only at speedup 5 | **7.5** vehicle seconds | 75% of ArduCopter's 10 s `DISARM_DELAY`; a vehicle armed, held, and had auto-disarmed by the next statement |
| Gazebo lockstep at RTF 0.6 | **0.9** vehicle seconds | a *shorter* look at the aircraft than intended, in the tier that matters most |

Every timer the question is actually about — `DISARM_DELAY`, mode-switch
re-reads, failsafes — runs on the vehicle's clock.

**Fix:** the window is 1.5 seconds of *vehicle* time, converted with
`MavlinkLink.speedup`, which is measured from the vehicle's own timestamps
rather than assumed. Capped in wall time so a slow world cannot hang a
command.

---

## Why the same mistake three times

Each constant was chosen by imagining the situation rather than measuring it,
and each was *reasonable* for the situation imagined. 0.30 m is generous for a
model sitting on a runway. 8 seconds is ample for a 6 m climb at real time.
1.5 seconds comfortably brackets a 140 ms revert.

They failed because the situation was not the one imagined — the vehicle was
hovering, the world was running at 0.6x, the simulator was at speedup 5. **A
constant encodes an assumption about conditions, and a simulator is a machine
for changing conditions.**

## Where this already applied before v1.3

The pattern is not new; v1.1 reached it from the other direction. `StabilityWatch`
counts time outside an attitude band **on the vehicle's clock**, weighted by
each sample's own interval, precisely because "wall-clock timing was tried
first and is wrong twice over" — telemetry arrives in bursts, and under
speedup a wall second is not a second of flight.

v1.3 fleet acceptance follows the same discipline: criteria are judged on
*seconds spent outside* a band against a declared tolerance, never on a peak
or a minimum sample. A single bad sample is noise; duration is the signal.

## What to do when you need a number anyway

Some quantity has to be concrete somewhere. When it does:

* put it in the **spec**, where it is declared and visible
  (`min_separation_m`, `max_rtf_drop`, `start_delay_s`) rather than in code;
* if it must live in code, make it a **named constant with the measurement
  that produced it in the comment** — `DEFAULT_MAX_VEHICLES = 4` carries the
  RTF curve that refuted the previous formula;
* and prefer a **cap** over a target: `MAX_HOLD_WALL_S` exists so a pathological
  rate cannot hang a command, not to define correct behaviour.

## The test that keeps this honest

A threshold that has never been observed to fire is a threshold nobody has
checked. Where practical, the failure it guards against is induced on purpose:
the lockstep stall by `SIGSTOP`, the partial-ACK matrix by removing one
vehicle's arming voltage, the separation violation by demanding more clearance
than a recorded run achieved. See `docs/fleet-lockstep-stall.md` and
`docs/fleet-group-commands.md`.
