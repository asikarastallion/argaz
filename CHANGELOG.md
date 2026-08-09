# Changelog

## v1.3.0 — 2026-08-10

### What this release is about

v1.1 made a run produce evidence. v1.2 let you watch one happen. This one is
about the two questions evidence still could not answer:

1. **When, and for how long?** An acceptance criterion could only ask whether
   something was true — now or before a timeout. A takeoff that reaches
   altitude and then sinks back satisfied exactly the same criteria as one that
   held it.
2. **Compared to what?** A run said whether its own criteria held. It could not
   see the failure that actually happens to a simulation project over months:
   every criterion still passes, and the aircraft is quietly getting worse at
   flying.

Nothing in the existing architecture was replaced. `models.json` → launch →
MAVLink → `ProcedureRunner` → `result.json` → run evidence → DataFlash report →
CI/status is the same path it was; each of the pieces below hangs off a point
on it.

### Temporal acceptance criteria — procedure schema 2

```yaml
schema: 2

expect:
  - condition: {alt_above: "{alt*0.9}"}
    within: 20s                    # must BECOME true inside a deadline

  - condition: {alt_above: "{alt*0.9}", armed: true, mode: GUIDED}
    for: 5s                        # then REMAIN true, continuously

  - condition: {angular_rate_above: 180}
    never: 5s                      # and this must not be observed at all
```

Four instantaneous conditions came with them — `roll_within`, `pitch_within`,
`angular_rate_above`, `angular_rate_below` — because `attitude_stable` is
accumulated over the whole procedure and cannot sensibly be asked to hold "for
five seconds". Asking it to is a load-time error that points at the
alternatives.

**They are measured on the vehicle's clock**, not on `time.time()`. Under SITL
speedup a wall-clock second is not a second of flight, so a `for: 5s` judged on
arrival time would demand five times the flight it says it does. Each window
also carries a wall-clock backstop sized from the measured speedup — the
vehicle's clock stops advancing when telemetry stops, and a criterion waiting
on a dead stream is a hang rather than a verdict. When the backstop is what
ended a window, the result says so, because reporting a wall-clock measurement
as vehicle time would make every duration in a run's evidence wrong by the
speedup factor.

**Durations must carry a unit.** `for: 5` is rejected at load time. Every other
number in a procedure is a metre, a degree, a PWM count or a parameter value,
and a duration that looked like one of those would be read wrong exactly once,
silently, in flight, by whoever inherits the file. `m` is deliberately not a
unit — in a flight procedure it reads as metres.

**`for:` does not restart on a lapse**, and a `for`/`never` whose telemetry
never arrived is reported as *not judged* rather than passed. Both are the same
rule this project keeps returning to: nothing measured is not the same as
nothing wrong.

The schema moved from 1 to 2 rather than being extended in place. Schema-1
files load and behave exactly as before; a schema-1 file using a schema-2
feature is refused with a message saying so. Extending in place would have been
quieter and worse — an older ArgazUI would have read a `within:` it does not
implement, out of a document claiming a version it satisfies.

`copter_takeoff.yaml` uses all three shapes. A capability with no procedure
behind it is a claim, and this project's whole subject is the difference
between a claim and evidence.

### Quantitative metrics

Eight derived numbers, computed from evidence a flight already produced: time
to target altitude, peak and RMS roll/pitch tracking error, peak angular rate,
time outside the declared attitude envelope, and the slowest mode transition.
Each carries its unit, the log message or recorded step it came from, and
whether it belongs to the run or to one procedure.

They are a **third kind of output** and cannot fail a run:

| | decided by | can fail a run? | threshold from |
|---|---|---|---|
| acceptance criteria | the procedure's `expect:` | **yes** | the procedure |
| advisories | `flightlog.py` | no | ArduPilot's documentation |
| metrics | `metrics.py` | no | nothing, until compared |

Giving a metric a threshold here would have created a second acceptance system
with limits nobody declared in a procedure. A metric that cannot be derived is
written as `null` with a stated reason — "no procedure in this run declared a
target altitude", "the log carries no IMU records" — rather than omitted: an
absent row and a measurement that could not be made look identical to a reader,
and only one of them is a fact.

