# ArgazUI — Usage Guide

A local control panel for running ArduPilot SITL + Gazebo flights from a single
browser page. The goal is to remove the loop of opening 2–3 terminals and
retyping `source env.sh`, `gz sim ...`, `sim_vehicle.py ...` for every attempt.

ArgazUI **never modifies** your existing `argaz` setup. `env.sh`,
`quadplane_env.sh`, `ardupilot/` and `ardu_ws/` are only **read and executed**.

---

## 1. Starting

```bash
cd argazui
./start.sh doctor
./start.sh
```

Then open **http://127.0.0.1:8770** in a browser.
Different port: `./start.sh --port 9000`

Before starting, `start.sh` runs the critical checks from `argazui doctor`.
Use `./start.sh doctor --json` for automation. The root paths and ports come
from CLI options, `ARGAZ_*` environment variables, `argaz.toml`, then
auto-detection; `env.sh` is not assumed to be in this tool's parent directory.
Copy `argaz.toml.example` to `argaz.toml` at the repository root and set the
paths for an installation with a different layout.

The server listens on **127.0.0.1 only** — it is not exposed to the network and
has no authentication. Press `Ctrl+C` to stop; it cleans up the terminals it
opened and any running simulation.

The interface is **English by default**; use the **EN / TR** switch in the top
bar to change language. The switch also changes the language of the backend
messages printed to the terminal, so the whole tool stays consistent.

### Why `./start.sh` and not `python3 -m argazui`?

Because `venv-ardupilot` is activated only from `~/.profile`, i.e. **only in
login shells**. A terminal opened by VS Code is not a login shell, so there
`python3` resolves to `/usr/bin/python3` and uvicorn is missing:

```
ModuleNotFoundError: No module named 'uvicorn'
```

`start.sh` therefore does not trust `PATH`. It tries `$ARGAZUI_PYTHON`, the
active venv, `~/venv-ardupilot`, the `python3` on `PATH` and `/usr/bin/python3`
in order, and uses the first one that has all of `uvicorn`, `fastapi` and
`pymavlink`. If none is ready it tries to install them into the venv.

To force a specific interpreter:

```bash
ARGAZUI_PYTHON=/path/to/python3 ./start.sh
```

Python packages are installed into `~/venv-ardupilot` (system packages are left
untouched): `fastapi`, `uvicorn`, `wsproto`. The terminal widget (`xterm.js`) is
vendored under `static/vendor/`, so no internet connection is required.

> `baslat.sh` still exists as a symlink to `start.sh` for convenience.

---

## 2. The interface

### 2.1 Top bar — status chips

| Chip | Meaning |
|---|---|
| **Vehicle** | The model currently running |
| **MAVLink** | ArgazUI's link to the vehicle (port 14550) |
| **READY** | Pre-arm checks. **ARM is rejected until this turns green.** |
| **Mode** | Active flight mode |
| **ARMED / DISARMED** | Whether the motors are armed |
| **Alt** | Altitude relative to the launch point |
| **Spd** | Ground speed |

The **EN / TR**, **HOW TO USE** and **CONTACT** controls sit at the top right
(`Esc` closes the panels).

### 2.2 Model picker

Models are grouped into three columns by vehicle class. Selecting one shows a
**preview image** and how it will be launched in the right-hand panel; click the
image for a larger view.

- **▶ START** — brings up Gazebo + SITL + MAVProxy. The commands are typed into
  the SIMULATION terminal verbatim.
- **■ STOP** — shuts down Gazebo, SITL, MAVProxy, RViz and any running mission
  script cleanly.
- **⟳ rescan models** — re-scans `SITL_Models/Gazebo/docs/` (your manual edits
  are preserved).

Only **one vehicle at a time** is supported; starting a new model closes the
previous one automatically.

### 2.3 Quick Commands

A button set that changes with the vehicle class. Buttons are sent over MAVLink
and the **result is written to the terminal**:

```
[ArgazUI] arm throttle  ->  ARM: accepted
[ArgazUI] mode guided   ->  mode -> GUIDED
```

If a command is rejected, the autopilot's own reason is shown
(`ARM: REJECTED (MAV_RESULT_FAILED) — autopilot: Arm: AHRS: waiting for home`).

Buttons activate only when a vehicle is running **and** MAVLink is connected.
ARM and TAKEOFF ask for confirmation.

### 2.4 Mission Script

Lists the `.py` files in `~/Documents/argaz/scripts/`.
**▶ RUN SCRIPT** runs the selected file in the **COMMAND / SCRIPT** terminal.

### 2.5 Terminal — two tabs

| Tab | Purpose |
|---|---|
| **SIMULATION** | Gazebo / SITL / MAVProxy run here. For models launched with `sim_vehicle.py`, MAVProxy is **interactive**: you can type `status`, `wp list`, `motortest 1 1 1005 2`, `magcal` directly. |
| **COMMAND / SCRIPT** | A plain bash shell. Mission scripts run here. |

**Why two terminals?** The simulation occupies the shell's foreground — this is
mandatory, because a process that is not in the foreground cannot read stdin (it
stops with SIGTTIN) and MAVProxy's interactivity depends on it. Since no script
can be run in that same shell, a second one is opened.

Both are **real bash sessions**; `Ctrl+C` sends a real SIGINT.

---

## 3. Launch methods

| method | How it works | Models |
|---|---|---|
| `ros2_launch` | `env.sh` + `ros2 launch ardupilot_gz_bringup iris_runway.launch.py console:=True map:=True rviz:=True` | Iris |
| `gz_plus_sitl_paramfile` | `quadplane_env.sh` + `gz sim -v4 -r <world>.sdf &` + `sim_vehicle.py ... --add-param-file=<param>` | SITL_Models models |
| `gz_plus_sitl_frame` | Same, but with `-f <frame>` instead of a param file | Zephyr |

**RViz and the ROS 2/DDS bridge exist only for models launched via
`ros2_launch` (currently Iris only).** The panel reports "RViz/DDS: no" for the
rest.

### Working directories

Each model runs in its own directory: `argazui/run/<model_id>/`

Why:
1. The `eeprom.bin`, `logs/` and `terrain/` files SITL produces are **not
   written into the ardupilot tree** — it stays read-only.
2. Models cannot corrupt each other's eeprom. (When they all shared one
   directory, one model's settings leaked into the next.)
3. Models that need Lua can get their own `scripts/` folder here.

To start a model from scratch, just delete its directory:
`rm -rf argazui/run/<model_id>`

---

## 4. MAVLink ports

| Port | Used by |
|---|---|
| **14550** | ArgazUI — quick command buttons and the status chips |
| **14551** | **Your mission scripts** |

Two listeners cannot share one UDP port, which is why they are split.

### Why buttons use MAVLink instead of writing to MAVProxy

On the Iris (`ros2_launch`) path, MAVProxy is started by ROS 2 launch with the
`--non-interactive` flag — it does **not** read commands from stdin (source:
`ardupilot_sitl/src/ardupilot_sitl/launch.py`). Typing "mode guided" into the
terminal does nothing there. MAVLink works on both paths and gives ACK feedback.
On the `sim_vehicle.py` path MAVProxy is interactive, so typing into the
SIMULATION terminal still works as an extra option.

Commands the interpreter understands: `mode <MODE>`, `arm throttle [force]`,
`disarm [force]`, `takeoff <metres>`, `param set <NAME> <VALUE>`,
`param fetch <NAME>`, `rc <channel> <pwm>`. Anything else is forwarded to the
SIMULATION terminal.

---

## 5. ARM problems and automatic fixes

**A rejected ARM is usually not a bug** — the vehicle simply is not ready yet.
The autopilot will not arm until the **READY** chip turns green (about 10–35 s
after startup).

