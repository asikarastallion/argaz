# `test_flying_from_the_browser` — the mode race, and how it was traced

**Status: diagnosed and fixed.** The fix is the mode-settle gate in
`mavlink_link.MODE_SETTLE_S` and the button gating in `static/app.js`. This
document is kept because the *diagnosis* is the reusable part: how the failure
was traced without changing any code, what the page state actually was at the
timeout, and why raising the timeout would not have helped.

## The symptom

`tests/e2e/test_flight.py::test_flying_from_the_browser` failed **3 times in 7
full-suite runs**, and passed when run alone. Failures were runs 1, 3 and 7;
runs 2, 4, 5 and 6 passed, so there was no ordering or warm-cache pattern — it
is a race, and which side wins is decided by tens of milliseconds.

It was not a regression from anything: it failed in a baseline run taken before
the change that was under suspicion existed.

Every failure carried the identical signature. The tightest recorded one — the
commanded mode did not even survive the vehicle's arrival in MANUAL:

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

The interface enabled its command buttons as soon as the link reported
connected, and that happens before this window closes. So the race was real for
a person too, not only for the test: click a mode button in the first fraction
of a second after a vehicle appears and the mode reverts with no explanation.
The test simply clicks faster and more reliably than a human, so it landed
inside the window about half the time.

## Why the obvious fix is the wrong one

Raising the 30 s timeout would not help. The mode is not late — it is *gone*,
and no amount of waiting brings it back; the failing run sat in MANUAL for
another 30 s and would have sat there all day. The timeout is a bystander.

Adding a sleep before the click in the test would be worse still: it would make
the suite green while leaving the application defect in place, which is the
failure mode this project exists to remove.

## The fix

**Gate the buttons on a settled mode, not merely on a connected link.** The
concrete condition: no mode change observed for `MODE_SETTLE_S`. A vehicle is
not ready for a mode command until the flight-mode switch has been read and the
mode has stopped moving on its own; "the link is up" does not imply either.

Two seconds of quiescence closes the ~100 ms window with more than an order of
magnitude of margin, and it closes it for **both** consumers — the e2e gate and
the button a person presses. It is counted on the **vehicle's** clock, because
every timer this is really about (the switch re-read, `DISARM_DELAY`, the
failsafes) runs on the aircraft's clock, and under SITL speedup a wall-clock
second is not a second of flight.

While the gate is closed the interface says why, rather than showing dimmed
buttons with no explanation.

### Still worth doing, and not done

`mavlink_link._do_mode` waits up to 5 s for a HEARTBEAT carrying the requested
`custom_mode`, and in the failing run it *saw* one — the revert came afterwards.
Re-checking after a short settle, and reporting "the vehicle reverted to
MANUAL" rather than success, would make this class of failure visible wherever
it happens instead of only preventing it here. A mode change that is accepted
and then undone still reports as success.

## How this was diagnosed without changing code

pytest retains the last three `tmp_path` trees, and the e2e harness points a
real `RunRecorder` at one. So a failing run leaves a complete
`mavlink_events.jsonl` behind:

    /tmp/pytest-of-<user>/pytest-30/e2e-flight0/runs/<stamp>_e2e_plane/

The suite record also keeps each failure's traceback tail
(`tests/conftest.py`, `pytest_runtest_logreport`), so the timing-out wait can
be identified after the fact even when the console output was not kept.

## A note on this document's own history

The fix landed once, was removed along with the multi-vehicle release it had
been developed beside, and the flake came back in the very next full-suite run
— which is how it was noticed a second time. Both the fix and this page were
restored in v1.3. That is the argument for keeping a diagnosis in the
repository rather than in a commit message: the second time cost minutes
instead of an afternoon.