The dataflash log knows what the aircraft did and nothing about what it was
told to do, so target altitudes, the declared envelope and the measured
mode-change durations are read out of the run's own `result.json`. That is the
only coupling between `flightlog.py` and the procedure system.

### Environment fingerprint

`versions.txt` answered "which software?" as a flat list for a human to read.
That is enough to look at and not enough to compare, so every run now also
writes `fingerprint.json`: ArgazUI and ArduPilot commits, the firmware identity
and whether it matches the checkout, SITL_Models, Gazebo, ROS, the interpreter,
the resolved configuration — and content hashes of **the procedures that ran**
and **the model's registry entry plus its parameter files**.

Those two hashes exist because they are what changes most often while moving no
version number at all: an edited acceptance criterion, a changed `.param`.

**Unknown is an answer and it comes with a reason.** A component that cannot be
identified is `null`, and the reason is recorded — `"/opt/SITL_Models is not a
git checkout"`, `"unavailable: [Errno 2] ... 'gz'"`. A manifest that quietly
omitted the field would read exactly like one taken on a machine where the
component was fine, and the whole point is that those two must not look alike.

### Run-to-run regression comparison

```bash
python3 -m argazui compare runs/<current> --baseline runs/<baseline>
```

Exit `0` for no regression, `1` for a degradation, `2` for runs that could not
be compared. `2` is separate from `1` on purpose: "these runs do not line up"
is not the same news as "this build got worse", and a pipeline that merged them
would eventually report a mis-specified baseline as a regression. The interface
exposes the same thing on a run's report as **⇄ compare with the previous run**.

The strict part is what it refuses. A different model or a different set of
procedures is refused outright. A changed procedure hash, model configuration,
ArduPilot commit or firmware makes the comparison `incomparable` and names the
field; so does one of those being *unknown* on either side, which is not
evidence that they match. `--ignore-config-drift` compares anyway and still
prints what differed — "I changed the firmware and I want to see what that did
to the numbers" is a real question that has to be asked out loud.

A metric is `unchanged` when it moved by less than its relative tolerance
(10% by default) **or** less than an absolute floor. The floor is not a
convenience: an RMS tracking error of 0.02° that becomes 0.04° is +100% and
means nothing, and judging on the percentage alone would fill CI with red for
quantities that are identical in engineering terms. Both are configurable per
metric under `[regression]` in `argaz.toml`.

No database. A baseline is a run directory; comparisons read `result.json` and
write `regression.json` beside the current run.

### Claim-scoped verification

A `passed` row in `docs/status.md` means "every procedure this model was flown
with met every criterion it declared". That is narrower than it looks, and the
gap is where an unearned claim grows back — so the status generator now also
emits **verification claims**: one row per procedure, per heartbeat-confirmed
mode change and per acceptance criterion, each with its result and the run that
proves it. A criterion that never ran is reported as *not evaluated*, which is
its own word: collapsing it into `failed` would be an invented result pointing
the other way from an invented pass.

The section says plainly that anything not listed was not verified, and names
what no model here has been flown through: a mission, wind, the edges of its
envelope, an injected fault, or enough repetitions to support any statement
about reliability.

### Engineering documentation portal

**DOCS** in the top bar: twenty-two pages in a persistent tree, a search that
matches page titles *and* every heading inside them, and deep links
(`#docs=metrics`, `#docs=regression/exit-codes`).

**It holds no prose.** Every page is a file in this repository or one named
section of one, and each page names its source. Writing the documentation into
the interface produces a second source of truth within a week: the page says
one thing, `README.md` says another, and the one a developer edits is whichever
they happen to open. The only generated page is the landing index, which is a
table of contents and states no technical fact of its own.

Ten new canonical documents were written for the subjects that had no home —
verification model, acceptance criteria, metrics, regression, reproducibility,
runs and evidence, lifecycle, CI/CD, diagnostics, testing — each with a Turkish
twin at `docs/<name>.tr.md`.

The markdown renderer escapes before it transforms, so a document cannot inject
markup into the page. The cost is that a deliberate `<sub>` shows as text, which
is a trade worth making for files anyone with a checkout can edit.

