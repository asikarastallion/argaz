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

The **EN / TR**, **DOCS**, **HOW TO USE** and **CONTACT** controls sit at the
top right (`Esc` closes the panels).

**DOCS** opens the engineering documentation portal: a tree down the left, a
search box that matches page titles *and* every heading inside them, and deep
links (`#docs=metrics`, `#docs=regression/exit-codes`) you can bookmark or
paste to somebody. Each page names the file in the repository it came from,
because the portal serves those files rather than holding a second copy of
them. Switch language from the top bar before opening it; a page with no
Turkish source shows the canonical English text with a note saying so.

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

Lists the `.py` files in your argaz root's `scripts/` folder (`scripts_root` in `argaz.toml`).
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
| `sitl_only` | `env.sh` + `sim_vehicle.py -v <vehicle> -f <frame>` and nothing else | none by default; add your own |

**RViz and the ROS 2/DDS bridge exist only for models launched via
`ros2_launch` (currently Iris only).** The panel reports "RViz/DDS: no" for the
rest.

### `sitl_only`: no Gazebo, no display

`sitl_only` runs the vehicle on **SITL's own built-in physics**. No Gazebo
process is started, no world is loaded, and MAVProxy runs without `--console`
and `--map` — so the whole thing works over SSH, in a container, or on a
machine with no graphics stack at all. Everything else is unchanged: the same
MAVLink ports, the same quick command buttons, the same procedures, the same
`runs/` artefacts.

Use it when:

* you are working on ArgazUI, a procedure or a mission script and the airframe
  is not the thing under test;
* the machine has no display (a remote box, CI);
* you want a vehicle in a few seconds rather than waiting for Gazebo.

Do **not** use it to conclude anything about a Gazebo model. The flight
dynamics are SITL's generic ones, not the model's; that is why the status
table's tier column exists.

One important detail, recorded because getting it wrong costs an hour of
confusion: this method must **not** pass `--model JSON` to `sim_vehicle.py`.
That flag tells SITL to take its physics from an external backend, so a vehicle
launched with it and no Gazebo waits forever and never sends a heartbeat — the
UI simply shows a model that never comes up.

Add one to `argazui/config/models.json` like this:

```json
{
  "id": "sitl_plane",
  "name": "SITL plane (no Gazebo)",
  "vehicle_class": "Plane",
  "method": "sitl_only",
  "env": "env.sh",
  "vehicle": "ArduPlane",
  "frame": "plane",
  "world": null,
  "param_file": null,
  "extra_sitl_args": [],
  "has_ros2": false
}
```

`frame` is any frame `sim_vehicle.py -f` accepts (`plane`, `quad`,
`quadplane`, `plane-tailsitter`, …). `param_file` and `extra_sitl_args` work
exactly as they do for the Gazebo methods.

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

| Port | Used by | Direction |
|---|---|---|
| **14550** | ArgazUI — quick command buttons and the status chips | ArgazUI listens |
| **14551** | **Your mission scripts** | your script listens |
| **14552** | Live telemetry mirror — see section 5d | ArgazUI **sends**, PlotJuggler listens |

Two listeners cannot share one UDP port, which is why they are split. 14552 is
the other way round: nothing in ArgazUI binds it, so whatever you point at it
gets the stream. Set `plotjuggler_port` in `argaz.toml` to move it, or to `0`
to switch the mirror off.

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

## 5c. Flight runs and the post-flight report

Every **START … STOP** writes one directory under `runs/`:

```
runs/20260802T103545Z_skywalker_x8/
├── scenario.yaml          the procedures that ran, verbatim
├── result.json            step-by-step pass/fail and the acceptance criteria
├── console.log            what the SIMULATION terminal showed
├── mavlink_events.jsonl   mode/arm/ACK/statustext + a 1 Hz state sample
├── 00000003.BIN           the autopilot's own dataflash log
├── params_full.txt        every parameter, read out of that log
├── params_diff.txt        the ones that differ from the firmware default
├── report.md / report.json  the post-flight report
├── plots/                 altitude and attitude PNGs (if matplotlib is installed)
└── versions.txt           ArduPilot SHA, Gazebo, ArgazUI, interpreter
```

`runs_root` in `argaz.toml` says where they go. The directory is gitignored:
it is the output of flying, not source.

**This is not `argazui/run/<model_id>/`.** That is still SITL's working
directory and it is *reused* by the next launch of the same model, so nothing
in it survives. Artefacts are copied out of it when the session stops.

