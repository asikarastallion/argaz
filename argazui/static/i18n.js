/* ArgazUI — interface string catalogue.
 *
 * Data only: no logic lives here. It is a separate file from app.js because a
 * catalogue is a table somebody edits, not a program somebody reads — and
 * tests/test_localisation.py parses this file directly to prove that English
 * and Turkish carry the same set of keys.
 *
 * The two blocks below must stay indented exactly as they are: the parser
 * finds them by "\n    en: {" and "\n    tr: {".
 */
window.ARGAZ_I18N = {
    en: {
      tagline: "ArduPilot SITL + Gazebo control panel",
      nav_help: "How to Use", nav_about: "Contact", nav_docs: "Documentation",
      nav_help_title: "How to Use", nav_about_title: "Contact & Project",
      nav_docs_title: "Engineering documentation",

      docs_search: "Search pages and headings…",
      docs_search_hint: "{pages} pages. Search matches page titles and every " +
                        "heading inside them.",
      docs_search_results: "{pages} page(s), {headings} heading(s) match " +
                           "\"{query}\".",
      docs_search_none: "Nothing matches \"{query}\".",
      docs_loading: "loading…",
      docs_failed: "This page could not be loaded: {error}",
      docs_missing: "unavailable",
      docs_source: "Source: {source} — this page is that file in the " +
                   "repository, shown here. Edit the file to change it.",
      docs_source_section: "Source: {source}, section “{section}” — this page " +
                           "is that part of the file, shown here. Edit the " +
                           "file to change it.",
      docs_source_generated: "Generated from the page registry in " +
                             "argazui/argazui/docs.py. It states no technical " +
                             "fact of its own.",
      docs_untranslated: "This page has no Turkish source. What follows is the " +
                         "canonical English document in the repository — a " +
                         "stale translation of a technical page would be worse " +
                         "than an honest English one.",
      docs_link_file: "file",
      selected_model: "SELECTED MODEL",
      click_to_enlarge: "click to enlarge",
      pick_for_preview: "select a model to preview",
      no_preview: "no image for this model",
      none_selected: "— none selected —",
      btn_start: "START", btn_stop: "STOP",
      btn_rescan: "rescan",
      rescan_title: "Re-scan the SITL_Models documentation",
      quick_commands: "Quick Commands",
      mission_script: "Mission Script",
      btn_run_script: "RUN SCRIPT", btn_refresh: "refresh",
      terminal: "Terminal",
      terminal_sub: "real bash sessions — you can type here too",
      tab_sim: "SIMULATION", tab_shell: "COMMAND / SCRIPT",
      cancel: "Cancel", confirm_yes: "Yes, apply", confirm: "Confirm",

      vehicle: "Vehicle", mode: "Mode", alt: "Alt", spd: "Spd",
      armed: "ARMED", disarmed: "DISARMED",
      link_connected: "connected (sys {sysid})",
      link_none: "MAVLink: —",
      ready_unknown: "—", ready_ok: "GO", ready_no: "NO-GO",
      ready_t_unknown: "Pre-arm check status appears here once the vehicle connects.",
      ready_t_ok: "Pre-arm checks passed — you can ARM.",
      ready_t_no: "The autopilot is not ready yet (sensors settling / waiting for " +
                  "home). ARM will be rejected right now.",
      t_model: "Running model",
      t_link: "ArgazUI's MAVLink connection (port 14550)",
      t_mode: "Active flight mode",
      t_armed: "Whether the motors are armed",
      t_alt: "Altitude relative to the launch point",
      t_spd: "Ground speed",

      no_models: "— no models —",
      needs_review: " ⚠ verify manually",
      cls: "class", method: "method", env: "env",
      rviz_yes: "RViz/DDS: yes", rviz_no: "RViz/DDS: no",
      ctx_none: "(no model selected)", ctx_idle: " — vehicle not running",
      hint_mode_settling: "waiting for the mode to settle — a command sent now would be silently overwritten by the flight-mode switch",
      hint_pick: "Pick a model. The buttons change with the vehicle class " +
                 "(Copter/Plane/VTOL).",
      hint_buttons: "Buttons are sent over MAVLink (port 14550). Results appear in " +
                    "the terminal. Edit config/buttons.json to add your own.",
      hint_scripts: "Scripts must connect to the MAVLink output on port {script} " +
                    "(the interface uses {ui}, so they do not clash).",
      no_scripts: "— scripts/ folder is empty —",
      live_plot: "LIVE PLOT",
      live_field_address: "Address", live_field_port: "Port",
      live_copy: "⧉", live_copy_host: "⧉",
      live_copy_t: "copy the port", live_copy_host_t: "copy the address",
      live_copied: "{what} copied to the clipboard",
      live_copy_failed: "could not copy — the value is {what}",
      live_idle: "opens when a vehicle starts",
      live_open: "streaming · {n} messages",
      live_waiting: "open, nothing sent yet",
      live_error: "not sending: {error}",
      live_hint: "PlotJuggler → Streaming → UDP Server → Start. Put {host} in " +
                 "Address and {port} in Port — two separate boxes — and set " +
                 "Message Protocol to JSON. One JSON object per MAVLink " +
                 "message, so every field becomes its own series " +
                 "(ATTITUDE/roll, VFR_HUD/alt …). The port is open only while " +
                 "a vehicle runs.",
      live_warn: "⚠ Type only {host} in PlotJuggler's Address box — not " +
                 "\"{host}:{port}\", and not blank. Either of those parses as " +
                 "no address, and PlotJuggler then shows \"Couldn't bind to " +
                 "IPv4 UDP server\" even though it is receiving fine. Pressing " +
                 "OK on that dialog is what stops the stream: close it with " +
                 "the window ✕, or Stop and reconnect with a bare address.",
      live_title: "ArgazUI sends live telemetry to this loopback UDP port; " +
                  "PlotJuggler listens on it. Nothing has to be listening — " +
                  "the datagrams simply go nowhere.",
      confirm_cmds: "These commands will be sent:",
      confirm_stop: "The running Gazebo / SITL / MAVProxy processes will be shut down.",
      ui_connected: "interface connected.",
      ui_lost: "connection lost, retrying in 2 s...",
      proc_title: "Procedure",
      proc_cancel: "cancel",
      proc_running: "running...",
      proc_passed: "PASSED — every acceptance criterion was met",
      proc_failed: "FAILED",
      proc_accept: "Acceptance criteria",
      // The third criterion outcome. Not a failure and not a pass: the
      // telemetry the criterion rests on never arrived, so nothing was
      // measured. Shown as a tooltip on the mark; the detail beside it names
      // the signal and arrives from the backend already translated.
      proc_unevaluable: "not judged — nothing was measured for this criterion",
      proc_alternatives: "alternatives:",
      proc_source: "from",
      confirm_proc: "This runs the procedure below. Each step is verified "
        + "against the vehicle's actual state, not just the ACK.",
      proc_no_match: "no procedure fits this vehicle",
      hint_sim: "Gazebo / SITL / MAVProxy run here. For models launched with " +
                "sim_vehicle.py you can type MAVProxy commands directly.",
      hint_shell: "Plain bash shell — mission scripts run here, and you can type " +
                  "any command.",
      runs_title: "Flight Runs",
      runs_none: "No runs yet. Every START…STOP writes one here: the console log, " +
                 "the MAVLink events, the parameters, the dataflash log and a report.",
      runs_hint: "One directory per session under {root}. A run is archived when you " +
                 "press STOP; the report is generated from the autopilot's own " +
                 "dataflash log a few seconds later.",
      runs_recording: "recording…",
      runs_show_more: "show {hidden} older run(s) — {total} in total",
      runs_show_less: "show only the {shown} most recent",
      runs_open: "report",
      runs_download: "dataflash .BIN",
      runs_copy_mavexplorer: "copy MAVExplorer command",
      runs_copied: "copied to the clipboard",
      runs_copy_failed: "could not copy — the command is: {cmd}",
      runs_rebuild: "rebuild report",
      runs_rebuilding: "rebuilding the report…",
      runs_compare: "compare with the previous run",
      runs_comparing: "comparing…",
      runs_compare_failed: "could not compare: {error}",
      cmp_title: "Compared against {baseline}",
      cmp_passed: "No regression — no metric degraded past its threshold.",
      cmp_regressed: "REGRESSION — at least one metric degraded past its threshold.",
      cmp_incomparable: "Not comparable — these two runs were not produced " +
                        "under conditions that make their numbers mean the " +
                        "same thing, so nothing was compared.",
      cmp_blocking: "{field}: {reason} (baseline {baseline}, current {current})",
      cmp_drift: "Configuration differences: a comparison across these " +
                 "measures the change as much as it measures the aircraft.",
      cmp_metric: "Metric", cmp_baseline: "Baseline", cmp_current: "Current",
      cmp_delta: "Δ", cmp_relative: "Δ%", cmp_verdict: "Verdict",
      cmp_v_improved: "improved", cmp_v_degraded: "degraded",
      cmp_v_unchanged: "unchanged", cmp_v_incomparable: "incomparable",
      cmp_note: "Metrics are measurements, not acceptance criteria. A " +
                "regression here does not mean a criterion failed — it means " +
                "the aircraft is doing the same thing measurably less well " +
                "than the baseline did.",
      runs_no_report: "No report for this run yet.",
      runs_no_bin: "this run has no dataflash log",
      runs_advisories: "{n} advisory",
      runs_clean: "no advisories",
      runs_adv_pending: "advisories: pending",
      runs_adv_title: "Health findings from the dataflash log (vibration, EKF, " +
                      "attitude tracking). They never change a run's pass/fail " +
                      "result — that comes from the procedure's acceptance criteria.",
      st_passed: "PASSED", st_failed: "FAILED", st_error: "ERROR",
      st_no_procedure: "no procedure", st_incomplete: "incomplete",
      st_passed_title: "Every acceptance criterion of every procedure held.",
      st_failed_title: "A step or an acceptance criterion did not hold.",
      st_error_title: "The procedure could not be evaluated — a fault in ArgazUI " +
                      "or the link, not a verdict about the aircraft.",
      st_no_procedure_title: "The model was started and stopped without running a " +
                             "procedure, so nothing was asserted.",
      runs_files: "Files in this run: {files}",

      // ------------------------------------------------- v1.5: traceability
      ev_title: "Evidence manifest",
      ev_complete: "Complete — every required artefact is in this run's directory.",
      ev_incomplete: "**Incomplete** — {n} required artefact(s) are missing, so " +
                     "the claims in this run rest on evidence that is not here.",
      ev_counts: "{present} of {expected} expected artefacts present; " +
                 "{explained} absent with a stated reason.",
      ev_unexplained: "{n} optional artefact(s) are absent with no reason " +
                      "recorded. \"Absent because matplotlib is missing\" and " +
                      "\"absent\" are different facts.",
      ev_artefact: "Artefact", ev_level: "Level", ev_present: "Present",
      ev_size: "Size", ev_producer: "Produced by",
      ev_yes: "yes", ev_no: "no", ev_missing: "MISSING",
      ev_none: "This run has no evidence manifest — it predates ArgazUI 1.5.",

      tr_title: "Traceability",
      tr_intent: "Intent", tr_manual: "flown by hand — no test asserts this",
      tr_verdict: "Verdict", tr_ok: "Every link in the chain resolves.",
      tr_problems: "{n} problem(s) in the chain — an identifier or an evidence " +
                   "reference does not resolve.",
      tr_derived: "{n} identifier(s) come from a position rather than a " +
                  "declaration, so they would change if a line were inserted " +
                  "above them.",
      tr_step: "step", tr_criterion: "criterion", tr_fault: "fault",
      tr_metric: "metric", tr_evaluated: "evaluated", tr_unevaluated: "not evaluated",
      tr_measured: "measured", tr_unmeasured: "not measured",
      tr_none: "This run has no result.json, so there is no chain to follow.",

      cov_title: "Coverage",
      cov_hint: "What this project declares and what has actually been run. " +
                "Not a test count: that number goes up when somebody adds a " +
                "test and never down when somebody adds a procedure nobody " +
                "runs. The uncovered lists are the point.",
      cov_dimension: "Dimension", cov_covered: "Covered", cov_declared: "Declared",
      cov_uncovered: "Not covered", cov_show: "show",
      cov_failed: "Coverage could not be read: {error}",
      cov_none: "No coverage information is available.",
      cov_all: "All {n} covered.",
      cov_unattributed: "{n} evaluated criterion result(s) come from runs " +
                        "recorded before criterion identifiers existed. They " +
                        "are not matched by position — a coverage figure " +
                        "inflated by a guess is what this project exists to " +
                        "remove.",

      // ------------------------------------------------- v1.4: why it failed
      // The classified category, never the raw message. "acceptance" and
      // "environment" send a reader to two different files, which is the whole
      // reason the category exists.
      fail_title: "Why it did not pass",
      fail_environment: "environment", fail_vehicle_readiness: "vehicle readiness",
      fail_procedure: "procedure", fail_acceptance: "acceptance criterion",
      fail_evidence: "evidence", fail_regression: "regression",
      fail_infrastructure: "infrastructure",
      fail_note: "Only “acceptance criterion” is a verdict about the aircraft. " +
                 "The others say the simulation, the tooling or the evidence " +
                 "went wrong.",

      // ------------------------------------------------ v1.4: scenarios
      scen_title: "Scenarios (fault injection)",
      scen_none: "No scenario matches the connected vehicle. Scenarios live in " +
                 "argazui/procedures/ with role: scenario.",
      scen_idle: "Start a vehicle to see which scenarios apply to it.",
      scen_run: "RUN SCENARIO",
      scen_faults: "{n} declared fault(s)",
      scen_warn: "A scenario deliberately degrades the SIMULATED vehicle — the " +
                 "GPS, or this program's own link to it. Everything it changes " +
                 "is restored when the run ends, and nothing here can reach " +
                 "hardware.",
      scen_fault_line: "{fault} on {target}, held {duration}, injected after " +
                       "step {step}",
      proc_faults: "Injected faults",
      fault_injected: "injected",
      fault_cleared: "cleared",
      fault_not_judged: "not judged",
      link_fault_on: "LINK FAULT ACTIVE — telemetry is being discarded on purpose",

      // ------------------------------------------------ v1.4: campaigns
      camp_title: "Repeatability campaign",
      camp_model: "Model", camp_procedure: "Procedure", camp_runs: "Runs",
      camp_start: "RUN CAMPAIGN", camp_cancel: "cancel campaign",
      camp_hint: "Flies the same procedure on the same model N times, each with " +
                 "its own run directory and its own evidence, and reports the " +
                 "spread rather than a verdict.",
      camp_running: "Campaign {id}: run {index} of {total}",
      camp_idle: "No campaign is running.",
      camp_none: "No campaign has been recorded yet.",
      camp_failed: "The campaign could not be started: {error}",
      camp_started: "Campaign {id} started: {runs} run(s) of {procedure}.",
      camp_open: "open",
      camp_col_id: "Campaign", camp_col_model: "Model",
      camp_col_procedure: "Procedure", camp_col_runs: "Runs",
      camp_result: "{passed} passed, {failed} failed, {flaky} flaky of {total}",
      camp_rate: "clean pass rate {rate}%",
      camp_sample: "{n} run(s) is {n} run(s). No confidence interval or " +
                   "reliability figure is computed from a sample this size.",
      camp_metric: "Metric", camp_n: "n", camp_mean: "Mean", camp_sd: "Std dev",
      camp_min: "Min", camp_max: "Max",
      camp_sd_none: "— (fewer than 3 measured values: not enough runs to say, " +
                    "which is not the same as no variation)",
      camp_drift: "The iterations were not identical, so any spread below " +
                  "measures the difference as much as it measures the aircraft.",

      // ----------------------------------------------- v1.6: experiments
      // An experiment is several campaigns in sequence, so every string here
      // names the ARM. Losing track of which side of a comparison the aircraft
      // is on is the one confusion this panel exists to prevent.
      exp_title: "Experiments",
      exp_hint: "A controlled comparison declared in a file: one model, one or " +
                "more arms — a procedure flown N times — a stated question, " +
                "acceptance criteria about the group, and what the answer does " +
                "not cover. Each arm is flown as an ordinary campaign.",
      exp_start: "RUN EXPERIMENT", exp_cancel: "cancel experiment",
      exp_open: "open",
      exp_idle: "No experiment is running.",
      exp_running: "Experiment {id}: {done} of {total} run(s) flown.",
      exp_none: "No experiment is declared in argazui/experiments/.",
      exp_no_runs: "No experiment has been flown yet.",
      exp_failed: "The experiment could not be started: {error}",
      exp_arms: "{n} arm(s), {runs} run(s)",
      exp_col_id: "Experiment", exp_col_model: "Model", exp_col_policy: "Compares",
      exp_col_arms: "Arms", exp_col_runs: "Runs", exp_col_flown: "Flown",
      exp_policy_arms: "arm against arm",
      exp_policy_baseline: "against its own earlier run",
      exp_policy_repeats: "nothing — distributions only",
      exp_never_flown: "declared, never flown",
      exp_v_passed: "every declared criterion held",
      exp_v_failed: "a declared criterion did not hold",
      exp_v_incomplete: "incomplete — something declared was never flown or " +
                        "never measured",
      exp_v_not_judged: "nothing was asserted — this experiment declares no " +
                        "acceptance criteria",
      exp_v_not_run: "no run carries this experiment id",
      exp_question: "Question",
      exp_criteria: "Acceptance criteria",
      exp_criterion_passed: "held", exp_criterion_failed: "DID NOT HOLD",
      exp_criterion_unjudged: "not judged",
      exp_delta: "Δ of means", exp_overlap: "Ranges overlap",
      exp_yes: "yes", exp_no: "no",
      exp_basis: "Basis", exp_reference: "Reference", exp_current: "Current",
      exp_no_stats: "No p-value, confidence interval or effect size is computed " +
                    "from a sample this size. What is reported is n on both " +
                    "sides, the two means, their difference, and whether the " +
                    "observed ranges overlap at all — which is not a " +
                    "significance test.",
      exp_limits: "Limitations and non-claims",
      exp_limits_none: "This experiment declared no limitations of its own, so " +
                       "only the standing ones apply.",
      exp_standing: "standing",
      exp_verification: "Everything here is verification: an implementation met " +
                        "criteria somebody declared. None of it is validation — " +
                        "nothing shows the criteria, the model or the question " +
                        "are representative of anything outside a simulator.",

      // Failure states. A blank readout with no explanation is not acceptable
      // in a panel someone flies from.
      panel_failed: "{panel} could not be loaded: {error}. The rest of the page " +
                    "still works; see the browser console for the full error.",
      panel_models: "The model list", panel_commands: "Quick Commands",
      panel_scripts: "The mission script list", panel_runs: "Flight Runs",
      link_ws_down: "interface offline",
      link_ws_connecting: "The browser is still connecting to the ArgazUI server. " +
                          "Nothing on this page is live yet.",
      link_ws_closed: "The WebSocket to the ArgazUI server is closed (code {code}). " +
                      "Reconnecting every 2 s. If this persists the server has " +
                      "stopped — check the terminal it was started from.",
      link_idle: "not started",
      link_idle_detail: "No vehicle has been started, so there is no MAVLink link " +
                        "to make. Pick a model and press START.",
      link_waiting: "no heartbeat yet",
      link_waiting_detail: "The vehicle was started but has never sent a heartbeat " +
                           "on port {port}. Gazebo/SITL may still be booting; watch " +
                           "the SIMULATION terminal for errors.",
      link_stale: "silent {age}s",
      link_stale_detail: "The last heartbeat on port {port} arrived {age} s ago. " +
                         "The vehicle has stopped talking — check the SIMULATION " +
                         "terminal.",
      ws_open: "connected", ws_connecting: "connecting…",
      ws_closed: "disconnected (code {code}) — retrying",
      ws_title: "The WebSocket carrying both terminals and the status bar.",
      why_disabled_no_vehicle: "No vehicle is running. Pick a model and press START.",
      why_disabled_no_link: "The vehicle is running but ArgazUI has no MAVLink " +
                            "connection to it yet.",
      proc_lookup_failed: "The procedure list could not be read from the server " +
                          "({error}), so this button cannot know what it would run.",
      hint_buttons_disabled: "Buttons are disabled: {reason}",
      build_mismatch_title: "⚠ This page and the server it is talking to are " +
                            "different builds of ArgazUI.",
      build_mismatch_body: "The server has been running since {since} and reports " +
                           "build {server}. This page was served by it but was built " +
                           "from {page}. The interface files are read from disk, so a " +
                           "server started before your last change keeps answering " +
                           "with its old API — anything on this page may be wrong " +
                           "or missing. Restart the server:",
      build_mismatch_old: "Page build: {page}. The server does not answer " +
                          "/api/version ({error}), an endpoint that has existed " +
                          "since ArgazUI 1.1 — so the server is older than the " +
                          "interface files it just served you from disk, and parts " +
                          "of this page are calling an API it does not have. " +
                          "Restart the server:",
      http_404_hint: "this endpoint does not exist on the server, which may be older " +
                     "than the interface it served you",
      build_fix_replace: "Run this — it stops that server and starts a current one. " +
                         "Copy the whole line; it needs no editing:",
      build_fix_kill: "This server is too old to tell us where it lives, so stop it " +
                      "by the port it holds — copy the whole line, it needs no " +
                      "editing — then start ArgazUI again the way you normally do:",
      drift_code_title: "⚠ The server is running code that no longer exists on disk.",
      drift_code_body: "Python is imported once, at startup. Whatever you changed " +
                       "since then is NOT running, and the API this page is calling " +
                       "is the old one.",
      drift_ui_title: "⚠ The interface files have changed since this server started.",
      drift_ui_body: "You are looking at the new interface files, but they are being " +
                     "driven by the Python this server loaded at startup, so the page " +
                     "may be calling an API it does not have.",
      drift_detail: "Running since {since}; changed since then: {layers}. " +
                    "Restart the server:",
      layer_code: "server code", layer_ui: "interface files",
      layer_procedures: "procedures", layer_config: "configuration",
      build_unstamped: "(the server did not stamp this page)",
      build_unstamped_reason: "the server served this page without a build stamp, " +
                              "which only servers older than ArgazUI 1.1 do",
    
      // ------------------------------------------- v1.8: the application shell
      // Navigation, the instrument bar and the module pages the panels moved
      // into. Section names are nouns, never slogans: the rail is a map of the
      // application, not a menu of things it would like you to feel about it.
      nav_group_operations: "OPERATIONS", nav_group_verification: "VERIFICATION",
      nav_group_evidence: "EVIDENCE", nav_group_knowledge: "KNOWLEDGE",
      nav_vehicles: "Vehicles", nav_quick_commands: "Quick Commands",
      nav_terminal: "Terminal", nav_procedures: "Procedures",
      nav_scenarios: "Scenarios", nav_campaigns: "Campaigns",
      nav_experiments: "Experiments", nav_coverage: "Coverage",
      nav_runs: "Flight Runs", nav_script: "Mission Script",
      nav_keys: "Alt+1…9 switches section",

      // The instrument bar. A label is markup and never changes; only the
      // reading beside it does.
      ro_vehicle: "VEHICLE", ro_link: "LINK", ro_ready: "READY",
      ro_mode: "MODE", ro_arm: "ARM", ro_alt: "ALT", ro_spd: "SPD",

      // What the aircraft is doing, in one line, from fields the status
      // endpoint already sends. No state here is inferred from a timer.
      veh_title: "VEHICLE",
      vst_none: "no vehicle selected",
      vst_selected: "selected — not running",
      vst_starting: "starting — no MAVLink yet",
      vst_connected: "connected",
      vst_ready: "ready",
      vst_not_ready: "not ready",
      vst_armed: "armed",
      vst_procedure: "procedure running",
      vst_link_fault: "link fault injected",
      cls_copter: "COPTER", cls_plane: "PLANE", cls_vtol: "VTOL",

      // The procedures page: what is declared, and what this aircraft can run.
      proc_page_sub: "Every procedure declared in argazui/procedures/. Which of " +
                     "them applies is decided from capabilities probed off the " +
                     "connected vehicle, so the availability column is empty " +
                     "until one is running. The steps and criteria shown here " +
                     "are read from the same file the regression suite executes.",
      proc_catalogue: "DECLARED PROCEDURES",
      proc_detail: "PROCEDURE DETAIL",
      proc_col_id: "Procedure", proc_col_role: "Role",
      proc_col_available: "Availability", proc_col_covered: "Coverage",
      proc_selected: "selected", proc_applies: "applies",
      proc_not_offered: "not offered", proc_unknown: "unknown",
      proc_run_before: "covered", proc_never_run: "not covered",
      proc_needs_vehicle: "No vehicle is connected, so no capability has been " +
                          "probed and nothing can be said about which of these " +
                          "applies. The declared list below is complete either way.",
      proc_empty: "No procedure is declared in argazui/procedures/.",
      proc_pick: "Select a procedure to read its contract.",
      proc_detail_needs_vehicle: "This procedure is declared but was not offered " +
                                 "for the connected vehicle, so the server sent " +
                                 "no steps or criteria for it. Start the aircraft " +
                                 "it applies to, or read the file directly.",
      proc_inputs: "Inputs", proc_detail_steps: "Steps",
      proc_no_criteria: "This procedure declares no acceptance criterion, so it " +
                        "asserts nothing about the aircraft.",
      proc_overrides: "Parameter overrides",
      proc_run: "RUN PROCEDURE",

      scen_applicable: "APPLICABLE TO THE CONNECTED VEHICLE",
      camp_new: "NEW CAMPAIGN", camp_recorded: "RECORDED CAMPAIGNS",
      exp_run_head: "RUN AN EXPERIMENT", exp_definition: "Definition",
      exp_declared: "DECLARED EXPERIMENTS",
      cov_matrix: "VERIFICATION MATRIX", cov_fraction: "Fraction",
      runs_recorded: "RECORDED RUNS",
      runs_col_when: "Started (UTC)", runs_col_verdict: "Verdict",
      script_available: "AVAILABLE SCRIPTS", script_file: "Script",
      script_note: "Scripts run in the COMMAND / SCRIPT terminal on the " +
                   "operations screen, which is where their output appears.",
      camp_no_procedure: "— start a vehicle to list the procedures it can run —",
          fault_catalogue: "FAULT MECHANISMS",
      fault_col_kind: "Fault", fault_col_observe: "What to observe",
      fault_col_mechanism: "Mechanism", fault_col_source: "Declared in",
      fault_none: "This build declares no fault mechanism.",
    },
    tr: {
      tagline: "ArduPilot SITL + Gazebo kontrol paneli",
      nav_help: "Nasıl Kullanılır", nav_about: "İletişim", nav_docs: "Dokümantasyon",
      nav_help_title: "Nasıl Kullanılır", nav_about_title: "İletişim & Proje",
      nav_docs_title: "Mühendislik dokümantasyonu",

      docs_search: "Sayfa ve başlık ara…",
      docs_search_hint: "{pages} sayfa. Arama, sayfa başlıklarıyla birlikte " +
                        "içlerindeki her başlıkta eşleşir.",
      docs_search_results: "\"{query}\" için {pages} sayfa, {headings} başlık " +
                           "eşleşti.",
      docs_search_none: "\"{query}\" ile eşleşen bir şey yok.",
      docs_loading: "yükleniyor…",
      docs_failed: "Bu sayfa yüklenemedi: {error}",
      docs_missing: "erişilemiyor",
      docs_source: "Kaynak: {source} — bu sayfa, depodaki o dosyanın kendisidir. " +
                   "Değiştirmek için dosyayı düzenle.",
      docs_source_section: "Kaynak: {source}, “{section}” bölümü — bu sayfa, o " +
                           "dosyanın ilgili kısmıdır. Değiştirmek için dosyayı " +
                           "düzenle.",
      docs_source_generated: "argazui/argazui/docs.py içindeki sayfa " +
                             "kaydından üretilir. Kendine ait hiçbir teknik " +
                             "bilgi barındırmaz.",
      docs_untranslated: "Bu sayfanın Türkçe kaynağı yok. Aşağıdaki metin, " +
                         "depodaki asıl İngilizce belgedir — teknik bir " +
                         "sayfanın eskimiş çevirisi, dürüst bir İngilizce " +
                         "metinden kötü olurdu.",
      docs_link_file: "dosya",
      selected_model: "SEÇİLİ MODEL",
      click_to_enlarge: "büyütmek için tıkla",
      pick_for_preview: "önizleme için bir model seç",
      no_preview: "bu model için görsel yok",
      none_selected: "— seçilmedi —",
      btn_start: "BAŞLAT", btn_stop: "DURDUR",
      btn_rescan: "yeniden tara",
      rescan_title: "SITL_Models dokümanlarını yeniden tara",
      quick_commands: "Hızlı Komutlar",
      mission_script: "Görev Scripti",
      btn_run_script: "SCRIPT ÇALIŞTIR", btn_refresh: "yenile",
      terminal: "Terminal",
      terminal_sub: "gerçek bash oturumları — buraya elle de komut yazabilirsin",
      tab_sim: "SİMÜLASYON", tab_shell: "KOMUT / SCRIPT",
      cancel: "Vazgeç", confirm_yes: "Evet, uygula", confirm: "Onay",

      vehicle: "Araç", mode: "Mod", alt: "Alt", spd: "Hız",
      armed: "ARMLI", disarmed: "DİSARM",
      link_connected: "bağlı (sys {sysid})",
      link_none: "MAVLink: —",
      ready_unknown: "—", ready_ok: "GEÇTİ", ready_no: "GEÇMEDİ",
      ready_t_unknown: "Araç bağlanınca ARM öncesi kontrollerin durumu burada görünür.",
      ready_t_ok: "ARM öncesi kontroller geçti — ARM verebilirsin.",
      ready_t_no: "Otopilot henüz hazır değil (sensörler oturuyor / ev konumu " +
                  "bekleniyor). Şimdi ARM verirsen reddedilir.",
      t_model: "Çalışan model",
      t_link: "ArgazUI'nin MAVLink bağlantısı (port 14550)",
      t_mode: "Aktif uçuş modu",
      t_armed: "Motorların kurulu olup olmadığı",
      t_alt: "Kalkış noktasına göre irtifa",
      t_spd: "Yer hızı",

      no_models: "— model yok —",
      needs_review: " ⚠ elle doğrula",
      cls: "sınıf", method: "yöntem", env: "env",
      rviz_yes: "RViz/DDS: var", rviz_no: "RViz/DDS: yok",
      ctx_none: "(model seçilmedi)", ctx_idle: " — araç çalışmıyor",
      hint_mode_settling: "mod oturana kadar bekleniyor — şimdi gönderilen komut uçuş modu anahtarı tarafından sessizce ezilir",
      hint_pick: "Bir model seç. Butonlar aracın sınıfına (Copter/Plane/VTOL) göre " +
                 "değişir.",
      hint_buttons: "Butonlar MAVLink üzerinden gönderilir (port 14550). Sonuçlar " +
                    "terminalde görünür. config/buttons.json ile yeni buton ekleyebilirsin.",
      hint_scripts: "Scriptler {script} portundaki MAVLink çıkışına bağlanmalı " +
                    "(arayüz {ui} portunu kullanıyor, çakışmasın).",
      no_scripts: "— scripts/ klasörü boş —",
      live_plot: "CANLI GRAFİK",
      live_field_address: "Adres", live_field_port: "Port",
      live_copy: "⧉", live_copy_host: "⧉",
      live_copy_t: "portu kopyala", live_copy_host_t: "adresi kopyala",
      live_copied: "{what} panoya kopyalandı",
      live_copy_failed: "kopyalanamadı — değer: {what}",
      live_idle: "araç başlayınca açılır",
      live_open: "akıyor · {n} mesaj",
      live_waiting: "açık, henüz veri gönderilmedi",
      live_error: "gönderilemiyor: {error}",
      live_hint: "PlotJuggler → Streaming → UDP Server → Start. Address " +
                 "kutusuna {host}, Port kutusuna {port} yaz — ikisi ayrı " +
                 "kutudur — ve Message Protocol'ü JSON yap. Her MAVLink mesajı " +
                 "bir JSON nesnesi olarak gider, böylece her alan kendi serisi " +
                 "olur (ATTITUDE/roll, VFR_HUD/alt …). Port yalnızca bir araç " +
                 "çalışırken açıktır.",
      live_warn: "⚠ PlotJuggler'ın Address kutusuna yalnızca {host} yaz — " +
                 "\"{host}:{port}\" değil, boş da değil. İkisi de geçersiz " +
                 "adres sayılır ve PlotJuggler veriyi sorunsuz aldığı halde " +
                 "\"Couldn't bind to IPv4 UDP server\" uyarısını gösterir. " +
                 "Akışı durduran şey o pencerede OK'a basmaktır: pencereyi ✕ " +
                 "ile kapat ya da Stop deyip düz adresle yeniden bağlan.",
      live_title: "ArgazUI canlı telemetriyi bu yerel UDP portuna gönderir; " +
                  "PlotJuggler bu portu dinler. Dinleyen olmak zorunda değil " +
                  "— paketler o durumda hiçbir yere gitmez.",
      confirm_cmds: "Şu komutlar gönderilecek:",
      confirm_stop: "Çalışan Gazebo / SITL / MAVProxy süreçleri kapatılacak.",
      ui_connected: "arayüz bağlandı.",
      ui_lost: "bağlantı koptu, 2 sn içinde yeniden denenecek...",
      proc_title: "Prosedür",
      proc_cancel: "iptal",
      proc_running: "çalışıyor...",
      proc_passed: "GEÇTİ — tüm kabul kriterleri sağlandı",
      proc_failed: "BAŞARISIZ",
      proc_accept: "Kabul kriterleri",
      proc_unevaluable: "değerlendirilmedi — bu kriter için hiçbir şey ölçülmedi",
      proc_alternatives: "alternatifler:",
      proc_source: "kaynak",
      confirm_proc: "Aşağıdaki prosedür çalıştırılacak. Her adım sadece ACK'e "
        + "değil, aracın gerçek durumuna karşı doğrulanır.",
      proc_no_match: "bu araca uyan prosedür yok",
      hint_sim: "Gazebo / SITL / MAVProxy burada çalışır. sim_vehicle.py ile açılan " +
                "modellerde MAVProxy komutlarını buraya yazabilirsin.",
      hint_shell: "Boş bash kabuğu — görev scriptleri burada çalışır, elle komut da " +
                  "yazabilirsin.",
      runs_title: "Uçuş Koşuları",
      runs_none: "Henüz koşu yok. Her BAŞLAT…DURDUR buraya bir tane yazar: konsol " +
                 "kaydı, MAVLink olayları, parametreler, dataflash log ve rapor.",
      runs_hint: "{root} altında oturum başına bir dizin. Koşu, DURDUR'a bastığında " +
                 "arşivlenir; rapor birkaç saniye sonra otopilotun kendi dataflash " +
                 "logundan üretilir.",
      runs_recording: "kaydediliyor…",
      runs_show_more: "{hidden} eski koşuyu daha göster — toplam {total}",
      runs_show_less: "yalnızca son {shown} koşuyu göster",
      runs_open: "rapor",
      runs_download: "dataflash .BIN",
      runs_copy_mavexplorer: "MAVExplorer komutunu kopyala",
      runs_copied: "panoya kopyalandı",
      runs_copy_failed: "kopyalanamadı — komut: {cmd}",
      runs_rebuild: "raporu yeniden üret",
      runs_rebuilding: "rapor yeniden üretiliyor…",
      runs_compare: "önceki koşuyla karşılaştır",
      runs_comparing: "karşılaştırılıyor…",
      runs_compare_failed: "karşılaştırılamadı: {error}",
      cmp_title: "{baseline} referansına karşı",
      cmp_passed: "Regresyon yok — hiçbir metrik eşiğini aşacak kadar kötüleşmedi.",
      cmp_regressed: "REGRESYON — en az bir metrik eşiğini aşacak kadar kötüleşti.",
      cmp_incomparable: "Karşılaştırılamaz — bu iki koşu, sayılarının aynı " +
                        "anlama gelmesini sağlayacak koşullarda üretilmemiş; " +
                        "bu yüzden hiçbir şey karşılaştırılmadı.",
      cmp_blocking: "{field}: {reason} (referans {baseline}, güncel {current})",
      cmp_drift: "Yapılandırma farkları: bunların üzerinden yapılan bir " +
                 "karşılaştırma, aracı ölçtüğü kadar değişikliği de ölçer.",
      cmp_metric: "Metrik", cmp_baseline: "Referans", cmp_current: "Güncel",
      cmp_delta: "Δ", cmp_relative: "Δ%", cmp_verdict: "Hüküm",
      cmp_v_improved: "iyileşti", cmp_v_degraded: "kötüleşti",
      cmp_v_unchanged: "değişmedi", cmp_v_incomparable: "karşılaştırılamaz",
      cmp_note: "Metrikler ölçümdür, kabul kriteri değil. Buradaki bir " +
                "regresyon bir kriterin düştüğü anlamına gelmez — aracın aynı " +
                "işi referansa göre ölçülebilir biçimde daha kötü yaptığı " +
                "anlamına gelir.",
      runs_no_report: "Bu koşunun henüz raporu yok.",
      runs_no_bin: "bu koşuda dataflash log yok",
      runs_advisories: "{n} danışma",
      runs_clean: "danışma uyarısı yok",
      runs_adv_pending: "danışma: bekliyor",
      runs_adv_title: "Dataflash logundan çıkan sağlık bulguları (titreşim, EKF, " +
                      "tutum takibi). Koşunun geçti/kaldı sonucunu asla " +
                      "değiştirmezler — o sonuç prosedürün kabul kriterlerinden gelir.",
      st_passed: "GEÇTİ", st_failed: "BAŞARISIZ", st_error: "HATA",
      st_no_procedure: "prosedür yok", st_incomplete: "yarım",
      st_passed_title: "Her prosedürün her kabul kriteri sağlandı.",
      st_failed_title: "Bir adım ya da bir kabul kriteri sağlanmadı.",
      st_error_title: "Prosedür değerlendirilemedi — ArgazUI ya da bağlantıdaki " +
                      "bir arıza; araç hakkında bir hüküm değil.",
      st_no_procedure_title: "Model başlatılıp durduruldu ama prosedür " +
                             "çalıştırılmadı; hiçbir şey iddia edilmedi.",
      runs_files: "Bu koşudaki dosyalar: {files}",

      // ------------------------------------------------- v1.5: izlenebilirlik
      ev_title: "Kanıt listesi",
      ev_complete: "Eksiksiz — gereken her artefakt bu koşunun dizininde.",
      ev_incomplete: "**Eksik** — gereken {n} artefakt yok; bu koşudaki " +
                     "iddialar burada olmayan kanıta dayanıyor.",
      ev_counts: "Beklenen {expected} artefaktın {present} tanesi mevcut; " +
                 "{explained} tanesi gerekçesi belirtilerek yok.",
      ev_unexplained: "{n} isteğe bağlı artefakt, gerekçesi kaydedilmeden yok. " +
                      "\"matplotlib olmadığı için yok\" ile \"yok\" farklı " +
                      "olgulardır.",
      ev_artefact: "Artefakt", ev_level: "Düzey", ev_present: "Mevcut",
      ev_size: "Boyut", ev_producer: "Üreten",
      ev_yes: "evet", ev_no: "hayır", ev_missing: "EKSİK",
      ev_none: "Bu koşunun kanıt listesi yok — ArgazUI 1.5'ten öncesine ait.",

      tr_title: "İzlenebilirlik",
      tr_intent: "Amaç", tr_manual: "elle uçuruldu — bunu doğrulayan test yok",
      tr_verdict: "Hüküm", tr_ok: "Zincirdeki her bağ çözülüyor.",
      tr_problems: "Zincirde {n} sorun — bir tanımlayıcı ya da bir kanıt " +
                   "başvurusu çözülmüyor.",
      tr_derived: "{n} tanımlayıcı beyandan değil konumdan geliyor; üstlerine " +
                  "bir satır eklenirse değişirler.",
      tr_step: "adım", tr_criterion: "kriter", tr_fault: "arıza",
      tr_metric: "metrik", tr_evaluated: "değerlendirildi",
      tr_unevaluated: "değerlendirilmedi",
      tr_measured: "ölçüldü", tr_unmeasured: "ölçülmedi",
      tr_none: "Bu koşuda result.json yok, izlenecek bir zincir de yok.",

      cov_title: "Kapsam",
      cov_hint: "Bu projenin beyan ettikleri ve gerçekten koşulanlar. Test " +
                "sayısı değil: o sayı biri test eklediğinde artar, kimsenin " +
                "koşmadığı bir prosedür eklendiğinde hiç azalmaz. Asıl mesele " +
                "kapsanmayanlar listesidir.",
      cov_dimension: "Boyut", cov_covered: "Kapsanan", cov_declared: "Beyan edilen",
      cov_uncovered: "Kapsanmayan", cov_show: "göster",
      cov_failed: "Kapsam okunamadı: {error}",
      cov_none: "Kapsam bilgisi yok.",
      cov_all: "{n} maddenin tamamı kapsandı.",
      cov_unattributed: "{n} değerlendirilmiş kriter sonucu, kriter " +
                        "tanımlayıcıları var olmadan önce kaydedilmiş " +
                        "koşulardan geliyor. Konuma göre eşleştirilmiyorlar — " +
                        "tahminle şişirilmiş bir kapsam değeri, bu projenin " +
                        "ortadan kaldırmak için var olduğu şeydir.",

      // ------------------------------------------------- v1.4: neden geçmedi
      fail_title: "Neden geçmedi",
      fail_environment: "ortam", fail_vehicle_readiness: "araç hazır değil",
      fail_procedure: "prosedür", fail_acceptance: "kabul kriteri",
      fail_evidence: "kanıt", fail_regression: "regresyon",
      fail_infrastructure: "altyapı",
      fail_note: "Yalnızca “kabul kriteri” araç hakkında bir hükümdür. " +
                 "Diğerleri simülasyonun, araçların ya da kanıtın bozulduğunu " +
                 "söyler.",

      // ------------------------------------------------ v1.4: senaryolar
      scen_title: "Senaryolar (arıza enjeksiyonu)",
      scen_none: "Bağlı araca uyan senaryo yok. Senaryolar argazui/procedures/ " +
                 "altında role: scenario ile tanımlanır.",
      scen_idle: "Hangi senaryoların uyduğunu görmek için bir araç başlat.",
      scen_run: "SENARYOYU ÇALIŞTIR",
      scen_faults: "{n} beyan edilmiş arıza",
      scen_warn: "Senaryo, SİMÜLE aracı bilerek bozar — GPS'i ya da bu programın " +
                 "araca olan bağlantısını. Değiştirdiği her şey koşu bitince " +
                 "geri alınır ve buradaki hiçbir şey donanıma ulaşamaz.",
      scen_fault_line: "{fault}, hedef {target}, {duration} uygulanır, {step}. " +
                       "adımdan sonra enjekte edilir",
      proc_faults: "Enjekte edilen arızalar",
      fault_injected: "enjekte edildi",
      fault_cleared: "geri alındı",
      fault_not_judged: "değerlendirilmedi",
      link_fault_on: "BAĞLANTI ARIZASI ETKİN — telemetri bilerek atılıyor",

      // ------------------------------------------------ v1.4: kampanyalar
      camp_title: "Tekrarlanabilirlik kampanyası",
      camp_model: "Model", camp_procedure: "Prosedür", camp_runs: "Koşu",
      camp_start: "KAMPANYAYI BAŞLAT", camp_cancel: "kampanyayı iptal et",
      camp_hint: "Aynı prosedürü aynı model üzerinde N kez uçurur; her koşu " +
                 "kendi dizinini ve kendi kanıtını alır. Tek bir hüküm yerine " +
                 "dağılımı raporlar.",
      camp_running: "Kampanya {id}: {total} koşudan {index}.",
      camp_idle: "Çalışan kampanya yok.",
      camp_none: "Henüz kaydedilmiş kampanya yok.",
      camp_failed: "Kampanya başlatılamadı: {error}",
      camp_started: "Kampanya {id} başladı: {procedure} prosedürü {runs} kez.",
      camp_open: "aç",
      camp_col_id: "Kampanya", camp_col_model: "Model",
      camp_col_procedure: "Prosedür", camp_col_runs: "Koşu",
      camp_result: "{total} koşudan {passed} geçti, {failed} kaldı, " +
                   "{flaky} kararsız",
      camp_rate: "temiz geçiş oranı %{rate}",
      camp_sample: "{n} koşu, {n} koşudur. Bu büyüklükte bir örneklemden güven " +
                   "aralığı ya da güvenilirlik değeri hesaplanmaz.",
      camp_metric: "Metrik", camp_n: "n", camp_mean: "Ortalama",
      camp_sd: "Std sapma", camp_min: "En az", camp_max: "En çok",
      camp_sd_none: "— (3'ten az ölçülmüş değer: söylemeye yetecek kadar koşu " +
                    "yok; bu, değişim yok demek değildir)",
      camp_drift: "Yinelemeler birbirinin aynısı değildi; aşağıdaki dağılım " +
                  "aracı ölçtüğü kadar bu farkı da ölçüyor.",

      // ----------------------------------------------- v1.6: deneyler
      exp_title: "Deneyler",
      exp_hint: "Bir dosyada beyan edilmiş kontrollü karşılaştırma: tek model, " +
                "bir ya da daha çok kol — N kez uçurulan bir prosedür —, açıkça " +
                "yazılmış bir soru, grup hakkında kabul kriterleri ve yanıtın " +
                "neyi kapsamadığı. Her kol sıradan bir kampanya olarak uçurulur.",
      exp_start: "DENEYİ ÇALIŞTIR", exp_cancel: "deneyi iptal et",
      exp_open: "aç",
      exp_idle: "Çalışan deney yok.",
      exp_running: "Deney {id}: {total} koşudan {done} tanesi uçuruldu.",
      exp_none: "argazui/experiments/ altında beyan edilmiş deney yok.",
      exp_no_runs: "Henüz uçurulmuş deney yok.",
      exp_failed: "Deney başlatılamadı: {error}",
      exp_arms: "{n} kol, {runs} koşu",
      exp_col_id: "Deney", exp_col_model: "Model",
      exp_col_policy: "Karşılaştırma", exp_col_arms: "Kol",
      exp_col_runs: "Koşu", exp_col_flown: "Uçurulan",
      exp_policy_arms: "kolu kola karşı",
      exp_policy_baseline: "kendi önceki koşusuna karşı",
      exp_policy_repeats: "hiçbir şey — yalnızca dağılım",
      exp_never_flown: "beyan edildi, hiç uçurulmadı",
      exp_v_passed: "beyan edilen her kriter sağlandı",
      exp_v_failed: "beyan edilen bir kriter sağlanmadı",
      exp_v_incomplete: "eksik — beyan edilen bir şey hiç uçurulmadı ya da hiç " +
                        "ölçülmedi",
      exp_v_not_judged: "hiçbir iddiada bulunulmadı — bu deney kabul kriteri " +
                        "beyan etmiyor",
      exp_v_not_run: "bu deney kimliğini taşıyan koşu yok",
      exp_question: "Soru",
      exp_criteria: "Kabul kriterleri",
      exp_criterion_passed: "sağlandı", exp_criterion_failed: "SAĞLANMADI",
      exp_criterion_unjudged: "değerlendirilmedi",
      exp_delta: "Ortalama farkı", exp_overlap: "Aralıklar örtüşüyor",
      exp_yes: "evet", exp_no: "hayır",
      exp_basis: "Dayanak", exp_reference: "Referans", exp_current: "Güncel",
      exp_no_stats: "Bu büyüklükte bir örneklemden p değeri, güven aralığı ya da " +
                    "etki büyüklüğü hesaplanmaz. Raporlanan şey iki taraftaki n, " +
                    "iki ortalama, farkları ve gözlenen aralıkların örtüşüp " +
                    "örtüşmediğidir — bu bir anlamlılık testi değildir.",
      exp_limits: "Sınırlar ve yapılmayan iddialar",
      exp_limits_none: "Bu deney kendine ait bir sınır beyan etmedi; yalnızca " +
                       "her zaman geçerli olanlar uygulanır.",
      exp_standing: "her zaman geçerli",
      exp_verification: "Buradaki her şey doğrulamadır: bir uygulama, birinin " +
                        "beyan ettiği kriterleri karşıladı. Hiçbiri geçerleme " +
                        "değildir — kriterlerin, modelin ya da sorunun " +
                        "simülatör dışındaki herhangi bir şeyi temsil ettiğini " +
                        "gösteren hiçbir şey yok.",

      panel_failed: "{panel} yüklenemedi: {error}. Sayfanın geri kalanı çalışmaya " +
                    "devam ediyor; tam hata için tarayıcı konsoluna bak.",
      panel_models: "Model listesi", panel_commands: "Hızlı Komutlar",
      panel_scripts: "Görev scripti listesi", panel_runs: "Uçuş Koşuları",
      link_ws_down: "arayüz bağlı değil",
      link_ws_connecting: "Tarayıcı hâlâ ArgazUI sunucusuna bağlanıyor. Bu sayfada " +
                          "henüz hiçbir şey canlı değil.",
      link_ws_closed: "ArgazUI sunucusuna giden WebSocket kapalı (kod {code}). Her " +
                      "2 sn'de yeniden deneniyor. Sürüyorsa sunucu durmuştur — " +
                      "onu başlattığın terminale bak.",
      link_idle: "başlatılmadı",
      link_idle_detail: "Çalışan bir araç yok, dolayısıyla kurulacak bir MAVLink " +
                        "bağlantısı da yok. Bir model seç ve BAŞLAT'a bas.",
      link_waiting: "henüz heartbeat yok",
      link_waiting_detail: "Araç başlatıldı ama {port} portundan hiç heartbeat " +
                           "göndermedi. Gazebo/SITL hâlâ açılıyor olabilir; " +
                           "SİMÜLASYON terminalindeki hatalara bak.",
      link_stale: "{age} sn sessiz",
      link_stale_detail: "{port} portundaki son heartbeat {age} sn önce geldi. " +
                         "Araç konuşmayı kesti — SİMÜLASYON terminaline bak.",
      ws_open: "bağlı", ws_connecting: "bağlanıyor…",
      ws_closed: "koptu (kod {code}) — yeniden deneniyor",
      ws_title: "Her iki terminali ve durum çubuğunu taşıyan WebSocket.",
      why_disabled_no_vehicle: "Çalışan araç yok. Bir model seç ve BAŞLAT'a bas.",
      why_disabled_no_link: "Araç çalışıyor ama ArgazUI henüz ona MAVLink ile " +
                            "bağlanamadı.",
      proc_lookup_failed: "Prosedür listesi sunucudan okunamadı ({error}); bu buton " +
                          "neyi çalıştıracağını bilemiyor.",
      hint_buttons_disabled: "Butonlar devre dışı: {reason}",
      build_mismatch_title: "⚠ Bu sayfa ile konuştuğu sunucu, ArgazUI'nin farklı " +
                            "derlemeleri.",
      build_mismatch_body: "Sunucu {since} tarihinden beri çalışıyor ve {server} " +
                           "derlemesini bildiriyor. Bu sayfayı o sunucu verdi ama " +
                           "sayfa {page} derlemesinden geliyor. Arayüz dosyaları " +
                           "diskten okunur; son değişikliğinden önce başlatılmış bir " +
                           "sunucu eski API'siyle yanıt vermeye devam eder — bu " +
                           "sayfadaki her şey yanlış ya da eksik olabilir. Sunucuyu " +
                           "yeniden başlat:",
      build_mismatch_old: "Sayfa derlemesi: {page}. Sunucu, ArgazUI 1.1'den beri " +
                          "var olan /api/version'a yanıt vermiyor ({error}) — yani " +
                          "sunucu, az önce diskten verdiği arayüz dosyalarından " +
                          "eski ve bu sayfanın bazı bölümleri onda olmayan bir " +
                          "API'yi çağırıyor. Sunucuyu yeniden başlat:",
      http_404_hint: "bu uç nokta sunucuda yok — sunucu, sana verdiği arayüzden " +
                     "eski olabilir",
      build_fix_replace: "Şunu çalıştır — o sunucuyu durdurup güncelini başlatır. " +
                         "Satırın tamamını kopyala; düzenlemeye gerek yok:",
      build_fix_kill: "Bu sunucu nerede olduğunu söyleyemeyecek kadar eski; tuttuğu " +
                      "porttan durdur — satırın tamamını kopyala, düzenlemeye gerek " +
                      "yok — sonra ArgazUI'yi her zamanki gibi başlat:",
      drift_code_title: "⚠ Sunucu, diskte artık bulunmayan bir kodu çalıştırıyor.",
      drift_code_body: "Python yalnızca açılışta import edilir. O andan sonra " +
                       "değiştirdiğin şey ÇALIŞMIYOR ve bu sayfanın çağırdığı API " +
                       "eski olanı.",
      drift_ui_title: "⚠ Sunucu başladığından beri arayüz dosyaları değişti.",
      drift_ui_body: "Yeni arayüz dosyalarına bakıyorsun ama onları sunucunun " +
                     "açılışta yüklediği Python sürüyor; sayfa, sunucuda olmayan " +
                     "bir API'yi çağırıyor olabilir.",
      drift_detail: "{since} tarihinden beri çalışıyor; o zamandan beri değişenler: " +
                    "{layers}. Sunucuyu yeniden başlat:",
      layer_code: "sunucu kodu", layer_ui: "arayüz dosyaları",
      layer_procedures: "prosedürler", layer_config: "yapılandırma",
      build_unstamped: "(sunucu bu sayfaya damga basmadı)",
      build_unstamped_reason: "sunucu bu sayfayı derleme damgası olmadan verdi; " +
                              "bunu yalnızca ArgazUI 1.1'den eski sunucular yapar",
    
      // ------------------------------------------ v1.8: uygulama iskeleti
      nav_group_operations: "OPERASYON", nav_group_verification: "DOĞRULAMA",
      nav_group_evidence: "KANIT", nav_group_knowledge: "BİLGİ",
      nav_vehicles: "Araçlar", nav_quick_commands: "Hızlı Komutlar",
      nav_terminal: "Terminal", nav_procedures: "Prosedürler",
      nav_scenarios: "Senaryolar", nav_campaigns: "Kampanyalar",
      nav_experiments: "Deneyler", nav_coverage: "Kapsam",
      nav_runs: "Uçuş Koşuları", nav_script: "Görev Scripti",
      nav_keys: "Alt+1…9 bölüm değiştirir",

      ro_vehicle: "ARAÇ", ro_link: "BAĞLANTI", ro_ready: "HAZIR",
      ro_mode: "MOD", ro_arm: "ARM", ro_alt: "İRTİFA", ro_spd: "HIZ",

      veh_title: "ARAÇ",
      vst_none: "araç seçilmedi",
      vst_selected: "seçildi — çalışmıyor",
      vst_starting: "başlatılıyor — henüz MAVLink yok",
      vst_connected: "bağlı",
      vst_ready: "hazır",
      vst_not_ready: "hazır değil",
      vst_armed: "armlı",
      vst_procedure: "prosedür çalışıyor",
      vst_link_fault: "bağlantı arızası enjekte edildi",
      cls_copter: "COPTER", cls_plane: "PLANE", cls_vtol: "VTOL",

      proc_page_sub: "argazui/procedures/ altında beyan edilmiş her prosedür. " +
                     "Hangisinin geçerli olduğu, bağlı araçtan yoklanan " +
                     "yeteneklerden belirlenir; bu yüzden bir araç çalışana " +
                     "kadar uygunluk sütunu boştur. Buradaki adımlar ve " +
                     "kriterler, regresyon testlerinin çalıştırdığı dosyanın " +
                     "aynısından okunur.",
      proc_catalogue: "BEYAN EDİLEN PROSEDÜRLER",
      proc_detail: "PROSEDÜR AYRINTISI",
      proc_col_id: "Prosedür", proc_col_role: "Rol",
      proc_col_available: "Uygunluk", proc_col_covered: "Kapsam",
      proc_selected: "seçili", proc_applies: "geçerli",
      proc_not_offered: "sunulmadı", proc_unknown: "bilinmiyor",
      proc_run_before: "kapsanan", proc_never_run: "kapsanmayan",
      proc_needs_vehicle: "Bağlı bir araç yok; hiçbir yetenek yoklanmadı ve " +
                          "bunlardan hangisinin geçerli olduğu söylenemez. " +
                          "Aşağıdaki beyan listesi her hâlükârda eksiksizdir.",
      proc_empty: "argazui/procedures/ altında beyan edilmiş prosedür yok.",
      proc_pick: "Sözleşmesini okumak için bir prosedür seç.",
      proc_detail_needs_vehicle: "Bu prosedür beyan edilmiş ama bağlı araç için " +
                                 "sunulmadı; sunucu onun adımlarını ve " +
                                 "kriterlerini göndermedi. Geçerli olduğu aracı " +
                                 "başlat ya da dosyayı doğrudan oku.",
      proc_inputs: "Girdiler", proc_detail_steps: "Adımlar",
      proc_no_criteria: "Bu prosedür hiçbir kabul kriteri beyan etmiyor; yani " +
                        "araç hakkında hiçbir şey iddia etmiyor.",
      proc_overrides: "Parametre geçersiz kılmaları",
      proc_run: "PROSEDÜRÜ ÇALIŞTIR",

      scen_applicable: "BAĞLI ARAÇ İÇİN GEÇERLİ OLANLAR",
      camp_new: "YENİ KAMPANYA", camp_recorded: "KAYITLI KAMPANYALAR",
      exp_run_head: "DENEY ÇALIŞTIR", exp_definition: "Tanım",
      exp_declared: "BEYAN EDİLEN DENEYLER",
      cov_matrix: "DOĞRULAMA MATRİSİ", cov_fraction: "Oran",
      runs_recorded: "KAYITLI KOŞULAR",
      runs_col_when: "Başlangıç (UTC)", runs_col_verdict: "Hüküm",
      script_available: "KULLANILABİLİR SCRIPTLER", script_file: "Script",
      script_note: "Scriptler operasyon ekranındaki KOMUT / SCRIPT " +
                   "terminalinde çalışır; çıktıları da orada görünür.",
      camp_no_procedure: "— çalıştırabileceği prosedürleri listelemek için bir araç başlat —",
          fault_catalogue: "ARIZA MEKANİZMALARI",
      fault_col_kind: "Arıza", fault_col_observe: "Ne gözlenir",
      fault_col_mechanism: "Mekanizma", fault_col_source: "Beyan yeri",
      fault_none: "Bu derleme hiçbir arıza mekanizması beyan etmiyor.",
    },
};