### Restored with the fleet withdrawal: the mode-settle gate

The commit that withdrew the multi-vehicle release took a genuine
single-vehicle fix with it, and its own commit message said so might be worth
re-applying. It turned out to be worth re-applying immediately: the flake it
had fixed reappeared in the very next full-suite run.

ArduPlane reads its flight-mode switch shortly after RC input first becomes
valid, and overwrites any mode commanded in that window — with **no NAK and no
STATUSTEXT**, so the command silently does nothing. Measured:

```
Throttle failsafe off  t=6.75
FBWA commanded         t=6.85   accepted
back to MANUAL         t=6.99   140 ms later, with no explanation
```

The interface enabled its command buttons as soon as the link reported
connected, which is before that window closes, so the race was real for a
person too — click a mode button in the first fraction of a second after a
vehicle appears and the mode reverts silently. The buttons now wait for the
mode to have stopped moving on its own for `MODE_SETTLE_S`, counted on the
vehicle's clock, and say why while they are waiting.

`docs/e2e-flight-flake.md` carries the diagnosis, including how it was traced
without changing any code. It is kept in the repository rather than left in a
commit message precisely because the second occurrence cost minutes instead of
an afternoon.

Still not done, and stated: `_do_mode` reports success for a mode change that
is accepted and then reverted. The gate prevents that here; it does not make it
visible everywhere else.

### Turkish

The portal's chrome, navigation, summaries and notices are translated, and
every document v1.3 added exists in both languages. The pages that are sections
of `README.md` or `USAGE.md` have no Turkish source; in Turkish mode the portal
shows the canonical English text with a notice, in Turkish, explaining exactly
that. Forking every repository document into a second language would recreate
the duplicate-source problem the portal was built to avoid, and a stale
translation of a technical page is worse than an honest English one.

### Verified

- **`tests/test_temporal_criteria.py`** — 31 cases pinning the evaluator down:
  pass, timeout, a lapse mid-hold, a single observed excursion, the boundary at
  the deadline, the vehicle-clock measurement at speedup 10, the wall-clock
  fallback when the clock stalls, and the refusal to judge without telemetry.
- **`tests/test_metrics.py`**, **`tests/test_regression.py`**,
  **`tests/test_fingerprint.py`**, **`tests/test_docs.py`** — the derivations,
  the classifier and its refusals, the manifest and its unknowns, the section
  extractor.
- **`tests/test_run_record.py`** — that a run and a report regenerated from it
  describe themselves identically. See *What this release got wrong first*.
- **`tests/test_tier1_evidence_chain.py`** — a real `arducopter`, the shipped
  `copter_takeoff` procedure, and the evidence followed all the way to a
  comparison verdict, in both directions: identical evidence compares as
  `unchanged` with a `passed` verdict, and perturbed evidence as `degraded`
  with a `regressed` one.
- **`tests/e2e/test_docs_portal.py`** — the portal in headless Chromium: every
  page in the tree resolves, tables and code blocks render, search matches
  headings, a deep link scrolls to its heading, Turkish says when a page has no
  Turkish source, and the console stays clean throughout.
- **`tests/e2e/test_compare_panel.py`** — the compare button in the same
  browser: a verdict and a table come back, the reader is told metrics are not
  criteria, a run with nothing behind it says so instead of showing an empty
  table, and opening another run clears the previous comparison rather than
  leaving one run's numbers under another run's name.
- **Tier 2, on the real model set in Gazebo: 7 passed, 3 failed, 1 skipped** —
  identical to the results recorded before this release. `zephyr`,
  `skycat_tvbs` and `swan_k1_hwing` failed exactly as they did at v1.2, and
  `iris` skipped for the same missing ROS 2 workspace. Nothing here changes
  what tier 2 can claim about any model, and this is the evidence for that
  rather than an assurance.

**Not verified by anything:** that the documentation is *correct*. No test can
read prose. What the tests check is that every page the tree offers resolves to
a file — the failure that would otherwise surface months later as a blank page
after somebody renamed a heading in `README.md`.

`docs/status.md` is unchanged in what it claims about any model. Everything
here is application-level.

### What this release got wrong first

