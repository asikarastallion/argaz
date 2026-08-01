# ArgazUI procedure schema — version 1

A **procedure** is a declarative flight sequence: a list of steps plus the
acceptance criteria that decide whether it worked. Procedures live in
`argazui/procedures/*.yaml` and are the *only* place a takeoff or landing flow
is defined.

## The single-source rule

The UI button and the regression test run the same file through the same
runner. There is no second implementation of a takeoff anywhere in the code
base. If a test passes, the button works — that is the entire point of this
format, and it is why acceptance criteria are part of the procedure rather than
part of the test.

## Why procedures exist at all

`MAV_CMD_NAV_TAKEOFF` sent as a `COMMAND_LONG` is a *Copter* idiom. On
ArduPlane the handler is compiled only under `HAL_QUADPLANE_ENABLED` and
returns `MAV_RESULT_FAILED` unless `quadplane.available()`
(`ArduPlane/GCS_MAVLink_Plane.cpp`, `handle_command_MAV_CMD_NAV_TAKEOFF`), so on
a fixed-wing aircraft it cannot ever produce a takeoff. Taking off is a
different *procedure* per vehicle capability, not a different argument to one
command. This schema models that difference.

---

## Top level

```yaml
schema: 1                       # required, integer, currently always 1
id: plane_takeoff               # required, must equal the filename stem
name:                           # required, shown in the UI
  en: Plane takeoff (TAKEOFF mode)
  tr: Plane kalkisi (TAKEOFF modu)
description:
  en: ...
  tr: ...
sources:                        # required, non-empty: where the flow comes from
  - https://ardupilot.org/plane/docs/takeoff-mode.html
applies_to: {...}               # required, see below
inputs: [...]                   # optional
timeout: 240                    # optional, whole-procedure ceiling in seconds
steps: [...]                    # required, non-empty
expect: [...]                   # required, non-empty
```

Every user-visible string (`name`, `description`, step `name`, `fail_message`,
input `label`) is a map with `en` and `tr` keys. A bare string is accepted and
used for both languages, but new procedures should supply both.

### `applies_to`

Selection is driven by **runtime vehicle capabilities**, probed over MAVLink
when a procedure is requested, not by the `vehicle_class` string in
`models.json`. A Swan-K1 and an Alti Transition are both `VTOL` in the
registry, but only one of them is a tailsitter.

```yaml
applies_to:
  role: takeoff                 # required: takeoff | land
  autopilot: ArduPlane          # optional: ArduCopter | ArduPlane; omitted = any
  quadplane: false              # optional tri-state; omitted = don't care
  tailsitter: false             # optional tri-state; omitted = don't care
  fw_takeoff_allowed: true      # optional tri-state; Q_OPTIONS bit 1
  default: true                 # optional, default false
  priority: 10                  # optional, default 0
```

Probed capabilities:

| key | how it is determined |
|---|---|
| `autopilot` | the model registry's `vehicle` field, confirmed by the heartbeat |
| `quadplane` | `Q_ENABLE > 0` read from the vehicle |
| `tailsitter` | `Q_TAILSIT_ENABLE > 0` read from the vehicle |
| `fw_takeoff_allowed` | `Q_OPTIONS` bit 1 (`Allow FW Takeoff`) set |

A procedure matches when **every** stated key equals the probed value.
Auto-binding a button picks the highest-`priority` match that also has
`default: true`; non-default matches stay available as explicit alternatives
(this is how `plane_takeoff_auto` and `vtol_takeoff_mission` are offered).

`models.json` may pin a choice per model, which overrides selection entirely:

```json
"procedures": { "takeoff": "plane_takeoff_auto", "land": "plane_land" }
```

### `inputs`

```yaml
inputs:
  - name: alt                   # referenced as {alt} in step values
    label: {en: "altitude (m)", tr: "irtifa (m)"}
    type: number                # number is the only type in schema 1
    default: 50
    min: 5
    max: 500
```

`{alt}` and `{alt*100}` placeholders are substituted in any string step value;
the multiplier form converts units (metres → centimetres). Values captured by
`get_param: store_as:` join the same namespace and can be referenced the same
way.

---

## Steps

Each list entry is a map with an optional `name`, optional common keys, and
**exactly one** step-type key that identifies what it does.

Common keys:

| key | meaning |
|---|---|
| `name` | `{en, tr}` label shown in the UI and the log |
| `timeout` | seconds for this step; each type has a sane default |
| `on_fail` | `abort` (default) or `continue` |
| `when` | run only if a condition (see below) currently holds; otherwise the step is recorded as `skipped` |

`when` is evaluated once, immediately, against the current vehicle state — it
does not wait. Combined with `on_fail: continue` on the preceding step it
expresses a conditional fallback, which is how `tailsitter_takeoff.yaml` only
force-arms when the normal arm was actually refused:

```yaml
- arm: {recover: true}
  on_fail: continue
- arm: {force: true}
  when: {armed: false}
```

### `set_param`

