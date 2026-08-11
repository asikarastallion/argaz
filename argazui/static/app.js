/* ArgazUI — single-page frontend. No build step; plain JS. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------- i18n
  // English is the default; the EN/TR switch in the top bar changes both the
  // interface and the backend messages (see POST /api/lang).
  const I18N = {
    en: {
      tagline: "ArduPilot SITL + Gazebo control panel",
      nav_help: "HOW TO USE", nav_about: "CONTACT", nav_docs: "DOCS",
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
      btn_start: "▶ START", btn_stop: "■ STOP",
      btn_rescan: "⟳ rescan models",
      rescan_title: "Re-scan the SITL_Models documentation",
      quick_commands: "Quick Commands",
      mission_script: "Mission Script",
      btn_run_script: "▶ RUN SCRIPT", btn_refresh: "⟳ refresh",
      terminal: "Terminal",
      terminal_sub: "real bash sessions — you can type here too",
      tab_sim: "SIMULATION", tab_shell: "COMMAND / SCRIPT",
      cancel: "Cancel", confirm_yes: "Yes, apply", confirm: "Confirm",

      vehicle: "Vehicle", mode: "Mode", alt: "Alt", spd: "Spd",
      armed: "ARMED", disarmed: "DISARMED",
      link_connected: "MAVLink: connected (sys {sysid})",
      link_none: "MAVLink: —",
      ready_unknown: "READY: —", ready_ok: "READY ✓", ready_no: "NOT READY",
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
      proc_cancel: "✕ cancel",
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
      runs_show_more: "⌄ show {hidden} older run(s) — {total} in total",
      runs_show_less: "⌃ show only the {shown} most recent",
      runs_open: "report",
      runs_download: "↓ dataflash .BIN",
      runs_copy_mavexplorer: "⧉ copy MAVExplorer command",
      runs_copied: "copied to the clipboard",
      runs_copy_failed: "could not copy — the command is: {cmd}",
      runs_rebuild: "⟳ rebuild report",
      runs_rebuilding: "rebuilding the report…",
      runs_compare: "⇄ compare with the previous run",
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
      scen_run: "▶ RUN SCENARIO",
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
      camp_start: "▶ RUN CAMPAIGN", camp_cancel: "✕ cancel campaign",
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
      exp_start: "▶ RUN EXPERIMENT", exp_cancel: "✕ cancel experiment",
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
      link_ws_down: "MAVLink: interface offline",
      link_ws_connecting: "The browser is still connecting to the ArgazUI server. " +
                          "Nothing on this page is live yet.",
      link_ws_closed: "The WebSocket to the ArgazUI server is closed (code {code}). " +
                      "Reconnecting every 2 s. If this persists the server has " +
                      "stopped — check the terminal it was started from.",
      link_idle: "MAVLink: not started",
      link_idle_detail: "No vehicle has been started, so there is no MAVLink link " +
                        "to make. Pick a model and press START.",
      link_waiting: "MAVLink: no heartbeat yet",
      link_waiting_detail: "The vehicle was started but has never sent a heartbeat " +
                           "on port {port}. Gazebo/SITL may still be booting; watch " +
                           "the SIMULATION terminal for errors.",
      link_stale: "MAVLink: silent {age}s",
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
    },
    tr: {
      tagline: "ArduPilot SITL + Gazebo kontrol paneli",
      nav_help: "NASIL KULLANILIR", nav_about: "İLETİŞİM", nav_docs: "DOKÜMANTASYON",
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
      btn_start: "▶ BAŞLAT", btn_stop: "■ DURDUR",
      btn_rescan: "⟳ modelleri yeniden tara",
      rescan_title: "SITL_Models dokümanlarını yeniden tara",
      quick_commands: "Hızlı Komutlar",
      mission_script: "Görev Scripti",
      btn_run_script: "▶ SCRIPT ÇALIŞTIR", btn_refresh: "⟳ yenile",
      terminal: "Terminal",
      terminal_sub: "gerçek bash oturumları — buraya elle de komut yazabilirsin",
      tab_sim: "SİMÜLASYON", tab_shell: "KOMUT / SCRIPT",
      cancel: "Vazgeç", confirm_yes: "Evet, uygula", confirm: "Onay",

      vehicle: "Araç", mode: "Mod", alt: "Alt", spd: "Hız",
      armed: "ARMED", disarmed: "DISARMED",
      link_connected: "MAVLink: bağlı (sys {sysid})",
      link_none: "MAVLink: —",
      ready_unknown: "HAZIR: —", ready_ok: "HAZIR ✓", ready_no: "HAZIR DEĞİL",
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
      proc_cancel: "✕ iptal",
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
      runs_show_more: "⌄ {hidden} eski koşuyu daha göster — toplam {total}",
      runs_show_less: "⌃ yalnızca son {shown} koşuyu göster",
      runs_open: "rapor",
      runs_download: "↓ dataflash .BIN",
      runs_copy_mavexplorer: "⧉ MAVExplorer komutunu kopyala",
      runs_copied: "panoya kopyalandı",
      runs_copy_failed: "kopyalanamadı — komut: {cmd}",
      runs_rebuild: "⟳ raporu yeniden üret",
      runs_rebuilding: "rapor yeniden üretiliyor…",
      runs_compare: "⇄ önceki koşuyla karşılaştır",
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
      scen_run: "▶ SENARYOYU ÇALIŞTIR",
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
      camp_start: "▶ KAMPANYAYI BAŞLAT", camp_cancel: "✕ kampanyayı iptal et",
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
      exp_start: "▶ DENEYİ ÇALIŞTIR", exp_cancel: "✕ deneyi iptal et",
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
      link_ws_down: "MAVLink: arayüz bağlı değil",
      link_ws_connecting: "Tarayıcı hâlâ ArgazUI sunucusuna bağlanıyor. Bu sayfada " +
                          "henüz hiçbir şey canlı değil.",
      link_ws_closed: "ArgazUI sunucusuna giden WebSocket kapalı (kod {code}). Her " +
                      "2 sn'de yeniden deneniyor. Sürüyorsa sunucu durmuştur — " +
                      "onu başlattığın terminale bak.",
      link_idle: "MAVLink: başlatılmadı",
      link_idle_detail: "Çalışan bir araç yok, dolayısıyla kurulacak bir MAVLink " +
                        "bağlantısı da yok. Bir model seç ve BAŞLAT'a bas.",
      link_waiting: "MAVLink: henüz heartbeat yok",
      link_waiting_detail: "Araç başlatıldı ama {port} portundan hiç heartbeat " +
                           "göndermedi. Gazebo/SITL hâlâ açılıyor olabilir; " +
                           "SİMÜLASYON terminalindeki hatalara bak.",
      link_stale: "MAVLink: {age} sn sessiz",
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
    },
  };

  let LANG = localStorage.getItem("argazui.lang");
  if (!I18N[LANG]) LANG = "en";               // default: English

  function t(key, vars) {
    let s = (I18N[LANG] && I18N[LANG][key]) || I18N.en[key] || key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
    return s;
  }

  let MODELS = [];
  let BUTTONS = {};
  let selected = null;      // selected model object
  let active = null;        // model id running on the server
  let linked = false;       // MAVLink connected?
  let lastStatus = null;

  async function applyLang(lang, push) {
    LANG = I18N[lang] ? lang : "en";
    localStorage.setItem("argazui.lang", LANG);
    document.documentElement.lang = LANG;

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll(".langbtn").forEach((b) => {
      b.classList.toggle("active", b.dataset.setLang === LANG);
    });
    // Long help/contact copy lives as two blocks in the HTML; swap them.
    document.querySelectorAll("[data-lang-block]").forEach((el) => {
      el.hidden = el.dataset.langBlock !== LANG;
    });

    $("btn-rescan").title = t("rescan_title");
    $("pill-model").title = t("t_model");
    $("pill-link").title = t("t_link");
    $("pill-mode").title = t("t_mode");
    $("pill-armed").title = t("t_armed");
    $("pill-alt").title = t("t_alt");
    $("pill-spd").title = t("t_spd");

    TABS.sim.hint = t("hint_sim");
    TABS.shell.hint = t("hint_shell");
    $("tabhint").textContent = TABS[activeTab].hint;

    selectModel(selected ? selected.id : null);
    renderModelLists();
    renderScripts();
    renderRuns();
    // These two write their own text rather than carrying data-i18n, because
    // both say different things depending on what is running. A language
    // switch has to reach them or they keep the previous language's sentence.
    renderScenarios();
    renderCampaigns();
    renderExperiments();
    renderCoverage();
    if (lastStatus) { $("buttons").dataset.key = ""; applyStatus(lastStatus); }

    const search = $("docs-search");
    if (search) search.placeholder = t("docs_search");

    // Keep backend terminal messages in the same language.
    if (push !== false) {
      try {
        await fetch("/api/lang", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lang: LANG }),
        });
      } catch (e) { /* offline is fine */ }
    }

    // The portal's titles, summaries and page bodies are chosen by the server
    // from its own language setting, so they can only be refreshed after the
    // POST above has landed. Only if the portal has been opened at all.
    if (DOCS) {
      try {
        await loadDocs();
        if (docsPage && !$("sheet-docs").hidden) await openDocs(docsPage);
      } catch (e) {
        console.error("ArgazUI: the documentation index could not be reloaded", e);
      }
    }
  }

  // -------------------------------------------------------------- terminals
  // Two ptys: "sim" runs the simulation (MAVProxy is interactive there for
  // sim_vehicle.py models), "shell" is free for mission scripts and commands.
  const TABS = {
    sim:   { el: "term-sim",   hint: "" },
    shell: { el: "term-shell", hint: "" },
  };
  let activeTab = "sim";

  for (const [name, cfg] of Object.entries(TABS)) {
    const term = new Terminal({
      fontSize: 13,
      fontFamily: 'ui-monospace, "JetBrains Mono", "DejaVu Sans Mono", monospace',
      theme: { background: "#0a0d12", foreground: "#d8e0ea", cursor: "#4da3ff" },
      cursorBlink: true,
      scrollback: 20000,
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open($(cfg.el));
    term.onData((d) => {
      if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ type: "in", stream: name, data: d }));
      }
    });
    cfg.term = term;
    cfg.fit = fit;
  }
  TABS.sim.fit.fit();

  function switchTab(name) {
    activeTab = name;
    for (const [n, cfg] of Object.entries(TABS)) $(cfg.el).hidden = n !== name;
    document.querySelectorAll(".tab").forEach((b) =>
      b.classList.toggle("active", b.dataset.stream === name));
    $("tabhint").textContent = TABS[name].hint;
    // Size cannot be measured while hidden; refit once visible.
    setTimeout(() => { TABS[name].fit.fit(); sendResize(name); TABS[name].term.focus(); }, 0);
  }
  document.querySelectorAll(".tab").forEach((b) => {
    b.onclick = () => switchTab(b.dataset.stream);
  });

  let ws = null;
  // Reported in the terminal header and used by the status bar to explain a
  // blank reading. "connecting" / "open" / "closed".
  let wsState = "connecting";
  let wsCloseCode = null;
  let statusSeen = false;

  function setWsState(state, code) {
    wsState = state;
    wsCloseCode = code === undefined ? wsCloseCode : code;
    renderLinkChip();
    if (lastStatus) applyStatus(lastStatus);
  }

  function connect() {
    setWsState("connecting");
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      setWsState("open", null);
      for (const n of Object.keys(TABS)) sendResize(n);
      TABS.sim.term.write(`\r\n\x1b[36m[ArgazUI]\x1b[0m ${t("ui_connected")}\r\n`);
    };
    ws.onmessage = (ev) => {
      // One malformed frame must not kill the socket's message handler and
      // with it every future status update.
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch (e) {
        console.error("ArgazUI: unparseable WebSocket frame", e);
        return;
      }
      try {
        if (msg.type === "out") {
          const cfg = TABS[msg.stream || "sim"];
          if (!cfg) return;
          const bin = atob(msg.data);
          const buf = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
          cfg.term.write(buf);
        } else if (msg.type === "status") {
          statusSeen = true;
          applyStatus(msg.status);
        } else if (msg.type === "procedure") {
          applyProcedureEvent(msg);
        } else if (msg.type === "campaign") {
          applyCampaignEvent(msg);
        } else if (msg.type === "experiment") {
          applyExperimentEvent(msg);
        }
      } catch (e) {
        console.error("ArgazUI: failed to handle a WebSocket message", msg && msg.type, e);
      }
    };
    ws.onclose = (ev) => {
      setWsState("closed", ev && ev.code);
      TABS[activeTab].term.write(`\r\n\x1b[31m[ArgazUI]\x1b[0m ${t("ui_lost")}\r\n`);
      setTimeout(connect, 2000);
    };
    ws.onerror = () => { /* onclose always follows; the code is reported there */ };
  }

  // ------------------------------------------------------- build identity
  // WHY THIS CHECK EXISTS
  // index.html and app.js are read from disk, so a server left running from an
  // older checkout serves TODAY's interface while answering with YESTERDAY's
  // API. That is precisely how the v1.1 regression reached a user: the page
  // called an endpoint the running server had never heard of, and the failure
  // read as a bug in the page. The server stamps its identity into the HTML it
  // serves; here we compare that against what it reports live.
  async function checkBuild() {
    // Opened as a local file rather than served: there is no server to compare
    // against, and nothing to warn about.
    if (!location.protocol.startsWith("http")) return;

    const served = document.querySelector('meta[name="argazui-build"]');
    let live = null;
    let error = "";
    try {
      live = await getJSON("/api/version", (b) => b && b.build_id);
    } catch (e) {
      error = String(e.message || e);
    }

    // A MISSING stamp is itself a mismatch, and it is the case that matters
    // most. The stamp is injected by the server when it serves this page, so a
    // server old enough to predate the stamping code hands over an unstamped
    // document — which is exactly the stale-server situation this check was
    // written for. Treating "no stamp" as "nothing to check" would have made
    // the whole mechanism blind to its own motivating bug.
    if (!served) {
      showBuildMismatch(t("build_unstamped"), live, error ||
                        t("build_unstamped_reason"));
      return;
    }
    if (!live) {
      showBuildMismatch(served.content, null, error);
      return;
    }
    if (live.build_id !== served.content) {
      showBuildMismatch(served.content, live, "");
      return;
    }
    // Same build id, but the files on disk have moved on since this server
    // booted. This is the everyday case: edit app.js, forget to restart. The
    // commit-based id cannot see it, the content digest can.
    if ((live.stale_layers || []).length) {
      showStaticDrift(live);
    }
  }

  // Which layer moved decides what the user is actually looking at, so the
  // warning names it. Server code going stale means the fix you just made is
  // not running at all; interface files going stale means the page in front
  // of you is newer than the API answering it. Procedures and config are
  // deliberately absent: both are re-read on demand, so a change there is
  // already live and telling someone to restart would be false.
  function showStaticDrift(live) {
    const bar = $("build-warning");
    if (!bar) return;
    const layers = live.stale_layers || [];
    const codeStale = layers.includes("code");
    bar.innerHTML = "";
    const title = document.createElement("b");
    title.textContent = codeStale ? t("drift_code_title") : t("drift_ui_title");
    const body = document.createElement("div");
    body.textContent = (codeStale ? t("drift_code_body") : t("drift_ui_body")) + " " +
      t("drift_detail", {
        since: live.started_utc,
        layers: layers.map((l) => t("layer_" + l) || l).join(", "),
      });
    bar.append(title, body, restartBlock(live));
    bar.hidden = false;
  }

  // A copy-paste block must run verbatim. No <pid>, no <path>: a user pasted
  // an earlier version of this and got "syntax error near unexpected token
  // 'newline'", because bash read the placeholder as a redirection.
  function restartBlock(live) {
    const pre = document.createElement("pre");
    pre.className = "build-fix";
    if (live && live.restart_command) {
      pre.textContent = live.restart_command;
    } else {
      // No /api/version, so the server's directory is unknown. This one-liner
      // needs nothing from us and no editing from the user.
      // Identical to the form in USAGE.md and TROUBLESHOOTING.md, and the
      // one tests/e2e asserts on: one tested command, not three variants.
      // It also reports cleanly when nothing is listening, instead of
      // producing a bash error about an empty pid.
      const port = location.port || "8770";
      pre.textContent =
        `pid=$(ss -ltnpH 'sport = :${port}' ` +
        `| sed -n 's/.*pid=\\([0-9]*\\).*/\\1/p' | head -1) ` +
        `&& kill -TERM "\${pid:?nothing is listening on port ${port}}"`;
    }
    return pre;
  }

  function showBuildMismatch(servedId, live, err) {
    const bar = $("build-warning");
    if (!bar) return;
    bar.innerHTML = "";
    const title = document.createElement("b");
    title.textContent = t("build_mismatch_title");
    const body = document.createElement("div");
    body.textContent = live
      ? t("build_mismatch_body", {
          server: live.build_id,
          since: live.started_utc,
          page: servedId,
        })
      : t("build_mismatch_old", { page: servedId, error: err });
    const how = document.createElement("div");
    how.className = "build-how";
    how.textContent = live ? t("build_fix_replace") : t("build_fix_kill");
    bar.append(title, body, how, restartBlock(live));
    bar.hidden = false;
  }

  // -------------------------------------------------------- safe API access
  // WHY THIS EXISTS
  // A 404 does not make `fetch` reject. Before this helper, `loadRuns()`
  // wrapped only the fetch in a try/catch, so an older backend answering
  // `{"detail":"Not Found"}` sailed straight through, and the render step
  // then threw on `RUNS.runs.length`. That exception propagated out of the
  // startup chain and `connect()` — three lines further down — never ran, so
  // both terminals, the whole status bar and every button died with it.
  async function getJSON(url, shape) {
    const res = await fetch(url);
    if (!res.ok) {
      // A 404 on our own API almost always means the running server predates
      // the interface it just served, so say that rather than a bare number.
      const hint = res.status === 404 ? ` — ${t("http_404_hint")}` : "";
      throw new Error(`${url} returned HTTP ${res.status}${hint}`);
    }
    const body = await res.json();
    if (shape && !shape(body)) {
      throw new Error(`${url} returned an unexpected shape: ${JSON.stringify(body).slice(0, 120)}`);
    }
    return body;
  }

  // Each panel starts independently. One broken panel shows a banner in its
  // own place; it does not take the rest of the page with it.
  async function initPanel(bannerId, label, fn) {
    try {
      await fn();
      clearPanelError(bannerId);
      return true;
    } catch (e) {
      console.error(`ArgazUI: ${label} panel failed to load`, e);
      showPanelError(bannerId, label, e);
      return false;
    }
  }

  function showPanelError(bannerId, label, err) {
    const el = $(bannerId);
    if (!el) return;
    el.textContent = t("panel_failed", { panel: label, error: String(err && err.message || err) });
    el.hidden = false;
  }

  function clearPanelError(bannerId) {
    const el = $(bannerId);
    if (el) el.hidden = true;
  }

  function sendResize(name) {
    const cfg = TABS[name];
    if (ws && ws.readyState === 1 && cfg.term.rows > 0) {
      ws.send(JSON.stringify({
        type: "resize", stream: name, rows: cfg.term.rows, cols: cfg.term.cols,
      }));
    }
  }
  window.addEventListener("resize", () => {
    TABS[activeTab].fit.fit();
    sendResize(activeTab);
  });

  // ----------------------------------------------------------------- status
  // Why is the link not up? Answered from facts the server sends, in the order
  // a user would check them: is the interface even talking to the server, has
  // a vehicle been started, and has that vehicle ever been heard from.
  function linkReason(s) {
    if (wsState !== "open") {
      return {
        short: t("link_ws_down"), cls: "bad",
        detail: wsState === "connecting"
          ? t("link_ws_connecting")
          : t("link_ws_closed", { code: wsCloseCode === null ? "?" : wsCloseCode }),
      };
    }
    if (!s || !s.link_running) {
      return { short: t("link_idle"), cls: "off", detail: t("link_idle_detail") };
    }
    const age = s.vehicle ? s.vehicle.heartbeat_age : null;
    if (age === null || age === undefined) {
      return { short: t("link_waiting"), cls: "warn",
               detail: t("link_waiting_detail", { port: s.ui_port }) };
    }
    return { short: t("link_stale", { age: Math.round(age) }), cls: "warn",
             detail: t("link_stale_detail", { age: Math.round(age), port: s.ui_port }) };
  }

  function renderLinkChip() {
    const chip = $("ws-state");
    if (!chip) return;
    const key = { open: "ws_open", connecting: "ws_connecting", closed: "ws_closed" }[wsState];
    chip.textContent = wsState === "closed"
      ? t("ws_closed", { code: wsCloseCode === null ? "?" : wsCloseCode })
      : t(key);
    chip.className = "wschip " + wsState;
    chip.title = t("ws_title");
  }

  function applyStatus(s) {
    const wasLinked = linked;
    const wasActive = active;
    lastStatus = s;
    active = s.active_model;
    linked = s.vehicle.connected;
    const v = s.vehicle;

    // The vehicle's capabilities can only be read once it is talking, and they
    // belong to that vehicle — so re-probe whenever the link or model changes.
    if ((linked && !wasLinked) || active !== wasActive) loadProcedures();
    if (active !== wasActive) {
      // A run appears when a model starts and gains its report a few seconds
      // after it stops — the report is parsed from the dataflash log on a
      // background thread, so look again once it has had time to finish.
      loadRuns();
      if (!active) { setTimeout(loadRuns, 6000); setTimeout(loadRuns, 20000); }
    }

    const model = $("pill-model");
    model.textContent = `${t("vehicle")}: ` + (s.active_model_name || "—");
    model.className = "pill wide " + (active ? "on" : "off");

    // A bare dash is not acceptable in an industrial panel: whenever the link
    // is not up, the chip states which of the three possible reasons applies.
    const link = $("pill-link");
    if (linked) {
      link.textContent = t("link_connected", { sysid: v.sysid });
      link.className = "pill on";
      link.title = t("t_link");
    } else {
      const reason = linkReason(s);
      link.textContent = reason.short;
      link.className = "pill " + reason.cls;
      link.title = reason.detail;
    }

    // Pre-arm state, so you can see in advance why ARM would be rejected.
    const ready = $("pill-ready");
    if (!linked || !v.prearm_known) {
      ready.textContent = t("ready_unknown");
      ready.className = "pill off";
      ready.title = t("ready_t_unknown");
    } else if (v.prearm_ok) {
      ready.textContent = t("ready_ok");
      ready.className = "pill on";
      ready.title = t("ready_t_ok");
    } else {
      ready.textContent = t("ready_no");
      ready.className = "pill warn";
      ready.title = t("ready_t_no");
    }

    $("pill-mode").textContent = `${t("mode")}: ` + (v.mode || "—");
    const armed = $("pill-armed");
    armed.textContent = v.armed ? t("armed") : t("disarmed");
    armed.className = "pill " + (v.armed ? "armed" : "off");
    $("pill-alt").textContent = `${t("alt")}: ${v.alt} m`;
    $("pill-spd").textContent = `${t("spd")}: ${v.groundspeed} m/s`;

    $("btn-stop").disabled = !active;

    const cls = s.vehicle_class || (selected && selected.vehicle_class);
    // THE MODE-SETTLE GATE.
    //
    // A vehicle is not ready for a command merely because its link is up.
    // ArduPlane reads its flight-mode switch shortly after RC input becomes
    // valid and overwrites any mode set in that window — with no NAK and no
    // STATUSTEXT, so the command silently does nothing. Measured three times
    // in seven full-suite runs; see docs/e2e-flight-flake.md.
    //
    // So the buttons wait for the mode to have stopped moving on its own.
    // `mode_settled` is computed on the VEHICLE's clock, per MODE_SETTLE_S.
    const settled = !active || v.mode_settled !== false;
    renderButtons(cls, !!active && settled);
    if (active && !settled) {
      $("cmd-hint").textContent = t("hint_mode_settling");
    }
    $("script-hint").textContent =
      t("hint_scripts", { script: s.script_port, ui: s.ui_port });
    renderLiveStream(s.plotjuggler);
  }

  // ------------------------------------------------- live telemetry mirror
  // Shows where to point PlotJuggler, and whether anything is actually going
  // out of that port. The message count is the point: "the mirror is open" is
  // a claim, "4127 messages have left it" is a measurement, and this project
  // shows the second wherever it can.
  let PLOT = null;

  function renderLiveStream(info) {
    const box = $("livestream");
    if (!box) return;
    PLOT = info || null;
    // Absent on a server too old to report it, and off when the configured
    // port is 0. Neither is an error; the strip simply is not there.
    if (!info || !info.enabled) { box.hidden = true; return; }
    box.hidden = false;
    box.title = t("live_title");
    // Never rendered as one "host:port" string: that is the token a user
    // pastes into PlotJuggler's Address box, and a host:port there parses as
    // no address at all — the bind "fails", the warning dialog appears, and
    // pressing OK on it tears down a socket that was receiving perfectly.
    $("ls-addr").textContent = info.host;
    $("ls-port").textContent = String(info.port);
    $("btn-copy-host").title = t("live_copy_host_t");
    $("btn-copy-plot").title = t("live_copy_t");
    $("ls-hint").textContent = t("live_hint", { host: info.host, port: info.port });
    $("ls-warn").textContent = t("live_warn", { host: info.host, port: info.port });

    const state = $("ls-state");
    if (info.error) {
      state.textContent = t("live_error", { error: info.error });
      state.className = "ls-state";
    } else if (!info.running) {
      state.textContent = t("live_idle");
      state.className = "ls-state";
    } else if (info.messages > 0) {
      state.textContent = t("live_open", { n: info.messages });
      state.className = "ls-state on";
    } else {
      state.textContent = t("live_waiting");
      state.className = "ls-state";
    }
  }

  // One button per field, each copying only its own value. A single button
  // copying "host:port" is precisely the mistake this feature has to avoid.
  async function copyPlotValue(what) {
    try {
      await navigator.clipboard.writeText(what);
      $("ls-hint").textContent = t("live_copied", { what });
    } catch (e) {
      // Same reason as the MAVExplorer button: the clipboard needs a secure
      // context, and ArgazUI is plain http on localhost.
      $("ls-hint").textContent = t("live_copy_failed", { what });
    }
  }

  $("btn-copy-host").onclick = () => PLOT && copyPlotValue(String(PLOT.host));
  $("btn-copy-plot").onclick = () => PLOT && copyPlotValue(String(PLOT.port));

  // ----------------------------------------------------------------- models
  async function loadModels() {
    const reg = await getJSON("/api/models", (b) => Array.isArray(b && b.models));
    MODELS = reg.models;
    renderModelLists();
  }

  function renderModelLists() {
    for (const cls of ["Copter", "Plane", "VTOL"]) {
      const ul = $("list-" + cls);
      if (!ul) continue;
      ul.innerHTML = "";
      MODELS.filter((m) => m.vehicle_class === cls).forEach((m) => {
        const li = document.createElement("li");
        const label = document.createElement("label");
        label.dataset.id = m.id;
        if (selected && selected.id === m.id) label.classList.add("sel");
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "model";
        radio.value = m.id;
        radio.checked = !!(selected && selected.id === m.id);
        radio.onchange = () => selectModel(m.id);
        const box = document.createElement("div");
        const meta = [];
        if (m.has_ros2) meta.push("ROS2 + RViz");
        if (m.world) meta.push(m.world);
        if (m.frame) meta.push("-f " + m.frame);
        box.innerHTML =
          `<span class="mname">${esc(m.name)}</span>` +
          `<span class="mmeta${m.needs_review ? " review" : ""}">` +
          `${esc(meta.join(" · "))}${m.needs_review ? esc(t("needs_review")) : ""}</span>`;
        label.append(radio);
        if (m.image) {
          const thumb = document.createElement("img");
          thumb.className = "mthumb";
          thumb.src = m.image;
          thumb.alt = "";
          thumb.loading = "lazy";
          label.append(thumb);
        }
        label.append(box);
        li.append(label);
        ul.append(li);
      });
      if (!ul.children.length) {
        ul.innerHTML = `<li class="mmeta" style="color:var(--muted)">${esc(t("no_models"))}</li>`;
      }
    }
  }

  function selectModel(id) {
    selected = MODELS.find((m) => m.id === id) || null;
    document.querySelectorAll(".col li label").forEach((l) =>
      l.classList.toggle("sel", l.dataset.id === id));
    $("selected-name").textContent = selected ? selected.name : t("none_selected");

    const bits = [];
    if (selected) {
      bits.push(`${t("cls")}: ${selected.vehicle_class}`);
      bits.push(`${t("method")}: ${selected.method}`);
      bits.push(`${t("env")}: ${selected.env}`);
      bits.push(selected.has_ros2 ? t("rviz_yes") : t("rviz_no"));
    }
    $("selected-meta").textContent = bits.join(" · ");
    $("btn-start").disabled = !selected;

    const fig = $("preview"), none = $("preview-none"), img = $("preview-img");
    if (selected && selected.image) {
      img.src = selected.image;
      img.alt = selected.name;
      fig.hidden = false;
      none.hidden = true;
    } else {
      fig.hidden = true;
      none.hidden = false;
      none.textContent = selected ? t("no_preview") : t("pick_for_preview");
    }

    if (selected && !active) renderButtons(selected.vehicle_class, false);
  }

  $("preview-img").onclick = () => {
    if (!selected || !selected.image) return;
    $("lightbox-img").src = selected.image;
    $("lightbox-img").alt = selected.name;
    $("lightbox-cap").textContent = selected.name;
    $("lightbox").hidden = false;
  };
  $("lightbox").onclick = () => { $("lightbox").hidden = true; };

  // ---------------------------------------------------------------- buttons
  async function loadButtons() {
    BUTTONS = await getJSON("/api/buttons", (b) => b && typeof b === "object");
  }

  function renderButtons(cls, enabled) {
    const wrap = $("buttons");
    const set = (cls && BUTTONS[cls]) || [];
    // LANG is part of the key so labels re-render on a language switch.
    const procKey = Object.entries(PROCS.roles || {})
      .map(([r, v]) => `${r}:${v.selected || "-"}`).join(",");
    const key = [cls, enabled, linked, set.length, LANG, procKey].join("|");
    if (wrap.dataset.key === key) return;   // status arrives every second
    wrap.dataset.key = key;
    wrap.innerHTML = "";

    $("cmd-context").textContent = cls
      ? `(${cls}${enabled ? "" : t("ctx_idle")})`
      : t("ctx_none");

    if (!set.length) {
      $("cmd-hint").textContent = t("hint_pick");
      return;
    }
    $("cmd-hint").textContent = (!enabled || !linked)
      ? t("hint_buttons_disabled", { reason: !enabled ? t("why_disabled_no_vehicle")
                                                      : t("why_disabled_no_link") })
      : t("hint_buttons");

    for (const b of set) {
      const g = document.createElement("div");
      g.className = "cmdgroup";
      const btn = document.createElement("button");
      btn.className = "btn " + (b.style || "");
      // Labels/tooltips are English-primary with optional *_tr overrides.
      btn.textContent = (LANG === "tr" && b.label_tr) || b.label;
      btn.disabled = !enabled || !linked;
      const desc = (LANG === "tr" && b.desc_tr) || b.desc;
      if (desc) btn.title = desc;

      // A procedure button takes its inputs from the procedure the vehicle
      // selected; a v1.0 command button keeps taking them from buttons.json.
      const isProc = !!(b.procedure_role || b.procedure);
      const proc = isProc ? procForButton(b) : null;
      const inputs = isProc ? ((proc && proc.inputs) || []) : (b.inputs || []);
      if (isProc && !proc) {
        btn.disabled = true;
        btn.title = procsError
          ? t("proc_lookup_failed", { error: procsError })
          : t("proc_no_match");
      } else if (isProc) {
        btn.title = [desc, `${t("proc_source")}: ${proc.id}.yaml`, proc.description]
          .filter(Boolean).join("\n\n");
      }
      // A greyed-out button with no explanation is a dead end. Say which
      // precondition is missing, in the order the user has to satisfy them.
      if (btn.disabled && !(isProc && !proc)) {
        btn.title = !enabled ? t("why_disabled_no_vehicle")
                             : (!linked ? t("why_disabled_no_link") : btn.title);
      }

      const fields = {};
      for (const inp of inputs) {
        const box = document.createElement("input");
        box.type = "number";
        box.value = inp.default;
        if (inp.min !== undefined) box.min = inp.min;
        if (inp.max !== undefined) box.max = inp.max;
        const inpLabel = (LANG === "tr" && inp.label_tr) || inp.label;
        box.title = inpLabel;
        const unit = document.createElement("span");
        unit.className = "unit";
        unit.textContent = inpLabel;
        fields[inp.name] = box;
        g.append(btn, box, unit);
      }
      if (!inputs.length) g.append(btn);

      btn.onclick = () => {
        const values = {};
        for (const [k, el] of Object.entries(fields)) values[k] = parseFloat(el.value);
        if (isProc) {
          if (!proc) return;
          const preview = [`${proc.id}.yaml — ${proc.name}`, ""]
            .concat(proc.steps.map((s, i) => `${i + 1}. ${s.name}`))
            .concat(["", `${t("proc_accept")}:`])
            .concat(proc.expect.map((e) => `• ${e}`))
            .join("\n");
          const go = () => runProcedure(b.procedure || null,
                                        b.procedure ? null : b.procedure_role, values);
          if (b.confirm) confirmDialog(b.label, `${t("confirm_proc")}\n\n${preview}`, go);
          else go();
          return;
        }
        const preview = b.commands.join("  →  ");
        if (b.confirm) {
          confirmDialog(b.label, `${t("confirm_cmds")}\n\n${preview}`,
            () => runCommands(b.commands, values));
        } else {
          runCommands(b.commands, values);
        }
      };
      wrap.append(g);
    }
  }

  async function runCommands(commands, values) {
    await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commands, values }),
    });
    // The result is already printed to the terminal as an [ArgazUI] line.
  }

  // ------------------------------------------------------------- procedures
  // A button carrying `procedure_role` does not have its own command list.
  // The steps, the inputs and the acceptance criteria all come from the YAML
  // in argazui/procedures/ — the same file the regression tests run.
  let PROCS = { capabilities: null, roles: {}, scenarios: [] };
  let procsError = "";

  async function loadProcedures() {
    // Called on every link/model change, so a transient failure degrades the
    // buttons to "no procedure matches" rather than breaking the page.
    try {
      PROCS = await getJSON("/api/procedures", (b) => b && typeof b.roles === "object");
      procsError = "";
    } catch (e) {
      console.error("ArgazUI: /api/procedures failed", e);
      PROCS = { capabilities: null, roles: {}, scenarios: [] };
      procsError = String(e.message || e);
    }
    $("buttons").dataset.key = "";     // force a re-render with the new inputs
    renderScenarios();
    renderCampaigns();
    if (lastStatus) applyStatus(lastStatus);
  }

  function procForButton(b) {
    if (b.procedure) {
      for (const role of Object.keys(PROCS.roles || {})) {
        const hit = (PROCS.roles[role].options || []).find((p) => p.id === b.procedure);
        if (hit) return hit;
      }
      return null;
    }
    const role = PROCS.roles && PROCS.roles[b.procedure_role];
    if (!role || !role.selected) return null;
    return (role.options || []).find((p) => p.id === role.selected) || null;
  }

  async function runProcedure(procedureId, role, values) {
    resetProcedurePanel();
    await fetch("/api/procedure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ procedure_id: procedureId || null, role: role || null, values }),
    });
  }

  function resetProcedurePanel() {
    $("proc-steps").innerHTML = "";
    $("proc-faults").innerHTML = "";
    $("proc-expect").innerHTML = "";
    $("proc-hint").textContent = "";
    $("proc-panel").hidden = false;
  }

  // One row per injected fault, showing the four things a scenario must keep
  // apart: what was injected, how long it was held, whether it was cleared,
  // and the verdict on the aircraft's response.
  // A criterion has THREE outcomes, not two. `passed` alone cannot tell "the