The evidence-chain test caught a defect that had already shipped in this
release's own working tree, and it is the reason that test exists.

`argazui report <run>` re-analyses an archived flight months later. Its output
has to line up with what the flight itself wrote, because the comparison layer
refuses to compare runs whose fingerprints disagree — and it cannot tell
"somebody changed the firmware" from "our own two code paths disagree about how
to hash a file".

They disagreed, twice. The live path hashed the full model dict it held in
memory; the regeneration path could only see the trimmed record in
`result.json`. And the live path hashed the procedure YAML as loaded, while the
regeneration path recovered it from `scenario.yaml` by dropping every `#` line
— which also dropped the comment block every procedure begins with.

Both produced perfectly plausible hashes. A regenerated run silently became
incomparable with the flight it was regenerated from, and the message would
have blamed a configuration change that never happened. The fix is that the
hash covers exactly what the run archives, `scenario.yaml` is parsed by its
fence rather than by stripping comments, and hashed text is normalised.

A second, smaller one: `GET /api/runs/<id>/compare` first answered `404` when a
run had no earlier run to compare against. The endpoint existed and had
answered; the answer was "this is the first run of this model". A 404 made the
browser log an error for an ordinary outcome, on a page whose first promise is
a clean console — which is how the e2e test found it. It returns `200` with
`ok: false` now, and 404 is kept for a run id that does not exist.

### Known limits

- `never:` samples vehicle state every 0.2 wall-clock seconds. An excursion
  shorter than one sampling interval of vehicle time can pass between two
  samples unseen; it is a claim about what was observed at that rate.
  `attitude_stable` remains the criterion that weighs every attitude sample.
- The default regression tolerance is 10%, chosen from SITL's own run-to-run
  scatter on repeated tier-1 takeoffs of the same frame. It is a starting point
  for a project's own baselines, not a property of any aircraft.
- The portal renders a known subset of markdown — headings, fenced code, lists,
  tables, blockquotes, links, inline code. Anything outside it renders as the
  literal text it is.
- A mode change that the autopilot accepts and then reverts still reports as a
  success from `_do_mode`. The mode-settle gate prevents the case that was
  actually biting; it does not make the class of failure visible.
- Nothing here changes what tier 2 can claim, and no new model was flown.

## v1.2.0 — 2026-08-04

### Live telemetry to PlotJuggler

Until now the only numbers you could see *during* a flight were MAVProxy's
console text; everything graphical came after it, from the dataflash report. A
running session now mirrors its telemetry to a loopback UDP port that
PlotJuggler plots in real time. The port opens when you press START and closes
when you press STOP, so the stream belongs to a session rather than to the
server.

- **Config key `plotjuggler_port`** (`argaz.toml`, `ARGAZ_PLOTJUGGLER_PORT`,
  `--plotjuggler-port`), default **14552** — next in the same block as 14550
  and 14551. `0` switches the mirror off.
- **A LIVE PLOT line under Quick Commands** with the address, a copy button for
  the port, and a running count of the messages that have actually left it —
  the count rather than an "open" badge, because one is a measurement and the
  other is a claim.
- Nothing is launched or bundled: ArgazUI opens the port, you connect
  PlotJuggler to it.

**It sends JSON, not MAVLink, and that was not the original plan.** The plan
was a raw MAVLink mirror for "PlotJuggler's MAVLink plugin". That plugin does
not exist. Checked against the installed build (3.17.2): PlotJuggler's live
data sources are UDP Server, WebSocket, ZMQ, MQTT, serial, ROS 2 and the
Foxglove bridge, and its parsers are JSON/CBOR/BSON/MessagePack, Protobuf, ROS
1/2, DataTamer and InfluxDB line protocol. ArduPilot's own PlotJuggler plugin
(`plotjuggler-apbin-plugins`) is a dataflash `.BIN` loader — offline, and a
different problem. A raw mirror would have had no reader, so the mirror emits
one JSON object per MAVLink message instead, which PlotJuggler flattens into
`ATTITUDE/roll`, `VFR_HUD/alt` and so on. Raw MAVLink to a third consumer
already exists and needed nothing new: another `sim_vehicle.py --out`.

