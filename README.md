# ArgazUI

**A single-page control panel for ArduPilot SITL + Gazebo.**
Pick a model, press START, and fly — no terminals, no retyped commands.

![ArgazUI](docs/screenshot.png)

---

## Why

Running an ArduPilot SITL flight in Gazebo normally means opening two or three
terminals and typing the same things every time:

```bash
source env.sh
gz sim -v4 -r alti_transition_runway.sdf &
cd ardupilot/ArduPlane
sim_vehicle.py -v ArduPlane --model JSON \
    --add-param-file=$SITL_MODELS/Gazebo/config/alti_transition_quad.param --console --map
# ...then remember the right MAVProxy commands to arm and take off
```

ArgazUI reduces that to one click. It discovers the available vehicle models
from the official ArduPilot documentation, launches the right combination of
Gazebo + SITL + MAVProxy for each one, and exposes arm/takeoff/mode commands as
buttons — while still giving you two **real, interactive bash terminals** so
nothing is hidden from you.

## Features

- **11 vehicle models** across Copter / Plane / VTOL, auto-discovered from the
  ArduPilot `SITL_Models` docs, each with a preview image.
- **One-click launch** — the exact shell commands are typed into a visible
  terminal, so you always see what ran.
- **Quick command buttons** per vehicle class (ARM, TAKEOFF, RTL, LAND, Q-modes,
  …), sent over MAVLink with real ACK feedback and the autopilot's own rejection
  reason when something fails.
- **A READY indicator** driven by the autopilot's pre-arm health bit, so you
  know when ARM will actually be accepted.
- **Automatic recovery** from the three most common ARM failures (see below).
- **Two real bash terminals** — one running the simulation (MAVProxy stays
  interactive), one free for mission scripts and shell commands.
- **Mission script runner** for your own `pymavlink` scripts, on a dedicated
  MAVLink port so they never clash with the UI.
- **English / Turkish** interface; the language switch also changes the
  backend's terminal messages.
- **Localhost only**, no authentication, no telemetry, no CDN — `xterm.js` is
  vendored.

## Requirements

ArgazUI is a front end for an existing simulation setup. It does **not** bundle
these, and expects them to sit next to it:

| Component | Notes |
|---|---|
| [ArduPilot](https://github.com/ArduPilot/ardupilot) | built SITL binaries (`arducopter`, `arduplane`) |
| [ardupilot_gazebo](https://github.com/ArduPilot/ardupilot_gazebo) + ROS 2 workspace | for the Iris / Zephyr models and the RViz bridge |
| [SITL_Models](https://github.com/ArduPilot/SITL_Models) | the Gazebo model, world and parameter files |
| Gazebo Harmonic, ROS 2 Jazzy | tested combination |
| Python 3.12 | `fastapi`, `uvicorn`, `wsproto`, `pymavlink` |

Verified on Ubuntu 24.04 with Gazebo Harmonic and ROS 2 Jazzy.

### Expected layout

ArgazUI reads `env.sh` from its parent directory, so it must live inside the
simulation root:

```
argaz/
├── env.sh                 # ROS 2 + Gazebo environment (yours)
├── quadplane_env.sh       # adds the SITL_Models resource paths (yours)
├── ardupilot/             # cloned separately  (not in this repo)
├── ardu_ws/               # cloned separately  (not in this repo)
├── SITL_Models/           # cloned separately  (not in this repo)
├── scripts/               # your mission scripts
└── argazui/               # this tool
```

The three large upstream trees are excluded from this repository via
`.gitignore` — together they exceed 10 GB and belong to their own projects.

## Quick start

```bash
git clone https://github.com/asikarastallion/argaz.git
cd argaz/argazui

# one-off: fetch the model preview images from the upstream ArduPilot docs
python3 -m argazui.fetch_images

./start.sh
```

Then open **http://127.0.0.1:8770**.

`start.sh` locates a Python interpreter that has the required packages (the
`venv-ardupilot` virtualenv is only activated in login shells, which is why
`python3 -m argazui` can fail inside a VS Code terminal), and installs the
missing ones if needed.

## How it works

```
browser ──WebSocket──┐
                     │            ┌── pty #1 ── bash ── ros2 launch / gz sim + sim_vehicle.py
   FastAPI (127.0.0.1:8770) ──────┤                      └── MAVProxy (interactive)
                     │            └── pty #2 ── bash ── your mission scripts
                     │
                     └──MAVLink UDP 14550──> the vehicle   (scripts use 14551)
```

Three design decisions are worth calling out, because each came out of testing
rather than planning:

**Buttons speak MAVLink, not MAVProxy stdin.** On the ROS 2 launch path MAVProxy
is started with `--non-interactive` and never reads stdin, so typing `mode
guided` into the terminal does nothing there. MAVLink works identically on both
launch paths and returns ACKs, so the buttons use it and report the real result.

**Two terminals, not one.** The simulation occupies the shell's foreground —
which is *required*, because a background process cannot read stdin (it stops
with `SIGTTIN`) and MAVProxy's interactivity depends on it. A second shell is
opened so mission scripts and manual commands remain possible.

**Process cleanup never matches on names.** `pkill -f <pattern>` can match the
command line of the very shell running it. Instead each terminal is started in
its own session (`start_new_session=True`), and STOP scans `/proc` for the
process groups belonging to that session and terminates them with `os.killpg`
in SIGINT → SIGTERM → SIGKILL order. Matching uses kernel-reported SID/PGID, so
killing the wrong process is impossible.

Each model also runs in its own working directory (`argazui/run/<model_id>/`)
so SITL's `eeprom.bin` and logs never touch the ArduPilot tree, and models
cannot corrupt each other's stored parameters.

## Supported models

Every model below was tested by actually flying it: ARM → takeoff → mode
changes → landing → STOP.

| Model | Class | Launch method | Status |
|---|---|---|---|
| Iris Quadcopter | Copter | `ros2_launch` | ✅ full (only model with RViz/DDS) |
| BiCopter | Copter | `gz_plus_sitl_paramfile` | ✅ full |
| Hexapod Copter | Copter | `gz_plus_sitl_paramfile` | ✅ full (needs a Lua mixer, copied automatically) |
| Zephyr Delta Wing | Plane | `gz_plus_sitl_frame` | ✅ full |
| Skywalker X8 | Plane | `gz_plus_sitl_paramfile` | ✅ full |
| X-UAV Mini Talon | Plane | `gz_plus_sitl_paramfile` | ✅ full |
| Weight-Shift Aircraft | Plane | `gz_plus_sitl_paramfile` | ✅ full (RC trim auto-corrected) |
| Alti Transition | VTOL | `gz_plus_sitl_paramfile` | ✅ full |
| SkyCat TVBS | VTOL | `gz_plus_sitl_paramfile` | ✅ full |
| Skywalker X8 Quad | VTOL | `gz_plus_sitl_paramfile` | ✅ full |
| Swan-K1 Tailsitter | VTOL | `gz_plus_sitl_paramfile` | ⚠ needs **ARM (FORCE)** — see below |

Rover, boat and walking-robot models in `SITL_Models` are intentionally out of
scope.

### Automatic ARM recovery

A rejected ARM is usually not a bug — the vehicle is not ready yet. ArgazUI
handles the three failures that actually occurred during testing:

| Autopilot says | What ArgazUI does |
|---|---|
| `AHRS: waiting for home`, `Accels inconsistent`, `EKF …` | Retries for 35 s until the vehicle is ready (BiCopter armed on the 8th attempt) |
| `Pitch (RC2) is not neutral` | Reads that channel's `RC*_TRIM` and centres the stick on it, then retries. The model's parameters are untouched. |
| `3D Accel calibration needed` | Runs a simple accelerometer calibration (`accelcalsimple`), which is correct in SITL because the vehicle sits level |

**Swan-K1** is the one model that still needs `ARM (FORCE)`. Its parameter file
is a full dump from a real flight controller; two of its contradictions are
corrected at boot through `sitl_param_overrides`, but the remaining mag-field
and yaw warnings come from the airframe being a tailsitter — it stands nose-up
while those checks assume a level vehicle. With ARM (FORCE) it flies normally.

## Configuration

Everything is plain JSON, generated automatically but meant to be edited.

| File | Purpose |
|---|---|
| `argazui/config/models.json` | Model registry — regenerate with `python3 -m argazui.scan_models --force`; entries marked `_manually_added` survive a rescan |
| `argazui/config/buttons.json` | Quick command buttons per vehicle class, with optional Turkish labels |

The scanner parses the `gz sim` / `sim_vehicle.py` lines out of
`SITL_Models/Gazebo/docs/*.md`, classifies Plane vs VTOL from `Q_ENABLE` in the
parameter file, and picks up "copy this `.lua` script" prerequisites.

## Mission scripts

Drop a `pymavlink` script into `scripts/` and it appears in the dropdown. Use
port **14551** — 14550 belongs to the interface:

```python
import os
from pymavlink import mavutil

PORT = int(os.environ.get("ARGAZ_MAVLINK_SCRIPT_PORT", "14551"))
conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{PORT}")
conn.wait_heartbeat(timeout=30)
```

Two examples are included: `00_connection_test.py` (read-only telemetry) and
`10_copter_takeoff_and_rtl.py` (GUIDED takeoff → RTL).

## Documentation

[**argazui/USAGE.md**](argazui/USAGE.md) is the full guide: every panel, adding
models/buttons/scripts, the launch methods, and troubleshooting. The same
material is available in-app under **HOW TO USE**, in English and Turkish.

[**TROUBLESHOOTING.md**](TROUBLESHOOTING.md) *(Turkish)* covers building the
underlying environment — apt conflicts, Gazebo/ROS 2 version mismatches, the
GTK/locale variables that make GUI apps crash under a snap terminal, and so on.
It is about the simulation stack rather than ArgazUI itself.

## Out of scope (v1.0)

Multi-vehicle / swarm simulation, authentication, remote access, graphical
mission planning (MAVProxy's map covers part of it) and telemetry dashboards
(MAVProxy's console covers the basics).

## Notes on licensing

ArduPilot, `ardupilot_gazebo` and `SITL_Models` are separate upstream projects
under their own licences (GPLv3) and are **not redistributed here**. The model
preview images are downloaded from those projects' documentation at setup time
by `fetch_images.py` and are likewise not committed to this repository.

No licence has been chosen for ArgazUI itself yet — add a `LICENSE` file if you
want others to reuse it.

## Contact

**M. Serdar Sökmen**

- E-mail — [mserdarsokmen@gmail.com](mailto:mserdarsokmen@gmail.com)
- LinkedIn — [linkedin.com/in/mserdarsokmen](https://www.linkedin.com/in/mserdarsokmen)
- GitHub — [github.com/asikarastallion](https://github.com/asikarastallion)