ArgazUI resolves three situations by itself:

| Situation | What the autopilot says | What ArgazUI does |
|---|---|---|
| Transient startup state | `AHRS: waiting for home`, `Accels inconsistent`, `EKF...` | Retries every 2.5 s for 35 s; arms as soon as the vehicle is ready (BiCopter armed on the 8th attempt) |
| Stick not neutral | `Pitch (RC2) is not neutral` | Moves that channel to its own `RC*_TRIM` value and retries. The model's parameters are not changed. |
| Accelerometer not calibrated | `3D Accel calibration needed` | Performs a simple accelerometer calibration (equivalent to `accelcalsimple`) — correct in SITL because the vehicle sits level |

If none of these help, the real reason is printed in the terminal.

### ARM (FORCE)

Arms the motors **bypassing** the pre-arm checks. It is an escape hatch for
models whose parameter file is a real flight-controller dump that does not fully
settle in SITL (see Swan-K1). **Never use this on a real aircraft.**

---

## 5b. Takeoff and landing procedures

The **TAKEOFF** and **LAND** buttons do not send a fixed command list. They run
a *procedure*: a declarative flight sequence in `argazui/procedures/*.yaml`,
with its acceptance criteria written into the same file. The format is
documented in [procedures/SCHEMA.md](procedures/SCHEMA.md).

**Why.** In v1.0 every vehicle class got the Copter idiom — GUIDED, arm,
`MAV_CMD_NAV_TAKEOFF`. On ArduPlane that command is compiled only under
`HAL_QUADPLANE_ENABLED` and its handler returns `MAV_RESULT_FAILED` unless the
aircraft is a quadplane, so on a fixed wing the button armed the aircraft and
left it sitting on the runway. Taking off is a different *procedure* per
aircraft, not a different argument to one command.

**The procedure is chosen from the aircraft, not the registry.** When the link
comes up, ArgazUI reads `Q_ENABLE`, `Q_TAILSIT_ENABLE` and `Q_OPTIONS` from the
vehicle and picks the matching procedure. This catches things `models.json`
does not know: SkyCat TVBS is registered as a plain QuadPlane but its parameter
file sets `Q_TAILSIT_ENABLE=1`, so it gets the tailsitter procedure.

| Aircraft | Takeoff | Landing |
|---|---|---|
| Copter | `copter_takeoff` — GUIDED + `MAV_CMD_NAV_TAKEOFF` | `copter_land` — LAND |
| Fixed wing | `plane_takeoff` — TAKEOFF mode | `plane_land` — AUTOLAND |
| QuadPlane | `vtol_takeoff` — QLOITER + throttle above mid | `vtol_land` — QLAND |
| Tailsitter | `tailsitter_takeoff` — arm in QSTABILIZE, climb in QHOVER | `tailsitter_land` — QLAND |