No second MAVLink implementation was added. The mirror decodes nothing — it is
fed from `MavlinkLink._absorb`, the one place every received message already
passes through, and only serialises objects pymavlink has already parsed. It
also sits *after* that method's ground-station heartbeat filter, so MAVProxy's
own HEARTBEAT cannot overwrite the aircraft's mode in the plot.

Two field types are dropped on the way out. Text, because nothing plots a
string and it is already in `mavlink_events.jsonl`. And `NaN`/infinity, which
ArduPilot really does send in unpopulated fields: `json.dumps` writes them as
bare literals that are not JSON, and PlotJuggler answers a message it cannot
parse by *stopping the stream* — so one of them would have ended the live plot
rather than spoiled one point. There is a test for exactly that.

### Verified

- Tier 1 (`tests/test_telemetry_mirror.py`): a real SITL quad, a listener bound
  to the mirror port, and an assertion that a `HEARTBEAT` arrives as valid JSON
  with its fields intact — plus that *every* datagram parses, and that the port
  goes silent when the session stops. Encoder tests pin the NaN and text rules
  without needing a vehicle.
- Measured, on that session: 34 message types, roughly 250 series, about 130
  datagrams (26 KB) per second of flight.
- **Not verified by anything: that PlotJuggler draws the graph.** No test in
  this project can see a rendered window. It is a new ✗ row in
  [docs/manual-checklist.md](docs/manual-checklist.md).

`argazui doctor` deliberately does **not** check this port. It checks that
14550 and 14551 are free to *bind*; 14552 is supposed to be held — by
PlotJuggler — so a bind check would report FAIL exactly when the feature works.

`docs/status.md` is unchanged: this is an application-level capability and
makes no claim about any vehicle model.

### Closeout — three things manual testing found

**The Address box, and a warning dialog that lies.** Connecting PlotJuggler
produced *"Couldn't bind to IPv4 UDP server at (127.0.0.1:14552, 14552)"* —
while the data was arriving perfectly. Pressing OK on it stopped the stream;
ignoring it did not. Root-caused against the real snap build (3.17.2) and
upstream's `plotjuggler_plugins/DataStreamUDP/udp_server.cpp`:

```cpp
QHostAddress address(address_str);      // "127.0.0.1:14552" -> a NULL address
bool success = true;
success &= !address.isNull();           // false already, from the text box
success &= _udp_socket->bind(address, port);   // but this SUCCEEDS: null means "any"
connect(_udp_socket, &QUdpSocket::readyRead, this, &UDP_Server::processMessage);
if (!success) { QMessageBox::warning(...); shutdown(); }
```

The flag comes from the text someone typed, not from the socket. `readyRead`
is connected before it is consulted and a modal `QMessageBox` runs a nested
event loop, so telemetry keeps arriving while the dialog sits there; OK returns
into `shutdown()`, which destroys a socket that was working. Confirmed at the
Qt API level (`bind()` returns true for both `127.0.0.1:14552` and an empty
box) and by `ss` showing the complaining process holding `0.0.0.0:14552`.

Nothing ArgazUI sends is involved — the bind happens before the first datagram
is read. It is still our bug: the LIVE PLOT strip displayed `127.0.0.1:14552`
as one selectable token, and **USAGE.md told the user to leave Address blank,
which produces the same null address and the same dialog.** Fixed by never
presenting a `host:port` token again — Address and Port are two separately
labelled, separately copyable values — and by documenting the exact field
values in both languages, in the app and in USAGE.md, including what to do if
you have already hit the dialog (close it with ✕; do not press OK). An e2e test
asserts the combined form appears nowhere in the strip except inside that
warning.

**The Flight Runs panel is capped at 5.** With real usage history it rendered
every run and became an endless scroll. It now shows the five most recent with
a control that reveals the rest and collapses again. Display only: `/api/runs`
still returns every run and nothing under `runs/` changed. `#run=<id>` deep
links keep working — the list expands automatically when the target is below
the fold, because a panel that hides data is fine and a link that silently does
nothing is not.