// aircraft did not comply" from "nothing was measured", and painting the
// second one red claims a verdict the run does not support. `evaluated` is
// absent on runs recorded before the field existed; those are read the old
// way, so an archived run still renders.
function expectState(e) {
  if (e.passed) return "passed";
  if (e.evaluated === false) return "unevaluated";
  return "failed";
}
const EXPECT_MARK = { passed: "\u2713", failed: "\u2715", unevaluated: "\u2013" };

function expectTitle(state) {
  return state === "unevaluated" ? t("proc_unevaluable") : "";
}

function renderFault(fault, state) {
    const box = $("proc-faults");
    if (!box.childElementCount) {
      const head = document.createElement("div");
      head.className = "expect-head";
      head.textContent = t("proc_faults");
      box.append(head);
    }
    const id = "proc-fault-" + fault.id;
    let row = $(id);
    if (!row) {
      row = document.createElement("div");
      row.id = id;
      box.append(row);
    }
    const judged = state === "done" && !((fault.evidence_missing || []).length);
    const mark = state !== "done" ? "▸" : judged ? (fault.passed ? "✓" : "✕") : "?";
    const verdict = state !== "done"
      ? t("fault_injected")
      : judged ? "" : t("fault_not_judged");
    row.className = "expect " + (state !== "done" ? "running"
      : judged && fault.passed ? "passed" : "failed");
    row.innerHTML = `<span class="mark">${mark}</span>`
      + `<span class="what">${esc(fault.label || fault.id)}</span>`
      + `<span class="detail">${esc(fault.mechanism || "")}`
      + (fault.held_s ? ` — ${fault.held_s}s` : "")
      + (verdict ? ` [${esc(verdict)}]` : "")
      + (fault.text ? ` ${esc(fault.text)}` : "") + `</span>`;
  }

  const STEP_MARK = { pending: "·", running: "▸", passed: "✓", failed: "✕", skipped: "–" };

  function applyProcedureEvent(msg) {
    const panel = $("proc-panel");
    if (msg.event === "start") {
      resetProcedurePanel();
      $("proc-name").textContent = `${msg.name} — ${t("proc_running")}`;
      for (const step of msg.steps) {
        const li = document.createElement("li");
        li.id = "proc-step-" + step.index;
        li.className = "step " + step.status;
        li.innerHTML = `<span class="mark">${STEP_MARK[step.status]}</span>`
          + `<span class="what">${esc(step.label)}</span><span class="detail"></span>`;
        $("proc-steps").append(li);
      }
      panel.hidden = false;
    } else if (msg.event === "step") {
      const step = msg.step;
      const li = $("proc-step-" + step.index);
      if (!li) return;
      li.className = "step " + step.status;
      li.querySelector(".mark").textContent = STEP_MARK[step.status] || "·";
      const detail = step.text ? `${step.text}` : "";
      li.querySelector(".detail").textContent =
        detail + (step.seconds ? `  (${step.seconds}s)` : "");
    } else if (msg.event === "expect") {
      const e = msg.expect;
      const state = expectState(e);
      const row = document.createElement("div");
      row.className = "expect " + state;
      row.innerHTML = `<span class="mark" title="${esc(expectTitle(state))}">`
        + `${EXPECT_MARK[state]}</span>`
        + `<span class="what">${esc(e.label)}</span>`
        + `<span class="detail">${esc(e.text || "")}</span>`;
      if (!$("proc-expect").childElementCount) {
        const h = document.createElement("div");
        h.className = "expect-head";
        h.textContent = t("proc_accept");
        $("proc-expect").append(h);
      }
      $("proc-expect").append(row);
    } else if (msg.event === "fault") {
      renderFault(msg.fault || {}, msg.state || "injected");
    } else if (msg.event === "fault_done") {
      renderFault(msg.fault || {}, "done");
    } else if (msg.event === "fault_expect" || msg.event === "fault_recovery") {
      const e = msg.expect || {};
      const state = expectState(e);
      const row = document.createElement("div");
      row.className = "expect sub " + state;
      row.innerHTML = `<span class="mark" title="${esc(expectTitle(state))}">`
        + `${EXPECT_MARK[state]}</span>`
        + `<span class="what">${esc(e.label)}</span>`
        + `<span class="detail">${esc(e.text || "")}</span>`;
      $("proc-faults").append(row);
    } else if (msg.event === "done") {
      const r = msg.result;
      $("proc-name").textContent = `${r.name} — `
        + (r.ok ? t("proc_passed") : `${t("proc_failed")}${r.text ? ": " + r.text : ""}`);
      $("proc-name").className = r.ok ? "ok" : "bad";
      $("proc-hint").textContent = `${r.seconds}s`;
      loadProcedures();
    }
  }

  $("btn-proc-cancel").onclick = () => fetch("/api/procedure/cancel", { method: "POST" });

  // ------------------------------------------------------ scenarios (v1.4)
  // Off-nominal flows. They are listed and started by name and are never bound
  // to a quick-command button: injecting a fault must be something a person
  // asked for, not something a capability match decided.
  function renderScenarios() {
    const list = $("scen-list");
    list.innerHTML = "";
    const found = (PROCS && PROCS.scenarios) || [];
    if (!linked) {
      $("scen-hint").textContent = t("scen_idle");
      return;
    }
    if (!found.length) {
      $("scen-hint").textContent = t("scen_none");
      return;
    }
    $("scen-hint").textContent = "";
    for (const scen of found) {
      const row = document.createElement("div");
      row.className = "scen";
      const faults = (scen.failures || []).map((f) =>
        t("scen_fault_line", { fault: f.fault, target: f.target,
                               duration: f.duration_text,
                               step: f.inject_after_step })).join("; ");
      row.innerHTML = `<div class="scen-head"><b>${esc(scen.name)}</b>`
        + `<span class="scen-id">${esc(scen.id)}</span></div>`
        + `<div class="scen-what">${esc(scen.description || "")}</div>`
        + `<div class="scen-faults">${esc(faults)}</div>`;
      const go = document.createElement("button");
      go.className = "btn small";
      go.textContent = t("scen_run");
      go.onclick = () => runProcedure(scen.id, null, defaultsOf(scen));
      row.append(go);
      list.append(row);
    }
  }

  function defaultsOf(proc) {
    const values = {};
    for (const input of proc.inputs || []) values[input.name] = input.default;
    return values;
  }

  // ------------------------------------------------------ campaigns (v1.4)
  let CAMPAIGNS = { campaigns: [], active: { running: false } };

  async function loadCampaigns() {
    CAMPAIGNS = await getJSON("/api/campaigns",
                              (b) => Array.isArray(b && b.campaigns));
    renderCampaigns();
  }

  function campaignProcedureOptions() {
    // Every procedure the connected vehicle can run, scenarios included: a
    // repeatability campaign over an off-nominal flow is the more interesting
    // one, because that is where a result of "four times in five" lives.
    const out = [];
    for (const role of Object.keys((PROCS && PROCS.roles) || {})) {
      for (const p of (PROCS.roles[role].options || [])) out.push(p);
    }
    for (const p of (PROCS && PROCS.scenarios) || []) out.push(p);
    const seen = new Set();
    return out.filter((p) => !seen.has(p.id) && seen.add(p.id));
  }

  function renderCampaigns() {
    const select = $("camp-procedure");
    const chosen = select.value;
    select.innerHTML = "";
    for (const proc of campaignProcedureOptions()) {
      const option = document.createElement("option");
      option.value = proc.id;
      option.textContent = `${proc.name} (${proc.id})`;
      select.append(option);
    }
    if (chosen) select.value = chosen;

    const running = CAMPAIGNS.active && CAMPAIGNS.active.running;
    $("btn-camp-start").disabled = !!running || !active || !select.options.length;
    $("btn-camp-cancel").hidden = !running;
    if (running) {
      const a = CAMPAIGNS.active;
      $("camp-active").textContent = t("camp_running", {
        id: a.definition.id, index: (a.done || 0) + 1, total: a.definition.runs });
    } else {
      $("camp-active").textContent = t("camp_idle");
    }

    const body = $("camp-table").querySelector("tbody");
    body.innerHTML = "";
    if (!(CAMPAIGNS.campaigns || []).length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="runs-empty">${esc(t("camp_none"))}</td>`;
      body.append(tr);
      return;
    }
    for (const entry of CAMPAIGNS.campaigns) {
      const tr = document.createElement("tr");
      const runs = entry.declared_runs
        ? `${entry.recorded_runs}/${entry.declared_runs}` : entry.recorded_runs;
      tr.innerHTML = `<td class="runs-when"><b>${esc(entry.id)}</b></td>`
        + `<td>${esc(entry.model_id || "—")}</td>`
        + `<td class="runs-proc">${esc(entry.procedure_id || "—")}</td>`
        + `<td>${esc(String(runs))}</td>`;
      const actions = document.createElement("td");
      actions.className = "runs-actions";
      const open = document.createElement("button");
      open.className = "btn small";
      open.textContent = t("camp_open");
      open.onclick = () => showCampaign(entry.id);
      actions.append(open);
      tr.append(actions);
      body.append(tr);
    }
  }

  async function showCampaign(id) {
    const box = $("camp-detail");
    box.hidden = false;
    box.textContent = t("runs_comparing");
    let body;
    try {
      body = await getJSON(`/api/campaigns/${encodeURIComponent(id)}`,
                           (b) => b && b.campaign);
    } catch (e) {
      box.textContent = t("camp_failed", { error: String(e.message || e) });
      return;
    }
    const doc = body.campaign;
    const c = doc.counts;
    const rate = doc.pass_rate === null ? "—" : Math.round(doc.pass_rate * 100);
    const parts = [];
    parts.push(`<b>${esc(doc.id)}</b><br>`
      + esc(t("camp_result", { passed: c.passed, failed: c.failed,
                               flaky: c.flaky, total: doc.runs_recorded }))
      + ` — ${esc(t("camp_rate", { rate }))}`);
    parts.push(`<p class="hint">${esc(t("camp_sample", { n: doc.runs_recorded }))}</p>`);
    if (doc.consistency && doc.consistency.checked && !doc.consistency.identical) {
      parts.push(`<p class="cmp-drift">${esc(t("camp_drift"))}</p>`);
    }
    if ((doc.metrics || []).length) {
      const head = [t("camp_metric"), t("camp_n"), t("camp_mean"), t("camp_sd"),
                    t("camp_min"), t("camp_max")];
      let table = `<table class="cmp-table"><thead><tr>`
        + head.map((h) => `<th>${esc(h)}</th>`).join("") + `</tr></thead><tbody>`;
      for (const row of doc.metrics) {
        const unit = row.unit ? ` ${row.unit}` : "";
        const sd = row.stdev === null ? "—" : `${row.stdev}${unit}`;
        table += `<tr><td>${esc(row.label)}${row.procedure ? " — " + esc(row.procedure) : ""}`
          + `<br><small>${esc(row.key)}</small></td>`
          + `<td>${row.n}</td>`
          + `<td>${row.mean === null ? "—" : esc(String(row.mean) + unit)}</td>`
          + `<td>${esc(sd)}</td>`
          + `<td>${row.min === null ? "—" : esc(String(row.min) + unit)}</td>`
          + `<td>${row.max === null ? "—" : esc(String(row.max) + unit)}</td></tr>`;
      }
      parts.push(table + "</tbody></table>");
    }
    let runs = `<table class="cmp-table"><tbody>`;
    for (const row of doc.runs || []) {
      const why = row.failure
        ? `${esc(t("fail_" + row.failure.category) || row.failure.category)}`
        : "—";
      runs += `<tr><td>${row.index}</td><td>${esc(row.run_id)}</td>`
        + `<td class="v-${esc(row.verdict)}">${esc(row.verdict)}</td>`
        + `<td>${why}</td></tr>`;
    }
    parts.push(runs + "</tbody></table>");
    box.innerHTML = parts.join("");
  }

  $("btn-camp-start").onclick = async () => {
    const err = $("err-camp");
    err.hidden = true;
    const body = {
      model_id: active,
      procedure_id: $("camp-procedure").value,
      runs: parseInt($("camp-runs").value, 10) || 5,
      values: {},
    };
    const chosen = campaignProcedureOptions().find((p) => p.id === body.procedure_id);
    if (chosen) body.values = defaultsOf(chosen);
    const res = await (await fetch("/api/campaign", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).json();
    if (!res.ok) {
      err.hidden = false;
      err.textContent = t("camp_failed", { error: res.text || "" });
      return;
    }
    loadCampaigns();
  };

  $("btn-camp-cancel").onclick = async () => {
    await fetch("/api/campaign/cancel", { method: "POST" });
    loadCampaigns();
  };

  function applyCampaignEvent(msg) {
    if (msg.event === "iteration_done" || msg.event === "written"
        || msg.event === "done" || msg.event === "cancelled") {
      loadCampaigns();
      loadRuns();
      // An experiment's arms ARE campaigns, so their iterations arrive here.
      // The experiment panel's progress line only moves if it is told.
      if (EXPERIMENTS.active && EXPERIMENTS.active.running) loadExperiments();
    } else if (msg.event === "iteration_start") {
      $("camp-active").textContent = t("camp_running", {
        id: msg.campaign, index: msg.index, total: msg.of });
    }
  }

  // ----------------------------------------------------- experiments (v1.6)
  // A controlled comparison declared in a file. The panel lists what is
  // declared and what has been flown SIDE BY SIDE, because a declared
  // experiment nobody has run is a question this project asked and never
  // answered — and it is invisible in a listing that only shows results.
  let EXPERIMENTS = { experiments: [], runs: [], active: { running: false } };

  async function loadExperiments() {
    EXPERIMENTS = await getJSON("/api/experiments",
                                (b) => Array.isArray(b && b.experiments));
    renderExperiments();
  }

  function experimentRunsOf(id) {
    return (EXPERIMENTS.runs || []).filter((r) => r.experiment_id === id);
  }

  function renderExperiments() {
    const select = $("exp-select");
    const chosen = select.value;
    select.innerHTML = "";
    for (const item of EXPERIMENTS.experiments || []) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.name} (${item.id})`;
      select.append(option);
    }
    if (chosen) select.value = chosen;

    const running = EXPERIMENTS.active && EXPERIMENTS.active.running;
    $("btn-exp-start").disabled = !!running || !select.options.length;
    $("btn-exp-cancel").hidden = !running;
    if (running) {
      const a = EXPERIMENTS.active;
      $("exp-active").textContent = t("exp_running", {
        id: a.run, done: a.done || 0, total: a.total || 0 });
    } else {
      $("exp-active").textContent = t("exp_idle");
    }

    const body = $("exp-table").querySelector("tbody");
    body.innerHTML = "";
    if (!(EXPERIMENTS.experiments || []).length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="runs-empty">${esc(t("exp_none"))}</td>`;
      body.append(tr);
      return;
    }
    for (const item of EXPERIMENTS.experiments) {
      const flown = experimentRunsOf(item.id);
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="runs-when"><b>${esc(item.id)}</b>`
        + `<br><small>${esc(item.question || "")}</small></td>`
        + `<td>${esc(item.model_id || "—")}</td>`
        + `<td class="runs-proc">${esc(t("exp_policy_" + item.compare.policy))}</td>`
        + `<td>${esc(t("exp_arms", { n: item.arms.length,
                                     runs: item.total_runs }))}</td>`;
      const actions = document.createElement("td");
      actions.className = "runs-actions";
      if (flown.length) {
        const open = document.createElement("button");
        open.className = "btn small";
        open.textContent = t("exp_open");
        open.onclick = () => showExperiment(flown[0].run);
        actions.append(open);
      } else {
        // Said out loud rather than left as an empty cell. "Declared and never
        // flown" is the entry that matters most in this table.
        const note = document.createElement("small");
        note.textContent = t("exp_never_flown");
        actions.append(note);
      }
      tr.append(actions);
      body.append(tr);
    }
  }

  function experimentVerdictText(verdict) {
    return t("exp_v_" + String(verdict).replace(/-/g, "_")) || verdict;
  }

  async function showExperiment(id) {
    const box = $("exp-detail");
    box.hidden = false;
    box.textContent = t("runs_comparing");
    let body;
    try {
      body = await getJSON(`/api/experiments/${encodeURIComponent(id)}`,
                           (b) => b && b.experiment);
    } catch (e) {
      box.textContent = t("exp_failed", { error: String(e.message || e) });
      return;
    }
    const doc = body.experiment;
    const definition = doc.definition || {};
    const parts = [];
    parts.push(`<b>${esc(doc.id)}</b> — `
      + `<span class="v-${esc(doc.verdict)}">`
      + `${esc(experimentVerdictText(doc.verdict))}</span>`);
    if (definition.question) {
      parts.push(`<p class="hint"><b>${esc(t("exp_question"))}:</b> `
        + `${esc(definition.question)}</p>`);
    }

    // Arms first: every number below belongs to one of them.
    let arms = `<table class="cmp-table"><thead><tr>`
      + [t("exp_col_arms"), t("camp_procedure"), t("exp_col_runs"),
         t("camp_result")].map((h) => `<th>${esc(h)}</th>`).join("")
      + `</tr></thead><tbody>`;
    for (const arm of doc.arms || []) {
      const c = arm.counts || {};
      arms += `<tr><td><b>${esc(arm.id)}</b><br><small>${esc(arm.label)}</small></td>`
        + `<td>${esc(arm.procedure_id || "—")}</td>`
        + `<td>${arm.recorded_runs}/${arm.declared_runs || "—"}</td>`
        + `<td>${esc(t("camp_result", { passed: c.passed || 0,
                                        failed: c.failed || 0,
                                        flaky: c.flaky || 0,
                                        total: arm.recorded_runs }))}</td></tr>`;
    }
    parts.push(arms + "</tbody></table>");

    const acceptance = doc.acceptance || {};
    if ((acceptance.criteria || []).length) {
      let table = `<h4>${esc(t("exp_criteria"))}</h4>`
        + `<table class="cmp-table"><tbody>`;
      for (const row of acceptance.criteria) {
        const mark = row.passed ? t("exp_criterion_passed")
          : row.evaluated ? t("exp_criterion_failed") : t("exp_criterion_unjudged");
        const cls = row.passed ? "v-passed" : row.evaluated ? "v-failed" : "v-incomplete";
        table += `<tr><td>${esc(row.label)}<br><small>${esc(row.criterion_id)}`
          + ` — ${esc(row.arm)}</small></td>`
          + `<td class="${cls}">${esc(mark)}</td>`
          + `<td><small>${esc(row.text)}</small></td></tr>`;
      }
      parts.push(table + "</tbody></table>");
    }

    for (const comparison of doc.comparisons || []) {
      let table = `<h4>${esc(comparison.current)} ← ${esc(comparison.reference)}</h4>`
        + `<table class="cmp-table"><thead><tr>`
        + [t("camp_metric"), t("exp_reference"), t("exp_current"), t("exp_delta"),
           t("exp_overlap"), t("exp_basis")]
          .map((h) => `<th>${esc(h)}</th>`).join("")
        + `</tr></thead><tbody>`;
      for (const row of comparison.metrics || []) {
        const unit = row.unit ? ` ${row.unit}` : "";
        const left = row.reference || {}, right = row.current || {};
        const cell = (side) => side.mean === null || side.mean === undefined
          ? "—" : `${side.mean}${unit} (n=${side.n})`;
        const overlap = row.ranges_overlap === null ? "—"
          : row.ranges_overlap ? t("exp_yes") : t("exp_no");
        table += `<tr><td>${esc(row.label)}<br><small>${esc(row.key)}</small></td>`
          + `<td>${esc(cell(left))}</td><td>${esc(cell(right))}</td>`
          + `<td>${row.delta === null ? "—" : esc(String(row.delta) + unit)}</td>`
          + `<td>${esc(overlap)}</td>`
          + `<td>${esc(row.basis)}${row.reason
              ? `<br><small>${esc(row.reason)}</small>` : ""}</td></tr>`;
      }
      parts.push(table + "</tbody></table>");
      parts.push(`<p class="hint">${esc(t("exp_no_stats"))}</p>`);
    }

    // The limitations are part of the result, not a footnote to it. They are
    // rendered here for the same reason section 10 exists in the document: a
    // reader who is not told where the claims stop decides for themselves.
    parts.push(`<h4>${esc(t("exp_limits"))}</h4>`);
    parts.push(`<p class="hint">${esc(t("exp_verification"))}</p>`);
    if (!doc.limitations_declared) {
      parts.push(`<p class="hint">${esc(t("exp_limits_none"))}</p>`);
    }
    let limits = "<ul class=\"exp-limits\">";
    for (const row of doc.limitations || []) {
      const mark = row.source === "standing"
        ? ` <em>(${esc(t("exp_standing"))})</em>` : "";
      limits += `<li><b>${esc(row.label)}</b> — ${esc(row.text)}${mark}</li>`;
    }
    parts.push(limits + "</ul>");
    box.innerHTML = parts.join("");
  }

  $("btn-exp-start").onclick = async () => {
    const err = $("err-exp");
    err.hidden = true;
    const res = await (await fetch("/api/experiment", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ experiment_id: $("exp-select").value }),
    })).json();
    if (!res.ok) {
      err.hidden = false;
      err.textContent = t("exp_failed", { error: res.text || "" });
      return;
    }
    loadExperiments();
  };

  $("btn-exp-cancel").onclick = async () => {
    await fetch("/api/experiment/cancel", { method: "POST" });
    loadExperiments();
  };

  function applyExperimentEvent(msg) {
    // Every experiment event re-reads the listing rather than patching a
    // number into the page. The server already knows how many runs are done;
    // a counter maintained here would be a second answer that drifts the first
    // time an arm is cancelled half way through.
    loadExperiments();
    if (msg.event === "written" || msg.event === "done"
        || msg.event === "cancelled") {
      loadRuns();
    }
  }

  // ------------------------------------------------ evidence & trace (v1.5)
  // Both are shown ABOVE the report, because they say whether the report can
  // be read as evidence at all: a run whose manifest is incomplete, or whose
  // chain has a dangling reference, still renders a report that looks right.
  async function showEvidence(runId) {
    const box = $("run-evidence");
    box.hidden = false;
    box.innerHTML = "";
    let body;
    try {
      body = await getJSON(`/api/runs/${encodeURIComponent(runId)}/evidence`,
                           (b) => b && b.evidence);
    } catch (e) {
      box.innerHTML = `<h3>${esc(t("ev_title"))}</h3>`
        + `<p class="hint">${esc(t("ev_none"))}</p>`;
      return;
    }
    const m = body.evidence;
    const c = m.counts;
    const head = m.complete
      ? `<b class="ok">${esc(t("ev_complete"))}</b>`
      : `<b class="bad">${esc(t("ev_incomplete", { n: c.missing_required }))}</b>`;
    let html = `<h3>${esc(t("ev_title"))}</h3>${head}`
      + `<p class="hint">${esc(t("ev_counts", {
            present: c.present, expected: c.expected,
            explained: c.absent_explained }))}</p>`;
    if (c.absent_unexplained) {
      html += `<p class="cmp-drift">`
        + `${esc(t("ev_unexplained", { n: c.absent_unexplained }))}</p>`;
    }
    html += `<table class="cmp-table"><thead><tr>`
      + [t("ev_artefact"), t("ev_level"), t("ev_present"), t("ev_size"),
         t("ev_producer")].map((h) => `<th>${esc(h)}</th>`).join("")
      + `</tr></thead><tbody>`;
    for (const row of m.artefacts) {
      const present = row.exists
        ? esc(t("ev_yes"))
        : (row.level === "required" ? `<b class="bad">${esc(t("ev_missing"))}</b>`
                                    : esc(t("ev_no")));
      const why = row.exists ? "" : `<br><small>${esc(row.absent_reason || "")}</small>`;
      const size = row.size_bytes === null ? "—" : `${row.size_bytes}`;
      const producer = row.producer
        + (row.producer_schema === null || row.producer_schema === undefined
           ? "" : ` (${row.producer_schema})`);
      html += `<tr><td>${esc(row.path || row.name)}`
        + `<br><small>${esc(row.purpose)}</small></td>`
        + `<td>${esc(row.level)}</td><td>${present}${why}</td>`
        + `<td>${esc(size)}</td><td>${esc(producer)}</td></tr>`;
    }
    box.innerHTML = html + "</tbody></table>";
  }

  async function showTrace(runId) {
    const box = $("run-trace");
    box.hidden = false;
    box.innerHTML = "";
    let body;
    try {
      body = await getJSON(`/api/runs/${encodeURIComponent(runId)}/trace`,
                           (b) => b && b.trace);
    } catch (e) {
      box.innerHTML = `<h3>${esc(t("tr_title"))}</h3>`
        + `<p class="hint">${esc(t("tr_none"))}</p>`;
      return;
    }
    const chain = body.trace;
    const manual = chain.test_id === "manual";
    let html = `<h3>${esc(t("tr_title"))}</h3>`
      + `<p class="hint">${esc(t("tr_intent"))}: <code>${esc(chain.test_id)}</code>`
      + (manual ? ` — ${esc(t("tr_manual"))}` : "")
      + ` · ${esc(t("tr_verdict"))}: ${esc(chain.verdict || "—")}</p>`;

    html += `<table class="cmp-table"><tbody>`;
    for (const procedure of chain.procedures) {
      html += `<tr><td colspan="3"><b>${esc(procedure.procedure_id)}</b> `
        + `→ ${esc(procedure.verdict || "—")}</td></tr>`;
      for (const step of procedure.steps) {
        html += `<tr><td>${esc(t("tr_step"))}</td>`
          + `<td><code>${esc(step.step_id)}</code></td>`
          + `<td>${esc(step.status)}</td></tr>`;
      }
      for (const criterion of procedure.criteria) {
        const mark = criterion.passed ? "passed"
          : (criterion.evaluated ? "failed" : t("tr_unevaluated"));
        html += `<tr><td>${esc(t("tr_criterion"))}</td>`
          + `<td><code>${esc(criterion.criterion_id)}</code></td>`
          + `<td>${esc(mark)}</td></tr>`;
      }
      for (const fault of procedure.faults) {
        html += `<tr><td>${esc(t("tr_fault"))}</td>`
          + `<td><code>${esc(fault.fault_id)}</code></td>`
          + `<td>${esc(fault.passed ? "passed" : "failed")}</td></tr>`;
      }
    }
    for (const metric of chain.metrics) {
      html += `<tr><td>${esc(t("tr_metric"))}</td>`
        + `<td><code>${esc(metric.metric_id)}</code></td>`
        + `<td>${esc(metric.measured ? t("tr_measured") : t("tr_unmeasured"))}</td></tr>`;
    }
    html += "</tbody></table>";

    if ((body.problems || []).length) {
      html += `<p class="cmp-drift">`
        + `${esc(t("tr_problems", { n: body.problems.length }))}</p><ul>`;
      for (const problem of body.problems) {
        html += `<li><code>${esc(problem.problem)}</code> ${esc(problem.subject)}`
          + ` — ${esc(problem.detail)}</li>`;
      }
      html += "</ul>";
    } else {
      html += `<p class="hint">${esc(t("tr_ok"))}</p>`;
    }
    if ((body.derived_ids || []).length) {
      html += `<p class="hint">`
        + `${esc(t("tr_derived", { n: body.derived_ids.length }))}</p>`;
    }
    box.innerHTML = html;
  }

  // ----------------------------------------------------------- coverage (v1.5)
  let COVERAGE = null;

  async function loadCoverage() {
    COVERAGE = await getJSON("/api/coverage",
                             (b) => b && b.coverage && b.coverage.dimensions);
    renderCoverage();
  }

  function renderCoverage() {
    const body = $("cov-table").querySelector("tbody");
    body.innerHTML = "";
    $("cov-detail").hidden = true;
    if (!COVERAGE) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" class="runs-empty">${esc(t("cov_none"))}</td>`;
      body.append(tr);
      return;
    }
    const doc = COVERAGE.coverage;
    for (const dimension of doc.dimensions) {
      const tr = document.createElement("tr");
      const fraction = dimension.fraction === null ? "—"
        : `${Math.round(dimension.fraction * 100)}%`;
      tr.innerHTML = `<td class="runs-when"><b>${esc(dimension.label)}</b></td>`
        + `<td>${dimension.covered} / ${dimension.declared}</td>`
        + `<td>${esc(fraction)}</td>`;
      const actions = document.createElement("td");
      actions.className = "runs-actions";
      if (dimension.uncovered.length) {
        const open = document.createElement("button");
        open.className = "btn small";
        open.textContent = `${dimension.uncovered.length} ${t("cov_uncovered")}`;
        open.onclick = () => showUncovered(dimension);
        actions.append(open);
      } else {
        actions.textContent = t("cov_all", { n: dimension.declared });
      }
      tr.append(actions);
      body.append(tr);
    }
    if (doc.unattributable_criteria) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" class="hint">`
        + `${esc(t("cov_unattributed", { n: doc.unattributable_criteria }))}</td>`;
      body.append(tr);
    }
  }

  function showUncovered(dimension) {
    const box = $("cov-detail");
    box.hidden = false;
    let html = `<b>${esc(dimension.label)}</b>`
      + `<table class="cmp-table"><tbody>`;
    for (const item of dimension.items) {
      if (item.covered) continue;
      html += `<tr><td><code>${esc(item.id)}</code></td>`
        + `<td>${esc(item.what || "")}</td></tr>`;
    }
    box.innerHTML = html + "</tbody></table>";
  }

  $("btn-cov-refresh").onclick = () => {
    const err = $("err-cov");
    err.hidden = true;
    loadCoverage().catch((e) => {
      err.hidden = false;
      err.textContent = t("cov_failed", { error: String(e.message || e) });
    });
  };

  // -------------------------------------------------------------------- runs
  // A reader for the runs/ directory. Nothing here starts or changes a flight;
  // the one write it can make is asking the server to rebuild a report from a
  // dataflash log that is already on disk.
  let RUNS = { runs: [], root: "", active: null };
  let openRun = null;

  // How many runs the panel shows before you ask for the rest. A real
  // installation accumulates dozens, and the panel was an endless scroll that
  // pushed everything below it off the page. Display only: /api/runs still
  // returns every run, newest first, and nothing under runs/ is touched.
  const RUNS_COLLAPSED = 5;
  let runsExpanded = false;

  // The acceptance verdict and the health advisories are two separate things
  // and are shown as two separate chips. A noisy airframe must not read as a
  // broken takeoff, and a genuine acceptance failure must not hide among
  // vibration warnings.
  const RUN_STATUS = {
    passed: "st_passed", failed: "st_failed", error: "st_error",
    "no-procedure": "st_no_procedure", incomplete: "st_incomplete",
  };

  async function loadRuns() {
    // A failure here must reach initPanel so the banner appears — it must not
    // be swallowed, and it must not escape into the startup chain either.
    RUNS = await getJSON("/api/runs", (b) => Array.isArray(b && b.runs));
    renderRuns();
  }

  function shortTime(iso) {
    if (!iso) return "—";
    // "2026-08-02T10:20:10Z" -> "2026-08-02 10:20 UTC"; the run id is UTC by
    // definition, so the label says so rather than silently localising it.
    return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
  }

  function renderRuns() {
    const body = $("runs-table").querySelector("tbody");
    body.innerHTML = "";
    $("runs-root").textContent = RUNS.root || "";
    $("runs-hint").textContent = t("runs_hint", { root: RUNS.root || "runs/" });

    const all = RUNS.runs || [];
    const more = $("btn-runs-more");
    if (!all.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5" class="runs-empty">${esc(t("runs_none"))}</td>`;
      body.append(tr);
      if (more) more.hidden = true;
      return;
    }

    const rows = runsExpanded ? all : all.slice(0, RUNS_COLLAPSED);
    if (more) {
      const hidden = all.length - RUNS_COLLAPSED;
      more.hidden = hidden <= 0;
      more.textContent = runsExpanded
        ? t("runs_show_less", { shown: RUNS_COLLAPSED })
        : t("runs_show_more", { hidden, total: all.length });
    }

    for (const run of rows) {
      const tr = document.createElement("tr");
      const recording = run.run_id === RUNS.active;
      const status = recording ? "recording" : run.status;
      const label = recording ? t("runs_recording") : t(RUN_STATUS[run.status] || "st_incomplete");
      const procedures = run.procedures.map((p) => p.id).join(", ") || "—";
      const seconds = run.seconds ? `${Math.round(run.seconds)}s` : "—";

      const when = document.createElement("td");
      when.className = "runs-when";
      when.innerHTML = `<b>${esc(shortTime(run.started_utc) )}</b>`
        + `<span class="runs-id">${esc(run.run_id)}</span>`;

      const model = document.createElement("td");
      model.textContent = (run.model && (run.model.name || run.model.id)) || "—";

      const proc = document.createElement("td");
      proc.className = "runs-proc";
      proc.textContent = procedures;

      const badge = document.createElement("td");
      const chip = document.createElement("span");
      chip.className = "runbadge " + status;
      chip.textContent = label;
      chip.title = t(`${RUN_STATUS[run.status] || "st_incomplete"}_title`);
      const dur = document.createElement("span");
      dur.className = "runs-dur";
      dur.textContent = seconds;
      badge.append(chip, dur);
      // The classified reason, beside the verdict. "failed" alone sends every
      // reader to the same place; the category sends them to the right one.
      if (run.failure && !recording) {
        const why = document.createElement("span");
        why.className = "runs-why " + run.failure.category;
        why.textContent = t("fail_" + run.failure.category) || run.failure.category;
        why.title = `${run.failure.code}: ${run.failure.detail || ""}\n\n`
          + t("fail_note");
        badge.append(why);
      }

      const actions = document.createElement("td");
      actions.className = "runs-actions";
      const open = document.createElement("button");
      open.className = "btn small";
      open.textContent = t("runs_open");
      open.disabled = !run.has_report;
      open.onclick = () => showRun(run.run_id);
      actions.append(open);

      if (run.dataflash) {
        const dl = document.createElement("a");
        dl.className = "btn small link";
        dl.textContent = "↓ .BIN";
        dl.href = `/api/runs/${encodeURIComponent(run.run_id)}/file/`
          + encodeURIComponent(run.dataflash);
        actions.append(dl);
      }
      // null is "the report has not been produced yet", which is a different
      // answer from zero and is labelled as such.
      const flag = document.createElement("span");
      if (run.advisory_count === null || run.advisory_count === undefined) {
        flag.className = "runs-adv pending";
        flag.textContent = run.has_report ? t("runs_clean") : t("runs_adv_pending");
      } else {
        flag.className = "runs-adv" + (run.advisory_count ? " on" : "");
        flag.textContent = run.advisory_count
          ? t("runs_advisories", { n: run.advisory_count })
          : t("runs_clean");
      }
      flag.title = t("runs_adv_title");
      actions.append(flag);

      tr.append(when, model, proc, badge, actions);
      body.append(tr);
    }
  }

  $("btn-runs-more").onclick = () => {
    runsExpanded = !runsExpanded;
    renderRuns();
  };

  // A collapsed list must never make a run unreachable. Anything that opens a
  // run by id — the #run= deep link most of all — expands the list first if
  // that run is below the fold, so the sheet and the table agree about what
  // exists. Called before the fetch so the page is already right if the
  // report itself is slow.
  function revealRun(runId) {
    const all = RUNS.runs || [];
    const index = all.findIndex((r) => r.run_id === runId);
    if (index >= RUNS_COLLAPSED && !runsExpanded) {
      runsExpanded = true;
      renderRuns();
    }
  }

  async function showRun(runId) {
    revealRun(runId);
    openRun = null;
    $("run-title").textContent = runId;
    $("run-report").textContent = "";
    $("run-plots").innerHTML = "";
    $("run-files").textContent = "";
    $("run-action-hint").textContent = "";
    // A comparison belongs to the run that was open when it was made; leaving
    // it on screen while a different run loads would attach one run's numbers
    // to another run's name.
    $("run-compare").hidden = true;
    $("run-compare").innerHTML = "";
    $("run-evidence").hidden = true;
    $("run-evidence").innerHTML = "";
    $("run-trace").hidden = true;
    $("run-trace").innerHTML = "";
    $("sheet-run").hidden = false;

    const detail = await (await fetch(`/api/runs/${encodeURIComponent(runId)}`)).json();
    openRun = detail;
    $("btn-run-bin").disabled = !detail.dataflash;

    const text = await fetch(`/api/runs/${encodeURIComponent(runId)}/report`);
    $("run-report").textContent = text.ok ? await text.text() : t("runs_no_report");

    // The report links its plots relatively; in the browser they are served
    // through the run's file endpoint.
    for (const plot of (detail.report && detail.report.plots) || []) {
      const img = document.createElement("img");
      img.src = `/api/runs/${encodeURIComponent(runId)}/file/${plot}`;
      img.alt = plot;
      img.loading = "lazy";
      $("run-plots").append(img);
    }
    $("run-files").textContent = t("runs_files", { files: (detail.files || []).join(", ") });

    // Whether the evidence is complete and whether the chain resolves. Both
    // fail soft: a run recorded before v1.5 has neither, and saying so is a
    // better answer than an empty box.
    await showEvidence(runId);
    await showTrace(runId);
  }

  $("btn-run-bin").onclick = () => {
    if (!openRun || !openRun.dataflash) return;
    window.location.href = `/api/runs/${encodeURIComponent(openRun.run_id)}/file/`
      + encodeURIComponent(openRun.dataflash);
  };

  $("btn-run-mavex").onclick = async () => {
    if (!openRun) return;
    const cmd = openRun.mavexplorer;
    if (!cmd) { $("run-action-hint").textContent = t("runs_no_bin"); return; }
    try {
      await navigator.clipboard.writeText(cmd);
      $("run-action-hint").textContent = t("runs_copied");
    } catch (e) {
      // Clipboard access needs a secure context; ArgazUI is plain http on
      // localhost, which some browsers refuse. Show the command instead of
      // pretending it was copied.
      $("run-action-hint").textContent = t("runs_copy_failed", { cmd });
    }
  };

  $("btn-run-rebuild").onclick = async () => {
    if (!openRun) return;
    $("run-action-hint").textContent = t("runs_rebuilding");
    await fetch(`/api/runs/${encodeURIComponent(openRun.run_id)}/report`, { method: "POST" });
    await showRun(openRun.run_id);
    await loadRuns();
  };

  $("btn-runs-refresh").onclick = loadRuns;

  // #run=<run_id> opens that report straight away, so a run can be linked to
  // (and so the panel can be checked without clicking through the page).
  function openRunFromHash() {
    const match = /^#run=(.+)$/.exec(location.hash || "");
    if (match) showRun(decodeURIComponent(match[1]));
  }
  window.addEventListener("hashchange", () => {
    openRunFromHash();
    openDocsFromHash();
  });

  // ---------------------------------------------------------------- scripts
  let SCRIPTS = { scripts: [], dir: "" };

  async function loadScripts() {
    SCRIPTS = await getJSON("/api/scripts", (b) => Array.isArray(b && b.scripts));
    renderScripts();
  }

  function renderScripts() {
    const sel = $("script-select");
    if (!sel) return;
    sel.innerHTML = "";
    $("scripts-dir").textContent = SCRIPTS.dir || "";
    if (!SCRIPTS.scripts || !SCRIPTS.scripts.length) {
      sel.innerHTML = `<option value="">${esc(t("no_scripts"))}</option>`;
      $("btn-script").disabled = true;
      return;
    }
    $("btn-script").disabled = false;
    for (const s of SCRIPTS.scripts) {
      const o = document.createElement("option");
      o.value = s.name;
      o.textContent = s.description ? `${s.name} — ${s.description}` : s.name;
      sel.append(o);
    }
  }

  // ------------------------------------------------------------------ modal
  let modalOk = null;
  function confirmDialog(title, text, onOk) {
    $("modal-title").textContent = title;
    $("modal-text").style.whiteSpace = "pre-wrap";
    $("modal-text").textContent = text;
    modalOk = onOk;
    $("modal").hidden = false;
  }
  $("modal-cancel").onclick = () => { $("modal").hidden = true; modalOk = null; };
  $("modal-ok").onclick = () => {
    $("modal").hidden = true;
    if (modalOk) modalOk();
    modalOk = null;
  };

  // -------------------------------------------------- help / contact sheets
  document.querySelectorAll(".navbtn").forEach((b) => {
    b.onclick = () => { $(b.dataset.sheet).hidden = false; };
  });
  document.querySelectorAll(".sheet-backdrop").forEach((bd) => {
    bd.addEventListener("click", (e) => {
      if (e.target === bd || e.target.hasAttribute("data-close")) bd.hidden = true;
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".sheet-backdrop").forEach((bd) => (bd.hidden = true));
    if (!$("modal").hidden) { $("modal").hidden = true; modalOk = null; }
  });

  document.querySelectorAll(".langbtn").forEach((b) => {
    b.onclick = () => applyLang(b.dataset.setLang);
  });

  // ----------------------------------------------------------------- events
  $("btn-start").onclick = async () => {
    if (!selected) return;
    switchTab("sim");
    await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: selected.id }),
    });
  };

  $("btn-stop").onclick = () => {
    confirmDialog(t("btn_stop"), t("confirm_stop"), async () => {
      await fetch("/api/stop", { method: "POST" });
    });
  };

  $("btn-rescan").onclick = async () => {
    await fetch("/api/rescan", { method: "POST" });
    await loadModels();
  };

  $("btn-script").onclick = async () => {
    const name = $("script-select").value;
    if (!name) return;
    switchTab("shell");     // script output goes to the COMMAND tab
    await fetch("/api/script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  };

  $("btn-script-refresh").onclick = loadScripts;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ------------------------------------------------------------------- docs
  // A markdown renderer, deliberately small. The portal shows files from this
  // repository, and those files use a known subset: headings, fenced code,
  // lists, tables, blockquotes, links and inline code. Anything outside that
  // subset is rendered as the literal text it is.
  //
  // EVERYTHING IS ESCAPED FIRST
  // Markdown in this repository contains raw HTML — `<br>`, `<sub>`, editing
  // comments — and the documents are files anyone with a checkout can edit.
  // Escaping before any transformation means a document can never inject
  // markup into this page; the cost is that a deliberate `<sub>` shows as
  // text, which is a trade this project is happy with.

  function slugify(text) {
    return String(text).toLowerCase()
      .replace(/[`*_~[\]()]/g, "")
      .replace(/[^a-z0-9À-ɏ]+/g, "-")
      .replace(/^-+|-+$/g, "") || "section";
  }

  // Filled from the docs index: "docs/metrics.md" -> "metrics". Lets a
  // relative link between two repository documents become a link between two
  // portal pages instead of a dead one.
  let DOCS_BY_SOURCE = {};

  function docsHref(href) {
    const bare = String(href).split("#")[0].split("/").pop();
    for (const [source, id] of Object.entries(DOCS_BY_SOURCE)) {
      if (source.split("/").pop() === bare) return `#docs=${id}`;
    }
    return "";
  }

  function mdInline(text) {
    let s = esc(text);
    // Code spans are pulled out first so nothing inside them is transformed.
    // The placeholder is NUL-delimited, not anything a document could contain:
    // a readable sentinel would eventually match real prose and silently turn
    // a piece of a sentence into a code span.
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (m, code) => {
      codes.push(code);
      return `\u0000${codes.length - 1}\u0000`;
    });
    // Images become their alt text: the portal shows documents, and a
    // repository-relative image path would 404 in this page's context.
    s = s.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (m, label, href) => {
      if (/^(https?:|mailto:|#)/i.test(href)) {
        return `<a href="${esc(href)}"${href.startsWith("#") ? ""
          : ' target="_blank" rel="noopener noreferrer"'}>${label}</a>`;
      }
      const internal = docsHref(href);
      if (internal) return `<a href="${internal}">${label}</a>`;
      // A relative path with no page behind it: show where the file is
      // instead of a link that would go nowhere.
      return `${label} <code>${esc(href)}</code>`;
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    return s.replace(/\u0000(\d+)\u0000/g, (m, i) => `<code>${codes[i]}</code>`);
  }

  function mdCells(row) {
    // Split on unescaped pipes only. `\|` is how a table cell writes a literal
    // pipe, and it is not a rare case here: the conditions table in the
    // acceptance-criteria page spells absolute values as \|p\|, \|q\|, \|r\|,
    // which a naive split turned into four empty columns.
    return row.replace(/^\s*\|/, "").replace(/(?<!\\)\|\s*$/, "")
      .split(/(?<!\\)\|/)
      .map((cell) => mdInline(cell.trim().replace(/\\\|/g, "|")));
  }

  function renderMarkdown(source) {
    const lines = String(source || "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let paragraph = [];
    const flush = () => {
      if (paragraph.length) out.push(`<p>${mdInline(paragraph.join(" "))}</p>`);
      paragraph = [];
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      const fence = /^\s*(```|~~~)/.exec(line);
      if (fence) {
        flush();
        const body = [];
        i++;
        while (i < lines.length && !lines[i].trimStart().startsWith(fence[1])) {
          body.push(lines[i++]);
        }
        out.push(`<pre><code>${esc(body.join("\n"))}</code></pre>`);
        continue;
      }

      const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
      if (heading) {
        flush();
        const level = heading[1].length;
        out.push(`<h${level} id="${esc(slugify(heading[2]))}">`
          + `${mdInline(heading[2])}</h${level}>`);
        continue;
      }

      if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) { flush(); out.push("<hr>"); continue; }

      // A table is a row of pipes followed by a separator row of dashes.
      if (line.includes("|") && i + 1 < lines.length
          && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1])
          && lines[i + 1].includes("|")) {
        flush();
        const head = mdCells(line);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
          rows.push(mdCells(lines[i++]));
        }
        i--;
        out.push("<table><thead><tr>"
          + head.map((c) => `<th>${c}</th>`).join("")
          + "</tr></thead><tbody>"
          + rows.map((r) => "<tr>" + r.map((c) => `<td>${c}</td>`).join("") + "</tr>").join("")
          + "</tbody></table>");
        continue;
      }

      if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
        flush();
        // One level of nesting, which is all these documents use. The stack
        // closes in order, so a malformed indent cannot leave a tag open.
        const open = [];
        while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
          const item = /^(\s*)([-*+]|\d+\.)\s+(.*)$/.exec(lines[i]);
          const depth = item[1].length >= 2 ? 1 : 0;
          const tag = /\d/.test(item[2]) ? "ol" : "ul";
          while (open.length > depth + 1) out.push(`</${open.pop()}>`);
          if (open.length < depth + 1) { open.push(tag); out.push(`<${tag}>`); }
          out.push(`<li>${mdInline(item[3])}</li>`);
          i++;
        }
        i--;
        while (open.length) out.push(`</${open.pop()}>`);
        continue;
      }

      if (/^\s*>\s?/.test(line)) {
        flush();
        const quoted = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          quoted.push(lines[i++].replace(/^\s*>\s?/, ""));
        }
        i--;
        out.push(`<blockquote>${renderMarkdown(quoted.join("\n"))}</blockquote>`);
        continue;
      }

      if (!line.trim()) { flush(); continue; }
      paragraph.push(line);
    }
    flush();
    return out.join("\n");
  }

  // ------------------------------------------------------------ docs portal
  let DOCS = null;              // the navigation index, as the server built it
  let docsPage = null;          // which page is open
  let docsQuery = "";

  async function loadDocs() {
    DOCS = await getJSON("/api/docs", (b) => Array.isArray(b && b.groups));
    DOCS_BY_SOURCE = {};
    for (const group of DOCS.groups) {
      for (const page of group.pages) {
        if (page.source) DOCS_BY_SOURCE[page.source] = page.id;
      }
    }
    renderDocsTree();
  }

  function docsPages() {
    return (DOCS ? DOCS.groups : []).flatMap((g) => g.pages);
  }

  function docsMatches(page, query) {
    if (!query) return { matched: true, headings: [] };
    const hay = `${page.title} ${page.summary} ${page.source}`.toLowerCase();
    const headings = (page.headings || [])
      .filter((h) => h.text.toLowerCase().includes(query));
    return { matched: hay.includes(query) || headings.length > 0, headings };
  }

  function renderDocsTree() {
    const tree = $("docs-tree");
    if (!tree || !DOCS) return;
    tree.innerHTML = "";
    const query = docsQuery.trim().toLowerCase();
    let pages = 0;
    let headings = 0;

    for (const group of DOCS.groups) {
      const shown = group.pages
        .map((page) => ({ page, ...docsMatches(page, query) }))
        .filter((entry) => entry.matched);
      if (!shown.length) continue;

      const label = document.createElement("div");
      label.className = "docs-group";
      label.textContent = group.title;
      tree.append(label);

      for (const entry of shown) {
        pages += 1;
        const button = document.createElement("button");
        button.className = "docs-link"
          + (entry.page.id === docsPage ? " active" : "")
          + (entry.page.available ? "" : " missing");
        button.innerHTML = `${esc(entry.page.title)}`
          + `<small>${esc(entry.page.available ? entry.page.summary
                                               : t("docs_missing"))}</small>`;
        button.onclick = () => openDocs(entry.page.id);
        tree.append(button);

        // Headings only appear while searching. Listing every heading of every
        // page at rest would make the tree longer than the documents.
        for (const heading of query ? entry.headings : []) {
          headings += 1;
          const jump = document.createElement("button");
          jump.className = "docs-heading" + (heading.level > 2 ? " deep" : "");
          jump.textContent = heading.text;
          jump.onclick = () => openDocs(entry.page.id, slugify(heading.text));
          tree.append(jump);
        }
      }
    }

    const hint = $("docs-searchhint");
    if (!hint) return;
    if (!query) {
      hint.textContent = t("docs_search_hint", { pages: docsPages().length });
    } else if (!pages) {
      hint.textContent = t("docs_search_none", { query: docsQuery.trim() });
    } else {
      hint.textContent = t("docs_search_results",
        { pages, headings, query: docsQuery.trim() });
    }
  }

  async function openDocs(pageId, anchor) {
    $("sheet-docs").hidden = false;
    docsPage = pageId;
    // A deep link can arrive before anything has fetched the tree.
    if (!DOCS) {
      try { await loadDocs(); } catch (e) {
        console.error("ArgazUI: the documentation index could not be loaded", e);
      }
    }
    renderDocsTree();
    $("docs-content").innerHTML = `<p class="hint">${esc(t("docs_loading"))}</p>`;
    $("docs-notice").hidden = true;
    $("docs-source").textContent = "";
    // The hash is written so a page can be linked to and reopened; `#docs=`
    // matches the `#run=` form the runs panel already uses.
    const wanted = `#docs=${pageId}${anchor ? "/" + anchor : ""}`;
    if (location.hash !== wanted) history.replaceState(null, "", wanted);

    let doc;
    try {
      doc = await getJSON(`/api/docs/${encodeURIComponent(pageId)}`);
    } catch (e) {
      $("docs-content").innerHTML =
        `<p class="panel-error">${esc(t("docs_failed", { error: e.message }))}</p>`;
      return;
    }

    $("docs-content").innerHTML = renderMarkdown(doc.markdown);
    $("docs-notice").hidden = doc.translated !== false;
    if (doc.translated === false) $("docs-notice").textContent = t("docs_untranslated");
    $("docs-source").textContent = doc.generated
      ? t("docs_source_generated")
      : (doc.section
          ? t("docs_source_section", { source: doc.source, section: doc.section })
          : t("docs_source", { source: doc.source }));

    const page = $("docs-page");
    const target = anchor && $("docs-content").querySelector(`#${CSS.escape(anchor)}`);
    if (target) target.scrollIntoView({ block: "start" });
    else page.scrollTop = 0;
  }

  function openDocsFromHash() {
    const match = /^#docs=([^/]+)(?:\/(.+))?$/.exec(location.hash || "");
    if (!match) return false;
    openDocs(decodeURIComponent(match[1]),
             match[2] ? decodeURIComponent(match[2]) : undefined);
    return true;
  }

  $("btn-docs").onclick = async () => {
    if (!DOCS) {
      try { await loadDocs(); } catch (e) {
        $("sheet-docs").hidden = false;
        $("docs-content").innerHTML =
          `<p class="panel-error">${esc(t("docs_failed", { error: e.message }))}</p>`;
        return;
      }
    }
    openDocs(docsPage || "index");
  };

  $("docs-search").oninput = (e) => { docsQuery = e.target.value; renderDocsTree(); };

  // -------------------------------------------------------- run comparison
  const CMP_VERDICT = {
    improved: "cmp_v_improved", degraded: "cmp_v_degraded",
    unchanged: "cmp_v_unchanged", incomparable: "cmp_v_incomparable",
  };

  function renderComparison(comparison) {
    const box = $("run-compare");
    box.hidden = false;
    box.innerHTML = "";

    const head = document.createElement("p");
    head.className = "cmp-head";
    const verdict = { passed: "cmp_passed", regressed: "cmp_regressed",
                      incomparable: "cmp_incomparable" }[comparison.verdict];
    head.innerHTML = `<b>${esc(t("cmp_title",
      { baseline: comparison.baseline.run_id }))}</b><br>${esc(t(verdict))}`;
    box.append(head);

    for (const item of comparison.compatibility.blocking || []) {
      const line = document.createElement("p");
      line.className = "cmp-note";
      line.textContent = t("cmp_blocking", {
        field: item.field, reason: item.reason,
        baseline: JSON.stringify(item.baseline), current: JSON.stringify(item.current),
      });
      box.append(line);
    }
    if ((comparison.compatibility.configuration_drift || []).length) {
      const drift = document.createElement("div");
      drift.className = "cmp-drift";
      drift.innerHTML = `<p class="cmp-note">${esc(t("cmp_drift"))}</p><ul>`
        + comparison.compatibility.configuration_drift
            .map((d) => `<li>${esc(d.what)} — <code>${esc(d.field)}</code> (${esc(d.reason)})</li>`)
            .join("")
        + "</ul>";
      box.append(drift);
    }

    const table = document.createElement("table");
    table.innerHTML = "<thead><tr>"
      + [t("cmp_metric"), t("cmp_baseline"), t("cmp_current"), t("cmp_delta"),
         t("cmp_relative"), t("cmp_verdict")]
        .map((h) => `<th>${esc(h)}</th>`).join("")
      + "</tr></thead>";
    const body = document.createElement("tbody");
    const number = (value, unit) =>
      value === null || value === undefined ? "—" : `${Number(value).toPrecision(3)} ${unit || ""}`;
    for (const row of comparison.metrics) {
      const tr = document.createElement("tr");
      // Signed, like the delta beside it: which way a metric moved is the
      // first thing a reader looks for, and an unsigned percentage makes an
      // improvement and a regression look identical at a glance.
      const relative = row.relative === null || row.relative === undefined
        ? "—" : `${row.relative > 0 ? "+" : ""}${(row.relative * 100).toFixed(1)}%`;
      const delta = row.delta === null || row.delta === undefined
        ? "—" : (row.delta > 0 ? "+" : "") + Number(row.delta).toPrecision(3);
      tr.innerHTML =
        `<td>${esc(row.label)}${row.procedure ? ` — <code>${esc(row.procedure)}</code>` : ""}`
        + `<br><small>${esc(row.key)}${row.reason ? " — " + esc(row.reason) : ""}</small></td>`
        + `<td class="num">${esc(number(row.baseline, row.unit))}</td>`
        + `<td class="num">${esc(number(row.current, row.unit))}</td>`
        + `<td class="num">${esc(delta)}</td>`
        + `<td class="num">${esc(relative)}</td>`
        + `<td class="v-${esc(row.verdict)}">${esc(t(CMP_VERDICT[row.verdict] || row.verdict))}</td>`;
      body.append(tr);
    }
    table.append(body);
    box.append(table);

    const note = document.createElement("p");
    note.className = "cmp-note";
    note.textContent = t("cmp_note");
    box.append(note);
  }

  $("btn-run-compare").onclick = async () => {
    if (!openRun) return;
    $("run-action-hint").textContent = t("runs_comparing");
    try {
      const body = await getJSON(
        `/api/runs/${encodeURIComponent(openRun.run_id)}/compare`);
      if (!body.ok) {
        // A run with nothing earlier to compare against is an ordinary answer,
        // not a failure. Say it where the other button hints appear.
        $("run-compare").hidden = true;
        $("run-action-hint").textContent = body.text;
        return;
      }
      renderComparison(body.comparison);
      $("run-action-hint").textContent = "";
    } catch (e) {
      $("run-compare").hidden = true;
      $("run-action-hint").textContent = t("runs_compare_failed", { error: e.message });
    }
  };

  // ------------------------------------------------------------------ start
  // WHY THE ORDER IS WHAT IT IS
  // The terminals and the status bar are the parts a user cannot work without,
  // so the WebSocket opens FIRST and depends on nothing. Every panel then
  // loads independently: a panel that throws paints its own banner and the
  // rest of the page carries on. The previous version awaited the panels in
  // one chain with `connect()` at the end, so a single failing fetch silently
  // took out both terminals, the whole status bar and every button.
  (async () => {
    switchTab("sim");
    connect();
    renderLinkChip();
    // Before anything else is interpreted: is the page even talking to the
    // server it came from?
    try {
      await checkBuild();
    } catch (e) {
      console.error("ArgazUI: the build identity check failed", e);
    }

    const panels = await Promise.all([
      initPanel("err-buttons", t("panel_commands"), loadButtons),
      initPanel("err-models", t("panel_models"), loadModels),
      initPanel("err-scripts", t("panel_scripts"), loadScripts),
      initPanel("err-runs", t("panel_runs"), loadRuns),
      initPanel("err-camp", t("camp_title"), loadCampaigns),
      initPanel("err-exp", t("exp_title"), loadExperiments),
      initPanel("err-cov", t("cov_title"), loadCoverage),
    ]);
    if (!panels.every(Boolean)) {
      console.warn("ArgazUI: some panels failed to load; the rest of the page is live");
    }

    // Language application touches every panel, so it runs after them and is
    // itself isolated — a rendering bug in one panel must not blank the page.
    try {
      await applyLang(LANG);
    } catch (e) {
      console.error("ArgazUI: applying the language failed", e);
    }
    try {
      openRunFromHash();
    } catch (e) {
      console.error("ArgazUI: could not open the run named in the URL", e);
    }
    // The documentation index is fetched only when the portal is actually
    // wanted — either by a deep link now, or by the DOCS button later. It is
    // twenty-odd file reads on the server and nothing on this page needs it.
    try {
      if (/^#docs=/.test(location.hash || "")) {
        await loadDocs();
        openDocsFromHash();
      }
    } catch (e) {
      console.error("ArgazUI: could not open the documentation page named in the URL", e);
    }
    setTimeout(() => { TABS[activeTab].fit.fit(); sendResize(activeTab); }, 200);
  })();
})();
