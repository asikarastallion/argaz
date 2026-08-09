# Diagnostics (`doctor`)

```bash
python3 -m argazui doctor            # human-readable
python3 -m argazui doctor --json     # machine-readable
python3 -m argazui doctor --tier tier1
```

Exit status is `0` when every **critical** check passed and `1` otherwise.

## It only observes

The doctor never installs a package, creates a directory, or starts a
simulator. It reports what is on the machine, and every failure carries a
`fix:` line saying what to do about it. A diagnostic that repairs things is a
diagnostic whose output you can no longer trust to describe the machine you
have.

## What it checks

| check | critical | what it means |
|---|---|---|
| `ardupilot_root` | yes | the configured ArduPilot checkout exists |
| `sitl_copter` / `sitl_plane` | yes | the SITL binary exists, is executable, and starts |
| `env_script`, `quadplane_env_script` | yes | the shell environment the launches source |
| `python_fastapi` / `uvicorn` / `pymavlink` / `yaml` | yes | importable **in this interpreter** |
| `runs_root` | no | the run archive directory is writable |
| `port_http`, `port_mavlink`, `port_script_mavlink` | yes | 8770 / 14550 / 14551 are free to bind |
| `ardu_ws_root`, `sitl_models_root`, `sitl_models_gazebo` | full profile | the ROS workspace and the Gazebo assets |
| `gz`, `ros2`, `ros_distro` | full profile | run **after sourcing the configured environment**, not against your login shell |

### Why the SITL binary check tolerates a non-zero exit

SITL's option parser deliberately exits `1` for `--help` on several ArduPilot
releases. Seeing its complete option banner still proves the executable starts
on this host; demanding exit `0` would label a working SITL as broken.

### Why the live-plot port is not checked

`doctor` checks that 14550 and 14551 are free to *bind*. Port 14552 is supposed
to be held — by PlotJuggler — so a bind check there would report FAIL exactly
when the feature is working.

## Two profiles, and why starting is not gated on the full one

`--tier tier1` covers ArduPilot, the SITL binaries, the Python packages and the
ports. `--tier full` adds Gazebo, ROS 2 and the model assets.

**Only the tier-1 set is fatal at startup.** Gating on the full profile made
ArgazUI refuse to start on any machine without Gazebo and ROS 2 — including the
tier-1 container image, where every e2e test died over assets none of them use.
It is also simply wrong for a user: the `sitl_only` launch method needs no
Gazebo at all, and a missing simulator is a reason some models cannot fly, not
a reason the application cannot run.

So the server starts, prints which models cannot be launched, and points at the
full report:

```
ArgazUI: starting without the full simulation stack. Models that
need it cannot be launched:
  - sitl_models_root: SITL_Models root not found: /opt/SITL_Models
  Run 'argazui doctor' for the complete report.
```

## In CI

`--json` gives `{"ok": bool, "tier": str, "config": {...}, "checks": [...]}`,
where `config` is the resolved configuration — which file was read, which roots
and ports came out of it. That block is the fastest way to find out why a
machine is looking in the wrong place.
