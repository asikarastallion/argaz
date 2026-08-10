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

## 5b. The live plot

| | step | expected |
|---|---|---|
| ✔ | press START, then check the LIVE PLOT line under Quick Commands | Address and Port are shown as two separate values and the message count climbs |
| ✔ | press STOP | the mirror port closes and stops sending |
| ✗ | connect PlotJuggler (**Streaming → UDP Server**; Address `127.0.0.1`, Port `14552`, protocol **JSON**) during a flight | series appear under `ATTITUDE/`, `VFR_HUD/`, `SYS_STATUS/` … and update live |
| ✗ | drag `ATTITUDE/roll` onto a plot and fly a manoeuvre | the trace moves with the aircraft, in step with the terminal |
| ✗ | leave PlotJuggler connected across a STOP → START | it resumes on the new session without being restarted |

*The ✔ rows are covered from both ends: a tier-1 test binds the mirror port
against a real SITL and asserts that a `HEARTBEAT` arrives as valid JSON and
that the port goes quiet on STOP, and an e2e test reads the address off the
page in a real browser while a vehicle flies. But **no test has ever seen a
rendered plot.** PlotJuggler stops its stream on the first message it cannot
parse, so a datagram this project never produced in testing would look, to a
user, like the feature silently not working.*

*Put only `127.0.0.1` in PlotJuggler's **Address** box. A `host:port` string
there — or an empty box — parses as no address, and PlotJuggler then shows
"Couldn't bind to IPv4 UDP server" for a socket that is receiving fine;
pressing OK on that dialog is what kills the stream. See USAGE.md 5d for why.*

## 5c. The Flight Runs panel with real history

| | step | expected |
|---|---|---|
| ✔ | open the panel with more than five runs recorded | five rows, and a control saying how many more there are |
| ✔ | click it, then click it again | the rest appear, then collapse back to five |
| ✔ | open `#run=<id>` for a run below the fold | the report opens and the list expands to show it |
| ✗ | scroll the panel on a laptop screen with ~50 runs recorded | the page stays usable and the panel does not dominate it |

*The row cap is asserted in `tests/e2e/test_runs_panel.py` against seeded run
directories. What no test judges is whether five is the right number on your
screen.*

## 5d. The documentation portal

| | step | expected |
|---|---|---|
| ✔ | press **DOCS** | a tree of twenty-two pages, grouped, with the landing index open |
| ✔ | open a page with tables and code in it | both render, and the footer names the repository file it came from |
| ✔ | type in the search box | pages *and* headings inside them match; a heading opens its page |
| ✔ | paste `#docs=regression/exit-codes` into the address bar | that page opens, scrolled to that heading |
| ✔ | switch to TR, then open a page with no Turkish source | the English text, under a Turkish notice saying why |
| ✗ | read three pages end to end, in each language | the text is right, current, and reads as engineering rather than as translation |
| ✗ | open the portal on a narrow screen | the tree stacks above the page and both stay usable |

*The ✔ rows are asserted in `tests/e2e/test_docs_portal.py` against real
Chromium, including that every page in the tree resolves to a file. **No test
can read prose.** A page that is well-formed, renders perfectly and says
something untrue would pass every check in this project — the only thing
standing between that and a reader is somebody reading it. The narrow-screen
row is the usual gap: e2e runs at one viewport size.*

## 5e. Comparing runs

| | step | expected |
|---|---|---|
| ✔ | open a run with an earlier run behind it, press **⇄ compare with the previous run** | a table of metrics, a verdict per row, and an overall result naming the baseline |
| ✔ | press it on the *first* run of a model | it says there is nothing to compare against — no error, no empty table |
| ◐ | compare two runs of *different* models | it refuses and names the model mismatch |
| ✗ | edit a procedure between two real flights, then compare | it declines as `incomparable` and names the procedure hash |
| ✗ | rebuild ArduPilot between two real flights, then compare | it declines and names the firmware; `--ignore-config-drift` compares anyway |
| ✗ | read the numbers against what you saw the aircraft do | the deltas match your judgement of which flight was better |