```yaml
- name: {en: Set takeoff altitude, tr: Kalkis irtifasini ayarla}
  set_param: {name: TKOFF_ALT, value: "{alt}"}
```

**Run-scoped.** The previous value is captured before writing and restored when
the procedure ends (including on failure), and both are recorded in the run
directory. Upstream `.param` files are never touched.

### `get_param`

```yaml
- get_param:
    name: TKOFF_DIST
    store_as: tkoff_dist
    min: 1                      # optional sanity bounds
    fail_message:
      en: "TKOFF_DIST is {value} — the plane has nowhere to fly to. Set it to 100-400 m."
      tr: "TKOFF_DIST {value} — ucagin gidecegi bir nokta yok. 100-400 m yap."
```

Fails the step when the parameter is unreadable or outside `min`/`max`.
`{value}` in `fail_message` is the value that was read.

### `set_mode`

```yaml
- set_mode: TAKEOFF
```

Confirmed against the heartbeat's `custom_mode` **number**, not the mode name —
some models report a mode table that does not match their autopilot.

### `arm` / `disarm`

```yaml
- arm: {force: false, recover: true}
- disarm: {force: false}
```

`recover: true` (the default for `arm`) enables the automatic recovery
behaviour that v1.0 had in the ARM button: centre a non-neutral RC channel on
its own `RC*_TRIM`, run a simple accelerometer calibration when the autopilot
asks for one, and retry while the rejection reason is a transient start-up
condition. The autopilot's own rejection text is reported either way.

### `rc_override` / `rc_release`

```yaml
- rc_override: {channels: {3: 1700}, hold: 2}   # hold seconds, optional
- rc_release: true
```

`rc_release` clears all overrides. The runner also clears them when a procedure
ends, so a failed procedure cannot leave a stick jammed.

### `send_command`

```yaml
- send_command:
    command: MAV_CMD_NAV_TAKEOFF
    type: long                  # long | int
    frame: MAV_FRAME_GLOBAL_RELATIVE_ALT_INT   # int only
    params: {p7: "{alt}"}       # p1..p7 for long; p1..p4 + x/y/z for int
    accept: [ACCEPTED]          # MAV_RESULT names treated as success
```

`command` and `frame` are MAVLink enum names, resolved through `pymavlink`.
Unset params default to 0.

### `upload_mission`

```yaml
- upload_mission:
    items:
      - {command: MAV_CMD_NAV_VTOL_TAKEOFF, frame: MAV_FRAME_GLOBAL_RELATIVE_ALT, z: "{alt}"}
```

Replaces the mission on the vehicle for the duration of the run. `p1..p4`,
`x`, `y`, `z` are available per item; `x`/`y` are degrees and are converted to
the 1e7 integer form.

### `wait_for`

```yaml
- wait_for: {alt_above: 15, climb_rate_above: 0.5}
  timeout: 90
```

Blocks until **all** listed conditions hold simultaneously, or the timeout
expires. See the condition table below.

### `sleep`

```yaml
- sleep: 3
```

---

## Conditions

Used by `wait_for`, `when`, and `expect`.

| condition | true when |
|---|---|
| `armed: true` / `false` | the armed flag matches |
| `mode: QLOITER` | the current mode matches (by number) |
| `mode_in: [QLOITER, QHOVER]` | the current mode is one of these |
| `alt_above: 15` | relative altitude (m) is greater |
| `alt_below: 1.5` | relative altitude (m) is less |
| `climb_rate_above: 0.5` | `VFR_HUD.climb` (m/s) is greater |
| `climb_rate_below: -0.2` | `VFR_HUD.climb` (m/s) is less |
| `groundspeed_above: 5` | `VFR_HUD.groundspeed` (m/s) is greater |
| `prearm_ok: true` | the `SYS_STATUS` pre-arm health bit is set |
| `param: {name: Q_ENABLE, min: 1}` | the parameter is within bounds |

Numeric values accept `{placeholder}` strings.

## `expect`

The acceptance criteria. **An ACK is not success.** A procedure is only
reported as passed when a measurable state change is observed.

```yaml
expect:
  - condition: {alt_above: "{alt*0.8}"}
    timeout: 120
    message:
      en: climbed to at least 80% of the requested altitude
      tr: istenen irtifanin en az %80'ine tirmandi
  - condition: {armed: true}
    message: {en: still armed, tr: hala armli}
```

Each entry is evaluated after the steps finish. `timeout` (default 30 s) lets a
criterion wait for a state that is still developing. Every criterion must hold
for the procedure to pass, and each one's pass/fail lands in `result.json`.

---

## Reserved for schema 2

The following top-level keys are **reserved and rejected by the schema-1
validator** so that no procedure starts using them informally before the
scenario runner exists:

```yaml
mission:      # a full mission to fly, with per-waypoint acceptance criteria
failures:     # fault injection (sensor dropouts, motor loss, RC/GCS failsafe)
```

They are listed here because the format was designed around them: steps,
conditions and `expect` are already the vocabulary a scenario would need, so
adding these two keys does not require reworking anything above.