**`params_diff.txt` really means "differs from default".** The autopilot logs
each parameter's firmware default next to its value (`PARM.Default`), so the
diff is the vehicle's own statement, not a comparison against whichever
`.param` file happened to be loaded. Parameters that are calibrated at boot
(`BARO*_GND_PRESS`) have no default and are listed separately.

**The report is generated after STOP**, on a background thread, from the
dataflash log. It gives the mode timeline, arm/disarm intervals, the altitude
profile, the demanded-vs-achieved roll and pitch error, EKF innovation test
ratios, vibration and clipping, and the battery — with every warning threshold
named and sourced. Nothing in it is measured over telemetry; the log is the
autopilot's full-rate record of itself.

In the interface the **Flight Runs** panel lists them: a result badge, the
report in-app with its plots, a `.BIN` download, and a button that copies the
`MAVExplorer.py <path>` command to the clipboard. `#run=<run_id>` in the URL
opens one directly.

From the shell:

```bash
python3 -m argazui runs                    # list every recorded run
python3 -m argazui report                  # rebuild the newest run's report
python3 -m argazui report some/other.BIN   # analyse any dataflash log
```

The last form works on a log from a real flight controller too — it does not
need a run directory.

---

## 5c-2. Comparing a run against a baseline

The report says what one flight did. It cannot see the thing that actually
happens over months: every acceptance criterion still passes while the aircraft
gets quietly worse at flying — the climb takes four seconds longer, tracking
error creeps up, a mode change that used to confirm in 100 ms now takes two
seconds.

So a run's **metrics** can be compared against a named baseline.

In the browser: open a run's report and press **⇄ compare with the previous
run**. It compares against the newest earlier run of the same model and writes
`regression.json` and `regression.md` into the run's directory.

From the shell, which is what CI should use:

```bash
python3 -m argazui compare runs/<current> --baseline runs/<baseline>
```

| exit | meaning |
|---|---|
| `0` | no metric degraded past its threshold |
| `1` | at least one did — the regression signal |
| `2` | the two runs could not be compared, or could not be read |

**Two runs are not comparable just because they exist.** A different model or a
different set of procedures is refused outright. A changed procedure, model
configuration, ArduPilot commit or firmware makes the comparison
`incomparable` and names the field that changed; `--ignore-config-drift`
compares anyway and still reports what differed. Nothing is ever compared
silently — see [docs/regression.md](../docs/regression.md) and
[docs/metrics.md](../docs/metrics.md).

Metrics are measurements, not acceptance criteria. A regression does not mean a
criterion failed; it means the aircraft is doing the same thing measurably less
well than the baseline did.

## 5d. Live telemetry in PlotJuggler

