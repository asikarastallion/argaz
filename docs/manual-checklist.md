# Manual check-list

What a person still has to try by hand, and what the machine already covers.

This list exists because three times in this project's history the tests were
green while the application was unusable — the Plane TAKEOFF button, the
front-end startup chain, and the recovery instructions the interface printed.
Each gap was closed afterwards, and the ✔ marks below say exactly which. The
✗ marks are the honest remainder: **nothing verifies these but you.**

| mark | meaning |
|---|---|
| ✔ | an automated test asserts this; if it broke, CI would go red |
| ◐ | partly covered — read the note, the uncovered part is named |
| ✗ | **not covered by any test.** Only this list stands between it and a user |

Run it against a real installation, in this order, after any change that
touches launching, the terminals, or the page. About ten minutes.

---

## 1. Start-up

| | step | expected |
|---|---|---|
| ✔ | `argazui/start.sh` on a machine with no venv active | prints `ArgazUI: using interpreter …` and does not choose `/usr/bin/python3` |
| ✔ | run it again while the first is still up | names the pid, the start time and the command line, and offers two runnable commands |
| ✔ | paste the `--replace` command it printed | the old server stops and a new one answers on the same port |
| ✔ | `argazui doctor` | every line either OK or a FAIL with a fix that runs verbatim |
| ✗ | open the printed URL in **your** browser (Firefox, Safari, a phone) | the page loads and is usable |

*e2e drives headless Chromium only. A layout that breaks in Firefox, or on a
narrow screen, would not be noticed by anything but you.*

## 2. Spawning a model

| | step | expected |
|---|---|---|
| ✔ | pick a model, press START | the status bar fills within ~90 s: link connected, mode, altitude |
| ✔ | watch the SIMULATION tab during start-up | the launch commands appear and scroll |
| ◐ | check the model that appears **in Gazebo's window** | it is the airframe you chose, on the runway, right way up |
| ✗ | look at the model's picture in the panel | it matches the aircraft |

*◐: tier 2 flies eleven models headless and asserts they take off, change mode
and land — but with `gz sim -s`, so **no test has ever looked at a rendered
frame.** A model loaded upside-down, at the wrong scale, or with a missing
mesh would fly its procedure and pass.*

## 3. The quick command buttons

| | step | expected |
|---|---|---|
| ✔ | before START, hover a disabled button | a tooltip says why it is disabled |
| ✔ | after START, click a mode button | the mode chip changes and the terminal shows the ACK |
| ✔ | click TAKEOFF | the aircraft climbs and the run is judged against the procedure's own criteria |
| ✔ | click LAND | the aircraft descends and disarms |
| ✗ | click TAKEOFF twice quickly, or LAND during a takeoff | the interface does something sensible |

*Concurrent and contradictory commands are not tested at all. The procedure
runner takes one at a time, but what the browser does when you insist has
never been checked.*

## 4. The two terminals

| | step | expected |
|---|---|---|
| ✔ | type `echo hello` in COMMAND | it echoes back |
| ✔ | type into SIMULATION while a vehicle runs | MAVProxy responds (on `sim_vehicle.py` models) |
| ✗ | press `Ctrl+C` in SIMULATION | the simulator stops, the page stays alive |
| ✗ | resize the browser window with both terminals open | the terminals reflow and stay readable |
| ✗ | leave the page open for an hour, then use it | the WebSocket has reconnected or says it is disconnected |

*Signals, resizing and long-lived sockets are all real user actions with no
test behind them.*

## 5. A mission script

| | step | expected |
|---|---|---|
| ✗ | run one of `scripts/*.py` from the COMMAND tab while a model flies | it connects on 14551 and drives the vehicle |
| ✗ | run it while ArgazUI's own buttons are also being used | neither loses its link |

*The 14551 fan-out is configured by the launch commands and never exercised by
a test. This is the largest uncovered area in the project.*

## 6. Stopping, and the evidence

| | step | expected |
|---|---|---|
| ✔ | press STOP | the vehicle stops, the status bar returns to "not started" |
| ✔ | look at Flight Runs | the finished run is listed |
| ✔ | open the run's report | it names the firmware, the parameters the run changed, and any advisories |
| ✔ | check the run directory | it holds a complete `.BIN`, `result.json`, `report.md`, parameter dumps |
| ✗ | press STOP while Gazebo is mid-crash, or kill the terminal instead | no orphaned `gz sim` or SITL process is left behind |

*Process cleanup is by session and process group and has never been tested
against a hostile shutdown. Check with `ps -eo pid,pgid,cmd | grep -E "gz sim|arduplane|arducopter"`.*

## 7. Version drift

| | step | expected |
|---|---|---|
| ✔ | edit a `.py` file while the server runs, reload the page | a banner says the server is running superseded code, and names "server code" |
| ✔ | edit a file under `static/`, reload | the banner names "interface files" instead |
| ✔ | edit a procedure YAML | **no** banner — procedures are re-read on change |
| ✔ | paste the command the banner prints | it runs and restarts the server |

---

## What the marks are worth

Everything ✔ is asserted by `pytest -m tier1`, which runs on every push, or by
`pytest -m tier2`, which runs nightly against the real model set. See
[status.md](status.md) for what tier 2 currently verifies, per model.

Everything ✗ is a gap. It is written down rather than fixed because writing it
down is honest and quietly leaving it out is not. If one of them bites you,
that is the entry to turn into a test next.