**Removed the v1.1 handover note from `docs/`.** It listed what was still
missing when v1.1 closed — chiefly that `docs/status.md` and this file did not
yet exist. Both do, and the roles it filled are covered by
[docs/status.md](docs/status.md),
[docs/manual-checklist.md](docs/manual-checklist.md) and this changelog. It is
in the git history if anyone wants it.

---

## v1.1.0 — 2026-08-03

v1.0 was a control panel. v1.1 is a control panel that can prove its own
claims, and the first thing that proof did was contradict v1.0's README.

### Two things v1.0 got wrong, stated plainly

**Plane TAKEOFF never worked.** Every fixed-wing model in v1.0 — Zephyr,
Skywalker X8, Mini Talon, the Weight-Shift Aircraft — was listed as fully
tested, and the TAKEOFF button was wired to a copter's flow: switch to GUIDED,
arm, send `MAV_CMD_NAV_TAKEOFF`. A plane in GUIDED does not take off from that
command; it loiters at its current altitude, and ArduPlane rejects the copter
takeoff outright. There was one takeoff path for every airframe, and it was a
multirotor's. Nothing noticed because nothing checked the aircraft afterwards
— the button reported the ACK it received and stopped there.

Fixed by making the flow a property of the *airframe*: procedures are
declarative YAML per vehicle class, chosen from capabilities probed off the
vehicle over MAVLink (`Q_ENABLE`, `Q_TAILSIT_ENABLE`, `Q_OPTIONS`), never from
what `models.json` claims the model is.

**v1.0's README carried unverified support claims.** It listed eleven models
with green ticks and the sentence "Every model below was tested by actually
flying it". Nothing produced those ticks except somebody's belief. The table
is gone; [docs/status.md](docs/status.md) is generated from test output by CI
and any hand edit to it is overwritten. Expect it to be smaller than the list
it replaced — that is the correction, not a regression.

### The tailsitter: a weak criterion showed green for a tumble

The best story in this release, because it is the failure mode the whole
version exists to catch, caught in our own work.

`tailsitter_takeoff` passed three times, at 24.9 m, 23.6 m and 18.3 m. It
reached altitude, stayed armed and reported QHOVER, and those were the only
three things the acceptance criteria asked about.

When the criteria were tightened to measure *attitude* as well, the same
procedure on the same frame recorded peak body rates of **1263–1306 °/s** —
three and a half revolutions per second — with a median of 183–399 °/s, roll
spanning ±180° and control outputs saturated for the entire flight. The
aircraft had been tumbling the whole time. Altitude was a side effect of a
thrust vector that happened to point roughly upwards; nothing in the old
criteria could tell a controlled climb from a fall in the wrong direction.

Diagnosis, which turned out to be upstream's: `plane-tailsitter` ships no VTOL
attitude tuning at all, and ArduPilot's own test suite lists it as a
known-broken frame — *"unstable in hover; unflyable in cruise"* — and skips it
(`Tools/autotest/arduplane.py`, `FlyEachFrame`). Rebooting SITL first, as
upstream does for tailsitters, improves the peak from 1263 to 235 °/s but does
not stabilise it. The only alternative frame,
`quadplane-copter_tailsitter`, is properly tuned and rock-steady at 0.1 °/s
but produces no lift from stick input at any throttle up to full.

So tier 1 cannot verify this procedure on this checkout. **It is left red.**
Tuning the airframe until our own test passes would prove nothing, and an
`xfail` would paint it green.

### What is new

- **Procedures.** Takeoff and landing for copter, plane, quadplane and
  tailsitter as declarative YAML in `argazui/procedures/`, with a versioned
  schema. The button and the regression test execute the *same file*.
- **Acceptance criteria that measure state.** `expect:` blocks judge altitude,
  mode, arm state, parameters — and, since this release, the attitude envelope
  the aircraft flew through, in seconds spent outside a declared band rather
  than in peaks. An ACK is never a pass.
- **Declared parameter overrides.** A procedure may only change a parameter it
  declares, with a reason in both languages; the values are restored when it
  ends, including when it fails. Upstream `.param` files are never edited.
- **Installable elsewhere.** `argaz.toml`, `ARGAZ_*` variables or CLI flags;
  no absolute path is baked into anything. `argazui doctor` checks the
  installation, and every fix it prints runs verbatim when pasted.