Alternatives that are not auto-selected: `plane_takeoff_auto` (AUTO mission),
`vtol_takeoff_mission` (`NAV_VTOL_TAKEOFF`), `plane_land_rtl` (returns but does
**not** land — a plane's RTL loiters).

**An ACK is not success.** Every procedure ends in an `expect:` block that is
checked against measured state — altitude, climb rate, mode, armed flag. The
panel that appears under Quick Commands shows each step and each criterion as
it is evaluated.

**Parameters are run-scoped.** If a procedure sets a parameter (for example
`TKOFF_ALT`), the previous value is restored when the procedure ends, including
when it fails. Upstream `.param` files are never edited.

**The tests run these same files.** There is no separate test implementation of
a takeoff, so a passing test means a working button.

A model can pin its own choice in `models.json`:

```json
"procedures": { "takeoff": "plane_takeoff_auto", "land": "plane_land" }
```

---

## 6. Adding a mission script

1. Drop your `.py` file into `~/Documents/argaz/scripts/`.
   (Files starting with an underscore — `_helpers.py` — are hidden from the list.)
2. The first comment line is shown as the description in the interface.
3. Connect to port **14551**:

```python
import os
from pymavlink import mavutil

PORT = int(os.environ.get("ARGAZ_MAVLINK_SCRIPT_PORT", "14551"))
conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{PORT}")
conn.wait_heartbeat(timeout=30)
```

4. In the interface press **⟳ refresh** → pick it from the list → **▶ RUN SCRIPT**.

Two examples ship with the project: `00_connection_test.py` (read-only
telemetry) and `10_copter_takeoff_and_rtl.py` (GUIDED takeoff → RTL).

---

## 7. Adding a model / the registry

Registry: `argazui/config/models.json` — generated automatically, editable by
hand.

```bash
python3 -m argazui.scan_models --dry-run   # report only
python3 -m argazui.scan_models --force     # regenerate (merging)
```

The scanner reads the `gz sim -r <world>.sdf` and `sim_vehicle.py ...` lines in
`SITL_Models/Gazebo/docs/*.md`, plus **"Copy the script ....lua"**
prerequisites. Only `ArduCopter` and `ArduPlane` are included.

**Plane / VTOL classification** is based on `Q_ENABLE` in the parameter file
(`1` → VTOL, `0`/absent → Plane).

### Adding a model by hand

```json
{
  "id": "my_model",
  "name": "My Model",
  "vehicle_class": "VTOL",
  "method": "gz_plus_sitl_paramfile",
  "env": "quadplane_env.sh",
  "world": "my_world.sdf",
  "vehicle": "ArduPlane",
  "param_file": "$SITL_MODELS/Gazebo/config/my.param",
  "lua_scripts": [],
  "sitl_param_overrides": {},
  "has_ros2": false,
  "_manually_added": true
}
```

A rescan **never deletes** entries marked `_manually_added: true`. To stop a
scanned entry from being overwritten, add `"_manually_edited": true`.

### Special fields

| Field | Purpose |
|---|---|
| `lua_scripts` | For models that need a Lua motor mixer. ArgazUI copies the file into `run/<id>/scripts/`. Without it, Hexapod Copter (`FRAME_CLASS 17`, Dynamic Scripting Matrix) fails with `PreArm: Motors: Check frame class and type`. |
| `sitl_param_overrides` | Applied at startup as a second `--add-param-file`. For models whose parameter file is a real hardware dump that contradicts itself in SITL. Parameters that only take effect at boot (such as `EK3_ENABLE`) must be set this way. The model's own parameter file is **never modified**. |
| `image` | Path to the preview image. |

---

## 8. Model images

```bash
python3 -m argazui.fetch_images           # fetch missing ones
python3 -m argazui.fetch_images --force   # refresh all
```

Images are taken from the ArduPilot SITL_Models / ardupilot_gazebo
documentation and stored **locally** under `static/models/<id>.png`, so the page
never fetches anything remotely. For models with no image in any source, the
procedure for capturing a screenshot from the simulation is documented at the
top of `argazui/fetch_images.py` — the Iris image was produced that way.

---

## 9. Verified behaviour

Every model was tested by actually flying it (ARM → takeoff → mode changes →
landing → STOP):

| Model | Class | Result |
|---|---|---|
| Iris | Copter | ✅ full |
| BiCopter | Copter | ✅ full (ARM succeeded on the 8th attempt, transient reason) |
| Hexapod Copter | Copter | ✅ full (needs a Lua script, copied by ArgazUI) |
| Zephyr | Plane | ✅ full |
| Skywalker X8 | Plane | ✅ full |
| X-UAV Mini Talon | Plane | ✅ full |
| Weight-Shift Aircraft | Plane | ✅ full (via the RC2 neutral fix) |
| Alti Transition | VTOL | ✅ full |
| SkyCat TVBS | VTOL | ✅ full |
| Skywalker X8 Quad | VTOL | ✅ full |
| Swan-K1 Tailsitter | VTOL | ⚠ normal ARM fails — flies with **ARM (FORCE)** |

### Why is Swan-K1 different?

Its parameter file is a complete dump from a real flight controller and
contains several contradictions in SITL. Two of them are corrected via
`sitl_param_overrides` (it asks for `AHRS_EKF_TYPE=3` while leaving
`EK3_ENABLE=0`; compasses 2 and 3 do not exist in SITL and produce garbage).
The remaining `Check mag field` / `DCM Yaw inconsistent` warnings come from the
vehicle being a **tailsitter**: it stands nose-up on the ground, while the
compass/yaw checks assume a level airframe. Solving that properly requires
model-specific tailsitter configuration.

Practical route: **ARM (FORCE)** → QLOITER/GUIDED. Tested this way and the
vehicle flew (it climbed to 81 m for a 20 m target — that is how a tailsitter
GUIDED takeoff behaves).

### Other notes

- **AUTO**: without a loaded mission the autopilot will not stay in AUTO and
  falls back to RTL. Not a bug.
- **BiCopter mode names**: BiCopter flies with ArduCopter but reports itself as
  a Plane type, so MAVProxy shows Plane mode names
  (`SITL_Models/Gazebo/docs/BiCopter.md` documents this). ArgazUI picks the mode
  table from the registry's autopilot type rather than MAV_TYPE, so the buttons
  and the displayed mode are correct. But when typing commands to MAVProxy by
  hand in the SIMULATION terminal you must use the **Plane mode name**
  (Copter GUIDED = Plane ACRO, etc.; the table is in that document).
- **There is no `CIRCLE_RADIUS` parameter.** Copter uses `CIRCLE_RADIUS_M`
  (**metres**); Plane/VTOL has none at all — Plane's CIRCLE mode has no radius,
  and the radius-controlled circle is **LOITER** + `WP_LOITER_RAD` (**metres**).

---

## 10. Troubleshooting

### `ModuleNotFoundError: No module named 'uvicorn'`

Use **`./start.sh`** instead of `python3 -m argazui` (see section 1).

### Never use `pkill -f <name>`

In an earlier session a script running `pkill -f` matched its own command line
and killed itself. (The same mistake happened once more while building this
project: `pkill -TERM -f "argazui --port 8770"` closed the shell it ran in,
because that shell's own command line contained the pattern.)

ArgazUI therefore never matches on names:

- Terminals are opened in their own **session (SID)** via `start_new_session=True`.
- On STOP, `/proc` is scanned for the **process groups (PGID)** belonging to that
  session, which are then terminated with `os.killpg` in SIGINT → SIGTERM →
  SIGKILL order.
- Matching uses the SID/PGID reported by the kernel, so killing the wrong
  process is impossible.

If you need to stop it by hand, find it by port:

```bash
ss -lptn 'sport = :8770'
kill -TERM <pid>
```

### MAVLink never connects ("MAVLink: —" stays)

1. Read the errors in the SIMULATION tab (the most common cause is Gazebo not
   finding the world file → `GZ_SIM_RESOURCE_PATH`).
2. Another program may hold 14550: `ss -lunp | grep 14550`
3. STOP → START.

### ARM does not work

See section 5. In short: wait for **READY** to turn green; if that does not
help, read the autopilot message in the terminal; as a last resort use
**ARM (FORCE)**.

### The Gazebo window does not open / the GUI crashes

A known issue that `env.sh` solves (GTK/locale variables leaking from the VS Code
snap package). ArgazUI sources `env.sh` in every session. Start ArgazUI from a
normal terminal, not from a snap terminal.

### A script says "no heartbeat"

Scripts must use **14551**; 14550 belongs to the interface.

### A model behaves strangely

Delete its working directory and start fresh: `rm -rf argazui/run/<model_id>`
