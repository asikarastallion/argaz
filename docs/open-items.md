# ArgazUI — what is still open after v1.1

Written 2026-08-03, at the point where v1.1 was closed. This is a handover
note for whoever picks the work up next, including a fresh assistant session
with no memory of how any of it was decided.

Six source files already reference `docs/status.md` and one references
`CHANGELOG.md`. **Neither file exists yet.** That is the largest single loose
end and it is item E below.

---

## 1. Where v1.1 actually got to

Done and verified by running it:

| | |
|---|---|
| Declarative procedures | `argazui/procedures/*.yaml`, schema 1, one executor shared by the UI button and the test suite |
| Acceptance criteria | measurable state only — and since C.0.5, **attitude too** |
| Config resolution | `argaz.toml` / `ARGAZ_*` / CLI; no absolute paths anywhere in the tree |
| `doctor` | installation diagnostics, `--json`, tier-aware |
| Run artefacts | `runs/<UTC>_<model_id>/` with dataflash, params, report, plots |
| Version-mismatch detection | four hashed source layers, browser banner, runnable recovery command |
| Test suite | 39 tier-1 tests: 13 procedure, 18 e2e (real server, real browser), 8 criterion checks |

The suite's own record lands in `runs/tests/suite.json` (schema 1) on every
run: per-test outcome, skip reason, markers, duration, and an environment
label. **That file is the intended input for the generated status table.**

Last measured full run: **38 passed, 1 failed, 5m24s** on a developer machine.
The one failure is the tailsitter, deliberately (§3).

---

## 2. Not done — in the order it was planned

### C.1 — Neither container image has ever been built

`docker/Dockerfile.tier1` and `docker/Dockerfile.tier2` are written and were
edited during v1.1, but **no image was ever built and nothing has run inside
one.** Do not describe them as working until that happens.

`Dockerfile.tier1` should be quick to settle: install both requirement files,
`python3 -m playwright install --with-deps chromium`, run `pytest -m tier1`.
Building ArduPilot from source inside it is the slow part.

`Dockerfile.tier2` carries the project's riskiest unverified assumption:
**Gazebo Harmonic running headless inside a container.** If it does not work,
that is an acceptable answer — say so plainly and fall back to a self-hosted
runner. It is not an acceptable answer to make Tier 2 report green without
flying anything.

### C.2 — There is no CI at all

No `.github/` directory exists. The structure was decided and is not open for
relitigation:

- **`images.yml`** — builds the images and pushes them to GHCR. Triggers:
  `docker/**`, `argazui/requirements*.txt`, the ArduPilot reference, plus
  `workflow_dispatch`. Layer caching.
- **`tier1.yml`** — every push and PR. **Pulls** the image, bind-mounts the
  checkout at that commit so the tests run against the commit rather than
  against a stale copy baked into the image, runs `pytest -m tier1`.
- **`tier2.yml`** — nightly `schedule` + `workflow_dispatch`, tier-2 image,
  uploads `runs/` as artefacts.

**Locked decision: CI must never compile ArduPilot from source on every
push.** On a free runner that alone makes the 10-minute target impossible.

Measure Tier 1's real duration on a runner and report it. If it exceeds 10
minutes, do not invent an optimisation — propose splitting it (fast layer:
procedures + page e2e; slow layer: flights) and let the owner decide.

Two things CI will hit immediately:

1. **The tailsitter test fails by design** (§3), so the tier-1 job is red from
   its first run. That was an explicit decision: a procedure marked broken is
   far better than one shown as passing. Decide how to present it — but not
   with `xfail` or `skip`.
2. **SITL rejects `MAV_CMD_NAV_TAKEOFF` under host load.** Observed four times
   consecutively on a desktop at load average 7.7, with
   `EKF3 IMU0 MAG0 in-flight yaw alignment complete` as the nearest reason;
   the same test passes on an idle machine. Shared runners are loaded
   machines. Expect this and design for it — the one-retry-then-`flaky`
   mechanism in `run_procedure()` already exists for exactly this.

### C.3 — `docs/status.md` is not generated

Referenced from six places, does not exist. Generate it from
`runs/tests/suite.json` plus the `result.json` of each run. Columns:

| Model | Class | Launch method | Procedures | Result | Advisories | Last run (UTC) | Firmware | Tier |

Rules, all locked:

- Result is only `passed` / `failed` / `flaky` / `untested`. No other value.
- `no-procedure` → `untested`. A skipped test → `untested`, **never**
  `passed`.
- **Tier 1 claims no model coverage.** A model that has not run under Tier 2
  stays `untested`, and the Tier column says what was actually verified. If
  that distinction blurs, the whole exercise is pointless.
- Firmware is the canonical string from `versions.py::BuildId.text()`.
- A header saying the file is machine-generated, by which workflow, and when.

**Most of the table will read `untested`, because Tier 2 has never run and no
Gazebo model has ever been machine-verified.** That is the correct output, not
a problem to paper over.

### D — Two small items

- **`RC_KEEPALIVE_INTERVAL` is still a hard-coded `0.25`**
  (`argazui/argazui/mavlink_link.py`). It should be derived from
  `RC_OVERRIDE_TIME` (3 vehicle-seconds) divided by the SITL speedup, with a
  safety margin and the reasoning in a comment. The current constant is
  documented but it is a magic number, and it is the reason
  `tests/sitl.py` caps `DEFAULT_SPEEDUP` at 5 instead of 10.
- **`docs/manual-checklist.md` does not exist.** It should list what a human
  checks by hand — spawn, Gazebo, buttons, both terminals, mission script,
  log — marking which steps the e2e suite already covers and which it does
  not. The point is to make the uncovered ones visible.

### E — The release itself

