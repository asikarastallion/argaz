# Composing a fleet world, measured

**Every number and every verdict here came from running the thing on this
machine.** Where the v1.3 architecture note guessed, the measurement wins and
the difference is stated. Three of its instructions turned out to be wrong;
one of them would have produced a fleet that looked correct on screen while
every separation reading was fiction.

    measured   2026-08-05
    Gazebo     Sim 8.14.0 (Harmonic), SDFormat as shipped with it
    plugin     ardu_ws/src/ardupilot_gazebo (libArduPilotPlugin.so)
    ArduPilot  ArduPilot-4.6.0-beta1-7768-g0b38722bd5 @ 0b38722bd5a4
    models     iris_with_ardupilot (probes), hexapod_copter (the gate run)

---

## 1. The question that gates everything: what is position relative to?

If `ArduPilotPlugin` reports the vehicle's pose **relative to its own spawn
point**, every vehicle in a fleet reports `(0, 0)` and each SITL must be given
its own offset home or they all believe they are in the same place. If it
reports pose **relative to the world origin**, the Gazebo `<pose>` already
carries the offset and giving SITL an offset home as well counts it twice.

Both mistakes are invisible: Gazebo draws the vehicle where the `<pose>` says
regardless, so the picture looks right either way and only the numbers lie.

### The experiment

One `iris_with_ardupilot`, spawned twice in an otherwise identical world —
once at the origin, once 10 m east — with an identical SITL command line, then
asked where it thought it was. Repeated with and without a
`<spherical_coordinates>` block to separate two variables at once.

| world | Gazebo `<pose>` | SITL lat | SITL lon | `LOCAL_POSITION_NED` east |
|---|---|---|---|---|
| no `spherical_coordinates` | `0 0 0.2` | -35.3632621 | 149.1652374 | 0.000 |
| no `spherical_coordinates` | `10 0 0.2` | -35.3632621 | 149.1653475 | **9.995** |
| with `spherical_coordinates` | `0 0 0.2` | -35.3632621 | 149.1652374 | 0.000 |
| with `spherical_coordinates` | `10 0 0.2` | -35.3632621 | 149.1653475 | **9.995** |

### The answer

**Position is relative to the Gazebo world origin.** The 10 m offset appears
in what SITL believes, at 9.995 m of a commanded 10.000 m.

This is what the source says too, once you know where to look — the plugin
reads the IMU link's *world* pose, not a pose relative to the model:

```cpp
const gz::sim::components::WorldPose* worldPose =
    _ecm.Component<gz::sim::components::WorldPose>(this->dataPtr->imuLink);
...
gz::math::Pose3d wldGToBdyG = worldPose->Data();          // ArduPilotPlugin.cc:1833
```

### What follows, and it is the opposite of the brief

> The architecture note says: *"SITL home is set via `--custom-location`,
> derived from `[fleet.origin]` plus the ENU offset."*

That is wrong, and the failure it produces is the quiet kind. **Every vehicle
in a fleet gets the SAME home — the fleet origin.** The per-vehicle ENU offsets
go into the Gazebo `<pose>` and nowhere else.

Adding the offset to home as well puts vehicle 2 at twenty metres when the
world places it at ten. Gazebo still draws it at ten. The separation monitor,
reading MAVLink, would report distances that do not match the picture, and the
acceptance criterion built on it would be measuring nothing real.

Implemented as `world.home_for(spec)`, which deliberately takes the *fleet*
and not a vehicle, so there is no signature that would let a caller offset it
per vehicle by accident.

### Verified end to end

The 3-vehicle gate run (§5) launched all three SITLs with one identical
`--home` and each reported its own distinct, correct position:

```
v1: sysid=1  east/north=(-5.0,  5.0)   want (-5.0,  5.0)   OK
v2: sysid=2  east/north=( 4.99, 5.0)   want ( 5.0,  5.0)   OK
v3: sysid=3  east/north=(-5.0, -5.0)   want (-5.0, -5.0)   OK
```

---

## 2. `<spherical_coordinates>`: emitted, and honest about what it does not do

`hexapod_copter_runway.sdf` declares no datum at all. The composer emits one,
derived from `[fleet.origin]`, so the generated world is self-describing and
cannot disagree with the spec that produced it.

**It does not change where SITL thinks the vehicle is.** The table in §1 is the
baseline comparison: with and without the block, the same vehicle at the same
pose reported the identical latitude, longitude and NED east to every digit.
That is the finding, and it is worth more than the convenience — the datum is
documentation for Gazebo's own consumers (the GUI, `ros_gz` bridges, future
sensor plugins), not part of the path that positions the aircraft. The path
that positions the aircraft is: plugin reports a local offset from the world
origin → SITL adds it to its `--home`.

So the block is emitted for self-description, and nothing downstream is
allowed to depend on it for position.

---

## 3. Three composition approaches. One is a trap.

The problem: `ardupilot_gazebo` model SDFs carry `<fdm_port_in>9002</fdm_port_in>`
*inside the model*, so including one model four times gives four plugins all
wanting 9002.

