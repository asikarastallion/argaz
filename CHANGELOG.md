# Changelog

## Unreleased (v1.2 in progress)

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