- **Run artefacts.** `runs/<UTC>_<model>/` per flight: dataflash log, full and
  differential parameter dumps, the procedure verbatim, MAVLink event stream,
  console log, and a post-flight report with advisories (vibration, EKF
  innovations, attitude tracking) that never change a verdict.
- **A test suite that flies.** Real SITL, a real FastAPI server, a real
  browser; no mocks anywhere. Tier 1 runs on every push in under six minutes;
  tier 2 flies the model set in Gazebo nightly.
- **Version-drift detection.** The page compares the identity of the server
  answering it against the files it was served, names which layer changed
  (server code vs interface files), and prints a restart command that runs.
- **`sitl_only` launch method.** SITL's own physics, no Gazebo, no display —
  for working on procedures, CI, or a machine with no graphics stack.
- **Headless launching.** Gazebo runs server-only and MAVProxy opens no
  windows when there is no display, so the same launch commands work over SSH
  and in a container.

### Fixed

- The takeoff flow was a multirotor's for every airframe (above).
- The procedure runner let any exception other than an abort escape into its
  thread, freezing the interface with no message.
- A failing panel took the whole page down: one 404 left the startup chain
  rejected before the WebSocket was ever connected. Panels are isolated now
  and each reports its own failure.
- `start.sh` chose `/usr/bin/python3` because `"${VIRTUAL_ENV:-}/bin/python3"`
  expands to exactly that when the variable is unset, then tried to install
  into a PEP 668 interpreter. It now explains every candidate it rejected and
  never uses `--break-system-packages`.
- Recovery commands printed by the interface contained `<pid>` and produced
  `bash: syntax error near unexpected token 'newline'` when pasted. Every
  command any part of this project prints is now runnable as-is, and a test
  parses them.
- ArgazUI refused to start on any machine without Gazebo and ROS 2, because
  the startup preflight ran the full doctor profile. A missing simulator stops
  some models from flying, not the application from running.
- A fresh clone logged eleven 404s in the browser console: `models.json` names
  a preview image for every model, but `static/models/` is fetched separately.
- The post-flight report was generated on a daemon thread, so the last flight
  of a test session lost its report every time — a complete dataflash log and
  nothing that had read it.
- `RC_KEEPALIVE_INTERVAL` was a constant, though both terms of the budget it
  approximates are variables. It is derived now: `RC_OVERRIDE_TIME` is read
  from the vehicle and the SITL speedup is measured from the vehicle's own
  clock.

### Known limits

- **`plane-tailsitter` fails tier 1** and will keep CI red until either
  upstream tunes the frame or the procedure is proven on hardware. See above.
- **Three models fail tier 2**: `zephyr` (hand-launched wing; the plane
  takeoff procedure expects a runway roll, and "needs hand launch" is not yet
  a probed capability), `skycat_tvbs` (outside the tailsitter pitch band,
  though measured rates are calm — whether that is the aircraft or the band
  has not been established), `swan_k1_hwing` (never passes pre-arm: no
  airspeed sensor).
- **`iris` is `untested`**: it launches through `ros2 launch`, which needs a
  built `ardupilot_gz` workspace that the tier-2 image does not contain.
- **Tier 2 runs on GitHub's hosted runners** — verified, roughly 24 minutes
  for eleven models — but the image is 10.3 GB and close to a runner's free
  disk. `tier2.yml` carries self-hosted instructions if that stops working.
- **No test has ever looked at a rendered Gazebo frame.** Models are flown
  headless, so a model loaded upside-down or at the wrong scale would fly its
  procedure and pass. See [docs/manual-checklist.md](docs/manual-checklist.md)
  for this and the other gaps.
- Mission scripts on port 14551 are configured by the launch commands and
  exercised by no test at all.

### Not in this version

Deliberately out of scope and not started: multi-vehicle/swarm simulation,
HITL, scenario YAML (the `mission:` and `failures:` keys are reserved in the
procedure schema and rejected until then), failure injection through `SIM_*`,
regression comparison between runs, authentication and remote access.

---

## v1.0.0

First release. Model registry, two terminal sessions, quick command buttons
over MAVLink, ARM recovery, mission script support.