*The ✔ rows are driven in a real browser by `tests/e2e/test_compare_panel.py`.
◐: the refusal itself is asserted exhaustively in `tests/test_regression.py`
and the whole chain on real evidence in `tests/test_tier1_evidence_chain.py`,
but **no test drives the different-model refusal through the panel**. What no
test does at all is change the environment between two real flights — the drift
cases above are produced by editing a fingerprint, not by rebuilding a
firmware. And no test can say whether a metric that moved 12% describes
something you would call a regression; that judgement is why the thresholds are
configurable.*

## 5f. Scenarios (fault injection)

| | step | expected |
|---|---|---|
| ✔ | open the page with nothing running | the SCENARIOS panel says a vehicle has to be started, and states that a scenario degrades the **simulated** vehicle only |
| ✔ | start a Copter, run `copter_gps_loss` | the terminal announces the injection with its mechanism, the fault is held, the parameter is restored, and the verdict comes from the criteria |
| ✔ | run `copter_link_loss` | the status bar goes quiet for the window and recovers; the criteria are judged afterwards |
| ✗ | watch the **Gazebo window** during a GPS loss | the aircraft does what the report says it did |
| ✗ | run a scenario on an ArduPilot without `SIM_GPS1_*` | the procedure aborts before arming and the run is recorded `environment` / `fault-not-applied` |
| ✗ | kill ArgazUI *while* a fault is injected | the next session finds a vehicle in its normal configuration |

*The ✔ rows are flown against real SITL by `tests/test_tier1_faults.py` and one
is flown in Gazebo by `tests/test_tier2_models.py`. **No test has looked at a
rendered frame of an aircraft losing its GPS** — the models are flown headless,
so what the report says and what the aircraft looked like have never been
compared by anyone but a person. And nothing tests the fail-closed path on a
firmware that genuinely lacks the parameter: the unit test simulates that
firmware, it does not run on one.*

*The last row matters more than it looks. The injector restores from a
`finally`, the runner clears the link fault from a second one and
`MavlinkLink.stop()` from a third — but a `SIGKILL` bypasses all three, and the
simulated vehicle's parameters live in `argazui/run/<model_id>/eeprom.bin`. A
scenario killed at exactly the wrong moment is the one case where a `SIM_*`
value could outlive its run.*

## 5g. Repeatability campaigns

| | step | expected |
|---|---|---|
| ✔ | open the page with nothing running | the campaign panel lists nothing, says so, and its start button is disabled |
| ✔ | run a 2-run campaign from the shell suite | two independent run directories, both stamped with the campaign, one aggregate document |
| ◐ | run a 5-run campaign from the browser on a real model | five START…STOP cycles, progress in the terminal, a summary at the end |
| ✗ | cancel a campaign half way | the runs already flown keep their evidence and the document covers them |
| ✗ | edit the procedure between two iterations of a running campaign | the document reports the iterations as not identical |
| ✗ | read a spread of five real flights | the numbers match what you saw the aircraft do |

*◐: `tests/test_tier1_campaign.py` flies two iterations through the same
executor, and `tests/e2e/test_scenarios_and_campaigns.py` drives the panel — but
**no test runs a campaign through the browser against a real model**, which is
the path a user actually takes. Cancellation is unit-tested against a fake
launcher and has never been exercised against a live Gazebo session.*

## 6. Stopping, and the evidence

| | step | expected |
|---|---|---|
| ✔ | press STOP | the vehicle stops, the status bar returns to "not started" |
| ✔ | look at Flight Runs | the finished run is listed |
| ✔ | open the run's report | it names the firmware, the parameters the run changed, any advisories, the metrics and the environment it ran in |
| ✔ | check the run directory | it holds a complete `.BIN`, `result.json`, `report.md`, `fingerprint.json`, parameter dumps |
| ✗ | read `fingerprint.json` on **your** machine | every field is either right or `null` with a reason you agree with — nothing is a plausible-looking guess |
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