The report in section 5c is what you read *after* a flight. This is how you
watch one happen: while a vehicle is running, ArgazUI mirrors its telemetry to
a loopback UDP port that [PlotJuggler](https://plotjuggler.io) can plot in real
time. Nothing is bundled and nothing is launched for you — ArgazUI only opens
the port.

### Connecting

1. Press **▶ START** and wait for the link. The **LIVE PLOT** line under Quick
   Commands shows the address and port as two separate values, each with its
   own **⧉** copy button, plus a running count of the messages that have left
   the mirror.
2. In PlotJuggler: **Streaming → UDP Server → Start**.
3. In the dialog, three separate boxes:

   | Box | Value |
   |---|---|
   | **Address** | `127.0.0.1` — **a bare host. Not `127.0.0.1:14552`, and not blank.** |
   | **Port** | `14552` |
   | **Message Protocol** | `JSON` |

4. Drag any series from the left-hand tree onto a plot.

### If you see "Couldn't bind to IPv4 UDP server"

> ⚠ **Do not press OK on that dialog.** Close it with the window **✕**, or press
> **Stop** and reconnect with `127.0.0.1` in the Address box.

This is the one trap in the whole feature, and it is worth stating exactly
because the symptom is the opposite of the cause. If **Address** contains
anything that is not a bare IP — `127.0.0.1:14552`, or an empty box —
PlotJuggler pops:

```
Couldn't bind to IPv4 UDP server at (127.0.0.1:14552, 14552)
```

**It is a false alarm.** The socket bound fine and is already receiving: the
Timeseries List behind the dialog fills up and the values update while it sits
there. Verified against PlotJuggler 3.17.2, and against its source
(`plotjuggler_plugins/DataStreamUDP/udp_server.cpp`), the sequence is:

```cpp
QHostAddress address(address_str);      // "127.0.0.1:14552" -> a null address
bool success = true;
success &= !address.isNull();           // ...so success is already false here
success &= _udp_socket->bind(address, port);   // but THIS succeeds: null means "any"
connect(_udp_socket, &QUdpSocket::readyRead, this, &UDP_Server::processMessage);
if (success) { /* "IPv4 UDP listening on ..." */ }
else { QMessageBox::warning(... "Couldn't bind to IPv%4 UDP server ..."); shutdown(); }
```

`readyRead` is connected before `success` is ever consulted, and a modal
`QMessageBox` runs a nested event loop — which is why the data keeps arriving
while the dialog is open. **Pressing OK is what breaks it**: the message box
returns, `shutdown()` runs, and the working socket is destroyed. The dialog is
reporting the text you typed, not the state of the socket.

Nothing on ArgazUI's side is involved — the bind and that flag both happen
before the first datagram is read.

The port is open only while a vehicle is running. It opens when you press START
and closes when you press STOP, so a stale PlotJuggler session simply stops
receiving rather than showing an old flight's numbers.

### What arrives

One JSON object per MAVLink message, exactly as the interface received it:

```json
{"t":1785836917.799614,"ATTITUDE":{"time_boot_ms":2494,"roll":0.000182,"pitch":0.000034,"yaw":0.0000005,"rollspeed":0.0000074,"pitchspeed":0.000083,"yawspeed":0.000025}}
```

PlotJuggler flattens that into one series per field, named after the message it
came from — `ATTITUDE/roll`, `VFR_HUD/alt`, `SYS_STATUS/voltage_battery`,
`VIBRATION/vibration_x`, and so on. A measured ArduCopter session produced 34
message types and roughly 250 series, at about 130 datagrams (26 KB) per second
of flight.

`t` is the wall-clock time ArgazUI received the message, which is also what
PlotJuggler uses for the X axis by default, so no options need setting. Vehicle
timestamps (`time_boot_ms`, `time_usec`) are still there as ordinary fields.

Two kinds of field are deliberately not sent: text (`STATUSTEXT.text`,
`PARAM_VALUE.param_id` — nothing plots a string, and they are already in
`mavlink_events.jsonl`), and `NaN`/infinity, which ArduPilot really does put in
unpopulated fields. The second matters more than it looks: `NaN` is not valid
JSON, and PlotJuggler answers a message it cannot parse by **stopping the
stream**, so one of them would end the live plot rather than spoil one point.

### Why JSON and not MAVLink

Because PlotJuggler has no MAVLink plugin. Its live data sources are UDP
Server, WebSocket, ZMQ, MQTT, serial and ROS 2, and its parsers are
JSON/CBOR/BSON/MessagePack, Protobuf, ROS and InfluxDB line protocol.
ArduPilot's own PlotJuggler plugin,
[plotjuggler-apbin-plugins](https://github.com/ArduPilot/plotjuggler-apbin-plugins),
loads **dataflash `.BIN` files** — offline, after the flight, and a different
job from this one.

If you want *raw* MAVLink somewhere else — QGroundControl, a second script —
that already exists and does not need this feature: add another
`--out 127.0.0.1:<port>` to the `sim_vehicle.py` line, which is exactly how
14551 is made.

### Türkçe: PlotJuggler ile canlı telemetri

Bir araç çalışırken ArgazUI, telemetriyi yerel bir UDP portuna aynalar ve
PlotJuggler bunu anlık olarak çizer. ArgazUI PlotJuggler'ı başlatmaz, sadece
portu açar.

**Bağlanmak için:**

1. **▶ BAŞLAT**'a bas ve bağlantıyı bekle. Hızlı Komutlar'ın altındaki
   **CANLI GRAFİK** satırı adresi ve portu ayrı ayrı, her biri kendi **⧉**
   kopyalama düğmesiyle gösterir; yanında aynadan çıkan mesaj sayısı vardır.
2. PlotJuggler'da: **Streaming → UDP Server → Start**.
3. Açılan pencerede üç ayrı kutu var:

   | Kutu | Değer |
   |---|---|
   | **Address** | `127.0.0.1` — **yalnızca host. `127.0.0.1:14552` değil, boş da değil.** |
   | **Port** | `14552` |
   | **Message Protocol** | `JSON` |

4. Soldaki ağaçtan istediğin seriyi grafiğe sürükle.

#### "Couldn't bind to IPv4 UDP server" uyarısını görürsen

> ⚠ **O pencerede OK'a basma.** Pencereyi **✕** ile kapat ya da **Stop** deyip
> Address kutusuna `127.0.0.1` yazarak yeniden bağlan.

Bu özelliğin tek tuzağı bu ve belirti sebebin tam tersi göründüğü için açıkça
yazıyoruz. **Address** kutusunda düz bir IP dışında bir şey varsa —
`127.0.0.1:14552` ya da boş kutu — PlotJuggler şunu gösterir:

```
Couldn't bind to IPv4 UDP server at (127.0.0.1:14552, 14552)
```

**Bu yanlış alarmdır.** Soket aslında açıldı ve veri geliyor: pencere açık
dururken arkadaki Timeseries List dolar ve değerler güncellenir. PlotJuggler
3.17.2 üzerinde ve kaynağında
(`plotjuggler_plugins/DataStreamUDP/udp_server.cpp`) doğrulandı: `readyRead`
sinyali, `success` bayrağına bakılmadan ÖNCE bağlanıyor ve modal `QMessageBox`
iç içe bir olay döngüsü çalıştırıyor — veri bu yüzden akmaya devam ediyor.
**Akışı bozan şey OK'a basmaktır**: mesaj kutusu kapanınca `shutdown()`
çalışıyor ve çalışan soket yok ediliyor. Uyarı, soketin durumunu değil, senin
yazdığın metni bildiriyor.

ArgazUI tarafında bir sorun yok — bind de o bayrak da ilk paket okunmadan önce
oluyor.

Port yalnızca bir araç çalışırken açıktır: BAŞLAT ile açılır, DURDUR ile
kapanır. Böylece açık kalmış bir PlotJuggler oturumu eski bir uçuşun
değerlerini göstermeye devam etmez, sadece veri almayı keser.

**Ne gelir:** Her MAVLink mesajı bir JSON nesnesi olarak gider ve PlotJuggler
bunu alan başına bir seriye açar — `ATTITUDE/roll`, `VFR_HUD/alt`,
`SYS_STATUS/voltage_battery` gibi. Ölçülen bir ArduCopter oturumunda 34 mesaj
tipi ve yaklaşık 250 seri, uçuş saniyesi başına yaklaşık 130 paket (26 KB)
çıktı. `t` alanı ArgazUI'nin mesajı aldığı duvar saati zamanıdır ve
PlotJuggler'ın varsayılan X eksenidir; ayar yapman gerekmez.

Metin alanları (`STATUSTEXT.text` gibi) ve `NaN`/sonsuz değerler bilinçli
olarak gönderilmez. İkincisi önemli: `NaN` geçerli JSON değildir ve PlotJuggler
ayrıştıramadığı bir mesajda **akışı durdurur** — yani tek bir NaN, tek bir
noktayı değil bütün canlı grafiği bitirirdi.

**Neden MAVLink değil de JSON?** PlotJuggler'ın MAVLink eklentisi yok; canlı
kaynakları UDP Server, WebSocket, ZMQ, MQTT, seri port ve ROS 2, ayrıştırıcıları
ise JSON/CBOR/BSON/MessagePack, Protobuf, ROS ve InfluxDB satır protokolü.
ArduPilot'un kendi PlotJuggler eklentisi dataflash `.BIN` dosyalarını okur —
uçuştan sonra, çevrimdışı; bu ayrı bir iş. Ham MAVLink'i başka bir yere
(QGroundControl, ikinci bir script) göndermek istersen bu özelliğe gerek yok:
`sim_vehicle.py` satırına bir `--out 127.0.0.1:<port>` daha ekle — 14551 de
tam olarak böyle üretiliyor.

### Not covered by any test

That PlotJuggler actually draws the graph. A tier-1 test starts a real SITL,
binds the mirror port and asserts that a `HEARTBEAT` arrives as valid JSON and
that the port closes with the session — but nothing automated in this project
can look at a rendered window. That step is in
[docs/manual-checklist.md](../docs/manual-checklist.md), marked ✗.

---

## 6. Adding a mission script

1. Drop your `.py` file into the `scripts/` folder of your argaz root
   (`scripts_root` in `argaz.toml`).
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

If you need to stop it by hand, this one line finds it by port and stops it —
copy the whole line, it needs no editing:

```bash
pid=$(ss -ltnpH 'sport = :8770' | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1) && kill -TERM "${pid:?nothing is listening on port 8770}"
```

Easier still, `./start.sh --replace` does the same thing and then starts a
current server in its place.

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