Judged by one question — **which UDP ports does the `gz` process actually
bind** — because that is the only observable that distinguishes working from
broken here.

### Control: two unpatched copies

```
fdm_ports_bound: [9002]        two vehicles, ONE port
bind failures:   none
errors:          none
```

Both plugins bound 9002 and nothing complained. `SocketUDP` is constructed as
`SocketUDP(true, true)` (`ArduPilotPlugin.cc:227`) — the first `true` is
`reuseaddress`, and on Linux that lets a second UDP bind of the same address
succeed. **A port collision here produces no error, no log line and no failed
bind.** Detecting it is the allocator's job alone; nothing downstream will.

### A — `<plugin>` override inside `<include>`: **REJECTED**

The elegant one. First test looked like a success:

```
v1 override -> 9002,  v2 override -> 9012
fdm_ports_bound: [9002, 9012]        looks correct
```

It is not correct. That result only looked right because v1's override value
happened to equal the built-in default. Re-run with override ports that
exclude 9002:

```
v1 override -> 9012,  v2 override -> 9022
fdm_ports_bound: [9002, 9012, 9022]  <-- 9002 is STILL BOUND
```

**The `<include><plugin>` block ADDS a second `ArduPilotPlugin` rather than
replacing the model's own.** Every vehicle keeps a plugin on 9002 in addition
to the one on its assigned port, and those extra plugins all share 9002 —
silently, per the control result. One SITL's servo stream would drive every
vehicle's shadow plugin.

This is the most dangerous of the three precisely because it looks like it
works, and because the obvious way to test it (override the first vehicle to
the default port) hides the defect.

### B — per-vehicle materialisation into the run directory: **KEPT**

Copy the model directory to `runs/<run_id>/models/<vehicle_id>/`, patch it,
prepend that directory to `GZ_SIM_RESOURCE_PATH`.

```
fdm_ports_bound: [9002, 9012]        exactly the two allocated
```

**Only `fdm_port_in` is patched.** `fdm_addr` is the plugin's *bind* address
(`sock.bind(fdm_address, fdm_port_in)`, `ArduPilotPlugin.cc:1286`) and stays
`127.0.0.1`; the reply path is not configured at all — the plugin learns
SITL's address from the first packet (`get_client_address`, line 1434), and
SITL's FDM socket is unbound with an ephemeral source port. See
`docs/fleet-ports.md`.

Two further edits are required and one of them is easy to miss:

* **`<model name=>`** → the vehicle id, or two copies collide by name.
* **`<imuName>`** → re-namespaced. `iris_with_ardupilot` declares
  `<imuName>iris_with_standoffs::imu_link::imu_sensor</imuName>` — prefixed
  with the *original* model name. Renaming the model without fixing this
  leaves the plugin resolving a sensor that no longer exists, and it *still
  binds its port and still logs nothing*. The failure would present as "the
  vehicle does not respond".

  Not every model does this: `hexapod_copter` declares
  `<imuName>imu_link::imu_sensor</imuName>` with no prefix. The patcher
  rewrites the prefix only when it matches the original model name, so both
  conventions are handled and neither is corrupted.

### C — runtime spawn via `gz service .../create`: works, not used in v1.3

```
before spawn: (no FDM ports)
gz service -s /world/compose/create ... -> data: true
after spawn:  9012
errors:       none
```

It works. But it spawns a *materialised* model — the SDF handed to it still
needs its `fdm_port_in` patched — so **C is not an alternative to B, it is a
different way to place what B produces.**

B is kept because:

* the generated `fleet.sdf` is itself the reproducibility artefact the run
  directory has to contain, and a world assembled by a sequence of runtime
  service calls leaves no such file;
* every vehicle exists before physics starts, so lockstep is consistent from
  the first step rather than acquiring a new FDM participant mid-run.

C is recorded as the path for adding a vehicle to a running fleet, which v1.3
does not do.

---

## 4. ENU → LLA

```
lat = lat0 + north_m / M
lon = lon0 + east_m  / (M * cos(lat0))
alt = alt0 + up_m
```

`M = 111318.845 m/deg`, taken from ArduPilot's own `LATLON_TO_M`
(`libraries/AP_Math/definitions.h`: `0.011131884502145034` m per 1e-7 degree).

The first version used the familiar `111320` while the docstring claimed to
match ArduPilot. It does not — the difference is about 0.1 mm over 10 m, far
too small to matter and exactly the sort of unearned claim worth removing.
Using the autopilot's constant makes the sentence true.

**Round trip** closes to floating-point exactness (the transform is linear);
tested over ±500 m at under 0.1 m as required.

**Cross-checked against a great circle**, so the test proves more than that the
inverse was typed correctly. The two disagree by a *constant* 0.112% of
distance — 1.1 cm at 10 m, 11 cm at 100 m — because `haversine_m` uses a
spherical mean radius (6371 km) and the conversion uses ArduPilot's constant.
Those are different earth models, not an error in either. The test pins the
*linearity* of the divergence, which is what distinguishes a scale choice from
a curvature bug that happens to be small nearby.

