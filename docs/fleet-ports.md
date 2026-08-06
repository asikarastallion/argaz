# The SITL port map, measured

**This file is measurement, not documentation of intent.** Every number below
was observed on this machine by launching real SITL binaries and watching what
they bound, sent to and printed. Where the v1.3 architecture note guessed
differently, the measurement wins and the difference is called out.

    measured   2026-08-05
    ArduPilot  ArduPilot-4.6.0-beta1-7768-g0b38722bd5 @ 0b38722bd5a4
    binary     ardupilot/build/sitl/bin/arducopter
    host       Linux 7.0.0-28-generic, 16 cores
    method     scratch scripts: 3 instances at -I 0/1/2, `ss -lntup` per PID,
               SITL stdout, and a fake Gazebo bound to each FDM port

---

## The map

For instance `i` (`-I i`):

| Resource | Port | Who **binds** it | Who **sends** to it | Verified |
|---|---|---|---|---|
| SITL SERIAL0 (TCP) | `5760 + 10*i` | **SITL** | fleet router | yes — 5760 / 5770 / 5780 |
| FDM servo out | `9002 + 10*i` | **Gazebo** (`ArduPilotPlugin`) | SITL | yes — 9002 / 9012 / 9022 |
| FDM state return | *ephemeral* | SITL (implicitly) | Gazebo | yes — see below |
| RC in | `5501 + 10*i` | SITL, on demand | external RC | from source only |
| FlightGear view | `5503 + 10*i` | SITL, on demand | — | from source only |
| IRLock | `9005 + 10*i` | SITL, on demand | — | printed at boot |

Observed directly:

```
-I0  pid 187641   TCP listen 0.0.0.0:5760   JSON control interface set to 127.0.0.1:9002
-I1  pid 187642   TCP listen 0.0.0.0:5770   JSON control interface set to 127.0.0.1:9012
-I2  pid 187643   TCP listen 0.0.0.0:5780   JSON control interface set to 127.0.0.1:9022
```

The 10-per-instance stride is real and it is applied by ArduPilot itself, in
`libraries/AP_HAL_SITL/SITL_cmdline.cpp` under `case 'I'`. **Nothing has to be
passed to get it.**

---

## Four things the architecture note got wrong

### 1. There is no `9003 + 10*i` in the JSON FDM path

The note lists "FDM out `9003 + 10*i`, consumer: SITL". That port is not used.

`SIM_JSON.cpp` takes both ports and then ignores the inbound one:

```cpp
void JSON::set_interface_ports(const char* address, const int port_in, const int port_out)
{
    ...
    control_port = port_out;      // port_in is never stored
}
```

There is **one** unbound UDP socket (`SocketAPM sock`). SITL `sendto()`s the
servo packet, which makes the kernel assign an ephemeral source port, and
`recv()`s the state back on that same socket. Measured source ports across
runs: 52975, 59226, 33563, 51986, 44121 — different every time.

The Gazebo plugin learns where to reply rather than being told:

```cpp
_sock.get_client_address(_fcu_address, _fcu_port_out);   // ArduPilotPlugin.cc:1434
...
this->dataPtr->sock.sendto(json_str.c_str(), json_str.size(),
                           fcu_address, fcu_port_out);   // :2031
```

**Consequence for L1:** only **one** FDM port per vehicle is a resource to be
allocated and lease-checked — `9002 + 10*i`, and it is bound by *Gazebo*, not
by SITL. The allocator must not reserve `9003 + 10*i` for anything; doing so
would be reserving a port nothing ever uses.

**Consequence for L2:** the materialised `model.sdf` needs **`fdm_port_in`
patched and nothing else**. `fdm_addr` is only the plugin's *bind* address
(`sock.bind(fdm_address, fdm_port_in)`, `ArduPilotPlugin.cc:1286`) and stays
`127.0.0.1`. The reply path is discovered, so there is nothing there to patch.

### 2. `-I` does **not** set the sysid

Three instances, no sysid argument:

```
tcp:5760  heartbeat sysid=1
tcp:5770  heartbeat sysid=1
tcp:5780  heartbeat sysid=1
```

All three claim to be vehicle 1. A fleet built on the assumption that `-I`
separates identities would have three vehicles fighting over one address, and
the "no `sysid=0` broadcast" rule would not save it — every command would be
correctly addressed to system 1 and arrive at all three.

Passing `--sysid` explicitly does work:

```
tcp:5760  heartbeat sysid=1   MAV_SYSID=1.0
tcp:5770  heartbeat sysid=2   MAV_SYSID=2.0
tcp:5780  heartbeat sysid=3   MAV_SYSID=3.0
```

