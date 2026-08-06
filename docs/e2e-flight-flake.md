# `test_flying_from_the_browser` — diagnosis, not a fix

**Status: diagnosed, deliberately not fixed.** Written during v1.3 phase 3
because a test failing half the time makes every later gate ambiguous. No code
was changed to produce this.

## It is not a regression

It failed in the **phase 0 baseline run**, before a single line of fleet code
existed — the first command run in the v1.3 work. Same test, same 30 s
`Page.wait_for_function` timeout. Everything added since is additive (a new
`argazui/fleet/` package, new test files, an additive config key, an additive
CLI verb), and `tests/test_characterisation.py` pins the single-vehicle launch
path byte for byte and passes.

Observed rate: **3 failures in 7 full-suite runs** (phases 0–6). It has also
passed when run alone. Failures were runs 1, 3 and 7; runs 2, 4, 5 and 6
passed, so there is no ordering or warm-cache pattern — it is a race, and
which side wins is decided by tens of milliseconds (see the timing table
below).

Every failure has carried the identical signature. The most recent, from
phase 6, is the tightest yet — the commanded mode did not even survive the
vehicle's arrival in MANUAL:

```
t=5.77  -            -> INITIALISING
t=6.42  INITIALISING -> FBWA      the click was accepted
t=6.50  FBWA         -> MANUAL    80 ms later it was not
        (no further mode events for the remaining 30 s)
```

## Where it fails

[`tests/e2e/test_flight.py:109`](../tests/e2e/test_flight.py#L109) — the last
and tightest wait in the test:

```python
page.click("#buttons button:has-text('FBWA')")
page.wait_for_function(
    "() => document.getElementById('pill-mode').textContent.includes('FBWA')",
    timeout=30000)
```

## What the page state is when it times out

The mode pill reads **`MANUAL`**, and it is correct — the vehicle really is in
MANUAL. This is not a UI update problem. From the failing run's own
`mavlink_events.jsonl`:

```
t=6.73  mode  INITIALISING -> MANUAL
t=6.85  mode  MANUAL       -> FBWA      <- the click was accepted
t=6.99  mode  FBWA         -> MANUAL    <- reverted 140 ms later
        (no further mode events for the remaining 30 s; last state t=43.54 MANUAL)
```

The command worked. Something put the vehicle back.

## Why

The event *ordering* is identical in passing and failing runs. Only the timing
differs:

| | "Throttle failsafe off" | FBWA commanded | gap | outcome |
|---|---|---|---|---|
| failing (pytest-30) | t=6.75 | t=6.85 | **100 ms** | reverted at 6.99 |
| passing (pytest-31) | t=6.63 | t=7.23 | **600 ms** | sticks |

`Throttle failsafe off` is emitted when ArduPlane first sees valid RC input.
Shortly after that it reads the flight-mode switch (`FLTMODE_CH`) and applies
the RC-selected position — MANUAL, which is where SITL's simulated transmitter
sits. **Any mode commanded between "RC became valid" and "the mode switch was
read" is overwritten**, silently, with no NAK and no STATUSTEXT.

The interface enables its command buttons as soon as the link reports
connected, and that happens before this window closes. So the race is real for
a person too, not only for the test: click a mode button in the first fraction
of a second after a vehicle appears and the mode reverts with no explanation.
The test simply clicks faster and more reliably than a human, so it lands
inside the window about half the time.

## Why the obvious fix is the wrong one

Raising the 30 s timeout would not help. The mode is not late — it is *gone*,
and no amount of waiting brings it back; the failing run sat in MANUAL for
another 30 s and would have sat there all day. The timeout is a bystander.

## The candidate fixes, for whoever takes this

Ranked by how much each one actually addresses:

1. **Gate the buttons on a settled mode, not merely on a connected link.**
   The concrete condition: *no mode change observed for N seconds*. The
   vehicle is not ready for a mode command until the flight-mode switch has
   been read and the mode has stopped moving on its own; "the link is up" does
   not imply either. Two seconds of quiescence would close the ~100 ms window
   with a wide margin, and it closes it for **both** consumers — the e2e
   gate and the UI button a person presses.

   This has NOT been done, deliberately. It is a change to the single-vehicle
   path, and folding it into the fleet work would mix a v1.2-path change into
   v1.3 with no separable red-then-green. It belongs in its own change, whose
   red is this test failing on demand once the window can be forced.

   Note that v1.3's fleet router already reports this class of failure rather
   than hiding it: a command that is acked and then abandoned is `REVERTED`,
   a distinct outcome from both ACCEPTED and DENIED. That does not fix the
   race — it makes it visible. See docs/fleet-group-commands.md.
2. **Have `_do_mode` verify and retry once.** `mavlink_link._do_mode` already
   waits up to 5 s for a HEARTBEAT carrying the requested `custom_mode`, and
   in the failing run it *saw* one — the revert came afterwards. Re-checking
   after a short settle, and reporting "the vehicle reverted to MANUAL" rather
   than success, would at least make the failure visible instead of silent.
3. **Do not** paper over it in the test with a sleep before the click. It
   would make the suite green while leaving the application defect in place,
   which is the failure mode this project exists to remove.

Option 1 is the real fix; option 2 is worth having regardless, because a mode
change that is accepted and then undone currently reports as success.

## How this was diagnosed without changing code

pytest retains the last three `tmp_path` trees, and the e2e harness points a
real `RunRecorder` at one. So a failing run leaves a complete
`mavlink_events.jsonl` behind:

    /tmp/pytest-of-<user>/pytest-30/e2e-flight0/runs/<stamp>_e2e_plane/

The suite record also keeps each failure's traceback tail
(`tests/conftest.py`, `pytest_runtest_logreport`), so the timing-out wait can
be identified after the fact even when the console output was not kept.