- **`README.md` still carries the hand-written support table** (lines
  ~214–230): ten models, every one marked `✅ full`. This is now not merely
  unverified but **contradicted** by the project's own evidence — nothing in
  that table has ever been machine-verified, and one shipped procedure is
  known broken. Replace it with a link to `docs/status.md` and a generated
  summary line, plus a visible section saying support status comes from CI
  output rather than human assertion, and that `untested` means "not yet
  machine-verified", not "broken".
- **`CHANGELOG.md` does not exist.** The `v1.1.0` entry should state plainly:
  that Plane TAKEOFF never worked in v1.0 and why; that v1.0's README carried
  unverified support claims; and that tightening the acceptance criteria
  revealed the tailsitter takeoff had been out of control on all three of the
  runs that previously "passed". That last one is the release's best story —
  a weak criterion showed green and a stronger one caught it. Do not soften
  it.
- **No `v1.1.0` tag exists.** `__version__` is already `"1.1.0"`. Tag, push
  the tag, write release notes containing the CHANGELOG summary, the current
  verification status from `docs/status.md`, and the known limits.

Pre-push checks (all currently clean, re-run them): `git status` clean,
`runs/` gitignored, and no absolute home paths in tracked files:

```bash
git ls-files -z | xargs -0 grep -ln "/home/" | grep -v docs/open-items.md
```

(This file is excluded because the line above contains the pattern it looks
for. The check reads tracked files only, so the vendor trees and `runs/`
cannot produce false positives the way a plain recursive grep does.)

---

## 3. The tailsitter: closed as unverifiable, not as broken

`tests/test_tier1_procedures.py::test_takeoff_mode_change_and_land[sitl_tailsitter]`
**fails, and is meant to.** The reasoning is in a comment at the frame
definition; the short version:

- `plane-tailsitter` arms, changes mode, obeys the stick and climbs past 20 m
  — every procedure step passes — while tumbling at **1263–1306 °/s peak**,
  spending 30–57 s of a 49–65 s flight outside its pitch band.
- The frame ships **no VTOL attitude tuning at all**: `Q_A_RAT_RLL_P` and
  `Q_A_RAT_PIT_P` are at ArduPilot's 0.25 defaults.
- ArduPilot's own suite lists it as known-broken and skips it:
  `"plane-tailsitter": "unstable in hover; unflyable in cruise"` in
  `Tools/autotest/arduplane.py`, `FlyEachFrame`.
- Rebooting SITL first, as upstream does for tailsitters "to pick up the
  rotated AHRS view", improves the peak from 1263 to **235 °/s** but does not
  stabilise it.
- The only alternative frame, `quadplane-copter_tailsitter`, is properly tuned
  and rock-steady (pitch 89.8–90.0°, peak **0.1 °/s** over 240 s) but produces
  **no lift from stick input at any throttle up to full** (`alt=0.09 m,
  climb=-0.00` at RC3=2000). Upstream flies it only through AUTO missions.

So the procedure itself has never been shown wrong; there is simply no SITL
tailsitter frame on this checkout that can validate it. **Do not tune the
airframe to make the test pass** — a harness that adjusts the vehicle until
its own test goes green proves nothing, which is the failure this whole
version exists to expose.

Two open routes for a future version:

1. Verify it in Tier 2 against a real Gazebo tailsitter model (SkyCat TVBS is
   registered as a QuadPlane but its parameters make it a tailsitter — the
   capability probe already detects this).
2. Add a mission-based tailsitter takeoff procedure, which is how upstream
   flies its tailsitters. `vtol_takeoff_mission.yaml` is a working example of
   the shape.

---

## 4. Smaller things noticed but not acted on

- **The plane's loiter entry rolls to −58°**, i.e. 1.4 s outside its declared
  [−45,45] band against a 3 s budget. It passes, but not comfortably. Either a
  real observation about ArduPilot's loiter entry or a band that wants
  widening with a stated reason — decide with data, not by loosening it
  because it is close.
- **`attitude_stable` is only declared on the four takeoff procedures.** The
  landing procedures have no attitude criteria. A landing envelope is a
  different shape — it ends with the aircraft on the ground and disarmed, and
  touchdown transients are legitimate — so it needs its own thinking rather
  than a copy of the takeoff numbers.
- **`test_never_tries_to_install_into_a_managed_interpreter`** is marked
  `container_only`. It happens to run and pass on the current developer
  machine, but whether it runs at all depends on the host's Python. When it
  skips, the terminal summary and the suite record say so; the status
  generator must not count it as a pass.
- **ATTITUDE is now requested at 10 Hz** (`MAV_DATA_STREAM_EXTRA1`) on top of
  the 4 Hz `STREAM_ALL`, because the attitude criterion cannot tell a 2 Hz
  oscillation from a hover at 4 Hz. If telemetry bandwidth ever matters on a
  real link, this is the knob.
- **Schema 2 keys `mission:` and `failures:` are reserved and rejected** at
  load time, deliberately, so nothing starts depending on a half-defined
  meaning. `SCHEMA.md` documents the intent.

---

## 5. Explicitly out of scope for v1.1 — do not start these by accident

Each belongs to its own version:

- multi-vehicle / swarm simulation
- HITL (a real hardware bridge)
- scenario YAML (the `mission:` / `failures:` schema-2 keys)
- failure injection (`SIM_*` wind, GPS loss, motor failure)
- run-to-run regression comparison
- authentication, remote access, graphical mission planning

v1.1 claims this and nothing more: **the right takeoff and landing procedures
for the vehicle's class, with measurable acceptance criteria; installable on
another machine; every flight leaves evidence; and support status is machine-
generated.** The last clause is the one still owing a `docs/status.md`.