SITL validates the range itself (`SITL_cmdline.cpp:565`: "You must specify a
SYSID greater than 0 and less than 256"), which is the same 1–255 rule the
fleet spec states. `sim_vehicle.py --auto-sysid` computes `instance + 1`; the
fleet spec declares sysids instead, which is stricter and better.

**The parameter has been renamed.** It is `MAV_SYSID`, not `SYSID_THISMAV`.
The old name is a conversion-table entry only (`ArduCopter/Parameters.cpp:1313`,
with `// SYSID_THISMAV was here` at line 41). A `--defaults` file containing
`SYSID_THISMAV,3` is silently ignored — measured: the vehicle still reported
sysid 1. Anything in v1.3 that reads or writes a vehicle's sysid by parameter
name must use `MAV_SYSID`.

### 3. SITL blocks at boot until something connects to SERIAL0

The default SERIAL0 device is `tcp:0:wait` (`SITL_State.h:30`). The `wait` is
part of the default, and it means what it says:

```
[default]  no FDM traffic in 18 s -> blocked waiting for a GCS
           last line: Waiting for connection ....
```

Until a TCP client connects to `5760 + 10*i`, SITL does not load parameters,
does not set home, and does not send a single servo packet. Adding
`--serial0 tcp:0` removes the wait:

```
[nowait]   servo packet after 0.0s from ('127.0.0.1', 44121) -> boots without a GCS
           last line: Home: -35.363262 149.165237 alt=584.000000m hdg=353.000000
```

**Consequence for L3.** With the default, the readiness gates are not
independent: a vehicle only *starts* when the router attaches, so "N vehicles
launched" and "N vehicles running" are different states separated by the
router's own progress. Worse, under lockstep a vehicle that never got a
connection never returns an FDM packet, and **the whole world's sim time
stops** — one unattached link stalls every other vehicle.

So the fleet supervisor launches with `--serial0 tcp:0`. Each vehicle boots on
its own, the FDM handshake begins as soon as Gazebo is listening, and the
router attaches whenever it is ready. This changes nothing about the
single-vehicle path, which goes through `sim_vehicle.py` and gets MAVProxy's
connection immediately.

### 4. Explicit port overrides are order-sensitive, and dangerously so

The `-I` handler only applies its offset when the value is still at the
compiled-in default:

```cpp
case 'I': {
    _instance = atoi(gopt.optarg);
    if (_base_port == BASE_PORT)             { _base_port += _instance * 10; }
    if (simulator_port_in == SIM_IN_PORT)    { simulator_port_in += _instance * 10; }
    if (simulator_port_out == SIM_OUT_PORT)  { simulator_port_out += _instance * 10; }
    ...
}
```

Two traps follow, and ArduPilot's own help text admits the first
("`--base-port PORT` ... must be before -I option" — the comment is inverted
relative to the code, which is its own warning):

* **Order matters.** `--sim-port-out 9012 -I 1` leaves the port at 9012;
  `-I 1 --sim-port-out 9012` also gives 9012, but by a different route. Mixing
  the two styles across a fleet is how one vehicle silently ends up on
  another's port.
* **An explicit value equal to the default is not treated as explicit.**
  `--sim-port-out 9002 -I 1` yields **9012**, not 9002, because the guard
  compares against `SIM_OUT_PORT` and cannot tell "still default" from
  "deliberately set to the default value".

**Consequence for L1:** the allocator derives every port from `-I` and passes
no port overrides at all. It is the only style with no ordering hazard, and it
is what upstream tests. If a future need forces an override, it must come
*after* `-I` on the command line and never equal the compiled-in default.

---

## What this means for the allocator

1. **One resource per vehicle needs a lease: the instance number `i`.** Every
   port follows from it. Leasing ports individually would model a freedom that
   does not exist.
2. **Two ports must be probed before committing to an `i`:**
   `5760 + 10*i` (will SITL be able to bind it?) and `9002 + 10*i` (will
   Gazebo?). Both were verified to refuse a second binder:

   ```
   bind TCP 127.0.0.1:5760 -> refused (98 Address already in use)
   bind TCP 0.0.0.0:5760   -> refused (98 Address already in use)
   ```

   Probing either address detects a live SITL, so the probe may use
   `127.0.0.1` and stay consistent with the rest of the project.
3. **SITL binds SERIAL0 on `0.0.0.0`, not loopback.** Observed:
   `TCP listen 0.0.0.0:5760`. Every vehicle's control port is reachable from
   the network for as long as the fleet runs. ArgazUI is a localhost-only tool
   and this is ArduPilot's behaviour rather than something v1.3 introduces, but
   it belongs in the README's limitations rather than being discovered later.
4. **A lease is only meaningful with a PID.** Nothing binds `9002 + 10*i`
   until Gazebo starts, so a free probe there does not mean the instance is
   unused — an allocated-but-not-yet-started vehicle looks identical to a free
   one. `ports.json` records the owning PID and stale entries are reclaimed by
   liveness, exactly as the architecture requires.

## What is still unmeasured

* Whether `gz sim` honours a plugin parameter override inside `<include>`, and
  whether `gz service .../create` can spawn a model with a patched
  `fdm_port_in` at runtime. **Phase 2**, into `docs/fleet-world-composition.md`.
* Lockstep behaviour with more than one FDM attached to one `gz sim` server,
  and what the stall signature looks like per vehicle. **Phase 3 / 5.**
* Whether instance numbers above 2 behave identically. The stride is
  arithmetic in the source and there is no table, so 8 vehicles should be
  8 × 10; not yet observed.

## Reproducing this

The measurement scripts are not committed — they launch real binaries and
belong to the investigation, not the product. The three that produced the
numbers above did this:

1. Launch `arducopter --model quad|JSON --speedup 1 -I<i> -w --defaults <frame defaults>`
   for `i` in 0,1,2, each in its own working directory, `start_new_session=True`.
2. Read `ss -lntp` / `ss -lunp`, filter by the PIDs, and read each instance's
   `sitl.log` for `JSON control interface set to`.
3. Bind a UDP socket to `9002 + 10*i` before launching to stand in for Gazebo,
   and record the source address of the first servo packet.
4. Attach `pymavlink` to `tcp:127.0.0.1:5760 + 10*i` and read the heartbeat's
   `srcSystem` and `MAV_SYSID`.

Teardown was `os.killpg` on each process group. No `pkill`. After every run,
`pgrep arducopter` was empty and no port in 5760–5790 or 9002–9030 was held.