**Validated against a real vehicle:** predicted longitude for 10 m east was
149.1653472; the vehicle reported 149.1653475, about 3 cm apart.
`LOCAL_POSITION_NED` is relative to the EKF origin while `GLOBAL_POSITION_INT`
is the EKF's absolute estimate fused from a *simulated GPS that has noise in
it*, so there is no reason for those to agree to the centimetre. The test is
held to a stated 0.5 m tolerance rather than demanding the GPS be noiseless.

---

## 5. The gate run

The actual composer, the actual Phase-5 model, three vehicles, one Gazebo:

```
allocation:
   v1: -I0 serial0=5760 fdm=9002 sysid=1
   v2: -I1 serial0=5770 fdm=9012 sysid=2
   v3: -I2 serial0=5780 fdm=9022 sysid=3
removed base includes: ['model://hexapod_copter']

1) FDM ports bound by gz : [9002, 9012, 9022]     (expected the same)
2) sysids as declared    : 1, 2, 3
3) positions             : (-5,5) (4.99,5) (-5,-5)  distinct, match spawns
4) per-model pose        : gz model -m v1|v2|v3 --pose all readable
orphan SITLs after teardown: 0
```

Note (3): the base world's own `hexapod_copter` include was removed and
replaced by the fleet, and each vehicle reported **its own** spawn point. That
is already a cross-wiring check at rest — if v2's SITL were wired to v1's
model it would have reported v1's position.

---

## 6. The cross-wiring hole, and the check that closes it

The allocator prevents an FDM *port* collision before launch. It cannot
prevent a *mis-wiring*: the plugin learns its reply address from whoever sends
to it first, so if vehicle 1's SITL were pointed at vehicle 2's port, the pair
would run happily with vehicle 1's servos driving model 2. Nothing in the port
map, the lease file or the SDF would show it.

§5 closes the static half. The dynamic half needs motion, and the primitive it
depends on is verified above: `gz model -m <name> --pose` returns one named
model's pose.

**Implemented and passing** (`fleet/wiring.py`, exercised by
`tests/test_fleet_gazebo.py`). Real output from a three-vehicle run:

```
v1: moved 8.011 m,  others {v2: 0.006, v3: 0.000}
v2: moved 7.995 m,  others {v1: 0.018, v3: 0.002}
v3: moved 7.995 m,  others {v1: 0.011, v2: 0.011}
-> 3 vehicles each moved their own model and nobody else's
```

Three orders of magnitude between the commanded vehicle and every other one.
That margin is what makes the check worth running: a mis-wire is not a
borderline reading.

Two things had to be corrected before it was trustworthy, and both were the
check accusing an innocent fleet:

* **The noise band cannot be a constant.** A fixed 0.30 m limit reported a
  mis-wire because a vehicle still hovering from its own earlier check drifted
  0.47 m while station-keeping — real movement, caused by the aircraft holding
  position rather than by anyone's command. The band is now derived from a
  measured floor: every model's movement over the same window with no command
  given. An idle model on the ground still has a floor near zero, so a genuine
  mis-wire that moved it metres is caught exactly as before.
* **The settle cannot be a fixed wall-clock wait.** At three vehicles the
  world runs at ~0.6x, so an 8 s window is under 5 s of vehicle time; a
  vehicle climbed only 0.84 m and was read as possibly mis-wired. The move
  function now waits on the vehicle's own altitude, which makes the check
  independent of simulation rate.

The original design:

1. With the fleet armed and holding, record every model's Gazebo pose.
2. Command **exactly one** vehicle to move — a small position change with an
   unambiguous signature, e.g. a 2 m altitude step in GUIDED.
3. Re-read every model's pose.
4. Assert the commanded model's pose changed by the expected amount **and
   every other model's pose did not change beyond a noise band**.
5. Repeat per vehicle. N commands, N assertions, no shared state.

It is cheap — one command and two pose reads per vehicle — and it is the only
evidence that N SITLs are wired to N models rather than to each other. It runs
once at `FLEET READY`, before any acceptance criterion is evaluated, so a
mis-wired fleet fails at bring-up instead of producing a plausible-looking
separation trace.

Failure is a fleet-level abort, not a warning: every measurement taken after a
mis-wire is meaningless, and a report that averaged them would be worse than
no report.

---

## 7. What is still unmeasured

* Lockstep with three FDM participants under load, and what the stall
  signature looks like per vehicle. **Phase 3 / 5.**
* Whether the composed world holds together for the full flight envelope —
  the gate run verified placement and wiring at rest, not a takeoff.
* `hexapod_copter`'s Lua script is copied per vehicle into each working
  directory; that path was exercised at bring-up but no vehicle has yet flown
  on it. **Phase 5.**
* Tier-2 has not been run on this machine for `hexapod_copter`; the gate run
  used `allow_unverified` with a stated reason. Per the Phase 1 decision, the
  local Tier-2 baseline is taken immediately before Phase 5.
