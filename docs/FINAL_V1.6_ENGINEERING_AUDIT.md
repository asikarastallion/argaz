# Argaz v1.6 — Final Engineering Audit

Independent audit performed 2026-08-11 against commit `d2a9983`
("v1.6: a question written down, two groups flown to answer it, and a delta
that says what it is worth"), branch `main`, working tree otherwise clean
(one untracked directory, `argaz_v1_3_to_v1_6_architecture/`).

The auditor was instructed to trust nothing: not the README, not the
CHANGELOG, not the release notes, not comments claiming completeness, and not
the existing tests. Every claim below is anchored to a file, a line, a command
that was executed, or an output that was observed. Where an assertion could
not be verified in this environment, it is marked UNCLEAR rather than assumed.

---

## 1. Executive Summary

Argaz v1.6 is a serious engineering project. It is not a SITL GUI with a
verification vocabulary painted on it. The distinctions it makes — verification
against validation, a measured criterion against an acknowledgement packet, an
injected fault against a handled fault, absence-with-a-reason against absence,
a test count against coverage — are the distinctions that separate a
verification tool from a launcher, and in this codebase they are implemented
rather than described. The `_Window` class in [procrunner.py:336](../argazui/argazui/procrunner.py#L336),
the `StabilityWatch` in [mavlink_link.py:176](../argazui/argazui/mavlink_link.py#L176),
the `differences()` gate in [fingerprint.py:315](../argazui/argazui/fingerprint.py#L315)
and the `limitations.py` standing-statements table are all work an experienced
verification engineer would recognise and respect.

It also has two defects that reach the verification result itself.

**The first is a false-PASS path.** The runner has an evidence guard —
`_unmeasurable()` at [procrunner.py:637](../argazui/argazui/procrunner.py#L637) —
which exists precisely to stop silence being read as success. It is wired into
two of the four criterion shapes and not the other two, and the condition
table it consults ([`CONDITION_EVIDENCE`, procrunner.py:329](../argazui/argazui/procrunner.py#L329))
covers attitude and pre-arm but not altitude, climb rate, ground speed, arm
state or mode. The consequence was demonstrated directly, not inferred: against
a `VehicleState` that has never received a single MAVLink message, the criteria
`alt_below: 1` and `armed: false` both return PASS. Those two criteria are the
entire `expect:` block of all four shipped landing procedures.

**The second is a misclassification.** `failures.py` is the module whose own
docstring says `acceptance` "is the only one that means the aircraft did
something wrong", and that conflating the categories "is how a broken harness
comes to be reported as a broken aircraft". It does exactly that. Five distinct
abort causes — a fault mechanism the firmware does not have, an operator
cancel, an overall procedure timeout, a fault start-condition that never held,
a malformed placeholder — were all classified `acceptance` / `criterion-not-judged`
in a direct probe.

Alongside those, v1.6 ships without CI evidence of its own: `docs/status.md`
and `docs/coverage.md` are generated artefacts last produced at
2026-08-10T15:08:01Z from v1.5's run, the v1.6 commit does not touch either,
and `docs/coverage.md` is missing the fifth coverage dimension that v1.6's own
`coverage.py` declares. The README's headline status line is that stale
sentence.

None of the three is architectural. All three are localised, and each is a
few tens of lines from being right. But until they are, the project's strongest
claim — that a PASS here is evidence and not a green light — is not fully
supported by its own implementation.

**Verdict: B — strong project, but several engineering gaps remain.** Full
reasoning in §29.

| Severity | Count |
|---|---:|
| CRITICAL | 2 |
| HIGH | 5 |
| MEDIUM | 12 |
| LOW | 6 |

---

## 2. Repository and Architecture Understanding

### 2.1 What is actually in the repository

The repository root is dominated by vendored third-party trees that are not
the project: `ardupilot/` (an ArduPilot checkout), `ardu_ws/` (a built ROS 2
workspace), `SITL_Models/`, `Micro-XRCE-DDS-Gen/`, `terrain/`. Of the ~601 000
Python lines under the root, the project itself is **26 530 lines** across
`argazui/argazui/` (30 modules) and `tests/` (37 files).

| Layer | Modules |
|---|---|
| Web/orchestration | `app.py` (1346) |
| Simulation lifecycle | `session.py` (372), `mavlink_link.py` (1232) |
| Execution | `procrunner.py` (1301), `procedures.py` (949) |
| Off-nominal | `faults.py` (462) |
| Post-flight | `flightlog.py` (1248), `metrics.py` (332) |
| Evidence | `runs.py` (1017), `evidence.py` (473), `fingerprint.py` (334), `versions.py` (355) |
| Judgement | `failures.py` (454), `regression.py` (427) |
| Aggregation | `campaign.py` (568), `experiments.py` (786), `analysis.py` (944) |
| Reporting | `status.py` (642), `coverage.py` (439), `trace.py` (321), `limitations.py` (313) |
| Support | `i18n.py` (612), `docs.py` (496), `paths.py` (160), `doctor.py` (231), `scan_models.py` (398), `telemetry_mirror.py` (213) |

Declarative content: 13 procedure YAML files, 2 experiment YAML files, 3
`SCHEMA.md` documents, `config/models.json` (11 models), `argaz.toml`.
Documentation: 51 files under `docs/` (25 English + 24 Turkish + 2 generated),
a 42 KB README, a 67 KB CHANGELOG. CI: 4 GitHub workflows, 2 Dockerfiles.

### 2.2 The pipeline, traced end to end

The conceptual pipeline in the audit brief was traced against the
implementation. It exists, with the deviations noted:

```
UI (static/app.js) ──POST /api/start──▶ Manager.start_model            app.py:250
   │                                      │
   │                                      ├─ RunRecorder opened FIRST  runs.py:149
   │                                      │  (so launch failures land in console.log)
   │                                      ├─ build_launch_commands()   session.py:105
   │                                      │  → shell lines typed into a real pty
   │                                      └─ MavlinkLink.start()       mavlink_link.py:474
   ▼
pty/bash ──▶ gz sim -v4 -r[-s] <world> &   ──▶  sleep 6   ← DEVIATION: no readiness check
         ──▶ sim_vehicle.py -v <veh> -f <frame> --model JSON --add-param-file=… --out …
                        │
                        └─▶ SITL ──▶ MAVProxy ──14550──▶ MavlinkLink._pump/_absorb
                                                              │
   readiness: state.connected (first vehicle HEARTBEAT)  ─────┤
              state.prearm_ok (SYS_STATUS PREARM_CHECK bit)   │
                                                              ▼
probe_capabilities()  ← reads Q_ENABLE / Q_TAILSIT_ENABLE / Q_OPTIONS FROM THE VEHICLE
                                       procrunner.py:95   (deliberately not models.json)
   ▼
procedures.select(role, caps, model) ──▶ ProcedureRunner.run(proc)   procrunner.py:1115
   │  _prepare_faults → _apply_overrides → stability.reset()
   │  → steps (each via link.submit → worker thread) → faults at declared points
   │  → acceptance criteria (eventually | within | for | never)
   ▼
result dict ──▶ RunRecorder.add_procedure()            runs.py:251
   ▼ STOP
Manager._stop_locked ──▶ TerminalSession.stop_children (SID/PGID walk)   session.py:307
   ▼
RunRecorder.finish()                                    runs.py:303
   ├─ versions.txt, fingerprint.json (pass 1, no firmware yet)
   ├─ scenario.yaml (procedure YAML verbatim, fenced per execution)
   ├─ _copy_dataflash (newest *.BIN newer than run start)
   ├─ result.json  → failures.classify_run()
   ├─ evidence.json → evidence.capture()
   └─ background thread: flightlog.analyse()
         ├─ single pass over the .BIN → params, plots, advisories
         ├─ metrics.compute()          metrics.py:215
         ├─ fingerprint pass 2 (firmware now known)
         └─ attach_report() → result.json rewritten → evidence re-captured
   ▼
regression.compare(baseline, current)                   regression.py:246
campaign.aggregate() / analysis.collect()               campaign.py:305 / analysis.py:414
coverage.collect() / status.generate()                  coverage.py:310 / status.py
   ▼
docs/status.md, docs/coverage.md  ← committed by .github/workflows/status.yml
```

**Deviations from the conceptual pipeline:**

1. There is no discrete "Gazebo started" state. `gz sim … &` followed by
   `sleep 6` ([session.py:156-157](../argazui/argazui/session.py#L156)) is the
   whole handshake. Gazebo failure surfaces only as an absent heartbeat 180 s
   later.
2. Launch is text typed into an interactive bash session. No exit status of any
   launched command is ever read. Process *ownership* is tracked (by session id);
   process *health* is not.
3. `Verify` and `Record` are interleaved, not sequential: the acceptance verdict
   is decided live over MAVLink, and the metrics are derived afterwards from the
   dataflash log. These are two different clocks and two different sampling
   rates, which matters in §8.
4. Regression is not in the automated path at all. It is a CLI subcommand and a
   browser endpoint; no workflow invokes it (§21).

### 2.3 The design idea, stated fairly

The organising principle is **single-source execution**. `ProcedureRunner` is
the only executor; the TAKEOFF button, the tier-1 pytest suite and the tier-2
nightly all call `ProcedureRunner.run()` on the same YAML file. Tier 2 goes
further and calls `session.build_launch_commands()` itself
([tests/gazebo.py:1-10](../tests/gazebo.py)), so a green model row is a
statement about the button rather than about the test harness. This is the
single best structural decision in the project and it holds up under
inspection — there is no second takeoff implementation anywhere in the tree.

---

## 3. Documentation vs Implementation

Each row was checked by reading the implementation, not the prose.

| Subsystem | Documented behaviour | Actual behaviour | Status |
|---|---|---|---|
| Single-source execution | "There is no second code path" (procrunner.py:3-9) | `ProcedureRunner` is the only executor; tier 2 calls `build_launch_commands` directly | **VERIFIED** |
| Capability-based procedure selection | Read from the vehicle, not `models.json` (procedures.py:9-24) | `probe_capabilities` reads Q_ENABLE/Q_TAILSIT_ENABLE/Q_OPTIONS over MAVLink | **VERIFIED** |
| Temporal criteria on vehicle time | `within`/`for`/`never` measured on `ATTITUDE.time_boot_ms` (procrunner.py:47-53) | `_Window` does exactly this, with a sticky wall-clock fallback that is reported | **VERIFIED** |
| Declared, restored parameter overrides | Only declared params writable; restore from `finally` (procrunner.py:19-32) | Enforced at parse time (procedures.py:815-822) and restored in `_restore` | **VERIFIED** |
| "Silence is not success" | Absent telemetry must fail, not pass (procrunner.py:277-281, 326-333) | True for `for`/`never` and `attitude_stable`; **false for `eventually`/`within` and for all altitude/arm/mode conditions** | **MISLEADING** — see F-01 |
| Fault injection fails closed | "the procedure ABORTS … never a nominal flight" (faults.py:31-36) | It does abort. The abort is classified `acceptance`, not `environment` as faults.py:196-202 states | **PARTIALLY VERIFIED** — see F-02 |
| Seven-category failure taxonomy | "conflating them is how a broken harness comes to be reported as a broken aircraft" (failures.py:33-35) | Five non-aircraft abort causes classify as `acceptance` | **MISLEADING** — see F-02 |
| Fault verdict from criteria alone | "A fault that was successfully injected is not a pass" (procrunner.py:68-70) | `result.passed = all(e.passed …)` gated by `evidence_missing`; a fault with no criteria is refused at parse time (procedures.py:690-695) | **VERIFIED** |
| Environment fingerprint | Records or says why it cannot (fingerprint.py:15-22) | `unknown[]` with reasons; no field is ever guessed | **VERIFIED** |
| Regression refuses unrelated runs | "Nothing here is ever compared silently" (regression.py:31) | Hard blocks on model/procedures; drift blocks on 4 identity fields unless overridden | **VERIFIED** |
| Regression CI contract | docs/ci.md:60-67 describes exit codes 0/1/2 for pipelines | Exit codes implemented (`__main__.py:269`); **no workflow calls `argazui compare`** | **PARTIALLY VERIFIED** — see F-16 |
| Retry never becomes a clean pass | campaign.py:38-40, runs.py:238-249 | `aggregate_status` reads last attempt but `flaky` is recorded and pass rate counts clean passes only | **VERIFIED** |
| Campaign iterations are independent | "a real launch and a real shutdown per iteration" (app.py:515-517) | True for process lifecycle; **`eeprom.bin` is shared and never wiped** | **PARTIALLY VERIFIED** — see F-07 |
| Evidence manifest detects incomplete evidence | evidence.py:15-31 | Implemented, three levels, `absent_reason` required for optional | **VERIFIED** |
| Coverage is not a test count | coverage.py:3-9 | Five declared dimensions, uncovered items named | **VERIFIED** (code) / **MISLEADING** (published artefact — see F-06) |
| Traceability chain resolves end to end | trace.py:11-21 | Computed from `result.json`, `integrity()` checks links | **VERIFIED** |
| "evaluated" vs "not judged" | Three consumers agree | Three consumers use three different string rules | **MISLEADING** — see F-10 |
| Verification ≠ validation | docs/verification-vs-validation.md | Excellent and precise | **VERIFIED** (doc) / contradicted by README:3 — see F-13 |
| Metrics are engineering measurements | metrics.py:1-34 | True for 6 of 7; `mode_transition_latency_max` is wall-clock | **PARTIALLY VERIFIED** — see F-04 |
| Docs portal holds no prose of its own | docs.py:1-16 | True — every page resolves to a repository file | **VERIFIED** |
| Turkish is a first-class artefact | README, docs.py:19-27 | Backend + UI catalogues at full parity (tested); **12 of ~30 portal pages have no Turkish source** | **PARTIALLY VERIFIED** — see F-17 |
| tier 1 makes no claim about a model | status.py:11-18, conftest.py:14-24 | `_tier2_models()` reads `suite.json` markers; tier-1 runs cannot reach the model dimension | **VERIFIED** |
| `pkill` is never used | session.py:4-14 | Confirmed: SID/PGID walk over `/proc`, `os.killpg` only | **VERIFIED** |

---

## 4. System Architecture Audit

### 4.1 Component boundaries — what is genuinely well separated

The separations that matter are real and demonstrable:

* **Process lifecycle vs readiness evaluation.** `TerminalSession`
  ([session.py:216](../argazui/argazui/session.py#L216)) owns processes and
  knows nothing about vehicles. `MavlinkLink` owns readiness and knows nothing
  about processes. Neither imports the other; `Manager` ([app.py:123](../argazui/argazui/app.py#L123))
  is the only place they meet. This is why `tests/support.py` can substitute a
  bare SITL over TCP for the whole pty/MAVProxy stack without touching a line
  of `procrunner.py`.
* **Measurement vs judgement.** `flightlog.py` computes advisories and hands
  raw series to `metrics.py`; neither can change a verdict. Stated at
  [flightlog.py:20-31](../argazui/argazui/flightlog.py#L20) and true in code —
  `attach_report()` explicitly does not touch `status`
  ([runs.py:716-723](../argazui/argazui/runs.py#L716)).
* **Procedure knowledge vs log knowledge.** `metrics.context_from_result()`
  ([metrics.py:151](../argazui/argazui/metrics.py#L151)) is the single seam:
  the log parser never learns what a procedure asked for; the run record
  supplies it. This keeps `flightlog.py` free of procedure semantics.
* **Storage.** There is no database anywhere. Campaigns, experiments,
  traceability and coverage are all recomputed from run directories on every
  request ([campaign.py:310-312](../argazui/argazui/campaign.py#L310),
  [trace.py:22-28](../argazui/argazui/trace.py#L22), [coverage.py:30-34](../argazui/argazui/coverage.py#L30)).
  A derived document therefore cannot drift from its evidence. This is a
  deliberate and correct choice for a project of this size.
* **Catalogue serving.** `faults`, `metrics`, `failure-categories` and
  `limitations` are served to the UI from their defining modules
  ([app.py:1023-1050](../argazui/argazui/app.py#L1023)) rather than duplicated
  in JavaScript, so a fault added to `faults.py` cannot appear under a name
  only the front end knows.

### 4.2 Architectural problems

**A-1 — `Manager` is a god object with implicit singleton state.**

*What:* `Manager` ([app.py:123-752](../argazui/argazui/app.py#L123)) owns two
terminals, the MAVLink link, the active model, the capability cache, the
procedure runner, the run recorder, the campaign runner and the experiment
runner. `mgr = Manager()` at module scope (app.py:807) plus `hub = Hub()`
(app.py:119) are process-global.

*Where:* `argazui/argazui/app.py`.

*Why it matters:* All concurrency control is one `threading.Lock` around
`start_model`/`stop`. `run_procedure`, `start_campaign` and `start_experiment`
each guard only their own thread handle. A campaign is running while
`self.run`, `self.active_model` and `self.mav` are being swapped by
`_CampaignIteration`, and `api_runs()` already has a comment about reading
`mgr.run` once because "STOP may clear it on another thread"
([app.py:1059-1060](../argazui/argazui/app.py#L1059)) — the race is known and
worked around at one call site rather than removed.

*Failure it could cause:* An operator pressing STOP during a campaign
iteration, or a manual `POST /api/procedure` arriving mid-campaign, can produce
a run directory whose recorder was replaced under it. There is no guard
preventing `run_procedure` during an active campaign.

*Cost to fix later:* Moderate. The state is cohesive enough to extract a
`SessionState` object behind one lock, but every endpoint touches it.

**A-2 — Launch is stringly-typed shell text with no result channel.**

*What:* `build_launch_commands()` returns a list of shell lines
([session.py:105](../argazui/argazui/session.py#L105)) which
`start_model` writes into a pty (app.py:287-288). No exit status, no
structured error, no readiness signal from any launched process.

*Why it matters:* The design intention is explicit and defensible — the user
sees exactly the commands they would have typed. But it means the entire
environment-failure detection story is "no heartbeat within 180 s", and the
only diagnosis available is grepping `console.log`. `gz sim` failing, a missing
`.sdf`, a `sim_vehicle.py` rebuild failing and a wrong `--frame` are
indistinguishable at the API level.

*Cost to fix later:* Low if kept additive (a sentinel echo of `$?` after each
line, parsed from the console stream); high if the pty is abandoned, which
would break the visible-terminal property the project values.

**A-3 — "Was this criterion evaluated?" is carried as localized prose.**

*What:* `ExpectResult` ([procrunner.py:155](../argazui/argazui/procrunner.py#L155))
has `passed: bool` and `text: str`, and no `evaluated: bool`. Three consumers
recover the missing boolean by string-matching the translated `text`:
`trace._was_evaluated` (trace.py:232), `failures._not_judged` (failures.py:207)
and `status.claims_of` (status.py:192). They use three different rules.

*Why it matters:* See F-10 — they already disagree today.

*Cost to fix later:* Very low. One field on the dataclass and three call sites.

**A-4 — Hidden coupling between `_recorded_procedures` and `fingerprint.normalise`.**

*What:* `runs._recorded_procedures` recovers archived YAML with `.strip()`
([runs.py:1010](../argazui/argazui/runs.py#L1010)) while
`fingerprint.normalise` only `rstrip()`s ([fingerprint.py:71](../argazui/argazui/fingerprint.py#L71)).
The pair is what makes a regenerated report comparable with the flight that
produced it — a fact documented at fingerprint.py:61-71 precisely because it
was got wrong once.

*Why it matters:* A procedure file with leading whitespace or a leading blank
line would hash differently on regeneration, silently making a regenerated run
incomparable with its own flight. No shipped procedure triggers it; the coupling
is undefended and untested.

*Cost to fix later:* Trivial.

### 4.3 What was checked and found clean

* **No circular imports.** `evidence.py` uses function-local imports for
  schema lookups (evidence.py:118-137) specifically to avoid one, and it is
  commented as such.
* **No runtime state leaking into persistent configuration.** Procedures may
  only write declared overrides, and upstream `.param` files are never written
  (verified: no write path to `paths.SITL_MODELS_CONFIG` exists). The one
  generated file, `argazui_overrides.parm` (session.py:191-200), is written
  into the model's own working directory and carries a "do not edit" header.
* **Path traversal is guarded.** `run_dir()`/`run_file()`
  ([runs.py:919-944](../argazui/argazui/runs.py#L919)) resolve and re-check
  containment; `run_script` checks `target.parent` (app.py:715-717).

---

## 5. Simulation Engineering Audit

### 5.1 The readiness question, answered precisely

> Does Argaz know the difference between "Gazebo started", "SITL started",
> "MAVLink is reachable", and "the vehicle is operational and ready for testing"?

**It distinguishes three of the four, and the one it misses is Gazebo.**

| State | Represented? | How |
|---|---|---|
| Gazebo started | **No** | `gz sim … &` then `sleep 6` (session.py:156-157). No process check, no `gz topic` probe, no exit status. |
| SITL started | **No, in the UI path** | Also fire-and-forget. Detected only via MAVProxy's 14550 output. In the *test* path it is checked properly: `tests/sitl.py:224-233` polls the SITL TCP port with a socket until it opens, and raises `SitlUnavailable` after 30 s. |
| MAVLink reachable | **Yes** | `state.connected`, set on the first non-GCS HEARTBEAT (mavlink_link.py:668-688). `wait_ready()` waits on exactly this. `heartbeat_age` is exposed so the UI can distinguish "never heard from" from "12 s stale" (mavlink_link.py:156-161). |
| Vehicle operational | **Yes, partially** | `state.prearm_ok` / `prearm_known` from the SYS_STATUS `MAV_SYS_STATUS_PREARM_CHECK` bit (mavlink_link.py:714-718). The `known`/`ok` pair is the right shape: "not yet observed" and "observed false" are different. `mode_settled` (mavlink_link.py:120-130) adds a third readiness dimension for mode commands. |

The `prearm_known` / `prearm_ok` and `attitude_known` pairs are genuinely good
engineering. Most tools of this kind carry a single boolean and cannot tell
"unhealthy" from "unobserved".

The gap is that **the abstraction is asymmetric between the UI path and the
test path.** `tests/sitl.py` does port polling, instance allocation
(`_free_instance()`) and eeprom wiping (`-w`, sitl.py:186-201). The UI and
tier-2 path do none of the three. A tier-1 pass therefore proves a lifecycle
that tier 2 and the button do not use.

### 5.2 Shutdown lifecycle — the strongest part of this section

`TerminalSession.stop_children()` ([session.py:307-348](../argazui/argazui/session.py#L307))
is correct and unusually careful:

* the pty's bash is started with `start_new_session=True` and made a controlling
  terminal, so it is a distinct kernel session;
* teardown enumerates `/proc/*/stat`, parses after the **last** `)` to survive
  a `comm` field containing parentheses (session.py:47-49), and collects every
  PGID whose SID matches, excluding the shell's own;
* signals escalate SIGINT (6 s) → SIGTERM (4 s) → SIGKILL (2 s), and SIGINT is
  first *specifically* so SITL flushes and closes its dataflash log
  (flightlog.py:1176-1181 explains why);
* survivors after SIGKILL are reported, not silently ignored.

The rule "`pkill -f` is never used" is stated at session.py:4-14 with the
incident that motivated it, and is honoured — there is no `pkill` in the tree.

Ordering at STOP is also right: `_stop_locked` kills the simulator *before*
`run.finish()` (app.py:322-329), because the `.BIN` is only closed when SITL
exits. `_copy_dataflash` then takes the newest `.BIN` **newer than the run
start minus 5 s** (runs.py:433), which is what prevents a restarted model from
archiving the previous session's log.

### 5.3 Port allocation and stale-state handling

* **Ports are fixed** in the UI path: 14550 (interface), 14551 (scripts),
  14552 (mirror), and SITL's own 5760/5762/5763. There is no allocation and no
  collision detection at START. `doctor` checks bindability
  ([doctor.py](../argazui/argazui/doctor.py)) but `start_model` does not.
  A second ArgazUI, or a MAVProxy left over from a crashed session, silently
  takes the link. The test path does allocate (`_free_instance()`,
  `_free_port()` in tests/e2e/harness.py:39).
* **The working directory is reused.** `argazui/run/<model_id>/` holds
  `eeprom.bin`, `logs/`, `mav.tlog`, `mav.parm`, `terrain/` and persists across
  runs. This is documented at runs.py:18-24 and is deliberate — it keeps SITL
  out of the ArduPilot tree and gives each model its own eeprom so models
  cannot corrupt each other. What it does **not** do is prevent a model
  inheriting its own previous run's parameter state (F-07).
* **The link fault cannot outlive the link.** `MavlinkLink.stop()` clears
  `_link_fault` (mavlink_link.py:503-506) as a second guarantee after the
  runner's `finally` (procrunner.py:1216). Correctly belt-and-braces.

### 5.4 Race conditions found

* `Manager` state is mutated from the campaign thread, the procedure thread,
  the pty reader thread and the asyncio loop, with one lock covering only
  start/stop (A-1).
* `RunRecorder` writes are lock-protected (`self._lock`, runs.py:181) and the
  `_finished` flag is checked before writing — this one is handled.
* `_Window.tick()` calls `_observe()` after pumping specifically to avoid a
  reader arriving after a long silence and resetting the "clock last moved"
  stamp (procrunner.py:428-432). That is a subtle race the author found and
  fixed; it is worth saying so.

---

## 6. Verification Engineering Audit

### 6.1 What a PASS actually proves

For a tier-2 model row marked `passed` in `docs/status.md`, a PASS proves:

* an ArduPilot SITL binary, built from the commit recorded in the fingerprint,
  running against a Gazebo model from `SITL_Models`, in one specific
  configuration, executed one named procedure;
* every declared step returned a MAVLink result the procedure accepted;
* every declared acceptance criterion evaluated true **against the state
  `MavlinkLink` held at the moment it was asked**;
* for `for`/`never` criteria, the condition held or did not occur across at
  least 3 samples over a window measured on the vehicle's own clock;
* for `attitude_stable`, the aircraft spent no more than the declared tolerance
  outside the declared bands, weighted by `ATTITUDE.time_boot_ms` intervals
  capped at 0.5 s, over at least 5 s of measured attitude.

### 6.2 What a PASS does not prove

The project states most of this itself, and states it well
(`docs/verification-model.md`, `docs/validation-limits.md`, the report's
non-claims section, `limitations.STANDING`). Beyond what it already says:

* **It does not prove the telemetry backing the criterion arrived.** For
  `alt_below`, `climb_rate_below`, `groundspeed_above`, `armed` and `mode`
  under `eventually` or `within`, an unpopulated field passes. See F-01.
* **It does not prove no excursion occurred.** `never` samples at
  `TEMPORAL_SAMPLE_S = 0.2` wall-clock seconds
  ([procrunner.py:293](../argazui/argazui/procrunner.py#L293)). At speedup 5
  that is one sample per second of vehicle time. The module says this plainly
  at procrunner.py:285-294 — an excursion shorter than one interval passes
  unseen — and points at `attitude_stable` as the criterion that weighs every
  sample. That is honest and correct, and it means `never` is a much weaker
  claim than its name.
* **It does not prove the aircraft was flying.** `alt_above` uses
  `GLOBAL_POSITION_INT.relative_alt`, an EKF estimate. Nothing cross-checks it
  against `POS.RelHomeAlt` in the log, and no criterion asserts the two agree.
* **It does not prove the model is right.** No test has ever looked at a
  rendered Gazebo frame; the CHANGELOG says so at line 1274. An inverted or
  mis-scaled model flies its procedure and passes.

### 6.3 Can the system produce PASS on incomplete or invalid evidence?

**Yes, and this was demonstrated rather than reasoned.** A probe was run
against a `MavlinkLink` stand-in whose `VehicleState` had never received a
message (`attitude_known=False`, `alt=0.0`, `armed=False`, `climb=0.0`),
evaluating criteria through the real `ProcedureRunner._evaluate`:

```
state: alt=0.0 armed=False attitude_known=False climb=0.0

PASS  alt_below: 1  (eventually)             -> alt=0.0m
PASS  armed: false (eventually)              -> armed=False
fail  climb_rate_below: -0.5                 -> climb=+0.0m/s
fail  alt_above: 5  (eventually)             -> alt=0.0m
PASS  pitch_within [-10,10] within 1s        -> became true after 0.02ms of the 1s allowed
fail  angular_rate_above 90 never 1s         -> not judged — rests on attitude telemetry that never arrived
```

The last line is the guard working. The first, second and fifth are it not
being applied. `copter_land`, `plane_land`, `vtol_land` and `tailsitter_land`
each declare exactly `{armed: false}` and `{alt_below: N}` as their complete
`expect:` block, so **a landing verdict can rest entirely on fields that were
never written**.

The published evidence already shows the shape. From
[docs/status.md:105](status.md), a passing tier-2 run:

```
| on the ground | acceptance criterion | plane_land | passed |   ← detail: "alt=0.0m"
```

`alt=0.0m` is the correct reading for a landed aircraft and the correct reading
for a position stream that never arrived. The evidence line cannot distinguish
them. That is exactly the property the project says it exists to remove.

### 6.4 Risk analysis

| Risk | Assessment |
|---|---|
| **False positive** | **Present and demonstrated.** Absence-reads-as-success for 5 condition types under 2 of 4 shapes (F-01). |
| **False negative** | Low. The failure modes examined all fail closed: `alt_above` with no data fails, `attitude_stable` below `min_seconds` fails (procrunner.py:594-597), `_resync` failing marks the fault not-judged rather than passed. |
| **Boundary conditions** | Correct and tested. `alt_above` is strict `>` (procrunner.py:533), `roll_within` is inclusive `<=` on both ends (procrunner.py:548-549) — asymmetric but consistent and documented in SCHEMA.md. Covered by `tests/test_temporal_criteria.py` (345 lines) and `tests/test_stability_criterion.py`. |
| **Timeout behaviour** | Good. Three independent ceilings: per-step `timeout`, procedure-level `timeout` checked each iteration (procrunner.py:1150), and `_Window`'s wall-clock backstop `budget/speedup × 3 + 15 s` (procrunner.py:374). |
| **Missing data** | Handled for attitude and pre-arm; unhandled for position/velocity/arm/mode. |
| **Malformed data** | Parse-time validation is genuinely strict — 40+ distinct `ProcedureError` raises in procedures.py, each naming the alternatives. Durations reject bare numbers (procedures.py:139-141) and reject `m` because "in a flight procedure it reads as metres". |
| **NaN / infinity** | **Not handled.** `float('nan')` in a condition value makes every comparison false; in telemetry it makes `min <= x <= max` false. No `math.isfinite` check exists anywhere in `_check` or in `metrics.compute`. A NaN attitude would fail closed (acceptable); a NaN metric would propagate into `regression._classify` and into `campaign.statistics` where `mean` becomes NaN and `stdev` NaN, both serialised into JSON as `NaN` (invalid JSON for strict parsers). Low likelihood, so LOW severity. |
| **Insufficient samples** | Handled well: `MIN_TEMPORAL_SAMPLES = 3` for `for`/`never`, `DEFAULT_STABILITY_MIN_SECONDS = 5.0` for the envelope, `MIN_SAMPLES_FOR_SPREAD = 3` before a standard deviation is printed. |
| **Transient vs sustained violation** | Correctly distinguished. `_expect_for` does **not** restart its window on a lapse (procrunner.py:695-702) — the reasoning is written out and is right. `attitude_stable` measures accumulated seconds outside a band rather than a peak, with the tailsitter incident as the stated motivation. |
| **Evaluator exceptions** | Caught. `run()` has a bare `except Exception` producing outcome `error`, distinct from `failed` (procrunner.py:1202-1210), and `error` is documented as "not a verdict about the aircraft". Correct design. |
| **Flaky simulation** | One retry allowed in tier 2 only, recorded in `flaky[]`, and the run is reported `flaky` not `passed` in both the status table and the campaign pass rate. Correctly implemented. |

---

## 7. Acceptance Criteria Audit

### 7.1 Per-criterion table

All 15 condition keys were checked against `_check`
([procrunner.py:510-579](../argazui/argazui/procrunner.py#L510)) and
`_check_condition` ([procedures.py:169](../argazui/argazui/procedures.py#L169)).

| Condition | Signal | Source msg | Unit | Comparison | Default when unobserved | Evidence-guarded? |
|---|---|---|---|---|---|---|
| `armed` | `state.armed` | HEARTBEAT `base_mode` | bool | `==` | `False` | **No** |
| `mode` / `mode_in` | `state.mode` | HEARTBEAT `custom_mode` via `_mode_table` | str | `==` / `in` | `"-"` | **No** (fails closed) |
| `alt_above` | `state.alt` | GLOBAL_POSITION_INT `relative_alt` | m | strict `>` | `0.0` | **No** (fails closed) |
| `alt_below` | `state.alt` | same | m | strict `<` | `0.0` | **No** (**fails open**) |
| `climb_rate_above` | `state.climb` | VFR_HUD `climb` | m/s | strict `>` | `0.0` | **No** (fails closed) |
| `climb_rate_below` | `state.climb` | same | m/s | strict `<` | `0.0` | **No** (fails open for positive thresholds) |
| `groundspeed_above` | `state.groundspeed` | VFR_HUD | m/s | strict `>` | `0.0` | **No** (fails closed) |
| `prearm_ok` | `state.prearm_ok` | SYS_STATUS health bit | bool | `==` | `False` | **Yes** (`prearm_known`) |
| `roll_within` / `pitch_within` | `state.roll/pitch` | ATTITUDE, deg | deg | inclusive `low <= x <= high` | `0.0` | **Yes** — but only under `for`/`never` |
| `angular_rate_above/below` | `max(abs(p,q,r))` | ATTITUDE body rates, deg/s | deg/s | strict | `0.0` | **Yes** — same limitation |
| `attitude_stable` | `StabilityWatch` accumulation | ATTITUDE at 10 Hz | s outside band | `outside > tolerance` | fails via `min_seconds` | **Yes** (own guard) |
| `param` | live `PARAM_VALUE` read | MAVLink | native | min/max/equals | `None` → fail | **Yes** (None fails) |

Two design decisions worth crediting:

* **`max_angular_rate` uses body rates, not Euler-angle derivatives**
  ([mavlink_link.py:132-141](../argazui/argazui/mavlink_link.py#L132)), with
  the reason written out: Euler angles are degenerate at vertical attitude,
  which is exactly where a tailsitter spends its takeoff. This is the correct
  choice and most people get it wrong.
* **`attitude_stable` is monotone and evaluated exactly once**
  (`MONOTONE_CONDITIONS`, procrunner.py:264-269), because polling an
  accumulating quantity would spin until timeout and return the same answer.
  Correct.

### 7.2 Temporal shapes

| Shape | Clock | Evidence guard | Minimum samples | Bypass risk |
|---|---|---|---|---|
| `eventually` (schema 1) | **wall clock** — `time.time() + timeout` (procrunner.py:626) | **none** | none | F-01 |
| `within` | vehicle clock via `_Window` | **none** | none | F-01 |
| `for` | vehicle clock, acquire phase on wall clock | `_unmeasurable` | 3 | — |
| `never` | vehicle clock | `_unmeasurable` | 3 | — |

The `eventually` shape being on the wall clock while the other three are on the
vehicle clock is not documented in `docs/acceptance-criteria.md` or
`procedures/SCHEMA.md`. At speedup 5 a `timeout: 30` criterion allows 30 wall
seconds = 150 vehicle seconds, which is a materially different question from
what the author wrote. Recorded as F-11.

### 7.3 Edge cases exercised

Beyond the probe in §6.3, the following were confirmed by reading and by the
existing suite (`tests/test_temporal_criteria.py`, 345 lines; 405 of 406 local
tier-1 non-e2e tests pass):

* exactly-equal-to-threshold: `alt_above: 5` at `alt == 5.0` **fails** (strict).
  Correct and deliberate, but `roll_within` at exactly `low` **passes**
  (inclusive). The asymmetry is intentional (a band vs a threshold) and is
  documented in SCHEMA.md.
* `for` with a lapse mid-window: fails, does not restart. Tested.
* `never` with a violation on the first sample: fails immediately with elapsed
  time reported. Tested.
* stalled vehicle clock: `STALL_AFTER_WALL_S = 2.0`, fallback is sticky, wall
  seconds are converted with the frozen speedup, and `clock: "wall"` is
  recorded in the run. This is a genuinely good piece of work — the reasoning
  at procrunner.py:304-319 identifies a bug class (a dead stream reporting a
  healthy measurement of zero) that most implementations never notice.
* zero-length / reversed bands: rejected at load time (procedures.py:198-210).
* duplicate criterion ids: rejected at load time (procedures.py:550-557).

---

## 8. Quantitative Metrics Audit

Seven metrics in `CATALOGUE` ([metrics.py:57](../argazui/argazui/metrics.py#L57)).
Each was traced from source signal to report cell.

| Metric | Definition | Source | Unit | Time base | Missing-data handling | Assessment |
|---|---|---|---|---|---|---|
| `time_to_target_alt` | first log sample at/after arming where `RelHomeAlt >= target` | `POS.RelHomeAlt` (fallback `CTUN.Alt`) | s | dataflash `TimeUS - t0` | `None` + "never reached in this log" | **Sound.** Target comes from the procedure's own `alt` input. |
| `tracking_error_roll_max` / `_pitch_max` | max abs of `Des* - *` | `ATT` | deg | n/a | `None` + "no ATT records" | **Sound.** |
| `tracking_error_roll_rms` / `_pitch_rms` | RMS of the same | `ATT` | deg | n/a | same | **Sound.** RMS over all logged samples including ground time — see below. |
| `peak_angular_rate` | max abs of `GyrX/Y/Z`, converted to deg/s | `IMU` | deg/s | n/a | `None` + "no IMU records" | **Sound.** Only the peak is retained, deliberately (metrics.py comment at flightlog.py:156-162). |
| `time_outside_attitude_envelope` | Σ dt where `ATT.Roll/Pitch` outside declared band, dt capped at 0.5 s | `ATT` + procedure's `attitude_stable` | s | dataflash | `None` + reason | **Frame mismatch — F-05.** |
| `mode_transition_latency_max` | max recorded `set_mode` step duration | run record `steps[].seconds` | s | **wall clock** | `None` + "no mode change recorded" | **Unit/time-base mismatch — F-04.** |

### 8.1 The two real problems

**F-04 — `mode_transition_latency_max` is wall-clock seconds in a set of
vehicle-clock seconds.** `step.seconds` is set at
[procrunner.py:1167](../argazui/argazui/procrunner.py#L1167) as
`time.time() - at`. Every other metric with unit `s` is measured on the
dataflash clock. The `unit` field says `"s"` and the `source` field says "the
recorded duration of each set_mode step", which is true but does not name the
clock. Consequences:

* `regression.py` compares the two runs' values with a 10% tolerance and a
  0.1 s floor. SITL speedup is **not** one of `fingerprint.IDENTITY_FIELDS`, so
  two runs at different speedups are `comparable` and this metric will differ by
  the speedup ratio. At speedup 1 vs speedup 5 that is a 5× change, reported as
  `DEGRADED` with a `regression` failure category, caused by nothing but a
  command-line argument.
* `campaign.statistics` will report a standard deviation that is largely CI
  runner load.

**F-05 — `time_outside_attitude_envelope` and the `attitude_stable` criterion
have the same name, the same bands, and different windows.** The criterion is
scoped to one procedure: `self.link.stability.reset()` is called after the
overrides and before the first step (procrunner.py:1142), so it measures the
flight only. The metric is computed over the **entire dataflash log**
(metrics.py:266-291) — which for a normal run covers takeoff *and* landing and
any ground time in between, and takes its band from *the first* procedure that
declared one (metrics.py:183-187). A run can therefore report
`attitude_stable: passed, 0.0 s outside` and
`time_outside_attitude_envelope: 40 s` and both be correct answers to different
questions. Nothing in the report says they are different questions.

### 8.2 Are these engineering measurements or UI numbers?

Six of seven are engineering measurements: each names its source signal, states
its unit, is `null` with a reason when it cannot be derived rather than absent,
and is explicitly barred from affecting a verdict. `_weighted_seconds`
(metrics.py:193-204) caps sample gaps at `MAX_SAMPLE_GAP_S = 0.5` with the
same reasoning and the same constant as `StabilityWatch.MAX_GAP` — a logging
dropout can neither manufacture nor excuse time outside a band. That is the
kind of detail that distinguishes a measurement from a number.

The seventh, `mode_transition_latency_max`, is currently closer to a UI number
than a measurement, for the reason above.

---

## 9. Reproducibility Audit

### 9.1 What a run records

`fingerprint.capture()` ([fingerprint.py:154](../argazui/argazui/fingerprint.py#L154))
produces, per run: Argaz version + commit + describe + dirty; ArduPilot commit
+ describe + dirty + firmware string + firmware commit +
`firmware_matches_checkout`; SITL_Models commit/dirty; Gazebo version; ROS
distro; Python version + executable + pymavlink version + platform; the model
record (`MODEL_RECORD_KEYS`, 10 fields) plus a `config_hash` over the registry
entry **and every `.param` file it names, byte for byte**; per-procedure
`{id, schema, file, hash}` plus one combined `procedure_hash`; the declared
scenario faults; `paths.source_summary()`; and an `unknown[]` list giving a
reason for every field that could not be determined.

The discipline is exemplary. Three details deserve credit:

* **Nothing is guessed.** `git_identity` returns `commit: None` plus a reason
  for a non-checkout, and `_note()` records why (fingerprint.py:176-178). The
  module states the rule at lines 15-22 and honours it everywhere.
* **The procedure hash is over the verbatim YAML the run executed**, not the
  file on disk, which may since have been edited (runs.py:186-189).
* **`normalise()` exists because of a real bug** — a freshly flown run and a
  regenerated report of the same flight produced different hashes and refused
  to compare with each other. The fix and its reason are both written down.

### 9.2 Can another engineer reconstruct the test?

**Mostly — with four named gaps.**

| Required to reproduce | Recorded? |
|---|---|
| Argaz commit | Yes (+ `dirty`) |
| ArduPilot commit and the binary that flew | Yes, both, with a mismatch flag |
| Gazebo version | Yes (`gz sim --version`) |
| ROS distro | Yes, or a stated reason it is unset |
| Python/pymavlink/platform | Yes |
| Model configuration + parameter files | Yes, content-hashed |
| Procedure content | Yes, hashed and archived verbatim in `scenario.yaml` |
| Scenario/fault declaration | Yes (and covered by `procedure_hash`) |
| Schema versions | Yes, per-artefact via `producer_schema` in `evidence.json` |
| Ports / config paths | Yes, via `paths.source_summary()` |
| **SITL speedup** | **No** — not captured anywhere in the fingerprint, despite `MavlinkLink._speedup` being measured and used for temporal criteria and RC keepalive |
| **Simulated eeprom state at launch** | **No** — see F-07 |
| **Regression thresholds in force** | **No** — `source_summary()` records the *key names* of the `[regression]` table, not the values (paths.py:153-154) |
| **Uncommitted changes** | **Partially** — `dirty: true/false` is recorded but not what changed, and `dirty` is not an identity field (F-08) |

A recorded hash is not by itself reproducibility, and this project mostly knows
that. The one place it slips is that `IDENTITY_FIELDS` compares four hashes and
none of the `dirty` flags, so two runs from two different dirty working trees
of the same commit compare as identical configurations.

---

## 10. Regression Audit

`regression.py` is the second-strongest module in the project after
`procrunner.py`.

**Compatibility** ([regression.py:197](../argazui/argazui/regression.py#L197))
is two-tier and correct:

* *Hard blocking*, no override: different `model_id`, different procedure sets,
  or either side carrying no metrics. These make the runs "not about the same
  thing".
* *Configuration drift*, overridable only by an explicit
  `ignore_config_drift=True`: any of the four `IDENTITY_FIELDS`
  (`model.config_hash`, `procedure_hash`, `ardupilot.commit`,
  `ardupilot.firmware_commit`).
* **A field that is `None` on either side counts as a difference**
  (fingerprint.py:326-330), with the reasoning stated: it is not a claim that
  they differ, it is a statement that nothing can show they are the same. This
  is the right default and it is unusual to see it chosen.

**Delta computation** (`_classify`, regression.py:230-243): absolute delta
always; relative only when the baseline is non-zero; `UNCHANGED` when
`|delta| <= floor` **or** `|relative| <= tolerance`. The floor exists because
"an RMS tracking error of 0.02° that becomes 0.04° is +100% and means nothing",
and per-metric floors are tabulated at `DEFAULT_FLOORS` in each metric's own
unit. The direction of "worse" comes from the metric's declared `better` field
rather than a hard-coded assumption, with the reason stated (metrics.py:42-46).

**Verdicts** are three-way — `passed` / `regressed` / `incomparable` — and
`incomparable` classifies as an **`evidence`** failure, not a `regression` one
(failures.py:420-443), because two runs that do not line up have not shown that
anything got worse. The CLI mirrors this with exit codes 0/1/2
(`__main__.py:269`).

### False-regression / false-non-regression scenarios

| Scenario | Outcome | Assessment |
|---|---|---|
| Different SITL speedup | **False regression** on `mode_transition_latency_max` | F-04 |
| Gazebo upgraded between runs | **False non-regression** — physics changed, `gazebo.version` is recorded but not an identity field | F-08 |
| Uncommitted ArduPilot changes | **False non-regression** — `dirty` not an identity field | F-08 |
| Baseline chosen by recency | Possible, via `previous_run_for()` | Correctly guarded: the docstring says it is "for the UI's convenience and nothing that must be reproducible", and CI is told to name its baseline (regression.py:168-174) |
| Metric present in one run only | `INCOMPARABLE` with a stated reason, not silently dropped | Correct |
| Metric `null` on one side | `INCOMPARABLE`, carrying the `detail` explaining why it could not be measured | Correct |
| Baseline of exactly zero | Floor is the only test; documented at regression.py:236-237 | Correct |

**The gap is integration, not logic.** No workflow invokes `argazui compare`.
`docs/ci.md:60-67` presents the exit-code contract as a snippet a reader could
add. So the regression system, which is well built, currently has zero
automated consumers. See F-16.

---

## 11. Repeatability Campaign Audit

`campaign.py` and its execution path in `app.py:513-605` were audited.

**What is right:**

* **A campaign has no storage format of its own.** It is a campaign id stamped
  into N ordinary run directories; the document is recomputed by `aggregate()`
  every time it is asked for (campaign.py:305-312). A campaign summary that
  could not be recomputed from its runs "would be a fourth kind of claim with
  no evidence under it" — the reasoning is right and it is implemented.
* **Retries never become clean passes.** `_verdict_for` (campaign.py:240-250)
  maps `status == passed and flaky` to `FLAKY`, and `pass_rate` counts only
  `PASSED` (campaign.py:356-360). The status table applies the same rule
  independently. **This is the audit brief's explicit test and the
  implementation passes it.**
* **`consistency()`** (campaign.py:403-422) checks that every iteration really
  flew the same fingerprint, and the rendered document says plainly that if
  they disagree "any spread below measures the difference as much as it
  measures the aircraft". Very few projects check the premise of their own
  repeatability claim.
* **Statistical restraint.** `MIN_SAMPLES_FOR_SPREAD = 3`; `stdev` is `None`
  rather than `0.0` for a single value; `spread_reported` is emitted so a
  reader never has to work out whether a missing spread means "identical" or
  "not enough runs"; no p-value, confidence interval or reliability figure is
  computed anywhere, and the rendered document says why (campaign.py:472-475).
* **A launch failure does not stop the campaign** — it is recorded as an
  `environment` failure for that iteration and the campaign continues, because
  "three of five starts failed" is itself a result about repeatability
  (campaign.py:186-195).
* **Iterations use the real START/STOP path** (`_CampaignIteration`,
  app.py:755-804), so a campaign's claim is about the code path people use.

**What is not right:**

* **F-07 — iterations are not state-independent.** Each iteration is a real
  process lifecycle, but every iteration of a given model runs in the same
  `argazui/run/<model_id>/` and inherits the same `eeprom.bin`. There is no
  `-w`. `tests/sitl.py:186-201` *does* wipe, so tier-1 campaigns are isolated
  and UI/tier-2 campaigns are not.
* **F-19 (LOW) — `CampaignRunner._one` never updates `row["verdict"]`**
  (campaign.py:177-203). It is initialised to `INCOMPLETE` and returned
  unchanged, so every live progress row streamed to the browser reads
  "incomplete" regardless of outcome. The final document is computed from disk
  and is correct; only the live view is wrong.
* **F-20 (LOW) — the pre-arm wait is silent on failure.**
  `_CampaignIteration.__init__` (app.py:787-792) polls for up to 240 s and then
  proceeds whether or not pre-arm passed, with no record that it timed out. The
  subsequent `arm` step will fail and be classified `vehicle_readiness`, so the
  outcome is right; the diagnosis loses four minutes of context.

---

## 12. Fault Injection Audit

Two fault families, four kinds, implemented in
[faults.py](../argazui/argazui/faults.py) (462 lines).

### 12.1 Mechanism, per fault

| Fault | Injection point | Mechanism | Restored? | Deterministic? |
|---|---|---|---|---|
| `gps_loss` | vehicle parameter | `SIM_GPS1_ENABLE = 0`, or `SIM_GPS_DISABLE = 1` on older ArduPilot | Yes, to the value read immediately before the write | Yes |
| `gps_degradation` | vehicle parameter | `SIM_GPS1_NUMSATS` and/or `SIM_GPS1_FIXTYPE` | Yes | Yes |
| `mavlink_interrupt` | ArgazUI's own socket | `_link_fault = {drop_one_in: 1, block_tx: True}` — every received message discarded unread, no HEARTBEAT and no RC_CHANNELS_OVERRIDE transmitted | Yes (flag cleared) | Yes |
| `mavlink_degradation` | same | every Nth received message discarded **by count** | Yes | Yes |

The `mavlink_interrupt` mechanism is the best-reasoned piece of fault work
here. The comment at [mavlink_link.py:545-554](../argazui/argazui/mavlink_link.py#L545)
identifies that ArduPilot's GCS failsafe keys on `sysid_mygcs_seen`, called from
exactly three handlers (HEARTBEAT, RC_CHANNELS_OVERRIDE, MANUAL_CONTROL), that
ArgazUI sends the first two and never the third, and that withholding them is
therefore "a complete model of the ground station going away rather than an
approximation of one". That is a claim traced to upstream source, and it is
correct.

Determinism is by construction: `drop_one_in` counts received messages
(`_rx_seen % drop_one_in`), so two runs of the same scenario discard the same
packets. `drop_one_in: 1` is refused for `mavlink_degradation` with the message
"that is `mavlink_interrupt` — declare that instead, so the run record says
what actually happened" (faults.py:436-442).

### 12.2 The critical distinction

> `fault successfully injected` must NOT automatically mean
> `vehicle handled fault correctly`.

**This is correctly implemented, in four independent places:**

1. `FaultResult` carries `applied`, `held_s`/`evidence_seen`, `expect`/`recovery`
   and `passed` as four separate fields, none derived from another
   (procrunner.py:189-244).
2. A fault declaring neither `expect:` nor `recovery:` is **refused at load
   time** with an explicit message: "A fault with no criteria proves only that
   the fault was injected, which is not a result about the aircraft"
   (procedures.py:690-695). Without this, `all([])` would have made every
   criterion-free fault pass.
3. Every fault must declare an `evidence:` list of signals its verdict rests on
   (procedures.py:697-708). If any required signal was never observed,
   `result.passed` is left `False` and the text is "not judged"
   (procrunner.py:954-959).
4. `_resync()` (procrunner.py:817-848) waits for the vehicle clock to advance
   before any `recovery:` criterion is evaluated. The reasoning is exact: the
   moment a fault is lifted, `link.state` still holds pre-fault values, so
   `{armed: true} within 15s` would pass "after 0 ms" against a reading the
   blackout itself froze. Most implementations of fault injection have this bug.

### 12.3 Fail-closed

`_prepare_faults` (procrunner.py:777-798) probes every declared fault **before
the first step and before any override**, so a scenario whose mechanism is
missing costs nothing and changes nothing. `GpsInjector.probe` tries both
parameter families and raises `FaultUnavailable` if neither answers; it also
refuses a degradation whose knobs do not exist ("nothing would be degraded",
faults.py:290-297). The procedure aborts.

**But the abort is classified `acceptance`, not `environment`.** faults.py:196-202
states: "The runner turns it into an aborted procedure with an `environment`
failure classification — never into a nominal flight." The second half is true;
the first is false. See F-02.

### 12.4 Host safety

Checked directly: every mechanism writes either a `SIM_*` parameter over
MAVLink or a flag in this process. There is no filesystem write, no `iptables`,
no `tc`, no raw socket, no privileged call anywhere in `faults.py`. The claim
"the mechanisms simply do not exist outside a simulator, which is a stronger
guarantee than a flag" (faults.py:21-24) is accurate. **The fault injection
cannot affect the host.**

The one host-visible effect is that `mavlink_interrupt` stops ArgazUI's own
socket traffic, which is by design and is surfaced in the UI (`link_fault` in
`Manager.status()`, app.py:745-748) so a status bar reporting "no telemetry"
during a deliberate blackout does not read as a broken tool.

### 12.5 Coverage of the fault layer

`docs/coverage.md` reports 4 of 6 fault items covered. Two of the four
implemented *mechanisms* — `gps_degradation` and `mavlink_degradation` — are
declared in `faults.KINDS` and used by no shipped procedure. They are code
paths with unit tests (`tests/test_faults.py`, 453 lines) and no flight
evidence.

---

## 13. Traceability Audit

The chain the brief asks about was checked link by link against
[trace.py](../argazui/argazui/trace.py) and a real run record.

| Link | Identifier | Explicit / implicit / derived / fragile / missing |
|---|---|---|
| Test intent | `test_id` | **Explicit.** pytest node id when a test drove it; the literal string `manual` when a person did, "because *flown by hand* is a real answer and it is the one that says no test asserts anything about this" (trace.py:62-64). |
| Procedure | `procedure_id` | **Explicit.** The YAML `id`, forced equal to the filename stem (procedures.py:741-743). |
| Step | `step_id` = `<proc>#s3` | **Derived by design**, and the design is argued: a step id is only read inside its own run, so position is a good enough name (trace.py:30-36). Author declaration is supported. |
| Criterion | `criterion_id` = `<proc>#alt-held` | **Explicit in all 13 shipped procedures.** Declared ids are validated against a narrow regex (trace.py:55) and must be unique per file. `declared_id: false` is recorded when one was derived, and `derived_ids()` reports them, "because a reader comparing two runs needs to know which of the names they are matching on are that kind". |
| Fault | `fault_id` = `<proc>#gps_off` | **Explicit.** Schema requires `id`. |
| Metric | `metric_id` = `key@procedure` | **Explicit**, and back-compatible: the older `identity` field is retained alongside (metrics.py:127-135). |
| Run | `run_id` = `<UTC>_<model>` | **Explicit.** |
| Evidence | manifest paths | **Explicit**, and cross-checked. |
| Verdict | `status` + `failure` | **Explicit.** |

### 13.1 Integrity checking

`integrity()` (trace.py:247-307) is not decorative. It detects duplicate step
and criterion ids, criteria whose id names a different procedure than the one
they were recorded under, metrics scoped to a procedure the run never executed,
chain-referenced artefacts the manifest does not list as present, and a missing
verdict. It is exposed at `GET /api/runs/{id}/trace` alongside `derived_ids`.
`tests/test_traceability.py` (290 lines) asserts every shipped criterion
declares its own identifier.

### 13.2 Can a reviewer walk backwards from a failed verdict?

**Yes, and this was tested against the published data.** From
`docs/status.md:138-144`, a reviewer holding only the failed `skycat_tvbs` row
gets: category `acceptance`, code `criterion-failed`, the run id
`20260810T044747Z_skycat_tvbs`, the procedure `tailsitter_takeoff`, the failing
criterion by label ("held a nose-up hover instead of tumbling"), and the
measurement that produced the verdict ("pitch outside [55,115]° for 15.3s; turn
rate above 90°/s for 0.0s (peak 76°/s) — allowed 3s each, measured over 15s").
That is intent → run → procedure → criterion → measurement in one table cell,
and it is better than most commercial tooling.

### 13.3 Orphans found

* **Orphaned criteria:** 8 of 32 declared criteria have never been evaluated
  (`docs/coverage.md`), all in the four procedures that no run has executed.
* **Orphaned procedures:** 4 of 13 (`plane_land_rtl`, `plane_takeoff_auto`,
  `tailsitter_land`, `vtol_takeoff_mission`).
* **Orphaned fault mechanisms:** 2 of 4 (`gps_degradation`,
  `mavlink_degradation`).
* **Unattributable results:** 50 evaluated criterion results carry no
  `criterion_id` because they predate v1.5. The report refuses to attribute
  them by position and says why. Correct, and it means the published 75%
  criterion coverage rests on a smaller body of evidence than the figure
  suggests.
* **Orphaned evidence:** none found — `integrity()` checks this and the tier-1
  chain test passes.

### 13.4 The fragile link

The chain is broken in one place, and it is the same string-matching problem as
A-3: whether a criterion was *evaluated* is recovered from localized prose, and
`status.claims_of` uses a different rule from `trace._was_evaluated`. Probed
directly:

```python
criterion text: "not judged — 'angular_rate_above' rests on attitude
                 telemetry that never arrived."
status.claims_of()      -> 'failed'          ← rendered as an aircraft failure
trace._was_evaluated()  -> False             ← correctly "not evaluated"
coverage._exercised()   -> excluded          ← correctly not covered
```

Three modules, one question, two answers. See F-10.

---

## 14. Evidence Integrity Audit

`evidence.py` answers the brief's nine questions almost exactly.

**1. What is mandatory?** Six artefacts, always: `result.json`,
`scenario.yaml`, `console.log`, `mavlink_events.jsonl`, `versions.txt`,
`fingerprint.json`. Plus the dataflash `.BIN` **conditionally** — required if
and only if the vehicle armed, because ArduPilot ships `LOG_DISARMED=0` and a
session that never armed writes none. The condition is evaluated from the run's
own record, not guessed (`_armed`, evidence.py:140-148).

**2. What is optional?** `report.json`, `report.md`, `params_full.txt`,
`params_diff.txt`, `plots/`, `regression.json`, `regression.md` — **but only
with a stated reason.** An optional artefact absent with no explanation is
reported as `absent_unexplained`, because "there are no plots because
matplotlib is not installed" and "there are no plots" are different facts and
only one of them is an answer (evidence.py:22-31). This three-level model is
the correct one and I have not seen it in a project of this size before.

**3. How is missing evidence detected?** `capture()` reads the directory rather
than trusting the run record — explicitly, "the point of the manifest is to
catch the case where the record says an artefact was written and it is not
there" (evidence.py:298-301). A directory that exists and is empty is treated
as absent ("absence wearing a folder", evidence.py:282-285).

**4. Can evidence be silently overwritten?** Partially. Run directories are
timestamped to the second and `mkdir(exist_ok=True)`, so two runs of the same
model starting in the same second would share a directory and append to each
other's `console.log`/`mavlink_events.jsonl`. Not reachable through the UI
(START is serialised by `self.lock`) but reachable through the tier-1 suite if
two tests boot the same model id in the same second. LOW.

**5. Can a result exist without its evidence?** Yes, and it is detected:
`classify_run` returns `EVIDENCE`/`evidence-artefact-missing` for any missing
required artefact (failures.py:388-392), and `evidence.complete: false` is
folded into `result.json`. **A run whose procedures all passed can still fail
on its evidence**, which is the correct rule and is implemented at
runs.py:394-399.

**6. Can evidence exist without a result?** Yes — an interrupted session leaves
a directory with no `result.json`. It is listed as `incomplete` rather than
hidden, "because a crashed run is precisely the one worth opening"
(runs.py:829-833). Correct.

**7. Can reports reference nonexistent artefacts?** `trace.integrity()` flags
`missing-evidence` for any chain reference the manifest does not list as
present. Checked and working.

**8. Are the hashes useful?** Yes, with one honest exclusion. SHA-256 over
every artefact except `result.json`, which is deliberately unhashed with the
reason recorded in the manifest itself: it is rewritten when the flight report
completes, "so a hash of it would be correct at one moment and wrong at the
next" (evidence.py:80-91). Files over 256 MB are unhashed with a stated reason.
The manifest embedded in `report.md` carries no hashes at all, because the
report is itself an artefact the manifest covers and two documents disagreeing
about the digest of a third would be an artefact of write order
(evidence.py:384-399). The double-capture in `_refresh_evidence`
(runs.py:749-769) is not belt-and-braces; the ordering argument is spelled out
and is correct.

What the hashes do **not** provide is tamper-evidence: they are stored in the
same directory as the files they cover, unsigned. Fine for the stated purpose
(detecting incomplete or truncated evidence); it should not be read as
integrity against modification.

**9. Is the evidence set sufficient to review the verdict independently?**
**Yes for the flight, with one gap.** A reviewer receives the procedure
verbatim, every step with its measured text, every criterion with what was
measured on which clock, the parameter changes and whether they were restored,
the autopilot's own full-rate log, the parameter dump, the environment
fingerprint, and the ten-section report. The gap is the one in §6.3: for the
condition types listed there, the recorded measurement (`alt=0.0m`) cannot
distinguish a real reading from an unwritten field.

### Why should a skeptical engineer trust this PASS?

Because they do not have to. They can open `scenario.yaml` and read the exact
YAML that ran, check its hash against the fingerprint, open the `.BIN` with
`MAVExplorer.py` (the command is printed in the run listing), and re-derive
the metrics with `python3 -m argazui report <run>` — which takes the same path
as the original and must produce the same fingerprint. **That is a genuinely
strong position.** The reservation is narrow and specific: for `alt_below`,
`climb_rate_below`, `armed` and `mode` criteria, they should independently
confirm from the `.BIN` that the corresponding stream was flowing, because the
`expect` block cannot tell them.

---

## 15. Coverage Audit

Five dimensions in `coverage.py`; four in the published `docs/coverage.md`.

| Dimension | Covered / declared (published) | Meaningful? |
|---|---|---|
| Models | 10 / 11 (91%) | **Yes.** Read from `suite.json` tier-2 markers only, with skips explicitly excluded ("A skip is not coverage. It is the absence of it.", coverage.py:240-245). Tier-1 runs *cannot* contribute. |
| Procedures | 9 / 13 (69%) | **Yes**, and the 4 uncovered are named. |
| Criteria | 24 / 32 (75%) | **Yes**, with the important refinement that a criterion the procedure never *reached* is not covered — `_was_evaluated` is applied (coverage.py:290-297). |
| Faults | 4 / 6 (67%) | **Yes**, counting both mechanisms and per-scenario declarations, and requiring `applied: true`. |
| Experiments | **absent from the published report** | Declared in `coverage.py:183-200` and `DIMENSIONS`; `docs/coverage.md` has no such section. |

**Is it meaningful, or file counting?** Meaningful. The design refuses the
three usual cheats: it does not count tests, it does not count a skip, and it
does not attribute a pre-v1.5 criterion result by position (50 such results are
reported as unattributable rather than folded in). `_pct` returns `None` rather
than 100% for an empty dimension, "because a dimension with no items is not
fully covered; it is empty, and the two read identically as a percentage".

**Is it reproducible?** Yes — recomputed from disk every time, no accumulator.

**Is it misleading anywhere?** Two places:

* The published artefact is stale (F-06): generated 2026-08-10T15:08 from v1.5,
  missing v1.6's fifth dimension entirely. A reader of `docs/coverage.md` today
  is told v1.6 declares four coverage dimensions when it declares five, and is
  told nothing about the two experiments the release was built to add.
* Coverage never expires. A criterion covered by a run from any date counts as
  covered forever. The report says "it does not mean the item was exercised
  recently", which is honest but means the figure only ever goes up as runs
  accumulate on disk.

**Uncovered areas not visible in any dimension:** the `ros2_launch` launch
method (only `iris` uses it and it is untested); the `upload_mission` step type
(only used by the two uncovered mission procedures); `rc_release`,
`get_param`'s `store_as`, `send_command` with `type: int`, and `on_fail:
continue` — none of these step features has flight evidence.

---

## 16. Validation Boundary

**This is the project's strongest area and it deserves to be said plainly.**

`docs/verification-vs-validation.md` opens with a two-row table stating that
verification is "what it does" and validation is "no". The page then explains
*why it exists*: "Because the gap closes by itself in a reader's head. A page
of passing checks, a coverage figure, a run directory full of hashed artefacts
and a traceability chain that resolves — all of it reads as *this aircraft
works*. None of it says that." That is an unusually clear-eyed statement about
the project's own failure mode.

The boundary is not only documented, it is **mechanised**:

* `limitations.py` defines four non-interchangeable categories (assumptions,
  model limitations, unverified physical effects, out of scope) with an argued
  reason they must not be collapsed into a "notes" field;
* `limitations.STANDING` carries statements that are printed on **every**
  experiment document whatever the file says, so a definition cannot quietly
  drop one. They include "A SITL frame is a generic airframe of its class. It
  is not a model of any particular aircraft", "No part of it has been compared
  against a measurement of a real aircraft by anything in this repository", and
  "Sensor failure modes are simulated by changing a parameter. Real receivers,
  IMUs and radio links fail in ways no parameter reproduces";
* an experiment that declares no limitations of its own gets an explicit
  paragraph saying so, and pointing out that "the limits that matter most to a
  particular question are usually the ones only its author knows"
  (limitations.py:293-299);
* the flight report's tenth section is "Limitations and non-claims"
  (`flightlog._non_claims`);
* `docs/status.md` carries the heading "**Anything not listed here was not
  verified** — not by this project, and not by the table above. In particular,
  no model has been flown through a mission, in wind, at the edges of its
  envelope, or repeatedly enough to say anything about reliability."

**Claims implying `SITL PASS = real aircraft validated`: one found.**

`README.md:3` — "**A local control and validation platform for ArduPilot SITL
and Gazebo**". The project's own vocabulary reserves "validation" for the thing
it explicitly does not do. `README.md:619` repeats it: "Docker:
clean-environment validation". Both are almost certainly using the word in its
colloquial sense, but this is the one repository where that reading is not
available: `docs/verification-vs-validation.md` exists to forbid it. Recorded
as F-13.

No other overreaching claim was found. `README.md:228-230` states the
distinction correctly ("Tier 1 can prove the first. Only tier 2 can prove the
second"), and `README.md:527-530` defines `untested` as "not yet verified by a
machine — it does not mean broken, and it does not mean working".

---

## 17. Configuration Management

### 17.1 Sources and precedence

`paths.py` defines a single, documented precedence chain
([paths.py:73-81](../argazui/argazui/paths.py#L73)):

```
CLI override  >  ARGAZ_* environment variable  >  argaz.toml  >  auto-detected default
```

`argaz.toml` is located by `ARGAZ_CONFIG`, then `<repo>/argaz.toml`, then
`<repo>/argazui/argaz.toml` — deliberately never the caller's CWD
("without making the caller's CWD special", paths.py:44). Relative paths in the
TOML resolve against the TOML's own directory, so the shipped
`argaz.toml.example` contains no machine-specific paths.

Configuration layers found:

| Layer | File | Validated? | Schema? |
|---|---|---|---|
| Application config | `argaz.toml` | Type-coerced (`int(...)`); a malformed TOML raises at import | No schema |
| Model registry | `config/models.json` | **Not validated at all** | No schema |
| Button definitions | `config/buttons.json` | Not validated | No schema |
| Procedures | `procedures/*.yaml` | **Heavily validated** | Versioned 1–4, documented in SCHEMA.md |
| Experiments | `experiments/*.yaml` | **Heavily validated** | Versioned 1, documented in SCHEMA.md |
| Environment | `env.sh`, `quadplane_env.sh` | Sourced into the pty; checked by `doctor` | n/a |
| Runtime overrides | procedure `overrides:` | Declared, reasoned, restored, recorded | Part of procedure schema |

### 17.2 Findings

* **The declarative layers are exemplary and the JSON layers are unguarded.**
  A procedure with an unknown key fails at load with a message naming the
  alternatives. `models.json` has no schema, no validator and no test that
  every entry is well formed — and it is the file whose fields are interpolated
  into a shell command line (F-09).
* **Generated configuration is marked as such.** `argazui_overrides.parm`
  carries a header saying "Bu dosyayi elle duzenleme" and names its source
  field (session.py:194-197).
* **`api_rescan` merges rather than overwrites** (`merge_registry`,
  app.py:1246-1254), so a hand-edited registry entry survives a rescan.
* **No runtime state leaks into persistent configuration.** Verified: the only
  writes outside a run directory are `models.json` (explicit rescan) and the
  generated `.parm` in the model's own working directory.

### 17.3 Can two engineers unknowingly run different configurations?

**Yes, in four ways, and three of them are invisible in the fingerprint:**

1. **Different `eeprom.bin` state** in `argazui/run/<model_id>/` — the largest
   one, since it holds every parameter the vehicle has ever been told to keep
   (F-07).
2. **Different SITL speedup** — not recorded anywhere.
3. **Different regression thresholds** in `[regression]` — `source_summary()`
   records the key names, not the values.
4. **Different `models.json`** — this one *is* covered: `model.config_hash`
   hashes the registry entry and every `.param` file it names.

`paths.source_summary()` is embedded in every fingerprint, which covers paths
and ports. The gaps above are the ones a reader would not notice.

---

## 18. Process and Session Management

Covered mechanically in §5.2. This section addresses abnormal termination.

| Interruption | Behaviour | Assessment |
|---|---|---|
| **Ctrl+C on the server** | FastAPI `shutdown` hook calls `mgr.stop()` if a model or run is active, then closes both terminals (app.py:1310-1318) | **Correct.** The comment states the reason: "a server closed with Ctrl+C must also complete its run; otherwise a real flight's artefacts would be left half-written". |
| **Browser/UI crash** | No effect on the server. The run continues; the WebSocket client is discarded from `hub.clients`. | Correct — the browser is a view. |
| **Python exception in a procedure** | Caught by `except Exception` in `run()`; outcome `error`, distinct from `failed`, with the type and message recorded. `_restore` and `clear_link_fault` still run from `finally`. | **Correct**, and the comment records that before this fix the exception escaped into the procedure thread and "the UI simply stopped updating". |
| **Gazebo crash** | Undetected as an event. SITL loses its physics backend, telemetry stops, `state.connected` goes false after 5 s, temporal windows fall back to the wall clock and record `clock: "wall"`, `_wait_for` times out, the step fails, classification is `procedure`/`step-timeout`. | **Degrades safely but diagnoses poorly.** Nothing says "Gazebo died". |
| **SITL crash** | Same path. `_copy_dataflash` finds a `.BIN` and `verify_dataflash` reports `complete: false` with the reader's exception, producing an `evidence`/`dataflash-truncated` failure. | **Good** — the truncation check exists exactly for this and is not optional. |
| **MAVProxy crash** | 14550 goes silent; `MavlinkLink` sees no heartbeats. SITL is still running and still writing its log. | Detected as a link loss; not distinguished from a vehicle loss. |
| **Server SIGKILL** | `console.log` and `mavlink_events.jsonl` are written append-as-you-go and flushed per record (runs.py:212-236), so the directory holds everything up to the moment of death. No `result.json`, so the run lists as `incomplete`. | **Correct, and deliberate** — runs.py:26-30 states this is the case where the evidence is most wanted. |
| **Orphan processes after a crash** | **Not recovered.** The `/proc` walk needs the session id, which lived in the dead process. A crashed server leaves `gz sim`, `sim_vehicle.py`, SITL and MAVProxy running, holding 14550/5760, and nothing detects or reports this at the next START. | **F-12.** `start.sh` diagnoses a held HTTP port (the tier-1 image installs `ss`/`ps`/`curl` for exactly this) but nothing performs the equivalent check for the MAVLink ports. |
| **Temporary files** | The pty's `.bash_history`, `mav.tlog`, `mav.parm`, `eeprom.bin` and `logs/*.BIN` accumulate in `argazui/run/<model_id>/` indefinitely. `logs/` in the repo root already holds 12 `.BIN` files; `argazui/run/` holds 27 model directories. | **F-22 (LOW)** — no retention policy anywhere. |

---

## 19. Failure Mode Analysis

Built from reading the implementation and from the probes described in §6.3
and §12.3.

| # | Failure | Expected behaviour | Actual behaviour | Severity |
|---|---|---|---|---|
| 1 | Gazebo fails to start | Detected as `environment`, named | `sleep 6`, then no heartbeat for 180 s, then `mavlink_failed` in the terminal. Procedure steps time out → classified `procedure`/`step-timeout`. Never `environment`. | **HIGH** (F-14) |
| 2 | SITL fails to start | Detected as `environment` | Same path as 1. In the *test* path, `SitlUnavailable` is raised in 30 s with SITL's stderr tail and the test **skips** — correct there. | HIGH (F-14) |
| 3 | MAVLink unavailable | Named as a link failure | `wait_ready` returns False, `mavlink_failed` logged; procedure submit returns `{"ok": False, "text": no_link}` → step fails → `procedure`. Not `infrastructure`. | MEDIUM |
| 4 | Vehicle never becomes ready | `vehicle_readiness` | **Correct.** `arm` step fails, `READINESS_STEPS` maps it to `vehicle_readiness`/`arm-refused`, and the autopilot's own STATUSTEXT is in `detail`. `swan_k1_hwing` in `docs/status.md` is a live example. | — |
| 5 | Procedure timeout | `procedure`/`step-timeout` | **Correct** for a step timeout (`_TIMED_OUT` regex matches both languages). **Wrong** for the procedure-level `timeout:` — no step is marked failed, so it falls to the criterion loop and classifies `acceptance`. | **CRITICAL** (F-02) |
| 6 | Missing DataFlash | `evidence`, with a reason distinguishing "never armed" | **Correct and careful.** `_ever_armed()` parses every JSONL line's `kind` field rather than substring-searching, specifically because a STATUSTEXT `"Arm: not armed"` would invert the answer (runs.py:465-473). | — |
| 7 | Truncated DataFlash | `evidence`/`dataflash-truncated` | **Correct.** `verify_dataflash` requires a parse to completion *and* a timestamped last record. | — |
| 8 | Malformed procedure | Fails at load, names the problem | **Correct and strict.** 40+ specific errors; `load_all` raises rather than skipping a bad file. | — |
| 9 | Missing metric | `null` + stated reason; comparison `incomparable` | **Correct.** `compute()` emits `value: null` with `detail` rather than omitting the key, "because an absent key and a measurement that could not be made look identical to a reader, and only one of them is a fact". | — |
| 10 | Regression input incompatible | `incomparable`, exit 2, classified `evidence` | **Correct.** Blocking reasons and drift are reported separately with field names. | — |
| 11 | Fault injection unavailable | Abort, classified `environment` | Aborts (correct). Classified **`acceptance`** (wrong). | **CRITICAL** (F-02) |
| 12 | Fault cannot be cleared | Not a verdict about the aircraft; the simulator is still degraded | **Correct.** `result.text = fault_not_cleared`, `passed` stays False, and `classify_procedure` maps `cleared is False` to `environment`/`fault-not-cleared`. | — |
| 13 | Telemetry never arrives for a `for`/`never` criterion | Refuse to judge | **Correct.** `_unmeasurable` returns "not judged". | — |
| 14 | Telemetry never arrives for an `eventually`/`within` criterion | Refuse to judge | **PASSES** for `alt_below`, `armed: false`, `pitch_within`, etc. | **CRITICAL** (F-01) |
| 15 | Interrupted run (SIGKILL) | Partial evidence preserved, listed as incomplete | **Correct.** | — |
| 16 | Server crashes leaving simulators running | Detect and report at next START | Not detected. Ports are silently stolen. | MEDIUM (F-12) |
| 17 | Two ArgazUI instances | Refuse or allocate | Both bind 14550 (`udpin`); behaviour is undefined. `doctor` would catch it if run. | MEDIUM (F-12) |
| 18 | Procedure cancelled by the operator | Not a verdict about the aircraft | Classified `acceptance`/`criterion-not-judged`. | **CRITICAL** (F-02) |
| 19 | An override cannot be applied | `environment`/`override-not-applied` | **Correct**, and checked before steps and criteria. | — |
| 20 | Report generation fails | Log kept, reason written | **Correct.** `_make_report` catches, writes a `report.md` containing the exception and the `MAVExplorer.py` command. | — |
| 21 | NaN/Inf in telemetry or a metric | Rejected or reported | No `isfinite` check anywhere; a NaN metric propagates into `regression` and `campaign.statistics` and serialises as invalid JSON `NaN`. | LOW (F-24) |

---

## 20. Test Infrastructure

### 20.1 Composition

476 tests collected. Markers overlap by design (e2e tests also carry `tier1`,
because the marker "says which CI job runs them, not that they need a
vehicle" — docs/testing.md:150-152).

| Set | Count | What it needs |
|---|---:|---|
| `tier1` (total) | 464 | the tier-1 CI job |
| ` └ pure unit` | ~330 | nothing |
| ` └ real SITL, no Gazebo` | ~76 | an `arducopter`/`arduplane` binary |
| ` └ e2e (also tier1)` | 58 | a real server + Playwright Chromium |
| `tier2` | 12 | Gazebo + SITL_Models + the model registry |
| `container_only` | 1 | the tier image |

### 20.2 What is genuinely connected

Considerably more than is typical. `tests/support.boot()` starts a **real SITL
binary**, connects a **real `MavlinkLink`**, uses a **real `RunRecorder`** and
runs the **real `ProcedureRunner`** on the **real procedure YAML**. The only
substitution is the transport (TCP straight to SITL instead of MAVProxy's UDP
fan-out), and `MavlinkLink` was designed to take either. `tests/e2e/harness.py`
starts the real FastAPI server on a free port and drives it with a real
browser, from a throwaway copy of `argazui/` so drift tests can edit files
without touching the checkout. `tests/gazebo.py` calls
`session.build_launch_commands` itself and runs it in a real pty, with the
reason written down (a piped stdin makes MAVProxy read EOF and exit, which
cost an hour to diagnose).

**There is no mock autopilot anywhere in the suite.** For a project of this
kind that is the right call and it is unusual.

### 20.3 What each tier proves

* **Tier 1** proves: capability probing selects the right procedure for a
  frame; acceptance criteria evaluate against measured state; declared
  overrides are applied and restored; faults inject, hold, clear and are judged
  from their criteria; a run directory comes out complete, hashed and
  parseable; campaigns and experiments produce stamped independent runs; the
  server, the API and the page work in a browser. It proves **nothing about any
  Gazebo model**, and `_tier2_models()` makes that structurally true rather
  than a promise.
* **Tier 2** proves: one named registry model, in Gazebo, took off, changed
  mode and landed, meeting its criteria.

### 20.4 Execution results in this environment

```
$ python3 -m pytest -m "tier1 and not e2e" -q
1 failed, 405 passed, 70 deselected, 1 warning in 432.55s
```

The single failure is `tests/test_tier1_procedures.py::test_takeoff_mode_change_and_land[sitl_tailsitter]`.
It is **not a flake and not a defect in Argaz.** The generic
`plane-tailsitter` frame climbs past 20 m while tumbling; the run's own output
is:

```
expect [OK]   reached at least 85% of the requested altitude — alt=25.8m
expect [OK]   still armed — armed=True
expect [OK]   hovering in QHOVER — mode=QHOVER
expect [FAIL] held a nose-up hover instead of tumbling —
              pitch outside [55,115]° for 56.6s; turn rate above 90°/s for 61.8s
              (peak 1882°/s) — allowed 3s each, measured over 65s
```

Three criteria pass on an aircraft that is tumbling at 1882 °/s, and only
`attitude_stable` catches it. **This is the single best piece of evidence in
the repository that the verification design works** — it is the exact scenario
`StabilityWatch` was written for (CHANGELOG:1168-1191), reproduced live.

The failure is deliberate and documented (`docs/testing.md:138-145`: "Tuning
the airframe until our own test passes would prove nothing, and marking it
`xfail` would make the failure invisible"). The reasoning is right. The
consequence is F-15: the tier-1 job can never be green, so a *new* regression
is only visible by diffing the failing-test list.

```
$ python3 -m pytest tests/test_docs.py tests/test_localisation.py \
      tests/test_coverage.py tests/test_traceability.py \
      tests/test_evidence_manifest.py tests/test_experiments.py \
      tests/test_experiment_analysis.py -q
170 passed in 0.61s
```

Note that the 12 docs/localisation failures listed in the committed
`docs/status.md` **do not reproduce** on this checkout — they were fixed
between that CI run and v1.6, and the published table was never regenerated
(F-06).

### 20.5 Weaknesses

* **Untested failure paths.** No test covers: a launch command failing; Gazebo
  dying mid-flight; an orphan process holding a port; concurrent access to
  `Manager`; a `models.json` with a malformed entry; NaN in telemetry.
* **The classification bug is untested in the direction that matters.**
  `tests/test_failure_classification.py` (302 lines) tests each category from a
  hand-built result dict that *already contains* the discriminating field. No
  test asserts that a fault-unavailable abort classifies `environment` — which
  is why F-02 survived.
* **The evidence-guard asymmetry is untested.** `tests/test_temporal_criteria.py`
  covers the `for`/`never` guard thoroughly and never asks whether
  `eventually`/`within` have one.
* **Tests that could pass while functionality is broken:** `test_launch_commands.py`
  asserts on the generated string; it would pass unchanged with the shell
  injection of F-09 present, because the injection is in what the string is
  *made of*, not its shape.

---

## 21. CI/CD

Four workflows. What each *actually executes* was read line by line.

| Workflow | Trigger | Runs | Fails the build on |
|---|---|---|---|
| `images.yml` | push to `docker/**`, manual | Builds and pushes both tier images to GHCR | Build failure |
| `tier1.yml` | every push and PR (except `docs/**`) | `docker run … pytest tests/ -m tier1 -q` — **all 464 tier-1 tests including the 58 e2e ones** | Any test failure |
| `tier2.yml` | nightly 03:00 UTC, manual | `pytest tests/ -m tier2 -q` | Any test failure |
| `status.yml` | on `workflow_run` completion of tier1/tier2, manual | Downloads both artefacts, runs `argazui status` (which also writes `coverage.md` and the README block), commits | Nothing — it always exits 0 |

**What CI does run:** the complete unit suite, the SITL-backed tier-1 tests,
the browser e2e tests (Playwright Chromium is installed in
`Dockerfile.tier1`), the Gazebo tier-2 model set nightly, and documentation +
status + coverage generation. Localisation *is* validated, because
`test_localisation.py` is a tier-1 test.

**What CI does not run:** `argazui compare` (regression), `argazui coverage` as
a gate, `argazui experiment` as a gate, `argazui doctor` as a gate, and any
lint or type check. Confirmed by grep: no workflow file mentions `compare`,
`coverage` or `experiment` as a command.

**Can CI produce a false green?**

* **A skip is not a pass.** `conftest.pytest_runtest_logreport` records the
  setup phase too, specifically because "a skip in setup is still a
  non-result", and `FROM_TEST_OUTCOME` maps `skipped` → `UNTESTED`, never
  `PASSED`. `pytest_terminal_summary` names `container_only` skips before
  anyone reads a total. **This is handled better than in most projects.**
* **`if-no-files-found: warn`** on both artefact uploads means a job that
  produced no runs at all uploads nothing and does not fail. `status.yml` then
  reports "no completed run yet" and generates a table from whatever it has.
  A silent evaporation of tier-2 evidence would show as models reverting to
  `untested` rather than as a red build. MEDIUM.
* **`status.yml` cannot fail.** Every step either succeeds or logs. A
  generation bug produces a wrong committed table with a green tick.
* **Generated artefacts are not verified.** Nothing checks that a committed
  `docs/status.md` matches what the current code would generate. F-06 is the
  direct consequence: the shipped v1.6 carries a v1.5 status table and a
  four-dimension coverage report against five-dimension code, and CI is green
  about it.
* **The permanent tier-1 red (F-15)** means the tier-1 job's pass/fail bit
  carries no information; only the failing-test list does.

**Genuinely good CI decisions:** ArduPilot is pinned by SHA in both
Dockerfiles with the reason written out ("if the image tracked a branch, two
builds of the same Dockerfile would fly different autopilots and no two CI
results could be compared"); the checkout is bind-mounted over the image copy
so the code under test is that commit; `[skip ci]` is scoped to the bot's
commit rather than adding `README.md` to `paths-ignore`, with a paragraph
explaining why the narrower fix was chosen; and artefacts are uploaded on
failure because "a failure is a result too".

---

## 22. Localization

Two languages, English canonical. Audited for parity, wiring and engineering
terminology.

### 22.1 Parity — machine-enforced and passing

`tests/test_localisation.py` (202 lines) enforces:

* every backend `CATALOG` key has both languages;
* no Turkish entry is byte-identical to its English one, with a named
  exception list of five keys that are command syntax rather than language;
* the `en:`/`tr:` object literals in `static/app.js` have identical key sets,
  extracted by brace-matching rather than regex;
* every `data-i18n` attribute in `index.html` resolves in both languages;
* the v1.3 and v1.6 UI surfaces are named explicitly, "so a later edit that
  drops one is a failure here";
* every value in `analysis.VERDICTS` has an `exp_v_*` string, because the panel
  builds the key from the verdict word and a new verdict would render as its
  own key name;
* every `limitations` category label, description and standing statement exists
  in both languages — "a limitation shown in English to a Turkish reader is
  shown to nobody".

All of these pass here (part of the 170-test run in §20.4). This is
substantially stronger localisation testing than most projects have.

### 22.2 Terminology — reviewed as engineering, not grammar

Spot-checked against Turkish aerospace/verification usage:

| English | Turkish used | Assessment |
|---|---|---|
| verification / validation | doğrulama / geçerleme | **Correct and non-obvious.** These are the two terms Turkish engineering practice actually distinguishes, and getting them the right way round is the whole point. |
| acceptance criterion | kabul kriteri | Standard. |
| traceability | izlenebilirlik | Standard. |
| evidence manifest | kanıt listesi | Acceptable. "kanıt bildirimi" would be closer to *manifest*, but "liste" is unambiguous. |
| fault injection | arıza enjeksiyonu | Standard in the field. |
| repeatability campaign | tekrarlanabilirlik kampanyası | Correct; "kampanya" is a loan but is used this way. |
| attitude envelope | tutum zarfı | **Questionable.** Turkish aerospace normally uses *yönelim* or *duruş* for attitude; *tutum* is the psychological sense. `metrics.py:96` uses "Tutum zarfinin disinda gecen sure". Not wrong enough to mislead an engineer, but not the field's word. |
| coverage | kapsam | Standard. |
| baseline | referans | Correct choice — "temel çizgi" would be a literal translation of nothing. |
| angular rate | açısal hız | Standard. |
| pre-arm | arm öncesi | Pragmatic; "arm" is untranslated throughout, which is right — Turkish ArduPilot users say "arm". |

The prose is written *as engineering*, not translated word for word. Compare
`limitations.py` EN "Physics that was absent from the simulation, or present in
it and never compared against anything real. These are the reasons not to
extrapolate" with TR "Simulasyonda hic bulunmayan ya da bulunup gercek hicbir
seyle karsilastirilmamis fizik. Sonucu genellememek icin gerekcelerdir." That
is a rewrite by someone who understood the sentence.

**One systematic oddity:** Turkish text is inconsistent about diacritics.
`i18n.py` and `limitations.py` are written in ASCII-folded Turkish
("Simulasyon varsayimlari", "gecerlenmemis"), while `docs.py` page titles use
proper Turkish ("Doğrulama", "Yapılandırma", "Değişiklik günlüğü") and the
`docs/*.tr.md` files are fully diacriticised. A Turkish reader sees correctly
spelled navigation and ASCII-folded body text in the same panel. Recorded as
F-23 (LOW).

### 22.3 The real localisation gap

**12 of the ~30 documentation-portal pages have no Turkish source at all.**
Those pages resolve to the English file with an in-portal notice
(`docs_untranslated`, verified by `test_a_page_without_a_turkish_source_is_flagged_rather_than_silently_english`).
The affected set is: architecture, quick-start, configuration, model-registry,
procedures, **procedure-schema**, **scenario-schema**, **experiment-schema**,
dataflash, mavlink-ports, gazebo-sitl, changelog.

The three schema references are the ones that matter: a Turkish user who wants
to *write* a procedure, a scenario or an experiment reads the entire reference
in English. The reason is defensible and stated (docs.py:19-27 — forking every
document would recreate the duplicate-source problem, and a stale translation
of a technical page is worse than an honest English one), and the fallback is
flagged rather than silent. But the release gate says "verify no accidental
English fallback remains for changed functionality", and v1.6's headline
feature ships its schema reference in English only. F-17.

No hardcoded user-facing strings were found in the Python backend. Error text
from `procedures.py`/`experiments.py` parse failures **is** English-only —
`ProcedureError` messages are literals, not `t()` calls. Those surface in the
UI when a procedure fails to load. F-18 (LOW).

---

## 23. Documentation Portal

Read as an engineer who has never seen Argaz.

### 23.1 The design

`docs.py` is an **index over the repository's own files**, holding no prose of
its own except a generated landing page. Every page resolves to a real file or
a named `##` section of one, and the portal reports which file and which
section it came from. The reasoning (docs.py:3-16) is that writing
documentation into the interface "produces a second source of truth within a
week: the page says one thing, README.md says another, and the one a developer
edits is whichever they happen to open".

This is the correct architecture for a docs portal in a repository of this
size, and it is rare.

Six groups, ~30 pages, with heading extraction for search and deep links
(`test_a_deep_link_opens_the_page_and_scrolls_to_the_heading` in the e2e suite).
HTML comments are stripped before serving, so a generated file's
"DO NOT EDIT" banner does not appear in the portal.

### 23.2 The brief's eight questions

| Question | Answer |
|---|---|
| Can I understand the architecture without reading the source? | **Yes.** `docs/lifecycle.md`, the README Architecture section and `docs/verification-model.md` together give an accurate mental model. |
| Can I configure a model? | **Yes.** Model Registry (USAGE.md §7) plus Configuration (README) plus `docs/reproducibility.md`. |
| Can I create a procedure? | **Yes** — `procedures/SCHEMA.md` is a complete reference for schemas 1–4. **In English only.** |
| Can I understand acceptance criteria? | **Yes.** `docs/acceptance-criteria.md` covers all four shapes. It does **not** state that `eventually` is measured on the wall clock while the other three are on the vehicle clock (F-11). |
| Can I understand a failed run? | **Yes, and unusually well.** `docs/failure-investigation.md` (176 lines) walks category → code → file. `docs/failure-classification.md` explains the seven categories and which one is about the aircraft. |
| Can I understand the evidence? | **Yes.** `docs/evidence-manifest.md` and `docs/runs-and-evidence.md` explain every file and why it is there. |
| Can I understand what Argaz does NOT verify? | **Yes — better than anywhere else in the tool.** `docs/verification-vs-validation.md`, `docs/validation-limits.md`, `docs/verification-model.md`, plus the non-claims section of every report. |
| Can I find troubleshooting? | **Yes.** `TROUBLESHOOTING.md` (Turkish original) / USAGE.md §10, plus `docs/diagnostics.md`. Notably, Troubleshooting is the one page whose Turkish source is a *different document* from its English one, because the Turkish was written first. |

### 23.3 Gaps

* **`docs/coverage.md` and `docs/status.md` are not in the portal.** The two
  generated documents that say what has and has not been verified are reachable
  from the README and from the repository, not from the Docs section. For a
  portal whose selling point is "what this does not verify", omitting the
  coverage report is an odd gap. F-21 (LOW).
* **`docs/manual-checklist.md` (262 lines) is not in the portal either.** It is
  the document that covers what no automated test does — including "no test has
  ever looked at a rendered Gazebo frame".
* **Stale content is served as current.** The portal serves `docs/status.md`'s
  data indirectly via the README summary, and that data is a day old and
  describes a different release (F-06).
* **No contradictions found** between portal pages, which follows structurally
  from there being one source per fact.

---

## 24. Security and Robustness

Not a penetration test; engineering robustness only.

### 24.1 Command construction — the real finding

`session.build_launch_commands()` quotes *paths* with `shlex.quote` and
interpolates *registry fields* raw. Demonstrated:

```python
model = {'id':'x', 'method':'gz_plus_sitl_paramfile', 'vehicle':'ArduPlane',
         'frame':'quad; touch /tmp/PWNED', 'world':'w.sdf $(id)',
         'param_file':'a.param', ...}

>>> build_launch_commands(model)
'gz sim -v4 -r w.sdf $(id) &'
'sim_vehicle.py -v ArduPlane -f quad; touch /tmp/PWNED --model JSON
     --add-param-file=a.param --speedup 5 --console --map --out 127.0.0.1:14551'
```

Both the `;` and the `$(id)` survive into a live interactive bash session. The
affected fields are `frame`, `world`, `param_file`, `extra_sitl_args`,
`lua_scripts` and the `ros2` package/launch/args. Their values come from
`config/models.json`, which `scan_models.py` generates by walking the
`SITL_Models` checkout — a third-party repository that `Dockerfile.tier2`
clones **unpinned at HEAD**. This is not a remote-attacker scenario; it is a
supply-chain-shaped robustness hole in a tool that runs shell commands for a
living, and the fix is `shlex.quote` on six interpolations. F-09.

### 24.2 Everything else checked

| Concern | Finding |
|---|---|
| Path traversal | **Guarded.** `run_dir` rejects `/`, `\`, leading `.` and requires the resolved path's parent to be the runs root. `run_file` re-checks with `relative_to`. `run_script` checks `target.parent`. |
| YAML parsing | **Safe.** `yaml.safe_load` everywhere (procedures.py:723, experiments.py). No `yaml.load`. |
| JSON parsing | Every `json.loads` on a file is wrapped in `except (OSError, JSONDecodeError)`. |
| Subprocess arguments | `doctor` and `versions` use list-form `subprocess.run` with no `shell=True`. `_configured_command` uses `bash -lc` with the script as `$0`-style positional arguments rather than interpolation — **correctly done**. |
| Network exposure | Server binds 127.0.0.1 only (stated app.py:3). Telemetry mirror is loopback-only by construction (`HOST = "127.0.0.1"`, telemetry_mirror.py:60) with the reason stated: it carries live vehicle state with no authentication. |
| Authentication | None. Correct for a single-user localhost tool, and documented. |
| Environment variables | `ARGAZ_*` are read as paths and resolved; `ARGAZ_HEADLESS` is parsed for explicit truthiness. No `eval` of any env var. |
| Temporary directories | The scratch/working directory is a fixed project path, not `/tmp` — no symlink or predictable-name exposure. |
| File overwrite | Run directories use `mkdir(exist_ok=True)` on a second-resolution timestamp; collision is possible but not reachable through the UI. |
| Untrusted procedure content | A procedure cannot execute code. Step kinds are a closed set; MAVLink enums resolve via `getattr` on `mavutil.mavlink` with a clear failure — which does allow reading any attribute of that module, but only as an `int` used as a command id. Bounded. |
| Denial of service | `MAX_HASH_BYTES` (256 MB), `MAX_SERIES_POINTS` (600), `Hub.MAX_BACKLOG` (256 KB ring), `CAMPAIGN_MAX_RUNS` (50), `MAX_ARMS` (4) — all bounded deliberately. |

---

## 25. Performance and Resource Usage

Only demonstrable problems are reported.

* **Log growth is unbounded.** `argazui/run/<model_id>/logs/*.BIN` accumulates
  every dataflash log the model has ever produced, plus `mav.tlog`,
  `mav.tlog.raw` and `<model>-simulation.log`. Observed:
  `argazui/run/alti_transition_quad/` holds 5 `.BIN` files plus a 415 KB tlog
  and a 279 KB raw tlog; the repository root's `logs/` holds 12 `.BIN` files.
  27 model working directories exist. No retention policy anywhere. F-22.
* **Run directories accumulate.** `runs/` holds 48 entries in this checkout,
  each with a dataflash log. `list_runs` has a `limit=200` for the listing but
  `campaign.list_campaigns` and `coverage._runs_under` **`rglob("result.json")`
  over the whole tree and parse every one**, on every `/api/campaigns` and
  `/api/coverage` request. Linear in total run count with no cache. At 48 runs
  this is milliseconds; at a few thousand it is a visible stall on a
  synchronous FastAPI endpoint. F-25 (LOW).
* **UI blocking.** All read endpoints are synchronous `def` handlers, so they
  occupy the event loop's threadpool. `api_run` calls `directory.rglob("*")`
  and reads the whole `report.json` (which carries downsampled plot series).
  Acceptable at present scale.
* **Report generation is correctly backgrounded.** `finish()` spawns a daemon
  thread so STOP does not wait for a long log parse, with `wait=True` for
  callers about to exit — and the comment records the bug that motivated it
  (the last run of a test session lost its report every time).
* **IMU handling is deliberately frugal.** Only the gyro peak is retained, not
  the series, "because IMU is the highest-rate record in the log and the one
  metric derived from it is a maximum". Correct.
* **Subprocess accumulation:** bounded in normal operation by the PGID sweep;
  unbounded after a server crash (F-12).
* **`gz --version` caching** (`_VERSION_CACHE`, fingerprint.py:132) saves ~1 s
  per fingerprint capture, with the staleness trade explicitly stated.

No premature-optimisation targets are reported.

---

## 26. Professional Engineering Tool Assessment

| Dimension | Score | Reason |
|---|---:|---|
| **Systems Engineering** | **8/10** | Component boundaries are real and load-bearing — the same `ProcedureRunner` serves three drivers, and swapping the transport for tests required no change to it. Schema versioning across four artefacts (procedure 1–4, result 1–6, report 1–3, experiment 1) with per-version migration notes is professional practice. Deducted for `Manager` (A-1) and for launch being untyped shell text with no result channel (A-2). |
| **Simulation Engineering** | **7/10** | The MAVLink layer is expert work: the mode-table correction for models reporting the wrong `MAV_TYPE`, the derived RC keepalive interval from `RC_OVERRIDE_TIME`/speedup with the floor deliberately overridden when physics demands it, the GCS heartbeat added because its absence tripped a real failsafe, body rates over Euler derivatives for tailsitters. Every one of those is a bug someone actually hit. Deducted for `sleep 6` as the Gazebo handshake, fixed ports, and the readiness abstraction differing between the test path and the real path. |
| **Verification** | **7/10** | Would be 9 without F-01. Temporal shapes on the vehicle's clock with a reported wall-clock fallback, `attitude_stable` measuring time-outside-band rather than peaks, the minimum-sample and minimum-duration guards, `error` separated from `failed`, the retry that costs a `flaky` — this is a verification engine, not a checklist. The evidence guard existing and being wired to only half the shapes is the flaw, and it is the one flaw that can produce a wrong green. |
| **Validation awareness** | **9/10** | The best dimension. `limitations.py`'s four non-interchangeable categories with mandatory standing statements, `docs/verification-vs-validation.md`'s "the gap closes by itself in a reader's head", the refusal to compute a p-value at n=5, "**5 runs is 5 runs**" printed in every campaign document. Docked one point only for `README.md:3` calling it a "validation platform". |
| **Reproducibility** | **7/10** | The fingerprint is thorough and never guesses; `unknown[]` with reasons is the right pattern; content hashes cover the two things that change without moving a version number. Docked for the unwiped `eeprom.bin`, unrecorded SITL speedup, unrecorded regression thresholds, and `dirty` not being an identity field. |
| **Traceability** | **8/10** | Every link named, criteria declared rather than derived (all 13 procedures), derived ids reported as such, `integrity()` actually checking that links resolve, and no database so the chain cannot outlive its evidence. Docked for the evaluated/not-judged string coupling that already produces three answers. |
| **Evidence quality** | **8/10** | The three-level required/conditional/optional model with mandatory reasons for absence, the conditional dataflash rule tied to `LOG_DISARMED=0`, hashing everything except the one file that is legitimately rewritten and saying so, and an evidence failure that can fail a run whose procedures all passed. Docked because the recorded measurement cannot distinguish a real reading from an unwritten field for several conditions. |
| **Test infrastructure** | **8/10** | 476 tests, no mock autopilot, real SITL, real server, real browser, and a suite record that treats a skip as a non-result. The single-source rule makes a green test mean a working button. Docked for the untested failure paths that let F-01 and F-02 through, and for the permanent red. |
| **Reliability** | **6/10** | Shutdown, cleanup and signal handling are excellent. Recovery is not: a crashed server leaves orphans nothing detects, ports are fixed, Gazebo failure is undiagnosed, and `Manager` has concurrency gaps. |
| **Documentation** | **9/10** | 51 documents plus a portal that indexes rather than duplicates. The code comments are the real achievement: nearly every non-obvious constant carries the measurement or incident that produced it (`MODE_SETTLE_S` with two recorded overwrite timings, `RC_KEEPALIVE_INTERVAL` with the ArduPilot source file, `ARM_RETRY_WINDOW` with per-model measured waits). Docked for the stale generated artefacts. |
| **Maintainability** | **8/10** | Small focused modules, no framework inversion, no metaprogramming, no dependency injection theatre. The heavy prose in module docstrings is unusual but earns its place — it records *why*, which is what rots first. Docked for `app.py`'s size and the stringly-typed couplings. |
| **Portfolio signal** | **9/10** | This is what an experienced reviewer would notice: a project that found its own weak criterion (`tailsitter_takeoff` passing three times during a tumble), wrote a measurement layer to catch it, kept the resulting failure red on purpose, and documented the whole sequence in the changelog. Very few portfolio projects contain a story like that, and fewer still contain the code that proves it. |

### Does Argaz v1.6 look like a serious engineering project, or mainly a sophisticated SITL GUI?

**A serious engineering project.** Bluntly, and without qualification on that
point.

The distinguishing test is what happens to inconvenient truths, and this
codebase keeps them. It keeps a permanently failing test because fixing it
would prove nothing. It reports three of eleven models as failing and one as
untested in its own README. It computes coverage in a way that goes *down* when
someone adds a procedure. It refuses to print a standard deviation from two
samples. It records "unknown, and here is why" instead of a plausible value. A
sophisticated GUI does none of those things, because none of them make the
screenshot better.

The features an experienced simulation/verification engineer would actually stop
on are §28.

What stops it being an unqualified yes is narrower and should not be softened:
the tool's central promise — that a PASS rests on something measured — has a
demonstrated hole in it, and the failure taxonomy that exists to stop a broken
harness being reported as a broken aircraft currently does the opposite for
five distinct causes. Both are small. Neither is cosmetic.

---

## 27. Critical Findings

### CRITICAL

---

**F-01 — Acceptance criteria can PASS against telemetry that never arrived**

* **Severity:** CRITICAL
* **Subsystem:** Verification / procedure runner
* **Location:** [`argazui/argazui/procrunner.py:637-651`](../argazui/argazui/procrunner.py#L637)
  (`_unmeasurable`), [`:329-333`](../argazui/argazui/procrunner.py#L329)
  (`CONDITION_EVIDENCE`), [`:660-667`](../argazui/argazui/procrunner.py#L660)
  (`_evaluate` dispatch); affects `argazui/procedures/{copter,plane,vtol,tailsitter}_land.yaml`
* **Observed behaviour:** `_unmeasurable()` is called only from `_expect_for`
  and `_expect_never`. The `eventually` and `within` shapes never consult it.
  Separately, `CONDITION_EVIDENCE` maps only attitude and pre-arm conditions —
  `alt_above`, `alt_below`, `climb_rate_*`, `groundspeed_above`, `armed` and
  `mode` have no entry, so even under `for`/`never` they are unguarded.
  Demonstrated against a `VehicleState` that had received no messages:
  `alt_below: 1` → PASS ("alt=0.0m"), `armed: false` → PASS ("armed=False"),
  `pitch_within: [-10,10] within: 1s` → PASS ("became true after 0.02 ms"). All
  four shipped landing procedures declare exactly `{armed: false}` and
  `{alt_below: N}` as their complete `expect:` block.
* **Expected behaviour:** A criterion resting on a signal that has never been
  observed must report "not judged", as `for`/`never` already do for attitude.
  The module states this rule at procrunner.py:277-281 ("A missing telemetry
  stream must never read as good behaviour") and at :326-333.
* **Engineering impact:** A landing can be reported PASS on evidence that was
  never collected. A `MAVLINK_DEGRADATION` fault, a failed `request_data_stream`
  (the exact bug documented at mavlink_link.py:637-646, where ArduCopter sent
  no `GLOBAL_POSITION_INT` and altitude read 0.0), or a partially-established
  link all produce this state. The verdict is indistinguishable from a genuine
  pass in the run record: `docs/status.md` line 105 shows a passing criterion
  whose recorded measurement is literally `alt=0.0m`.
* **Evidence:** direct probe through `ProcedureRunner._evaluate`, output in
  §6.3; `docs/status.md:105`.
* **Remediation:** (a) call `_unmeasurable()` from `_evaluate` for all four
  shapes, not from two of them; (b) extend `CONDITION_EVIDENCE` with
  `alt_above`/`alt_below` → a new `position_known` flag set in `_absorb` on
  `GLOBAL_POSITION_INT`, `climb_rate_*`/`groundspeed_above` → `vfr_known` on
  `VFR_HUD`, `armed`/`mode` → `connected`; (c) add a regression test asserting
  each condition type is refused rather than passed against an empty state.
* **Blocks release:** **Yes.**

---

**F-02 — Non-aircraft aborts are classified as `acceptance` failures**

* **Severity:** CRITICAL
* **Subsystem:** Failure classification
* **Location:** [`argazui/argazui/failures.py:337-352`](../argazui/argazui/failures.py#L337)
  (`classify_procedure`, criterion loop before the fallback), interacting with
  [`argazui/argazui/procrunner.py:1254-1265`](../argazui/argazui/procrunner.py#L1254)
  (`_unevaluated` marks pending steps `skipped`, not `failed`)
* **Observed behaviour:** Any `ProcedureAborted` that does not leave a *failed
  step* and does not populate `faults[]` falls through to the criterion loop,
  where `_unevaluated` has set every criterion `passed: False`. The first one
  matches and returns `ACCEPTANCE` / `criterion-not-judged`. Probed directly:

  | Abort cause | Classified as |
  |---|---|
  | fault mechanism unavailable on this firmware | `acceptance` / `criterion-not-judged` |
  | operator cancelled the procedure | `acceptance` / `criterion-not-judged` |
  | overall procedure timeout | `acceptance` / `criterion-not-judged` |
  | fault start-condition never held | `acceptance` / `criterion-not-judged` |
  | unknown placeholder in a value | `acceptance` / `criterion-not-judged` |

* **Expected behaviour:** `environment` for the two fault cases and the
  placeholder, `infrastructure` or a dedicated code for a cancel, `procedure`
  for the overall timeout. [`faults.py:196-202`](../argazui/argazui/faults.py#L196)
  states in terms that the runner "turns it into an aborted procedure with an
  `environment` failure classification".
  [`failures.py:32-35`](../argazui/argazui/failures.py#L32) states that
  `acceptance` "is the only one that means the aircraft did something wrong",
  and that conflating the categories "is how a broken harness comes to be
  reported as a broken aircraft".
* **Engineering impact:** The v1.4 headline feature reports the opposite of the
  truth for its own headline scenario. A missing `SIM_GPS1_ENABLE` — a
  *simulator* problem — appears in `docs/status.md`, in the campaign failure
  histogram and in the experiment document as an **aircraft acceptance
  failure**. Campaign `failure_categories` and experiment verdicts inherit the
  error, so a run of five iterations on a firmware without the GPS parameter
  reports five acceptance failures and reads as an aircraft that cannot fly.
* **Evidence:** direct probe through `failures.classify_procedure`, table above.
* **Remediation:** Carry the abort *reason* structurally instead of
  reconstructing it from text. Minimal fix: have `run()` record an
  `abort_kind` on the result (`fault-unavailable`, `fault-start-missed`,
  `cancelled`, `overall-timeout`, `placeholder`, `override`) and dispatch on it
  in `classify_procedure` **before** the criterion loop. Add one test per abort
  cause asserting the category.
* **Blocks release:** **Yes.**

---

### HIGH

---

**F-03 — v1.6 ships with no CI evidence of its own; generated artefacts are stale**

* **Severity:** HIGH · **Subsystem:** CI / reporting
* **Location:** `docs/status.md`, `docs/coverage.md`, `README.md:10`
* **Observed:** Both generated documents carry
  `Generated: 2026-08-10T15:08:01Z` and were produced from v1.5's artefacts.
  `git show --stat d2a9983` confirms the v1.6 commit touches neither.
  `docs/coverage.md` contains four dimensions; `coverage.DIMENSIONS` declares
  five (`experiments` was added by v1.6). `README.md`'s STATUS-SUMMARY block is
  the stale line. `docs/status.md` lists 15 failing tier-1 tests, 12 of which
  **do not reproduce** on this checkout (verified: `170 passed`).
* **Expected:** The release gate in all four architecture documents requires
  tests, docs and status to be current at commit time.
* **Impact:** The project's own machine-generated verification status describes
  a different release. A reader is told v1.6 declares four coverage dimensions
  and that twelve documentation tests are failing; neither is true.
* **Remediation:** Regenerate both, or make `status.yml` fail when the
  committed artefact differs from freshly generated output.
* **Blocks release:** Yes.

---

**F-04 — `mode_transition_latency_max` is wall-clock seconds among vehicle-clock seconds**

* **Severity:** HIGH · **Subsystem:** Metrics / regression
* **Location:** [`metrics.py:99-105`](../argazui/argazui/metrics.py#L99),
  [`procrunner.py:1167`](../argazui/argazui/procrunner.py#L1167)
* **Observed:** The metric's value is `time.time() - at` around a `set_mode`
  step. Every other `unit: "s"` metric is measured on the dataflash clock.
  SITL speedup is not a `fingerprint.IDENTITY_FIELDS` member, so two runs at
  different speedups are `comparable`.
* **Impact:** A speedup change produces a proportional change in this metric,
  reported by `regression.py` as `DEGRADED` past the 10% tolerance and 0.1 s
  floor, and classified as a `regression` failure. `campaign.statistics` will
  attribute CI-runner load to the aircraft.
* **Remediation:** Record the step duration on the vehicle clock (the runner
  already has `link.state.vehicle_clock_s`), or rename the metric and state the
  clock in `source`, and add `speedup` to the fingerprint.
* **Blocks release:** No, but it makes the regression layer unreliable.

---

**F-05 — `time_outside_attitude_envelope` measures a different window from the criterion of the same name**

* **Severity:** HIGH · **Subsystem:** Metrics
* **Location:** [`metrics.py:266-291`](../argazui/argazui/metrics.py#L266) vs
  [`procrunner.py:1142`](../argazui/argazui/procrunner.py#L1142)
* **Observed:** The criterion is scoped to one procedure (`stability.reset()`
  before the first step). The metric is computed over the entire dataflash log
  and takes its band from the *first* procedure that declared one.
* **Impact:** A run can report `attitude_stable: passed, 0.0 s outside` and
  `time_outside_attitude_envelope: 40 s` simultaneously, both correct, with
  nothing in the report indicating they answer different questions. A reviewer
  comparing them will conclude one of them is wrong.
* **Remediation:** Scope the metric to the armed interval of the procedure that
  declared the envelope (`armed_intervals` is already computed and passed in),
  or rename it `time_outside_attitude_envelope_whole_log` and say so in
  `source`.
* **Blocks release:** No.

---

**F-06 — Registry fields are interpolated into shell commands without quoting**

* **Severity:** HIGH · **Subsystem:** Process launch / robustness
* **Location:** [`session.py:132-211`](../argazui/argazui/session.py#L132)
* **Observed:** `frame`, `world`, `param_file`, `extra_sitl_args`,
  `lua_scripts` and the `ros2` fields are concatenated with `" ".join(...)`
  into lines typed into an interactive bash session, while the paths around
  them are `shlex.quote`d. Demonstrated: `frame: "quad; touch /tmp/PWNED"` and
  `world: "w.sdf $(id)"` both survive into the generated command.
* **Expected:** Every interpolated value quoted, as the paths already are.
* **Impact:** `models.json` is generated from the `SITL_Models` checkout, which
  `Dockerfile.tier2` clones unpinned at HEAD. An odd or hostile filename
  upstream becomes command execution in the user's shell with their privileges.
* **Remediation:** `shlex.quote` on the six interpolations; add a test asserting
  a metacharacter-bearing field is quoted.
* **Blocks release:** Yes for a public release; no for local portfolio use.

---

**F-07 — Repeated runs inherit simulated-vehicle state through a shared `eeprom.bin`**

* **Severity:** HIGH · **Subsystem:** Reproducibility / campaigns
* **Location:** [`session.py:165-211`](../argazui/argazui/session.py#L165)
  (no `-w`), `argazui/run/<model_id>/eeprom.bin`; contrast
  [`tests/sitl.py:186-201`](../tests/sitl.py#L186) which does pass `-w`
* **Observed:** The UI, campaign and tier-2 paths all reuse
  `argazui/run/<model_id>/` and its `eeprom.bin` with no wipe. Observed on
  disk: `argazui/run/alti_transition_quad/eeprom.bin`, 16384 bytes, modified
  after the run.
* **Expected:** A campaign's stated claim is "the same model, the same
  procedure, the **same environment/configuration**, N times"
  (v1.4-ARCHITECTURE.md, `campaign.py:16-24`).
* **Impact:** A parameter whose restore failed — a case the runner explicitly
  records rather than assuming away — persists into the next iteration and the
  next nightly. `model.config_hash` hashes the `.param` file, not the eeprom,
  so `campaign.consistency()` reports the iterations as identical. Any spread
  caused by carried-over state is attributed to the aircraft.
* **Remediation:** Pass `-w` on the first iteration of a campaign (or every
  START), or hash `eeprom.bin` into the fingerprint so drift is at least
  visible.
* **Blocks release:** No, but it undermines the repeatability claim.

---

### MEDIUM

---

**F-08 — `dirty` flags, Gazebo version and SITL speedup are recorded but not compared**

*Subsystem:* Reproducibility / regression · *Location:*
[`fingerprint.py:297-302`](../argazui/argazui/fingerprint.py#L297) (`IDENTITY_FIELDS`)

Four identity fields are compared: two content hashes and two ArduPilot
commits. `argaz.dirty`, `ardupilot.dirty`, `sitl_models.dirty`,
`gazebo.version`, `ros.distro` and `runtime.python` are all captured and none
is compared. Two runs from two different *uncommitted* working trees of the
same commit, or across a Gazebo upgrade that changed the physics, are reported
as fully comparable. **Remediation:** add `ardupilot.dirty`, `argaz.dirty` and
`gazebo.version` to `IDENTITY_FIELDS`; capture `speedup` in the fingerprint.
*Blocks release:* No.

---

**F-09 — `SITL_Models` is unpinned in the tier-2 image while ArduPilot is pinned**

*Subsystem:* CI / reproducibility · *Location:*
`docker/Dockerfile.tier2`, `git clone --depth 1 … SITL_Models`

`ARDUPILOT_REF` is pinned to a SHA with an explicit argument for why a moving
ref would defeat the purpose. `SITL_Models` — the source of the airframes,
worlds and parameter files that tier 2 exists to verify — is cloned at HEAD.
Two builds of the same Dockerfile can fly different aircraft. `sitl_models.commit`
is recorded per run, so drift is *visible* after the fact, but it is not
prevented and it is not an identity field. **Remediation:** pin
`SITL_MODELS_REF` the same way. *Blocks release:* No.

---

**F-10 — "Was this criterion evaluated?" has three implementations and two answers**

*Subsystem:* Traceability / status / coverage · *Location:*
[`trace.py:232-243`](../argazui/argazui/trace.py#L232),
[`failures.py:207-208`](../argazui/argazui/failures.py#L207),
[`status.py:192`](../argazui/argazui/status.py#L192)

`ExpectResult` carries no `evaluated` flag, so three consumers recover it by
substring-matching localized prose with three different rules.
`status.claims_of` matches only `"not evaluated"` / `"degerlendirilmedi"` and
misses `"not judged"`, which is the wording used by `temporal_no_evidence`,
`temporal_too_few_samples`, `fault_no_evidence` and `fault_no_resync`. Probed:

```
criterion text: "not judged — 'angular_rate_above' rests on attitude
                 telemetry that never arrived."
status.claims_of()      -> 'failed'      (rendered as an aircraft failure)
trace._was_evaluated()  -> False         (correctly not evaluated)
coverage._exercised()   -> excluded      (correctly not covered)
```

A criterion refused for missing evidence is therefore shown in `docs/status.md`
as a failed acceptance claim about the aircraft. **Remediation:** add
`evaluated: bool` to `ExpectResult`, set it in `_evaluate`, and read it in all
three consumers. *Blocks release:* No.

---

**F-11 — The `eventually` shape uses the wall clock; this is not documented**

*Subsystem:* Acceptance criteria / documentation · *Location:*
[`procrunner.py:620-634`](../argazui/argazui/procrunner.py#L620) vs
`docs/acceptance-criteria.md`, `procedures/SCHEMA.md`

`_wait_for` uses `time.time() + timeout`. `within`, `for` and `never` use
`_Window` on the vehicle clock, and the module argues at length why that
matters. `timeout:` is the schema-1 shape used by 20 of 32 shipped criteria and
is silently a different unit. At speedup 5, `timeout: 30` means 150 seconds of
flight. **Remediation:** document it, or move `_wait_for` to `_Window`.
*Blocks release:* No.

---

**F-12 — No orphan-process or port-holder detection at START**

*Subsystem:* Process management · *Location:*
[`app.py:250-293`](../argazui/argazui/app.py#L250)

Cleanup depends on the pty's session id, which dies with the server. After a
crash, `gz sim`, `sim_vehicle.py`, SITL and MAVProxy survive holding 14550 and
5760, and the next START neither detects nor reports it — `MavlinkLink` binds
`udpin:14550` and may receive the *previous* vehicle's telemetry.
`argazui/start.sh` already implements exactly this diagnosis for the HTTP port
(and the tier-1 image installs `ss`, `ps` and `curl` for it); the same check is
not applied to the MAVLink ports. **Remediation:** reuse the `start.sh` logic in
`start_model`, or run `doctor`'s port checks before launch.
*Blocks release:* No.

---

**F-13 — `README.md` calls Argaz a "validation platform"**

*Subsystem:* Documentation / claims · *Location:* `README.md:3`, `README.md:619`

"A local control and **validation** platform for ArduPilot SITL and Gazebo".
`docs/verification-vs-validation.md` exists specifically to state that
validation is the thing this tool does not do, and `limitations.py` prints a
standing statement to that effect on every experiment document. The README is
the first thing a reader sees and it uses the reserved word. **Remediation:**
"verification platform", or "control and verification". *Blocks release:* No,
but it is the single highest-leverage word in the repository.

---

**F-14 — Environment failures are classified as procedure failures**

*Subsystem:* Failure classification / lifecycle · *Location:*
`session.py:156-157`, `failures.classify_run`

Gazebo failing to start, `sim_vehicle.py` failing to build, a missing world
file and a missing model asset all reach the classifier as a step that timed
out, and are reported `procedure` / `step-timeout`. The `environment` category
exists and is documented as covering exactly this ("SITL or Gazebo did not
start, an asset was missing"), and no code path produces it for those causes —
it is only produced for a failed override, an unapplied fault and a
campaign-launch exception. **Remediation:** append `echo "ARGAZ_RC:$?"` after
each launch line and parse it from the console stream; classify a run whose
vehicle never connected as `environment`. *Blocks release:* No.

---

**F-15 — The tier-1 CI job can never be green**

*Subsystem:* CI · *Location:* `tests/test_tier1_procedures.py`,
`docs/testing.md:138-145`

`sitl_tailsitter` fails deliberately and permanently. The decision is correct
and well argued. The consequence is that the tier-1 job's pass/fail bit is
constant, so a newly introduced failure is only detectable by diffing the
failing-test list — which no automation does. **Remediation:** keep the test
running and failing, but gate CI on the *set* of expected failures rather than
on the count, so a new one turns the job red.
*Blocks release:* No.

---

**F-16 — The regression system has no CI integration**

*Subsystem:* CI / regression · *Location:* `.github/workflows/*`,
`docs/ci.md:60-67`

`argazui compare` implements a three-way exit-code contract (0 / 1 / 2) and
`docs/ci.md` documents it, but no workflow invokes it. Nor does anything invoke
`argazui coverage` or `argazui experiment` as a gate. A metric degrading past
its threshold has no automated consumer anywhere.
**Remediation:** add a step to `tier2.yml` comparing each model's run against a
named baseline run committed under `runs/baselines/`. *Blocks release:* No.

---

**F-17 — v1.6's schema reference ships in English only**

*Subsystem:* Localisation · *Location:* `docs.py` PAGES, `experiments/SCHEMA.md`

12 of ~30 portal pages have no Turkish source, including all three schema
references (`procedure-schema`, `scenario-schema`, `experiment-schema`). The
fallback is flagged in-portal rather than silent, and the reason for not
forking every document is stated and defensible. But the release gate requires
"no accidental English fallback for changed v1.x functionality", and v1.6's
headline artefact — the experiment schema — is exactly that.
*Blocks release:* No.

---

**F-18 — Nine of thirteen procedures assert only what their own steps already waited for**

*Subsystem:* Verification strength · *Location:* `argazui/procedures/*.yaml`

`copter_takeoff` uses `within` + `for` + `never` + `attitude_stable` and is a
genuinely strong procedure. The two scenarios are strong. The remaining ten use
only `eventually`, and in most the criterion restates the `wait_for` step
immediately above it — e.g. `copter_land` step 4 is
`wait_for: {armed: false}` (timeout 240 s) and criterion 1 is
`{armed: false}`. The criterion adds no independent evidence: if the step
passed, the criterion cannot fail. Combined with F-01 this means four of the
procedures assert essentially nothing beyond "a heartbeat said disarmed".
**Remediation:** give the land procedures a `for` on the disarmed state and a
`never` on the descent rate, and an `attitude_stable` envelope as
`copter_takeoff` has. *Blocks release:* No.

---

**F-19 — Four procedures, eight criteria and two fault mechanisms have never been executed**

*Subsystem:* Coverage · *Location:* `docs/coverage.md`

`plane_land_rtl`, `plane_takeoff_auto`, `tailsitter_land`,
`vtol_takeoff_mission`; the eight criteria inside them; and the
`gps_degradation` / `mavlink_degradation` mechanisms. Each has unit tests and
none has flight evidence. Additionally 50 evaluated criterion results are
unattributable (pre-v1.5), so the published 75% criterion coverage rests on a
smaller body of evidence than the number implies. The coverage report names all
of this correctly — this finding is about the gap, not about the reporting.
*Blocks release:* No.

---

### LOW

---

**F-20** — `Manager` concurrency. `run_procedure` is not blocked during an
active campaign or experiment; `self.run` and `self.active_model` are mutated
from four threads under one lock that covers only start/stop
(`app.py:123-752`). The known race is worked around at one call site
(`app.py:1059-1060`) rather than removed.

**F-21** — `CampaignRunner._one` initialises `row["verdict"] = INCOMPLETE` and
never updates it (`campaign.py:177-203`), so every live progress row streamed
to the browser reads "incomplete". The final document is recomputed from disk
and is correct.

**F-22** — `_CampaignIteration` waits up to 240 s for pre-arm and then proceeds
silently regardless of the outcome, with no record that it timed out
(`app.py:787-792`).

**F-23** — `MODE_SETTLE_S` / `state.mode_settled` is computed, documented with
two measured ArduPlane mode-overwrite timings, exposed in `/api/status` and
used only by the UI's button gating. `ProcedureRunner`'s `set_mode` step does
not consult it, so a procedure can command a mode inside the documented
overwrite window.

**F-24** — No `math.isfinite` guard anywhere in `_check`, `metrics.compute`,
`regression._classify` or `campaign.statistics`. A NaN metric propagates and
serialises as bare `NaN`, which is invalid JSON for strict parsers.

**F-25** — Unbounded artefact growth: 27 model working directories under
`argazui/run/`, each accumulating every `.BIN`, `mav.tlog` and `mav.tlog.raw`
it has ever produced; 48 run directories under `runs/`; 12 `.BIN` files in the
repository root's `logs/`. `campaign.list_campaigns` and `coverage._runs_under`
`rglob` and parse every `result.json` on the tree on each request, with no
cache. The repository root also carries stray artefacts (`mav.tlog`,
`mav.parm`, `eeprom.bin`, `last_sim_test.txt`, `quadplane_gz_test.txt`,
`quadplane_test_run.txt`, `last_build_log.txt`) that are noise in a
verification repository.

**F-26** — Turkish diacritic inconsistency: `i18n.py` and `limitations.py` use
ASCII-folded Turkish while `docs.py` titles and the `docs/*.tr.md` files use
proper Turkish. A Turkish reader sees both in one panel. Additionally,
`ProcedureError` / `ExperimentError` / `LimitationError` messages are
English-only literals rather than `t()` calls, and they surface in the UI when
a procedure fails to load. Also: `attitude` is rendered "tutum" (the
psychological sense) where Turkish aerospace uses "yönelim" or "duruş".

**F-27** — `docs/coverage.md`, `docs/status.md` and `docs/manual-checklist.md`
are absent from the documentation portal, so the three documents that state
what has *not* been verified are the ones a portal reader cannot reach.

**F-28** — `runs._recorded_procedures` recovers archived YAML with `.strip()`
(`runs.py:1010`) while `fingerprint.normalise` only `rstrip()`s
(`fingerprint.py:71`). A procedure with leading whitespace would hash
differently on regeneration, silently making a regenerated report incomparable
with the flight that produced it — the exact failure `normalise()` was written
to fix. No shipped procedure triggers it; the coupling is undefended and
untested.

---

## 28. Strong Engineering Decisions

Separating real engineering value from polish, as instructed. Everything below
is load-bearing; none of it is presentation.

**1. The single-source execution rule, structurally enforced.**
`ProcedureRunner` is the only executor, and `tests/gazebo.py` calls
`session.build_launch_commands` itself rather than composing its own `gz sim`
line. A green tier-2 model row is therefore a statement about the button. Most
projects claim this; this one has no second implementation to drift.

**2. `StabilityWatch`, and the incident behind it.** `tailsitter_takeoff`
passed three times while the aircraft was tumbling, because altitude, arm state
and mode were the only three things the criteria looked at. The response was
not to tighten a threshold but to build a measurement layer that weighs every
attitude sample by the vehicle's own inter-sample interval, caps gaps at 0.5 s
so a dropout can neither manufacture nor excuse time outside a band, and judges
**seconds outside a band rather than a peak** because "a peak is one sample and
one sample is noise". The suite run in §20.4 reproduces the catch live: three
criteria pass at 1882 °/s and only this one fails. **This is the single most
convincing artefact in the repository.**

**3. `_Window`'s stalled-clock detection.** v1.3 detected a clock that had
never started or had gone backwards. It did not detect one that dies
*mid-window*, where `time_boot_ms` simply keeps its last value and the window
reports `now - start = 0` for its whole duration — "a stalled stream described
as a healthy measurement of zero seconds". The fix converts wall seconds using
the speedup frozen at window construction, makes the fallback sticky so a
duration never changes unit mid-measurement, and records `clock: "wall"` in the
run. That is three correct decisions about one subtle bug.

**4. `_resync()` before recovery criteria.** After a MAVLink blackout is
lifted, `link.state` still holds pre-fault values, so `{armed: true} within
15s` would pass "after 0 ms" against a reading the blackout froze. The runner
waits for the vehicle clock to advance first, and the docstring explains that
this follows "from what a fault IS and not from which fault it was". Fault
injection implementations get this wrong routinely.

**5. Fail-closed fault injection, enforced at parse time.** A fault with
neither `expect:` nor `recovery:` is refused when the file is loaded — without
it, `all([])` would make every criterion-free fault pass. A fault must declare
the telemetry signals its verdict rests on, and a missing signal produces "not
judged" rather than a pass. Mechanisms are probed *before* the first step and
before any override, so an unavailable fault costs nothing and changes nothing.

**6. `evidence.py`'s three-level model with mandatory reasons.**
required / conditional / optional, where an optional artefact absent *without a
stated reason* is itself reported: "there are no plots because matplotlib is
not installed" and "there are no plots" are different facts and only one is an
answer. The dataflash log is conditional on the vehicle having armed, tied to
ArduPilot's `LOG_DISARMED=0` default. `result.json` is deliberately unhashed
with the reason recorded in the manifest that describes it.

**7. Absence with a reason, everywhere.** The same rule applied to five
subsystems: a fingerprint field that cannot be read is `null` with an entry in
`unknown[]`; a metric that cannot be derived is `value: null` with a `detail`;
a criterion that could not be judged says so; a coverage dimension with nothing
in it reports `None` rather than 100%; a standard deviation from two samples is
`—` with `spread_reported: false` so a reader never mistakes it for "no
variation".

**8. Statistical restraint under pressure.** `campaign.py` and `analysis.py`
both refuse to compute a p-value, a confidence interval, an effect size or a
reliability figure, and both say why in the rendered document: at n=5 every one
would be arithmetic that runs fine and means nothing. `analysis.py` reports
range *overlap* instead and states explicitly that an overlap is not a
significance test. The temptation to print a number that looks authoritative
is enormous and it was resisted.

**9. The verification/validation boundary, mechanised rather than described.**
`limitations.STANDING` prints statements on every experiment document that a
definition cannot drop, including that a SITL frame "is not a model of any
particular aircraft" and that "no part of it has been compared against a
measurement of a real aircraft by anything in this repository". An experiment
declaring no limitations of its own gets a paragraph saying so *and* noting
that the limits that matter most are usually the ones only its author knows.

**10. Coverage that can go down.** Measured over declared things rather than
over tests, with skips excluded, criteria counted only if actually *evaluated*
rather than merely present, and pre-v1.5 results reported as unattributable
rather than matched by position. The uncovered list is presented as the
deliverable and the percentage as the summary.

**11. Process lifecycle by kernel session id.** The `pkill -f` incident is
recorded, and the replacement — `start_new_session`, a `/proc` walk parsing
after the *last* `)` to survive a `comm` containing parentheses, PGID-scoped
signals escalating SIGINT → SIGTERM → SIGKILL with SIGINT first so SITL flushes
its log — is correct in every detail including the ones that only matter once.

**12. Comments that record measurements, not intentions.** `MODE_SETTLE_S`
carries two recorded ArduPlane mode-overwrite timings ("RC valid 6.75 → FBWA
commanded 6.85 → back to MANUAL 6.99"). `RC_KEEPALIVE_INTERVAL` cites the
ArduPilot header that defines `RC_OVERRIDE_TIME`, derives the interval from the
measured speedup, and states that the floor is deliberately overridden when
physics demands it "because a keepalive that guarantees the thing it exists to
prevent" is worse than extra traffic. `ARM_RETRY_WINDOW` carries per-model
measured pre-arm waits. This is the documentation that survives refactoring.

**13. `probe_capabilities` reads the vehicle, not the registry.** SkyCat TVBS
is registered as a plain QuadPlane and its parameter file sets
`Q_TAILSIT_ENABLE=1`; Swan-K1 ships `Q_OPTIONS=262274` whose bits change what a
`NAV_TAKEOFF` item means. Neither fact is in `models.json`, so procedure
selection reads Q_ENABLE / Q_TAILSIT_ENABLE / Q_OPTIONS over MAVLink. Both
examples are named in the docstring.

**14. The docs portal indexes rather than duplicates.** Every page resolves to
a repository file or a named section of one, and the portal reports which. The
alternative — writing the documentation into the interface — is named as the
thing that "produces a second source of truth within a week".

**15. Deliberate schema versioning across four artefact families.** Procedure
1–4, result 1–6, report 1–3, experiment 1, each with per-version notes stating
what moved and what did not, and each artefact recording its producer's schema
in the evidence manifest. Extending a schema in place is explicitly rejected as
"quieter and worse".

### What is polish rather than engineering

The screenshot, the two-terminal layout, the PlotJuggler mirror (well
engineered — the reasoning about why JSON rather than MAVLink is researched and
correct — but a convenience), the model images, the build-drift banner, and the
volume of documentation considered as volume. None of these would change an
experienced reviewer's assessment. Items 1–15 would.

---

## 29. Final Verdict

### **B — Strong project, but several engineering gaps remain.**

**Why not A.** A is "engineering-ready for portfolio demonstration" with no
material reservations. Two CRITICAL findings prevent it, and both sit on the
tool's central claim rather than at its edges:

* the evidence guard that makes a PASS mean "measured" is wired into two of
  four criterion shapes, and the four shipped landing procedures fall entirely
  in the unguarded half (F-01);
* the failure taxonomy whose stated purpose is to stop a broken harness being
  reported as a broken aircraft classifies five distinct non-aircraft aborts as
  `acceptance` — the one category documented as a verdict about the aircraft
  (F-02).

Both were demonstrated by execution, not inferred. Additionally, the release
ships without CI evidence of its own: the two generated verification documents
describe v1.5, and one of them is structurally out of date with the code it
claims to describe (F-03).

**Why not C.** C is "functionally impressive but verification claims are too
strong". That is the diagnosis this project was built to avoid, and it does not
apply. The claims are, with one exception, *narrower* than what the tool
delivers: tier 1 is structurally prevented from contributing to a model row;
`untested` is defined as "not yet verified by a machine — it does not mean
broken, and it does not mean working"; three of eleven models are reported as
failing in the project's own README; coverage names what has never been run;
every report ends with what it does not prove; and the one document that could
have hidden a problem — `docs/status.md` — instead publishes the failing test
list. The single overreach found in the entire repository is the word
"validation" in the README's first line.

**Why not D.** The architecture is sound. Component boundaries are real and
were demonstrated by substituting the transport for the test suite without
touching the executor. There is no circular dependency, no hidden global state
beyond the two module-level singletons, no duplicated verification logic, and
no second execution engine. The two CRITICAL findings are localised: F-01 is a
guard applied at two of four call sites plus six missing table entries; F-02 is
a dispatch order plus one missing field. Neither requires redesign.

**The honest summary.** This is a project whose *reasoning* is consistently
better than its coverage of its own reasoning. Nearly every hard decision in
it — vehicle clock versus wall clock, seconds-outside-band versus peak, body
rates versus Euler derivatives, absence-with-a-reason versus absence, refusing
statistics the sample cannot support, keeping a failing test failing — is
correct, and several are decisions most practitioners get wrong. What is
missing is the last step of applying each rule everywhere it applies. The
evidence guard exists and is right; it is wired to half the shapes. The failure
taxonomy exists and is right; the dispatch reaches the wrong branch for five
causes. The fingerprint is thorough; four of its fields are recorded and never
compared. Each gap is small. Together they mean the tool's strongest claim —
that a PASS here is evidence rather than a green light — is currently true of
most of its surface rather than all of it.

Fix F-01 and F-02, regenerate the status and coverage artefacts, and this is an
A.

---

## 30. Recommended Next Actions

Ordered by the ratio of verification value to effort. No new features are
proposed; this list is entirely about making the existing claims true.

**Before anything else — the two that change what a PASS means**

1. **F-01.** Call `_unmeasurable()` from `_evaluate` for all four shapes.
   Add `position_known` (set on `GLOBAL_POSITION_INT`) and `vfr_known` (set on
   `VFR_HUD`) to `VehicleState`, and extend `CONDITION_EVIDENCE` to cover
   `alt_above`, `alt_below`, `climb_rate_above`, `climb_rate_below`,
   `groundspeed_above`, `armed` and `mode`. Add a parametrised test that every
   condition type is refused, not passed, against a fresh `VehicleState`.
   *Estimate: ~40 lines plus one test file.*

2. **F-02.** Record an `abort_kind` on the result when `ProcedureAborted` is
   raised, and dispatch on it in `classify_procedure` before the criterion
   loop. Add one test per abort cause asserting the resulting category.
   *Estimate: ~30 lines plus six tests.*

**Then — restore the release gate**

3. **F-03.** Regenerate `docs/status.md` and `docs/coverage.md` from a v1.6 CI
   run, and add a `status.yml` step that fails when a committed generated
   artefact differs from freshly generated output.
4. **F-15.** Gate tier-1 CI on the *expected set* of failures rather than on
   the count, so `sitl_tailsitter` stays visibly red and a new failure turns
   the job red.

**Then — make the measurements trustworthy**

5. **F-04.** Move `set_mode` step timing to the vehicle clock, and add
   `speedup` to the environment fingerprint.
6. **F-05.** Scope `time_outside_attitude_envelope` to the armed interval of
   the procedure that declared the band, or rename it and say so in `source`.
7. **F-08.** Add `ardupilot.dirty`, `argaz.dirty` and `gazebo.version` to
   `fingerprint.IDENTITY_FIELDS`.
8. **F-10.** Add `evaluated: bool` to `ExpectResult` and read it in `trace.py`,
   `failures.py` and `status.py` instead of matching prose.

**Then — close the lifecycle and robustness gaps**

9. **F-06.** `shlex.quote` the six unquoted interpolations in
   `build_launch_commands`, with a test.
10. **F-07.** Pass `-w` on the first iteration of a campaign, or hash
    `eeprom.bin` into the fingerprint so carried-over state is at least visible.
11. **F-09.** Pin `SITL_MODELS_REF` in `Dockerfile.tier2` as `ARDUPILOT_REF`
    already is.
12. **F-14 / F-12.** Echo and parse an exit status after each launch line so
    Gazebo and SITL startup failures classify as `environment`; reuse
    `start.sh`'s port-holder diagnosis before START.

**Then — strengthen what is verified**

13. **F-18.** Give the four landing procedures criteria that are independent of
    their own wait steps: a `for` on the disarmed state, a `never` on descent
    rate, and an `attitude_stable` envelope.
14. **F-19.** Fly the four uncovered procedures and declare a scenario for
    `gps_degradation` and `mavlink_degradation`, so the two unexercised
    mechanisms acquire flight evidence.
15. **F-16.** Commit a baseline run per model under `runs/baselines/` and add an
    `argazui compare` step to `tier2.yml`, so the regression layer has a
    consumer.

**Then — the smaller ones**

16. **F-13.** Change "validation platform" to "verification platform" in
    `README.md:3` and `:619`.
17. **F-11.** Document that `eventually` / `timeout:` is measured on the wall
    clock, in `docs/acceptance-criteria.md` and `procedures/SCHEMA.md`.
18. **F-17.** Translate `experiments/SCHEMA.md` and `procedures/SCHEMA.md`.
19. **F-20 – F-28.** The LOW findings: `Manager` concurrency guards, the
    campaign progress verdict, the silent pre-arm timeout, `mode_settled` in
    the runner's `set_mode`, `isfinite` guards, a retention policy for
    `argazui/run/`, Turkish diacritic consistency, the three missing portal
    pages, and the `strip()`/`rstrip()` mismatch.

---

## Appendix A — Commands executed during this audit

```bash
# Structure
find argazui tests docs .github scripts docker -type f | grep -v __pycache__
find argazui/argazui tests -name '*.py' | xargs wc -l

# Test execution
python3 -m pytest --collect-only -q                             # 476 collected
python3 -m pytest --collect-only -q -m tier1                    # 464
python3 -m pytest --collect-only -q -m tier2                    # 12
python3 -m pytest --collect-only -q -m e2e                      # 58
python3 -m pytest -m "tier1 and not e2e" -q                     # 1 failed, 405 passed (432 s)
python3 -m pytest tests/test_docs.py tests/test_localisation.py \
    tests/test_coverage.py tests/test_traceability.py \
    tests/test_evidence_manifest.py tests/test_experiments.py \
    tests/test_experiment_analysis.py -q                        # 170 passed

# Behavioural probes (read-only; scripts written outside the repository)
#  1. criteria evaluated against an empty VehicleState  -> §6.3
#  2. failures.classify_procedure on five abort causes  -> F-02
#  3. status.claims_of on a "not judged" criterion      -> F-10
#  4. session.build_launch_commands with metacharacters -> F-06

# Provenance
git show --stat --oneline d2a9983
git log --oneline -- docs/status.md docs/coverage.md
```

## Appendix B — Limitations of this audit

Stated so the reader knows what is *not* covered:

1. **Tier 2 was not executed.** Gazebo and the `SITL_Models` assets were not
   exercised in this environment. All tier-2 conclusions come from reading
   `tests/gazebo.py`, `tests/test_tier2_models.py`, `docker/Dockerfile.tier2`
   and the committed `docs/status.md`. The 12 tier-2 tests are UNVERIFIED by
   this audit.
2. **The 58 e2e tests were not executed** (no Playwright browser in this
   environment). UI behaviour, the docs portal in a browser, the experiments
   panel and the console-cleanliness assertions are assessed from source only.
3. **No fault injection was performed against a live vehicle.** The GPS and
   MAVLink injectors were audited by reading `faults.py` and the tier-1 fault
   tests (which did run and pass); no `SIM_GPS1_ENABLE` write was observed on a
   real SITL instance during this audit.
4. **CI was not run.** Workflow behaviour is assessed from the YAML and from
   the artefacts already committed. Whether `tier1.yml` currently passes on
   GitHub is UNCLEAR; locally it does not, for the documented reason.
5. **Turkish terminology was reviewed by an auditor with working but
   non-native competence.** The parity findings are machine-verified; the
   terminology judgements in §22.2 (particularly "tutum" for attitude) should
   be confirmed by a native Turkish aerospace engineer.
6. **Long-run behaviour was not measured.** Memory growth over a 50-run
   campaign, the endpoint latency of `rglob` over a few thousand runs, and
   dataflash accumulation over months are reasoned from the implementation and
   from directory listings, not benchmarked.
7. **No source code, test, configuration or documentation file was modified**
   during this audit, with the single exception of this report. Nothing was
   committed or pushed.
