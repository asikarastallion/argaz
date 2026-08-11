# Process and session lifecycle

## START

1. The run recorder opens **first**, before any command is typed, so that
   launch output — including a Gazebo or SITL failure — lands in
   `console.log`.
2. `session.build_launch_commands(model)` produces the exact shell lines for
   the model's launch method. They are typed into the SIMULATION terminal
   verbatim, so what ran is visible rather than described.
3. The MAVLink link starts and waits for a heartbeat on port 14550.
4. Capabilities are probed **from the vehicle** — `Q_ENABLE`,
   `Q_TAILSIT_ENABLE`, `Q_OPTIONS` — because `models.json` cannot answer them.
   SkyCat TVBS is registered as a plain QuadPlane and its parameter file makes
   it a tailsitter.

## Why there are two terminals

The simulation occupies the shell's foreground, and that is *required*: on the
`sim_vehicle.py` path MAVProxy is interactive, and a process that is not in the
foreground cannot read stdin — it stops with SIGTTIN. While it holds the
foreground, that shell cannot run anything else, so ArgazUI opens a second,
empty one for mission scripts and manual commands.

## Why commands go over MAVLink instead of into the terminal

On the `ros2_launch` path, MAVProxy is started by ROS 2 with
`--non-interactive`. It does not read stdin at all, so typing `mode guided`
into the terminal does nothing for Iris. Both launch paths do produce a MAVLink
output, so that is the channel the buttons use — the same way on every model,
with an ACK to report.

## STOP

1. Any running procedure is cancelled, and its declared parameter overrides are
   restored from a `finally` block.
2. The MAVLink link stops.
3. Child processes are terminated **by process group**, never by name.
4. Two familiar shutdown messages appear and are harmless: Gazebo's `gz`
   wrapper reports `Errno::ESRCH` because the children were already stopped by
   group, and MAVProxy's `log_writer` thread raises while closing its own
   telemetry log. Neither writes the autopilot's dataflash log — SITL does — and
   every run records whether that log closed complete.
5. **Only then** are the artefacts collected. The dataflash log is closed when
   the process exits; copying earlier would archive a truncated file.

## Never match a process by name

`pkill -f arduplane` is not used anywhere in this project, and must not be. It
matches any command line containing the string — including an editor with the
file open, and including the test runner itself. Every process ArgazUI starts
runs in its own session (`start_new_session=True`) and is terminated by its
process group.

## What a run owns, checked before and after

A run owns exactly what it started, and ownership is established by the kernel
— session id, process group id, and the socket inode a port is held by — never
by a process name.

**Before launch**, the ports the run needs are checked. A port held by anything
this run did not start makes it refuse to launch, because a link that silently
attaches to a stranger's vehicle produces evidence about an aircraft nobody in
this run started. That was reachable before v1.7: a crashed server left
`gz sim`, SITL and MAVProxy holding 14550, and the next START bound
`udpin:14550` beside them and could receive the *previous* vehicle's telemetry.

The holder is **reported and never signalled**. A developer running their own
SITL on 14550 in another terminal gets a clear message, not a dead process, and
the ownership layer has no way to signal anything at all — asserted by a test
that parses it rather than by convention.

**After teardown**, cleanup is checked rather than assumed. `stop_children`
already reported survivors it could not kill, and that report went to the
console and nowhere else; the same two questions are now asked again and land
in the run record:

* are the owned processes gone, according to `/proc`?
* are the owned ports free, according to a real bind?

```json
"isolation": {"session_id": 481923, "ports": {"mavlink": 14550},
              "released": true, "survivors": []}
```

`released: true` is what makes "no orphan was left" a claim with evidence under
it instead of an absence of complaint. It is asked whatever ended the run — a
pass, a failure, a timeout, a cancellation or an exception — because the stop
path is the same in all five cases.

## Shutting the server down

A server stopped with Ctrl+C finishes its run first. Otherwise a real flight's
artefacts would be left half-written, which is precisely the situation the run
directory exists for.

## Hot reload, and what does not reload

Four layers are read off disk, and only two of them can go stale while the
server runs:

| layer | reloads? |
|---|---|
| `argazui/**/*.py` | **no** — imported once; stale until restart |
| `static/**` | served per request, but built against the API the running code has |
| `procedures/*.yaml` | yes, on mtime change |
| `config/*.json` | yes, on every request |

The page compares the build identity it was served with against
`/api/version`, and says so plainly when they differ — a server left running
from an earlier checkout hands the browser today's interface while answering
with yesterday's API, and that failure looks like a bug in the page.
