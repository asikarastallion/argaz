/* ArgazUI — single-page frontend. No build step; plain JS. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ------------------------------------------------------------------- i18n
  // English is the default; the EN/TR switch in the top bar changes both the
  // interface and the backend messages (see POST /api/lang).
  const I18N = window.ARGAZ_I18N;

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
    // The terminals' connection chip writes its own text, so a language switch
    // has to reach it: it has had a Turkish string all along and kept showing
    // the English one until the socket next changed state.
    renderLinkChip();

    selectModel(selected ? selected.id : null);
    renderModelLists();
    renderScripts();
    renderRuns();
    // These write their own text rather than carrying data-i18n, because each
    // says something different depending on what is running. A language
    // switch has to reach them or they keep the previous language's sentence.
    renderScenarios();
    renderCampaigns();
    renderExperiments();
    renderCoverage();
    renderProcedureCatalogue();
    renderFaults();
    if (lastStatus) { $("buttons").dataset.key = ""; applyStatus(lastStatus); }
    else renderVehicleState();

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
      // The fault catalogue is translated on the server from its own language
      // setting, so it can only be re-read after the POST above has landed.
      try {
        await loadFaults();
      } catch (e) {
        console.error("ArgazUI: the fault catalogue could not be reloaded", e);
      }
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

  // One instrument in the top bar: a fixed label, a value that changes, and a
  // state colour on the edge. The label is markup and stays put — a reading
  // that rewrites its own label cannot be found by eye at a glance.
  function readout(id, value, state, title) {
    const box = $(id);
    if (!box) return;
    const slot = box.querySelector(".ro-value");
    if (slot) slot.textContent = value;
    box.className = "readout" + (box.classList.contains("wide") ? " wide" : "")
      + (box.classList.contains("num") ? " num" : "") + (state ? " " + state : "");
    if (title) box.title = title;
  }

  // A table's column headings, replaced in place. Every list in the
  // application carries them, in both languages: an unlabelled column is a
  // column somebody has to guess at.
  function setHead(table, labels) {
    if (!table) return;
    const old = table.querySelector("thead");
    if (old) old.remove();
    const head = ArgazUI.el("thead");
    const row = ArgazUI.el("tr");
    for (const label of labels) row.append(ArgazUI.el("th", { text: label }));
    head.append(row);
    table.insertBefore(head, table.querySelector("tbody"));
  }

  // The one-line answer to "what is this aircraft doing", derived only from
  // fields the status endpoint already sends. Ordered by what would stop an
  // operator first: an injected fault, then armed motors, then readiness.
  function renderVehicleState() {
    const box = $("veh-state");
    if (!box) return;
    const s = lastStatus;
    const v = (s && s.vehicle) || {};
    let state = "none";
    let text = t("vst_none");
    if (s && s.link_fault)               { state = "fault";    text = t("vst_link_fault"); }
    else if (active && linked && v.armed){ state = "armed";    text = t("vst_armed"); }
    else if (active && linked && s && s.procedure_running)
                                         { state = "running";  text = t("vst_procedure"); }
    else if (active && linked && v.prearm_known && v.prearm_ok)
                                         { state = "ready";    text = t("vst_ready"); }
    else if (active && linked && v.prearm_known)
                                         { state = "waiting";  text = t("vst_not_ready"); }
    else if (active && linked)           { state = "running";  text = t("vst_connected"); }
    else if (active)                     { state = "starting"; text = t("vst_starting"); }
    else if (selected)                   { state = "selected"; text = t("vst_selected"); }
    ArgazUI.setState(box, state, text);
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

    readout("pill-model", s.active_model_name || "—", active ? "on" : "off",
            t("t_model"));

    // A bare dash is not acceptable in an industrial panel: whenever the link
    // is not up, the reading states which of the three possible reasons applies.
    if (linked) {
      readout("pill-link", t("link_connected", { sysid: v.sysid }), "on", t("t_link"));
    } else {
      const reason = linkReason(s);
      readout("pill-link", reason.short, reason.cls, reason.detail);
    }

    // Pre-arm state, so you can see in advance why ARM would be rejected.
    if (!linked || !v.prearm_known) {
      readout("pill-ready", t("ready_unknown"), "off", t("ready_t_unknown"));
    } else if (v.prearm_ok) {
      readout("pill-ready", t("ready_ok"), "on", t("ready_t_ok"));
    } else {
      readout("pill-ready", t("ready_no"), "warn", t("ready_t_no"));
    }

    readout("pill-mode", v.mode || "—", v.mode ? "" : "off", t("t_mode"));
    readout("pill-armed", v.armed ? t("armed") : t("disarmed"),
            v.armed ? "armed" : "off", t("t_armed"));
    readout("pill-alt", `${v.alt} m`, "", t("t_alt"));
    readout("pill-spd", `${v.groundspeed} m/s`, "", t("t_spd"));

    $("btn-stop").disabled = !active;
    renderVehicleState();

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
        ul.innerHTML = `<li class="empty">${esc(t("no_models"))}</li>`;
      }
    }
  }

  function selectModel(id) {
    selected = MODELS.find((m) => m.id === id) || null;
    document.querySelectorAll(".reg-list li label").forEach((l) =>
      l.classList.toggle("sel", l.dataset.id === id));
    $("selected-name").textContent = selected ? selected.name : t("none_selected");

    // Label and value, not one run-on line: how a model is launched is four
    // separate facts and an operator reads them one at a time.
    const meta = $("selected-meta");
    meta.innerHTML = "";
    if (selected) {
      const rows = [
        [t("cls"), selected.vehicle_class],
        [t("method"), selected.method],
        [t("env"), selected.env],
        ["ROS2 / RViz", selected.has_ros2 ? t("exp_yes") : t("exp_no")],
      ];
      for (const [key, value] of rows) {
        meta.append(ArgazUI.el("dt", { text: key }),
                    ArgazUI.el("dd", { text: String(value || "—") }));
      }
    }
    $("btn-start").disabled = !selected;
    renderVehicleState();

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
        // Marked, because pressing it runs a declared sequence that is
        // verified step by step — not one MAVLink message.
        g.classList.add("proc");
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
    renderProcedureCatalogue();
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
    // The step-by-step verification renders beside the quick commands and the
    // terminal, because that is where a person watching a flight is. A run
    // started from the Procedures or Scenarios page therefore brings the
    // operator back to the workstation — nothing starts out of sight.
    ArgazNav.show("operations", { anchor: "panel-commands" });
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
    // The commands panel scrolls, and the procedure appears at the bottom of
    // it. Verification that starts below the fold is verification nobody
    // watches, so it is brought into view when it starts.
    $("proc-panel").scrollIntoView({ block: "nearest" });
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

  // -------------------------------------------------- the procedure catalogue
  // The Procedures page answers two different questions with one table, and
  // keeps them apart:
  //
  //   what this project DECLARES   — every file in argazui/procedures/, which
  //                                  the coverage document already enumerates
  //                                  and which is knowable with nothing running
  //   what THIS vehicle can run    — only knowable once an aircraft is talking,
  //                                  because it comes from probed capabilities
  //
  // A page that showed only the second would be empty before START and would
  // hide the procedures nobody has ever exercised; a page that showed only the
  // first could not say which of them applies to what is in the air.
  let procSelected = null;

  /** Every applicable procedure the server offered, scenarios included. */
  function applicableProcedures() {
    const out = new Map();
    for (const role of Object.keys((PROCS && PROCS.roles) || {})) {
      const entry = PROCS.roles[role] || {};
      for (const option of entry.options || []) {
        out.set(option.id, { proc: option, role,
                             selected: entry.selected === option.id });
      }
    }
    for (const scen of (PROCS && PROCS.scenarios) || []) {
      if (!out.has(scen.id)) out.set(scen.id, { proc: scen, role: "scenario" });
    }
    return out;
  }

  /** The declared set, from the coverage document. `[]` if it never loaded. */
  function declaredProcedures() {
    const doc = COVERAGE && COVERAGE.coverage;
    const dimension = ((doc && doc.dimensions) || [])
      .find((d) => d.dimension === "procedures");
    return (dimension && dimension.items) || [];
  }

  function renderProcedureCatalogue() {
    const table = $("proc-table");
    if (!table) return;
    const body = table.querySelector("tbody");
    body.innerHTML = "";

    const available = applicableProcedures();
    const declared = declaredProcedures();
    const rows = declared.length
      ? declared.map((item) => ({ id: item.id, what: item.what || "",
                                  covered: !!item.covered }))
      : Array.from(available.keys()).map((id) => ({ id, what: "", covered: false }));

    $("proc-list-hint").textContent = linked ? "" : t("proc_needs_vehicle");
    setHead(table, [t("proc_col_id"), t("proc_col_role"),
                    t("proc_col_available"), t("proc_col_covered")]);

    if (!rows.length) {
      body.append(ArgazUI.emptyRow(4, t("proc_empty")));
      renderProcedureDetail();
      return;
    }

    rows.sort((a, b) => a.id.localeCompare(b.id));
    for (const row of rows) {
      const hit = available.get(row.id);
      // The coverage document spells a procedure as "Label [role]"; the role
      // is read back out of it so the column is filled even with no vehicle.
      const bracket = /\[([^\]]+)\]\s*$/.exec(row.what);
      const role = (hit && hit.role) || (bracket && bracket[1]) || "—";
      const label = row.what.replace(/\s*\[[^\]]+\]\s*$/, "")
        || (hit && hit.proc.name) || row.id;

      const tr = ArgazUI.el("tr", { class: "rowlink" });
      if (procSelected === row.id) tr.classList.add("selected");
      tr.onclick = () => { procSelected = row.id; renderProcedureCatalogue(); };

      tr.append(ArgazUI.el("td", { html:
        `<b>${esc(label)}</b><small>${esc(row.id)}</small>` }));
      tr.append(ArgazUI.el("td", { class: "mono", text: role }));

      const state = ArgazUI.el("td");
      if (hit && hit.selected) state.append(ArgazUI.badge(t("proc_selected"), "info"));
      else if (hit) state.append(ArgazUI.badge(t("proc_applies"), "ok"));
      else state.append(ArgazUI.badge(linked ? t("proc_not_offered") : t("proc_unknown"), ""));
      tr.append(state);

      tr.append(ArgazUI.el("td", { html: row.covered
        ? `<span class="badge ok">${esc(t("proc_run_before"))}</span>`
        : `<span class="badge">${esc(t("proc_never_run"))}</span>` }));
      body.append(tr);
    }
    renderProcedureDetail();
  }

  // The contract, read from the same YAML the regression suite executes:
  // inputs, ordered steps, acceptance criteria and declared faults. Nothing
  // is restated here — a procedure with no detail says why it has none.
  function renderProcedureDetail() {
    const box = $("proc-detail");
    if (!box) return;
    box.innerHTML = "";
    if (!procSelected) {
      box.append(ArgazUI.el("p", { class: "proc-detail-empty", text: t("proc_pick") }));
      return;
    }
    const hit = applicableProcedures().get(procSelected);
    if (!hit) {
      box.append(ArgazUI.el("p", { class: "proc-id", text: procSelected }));
      box.append(ArgazUI.el("p", { class: "proc-detail-empty",
                                   text: t("proc_detail_needs_vehicle") }));
      return;
    }
    const proc = hit.proc;
    const doc = ArgazUI.el("div", { class: "proc-doc" });
    doc.append(ArgazUI.el("div", { class: "proc-name", text: proc.name }));
    doc.append(ArgazUI.el("div", { class: "proc-id",
      text: `${proc.id}.yaml · ${t("proc_col_role")}: ${hit.role}` }));
    if (proc.description) {
      doc.append(ArgazUI.el("p", { class: "proc-desc", text: proc.description }));
    }

    const section = (title, node) => {
      doc.append(ArgazUI.el("div", { class: "sec-head", text: title }), node);
    };

    if ((proc.inputs || []).length) {
      const list = ArgazUI.el("dl", { class: "kv" });
      for (const input of proc.inputs) {
        list.append(ArgazUI.el("dt", { text: (LANG === "tr" && input.label_tr) || input.label }),
                    ArgazUI.el("dd", { text: String(input.default) }));
      }
      section(t("proc_inputs"), list);
    }

    const steps = ArgazUI.el("ol");
    for (const step of proc.steps || []) {
      steps.append(ArgazUI.el("li", { html:
        `${esc(step.name)} <code>${esc(step.kind || "")}</code>` }));
    }
    section(t("proc_detail_steps"), steps);

    const criteria = ArgazUI.el("ul");
    for (const item of proc.expect || []) {
      criteria.append(ArgazUI.el("li", { class: "crit", text: item }));
    }
    if (!(proc.expect || []).length) {
      criteria.append(ArgazUI.el("li", { text: t("proc_no_criteria") }));
    }
    section(t("proc_accept"), criteria);

    if ((proc.failures || []).length) {
      const faults = ArgazUI.el("ul");
      for (const fault of proc.failures) {
        faults.append(ArgazUI.el("li", { text: t("scen_fault_line", {
          fault: fault.fault, target: fault.target,
          duration: fault.duration_text, step: fault.inject_after_step }) }));
      }
      section(t("proc_faults"), faults);
    }

    if ((proc.overrides || []).length) {
      const overrides = ArgazUI.el("ul");
      for (const item of proc.overrides) {
        overrides.append(ArgazUI.el("li", { html:
          `<code>${esc(item.param)} = ${esc(item.value)}</code> — ${esc(item.reason)}` }));
      }
      section(t("proc_overrides"), overrides);
    }

    // Runnable only when there is an aircraft to run it on. The button is
    // disabled rather than hidden, and says which precondition is missing.
    const run = ArgazUI.el("button", { class: "btn primary", text: t("proc_run") });
    run.disabled = !linked;
    if (!linked) run.title = t("why_disabled_no_link");
    run.onclick = () => runProcedure(proc.id, null, defaultsOf(proc));
    doc.append(ArgazUI.el("div", { class: "ctlrow" }, run));
    box.append(doc);
  }

  $("btn-proc-refresh").onclick = () => {
    loadProcedures();
    loadCoverage().catch((e) => console.error("ArgazUI: coverage refresh failed", e));
  };

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

  // The fault catalogue: every mechanism this build can inject, what it does
  // to the simulated aircraft and what is supposed to be observed as a result.
  // Read from /api/faults, which serves faults.py — the module that performs
  // the injection — so the page cannot name a fault the code does not have.
  let FAULTS = { faults: [] };

  async function loadFaults() {
    FAULTS = await getJSON("/api/faults", (b) => Array.isArray(b && b.faults));
    renderFaults();
  }

  function renderFaults() {
    const table = $("fault-table");
    if (!table) return;
    const body = table.querySelector("tbody");
    body.innerHTML = "";
    setHead(table, [t("fault_col_kind"), t("fault_col_observe"),
                    t("fault_col_mechanism"), t("fault_col_source")]);
    if (!(FAULTS.faults || []).length) {
      body.append(ArgazUI.emptyRow(4, t("fault_none")));
      return;
    }
    for (const entry of FAULTS.faults) {
      const tr = document.createElement("tr");
      // A source that is a URL is followed rather than read out; one that is a
      // file reference is shown as the path it is.
      const source = String(entry.source || "");
      const cited = /^https?:\/\//.test(source)
        ? `<a href="${esc(source)}" target="_blank" rel="noopener noreferrer">${esc(source)}</a>`
        : esc(source);
      tr.innerHTML = `<td><b>${esc(entry.label)}</b>`
        + `<small>${esc(entry.kind)}</small>`
        + `<small class="prose">${esc(entry.what || "")}</small></td>`
        + `<td>${esc(entry.observe || "")}</td>`
        + `<td class="mono">${esc(entry.mechanism || "")}`
        + `<small>${esc((entry.targets || []).join(", "))}</small></td>`
        + `<td class="mono">${cited}</td>`;
      body.append(tr);
    }
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
    const options = campaignProcedureOptions();
    select.innerHTML = "";
    for (const proc of options) {
      const option = document.createElement("option");
      option.value = proc.id;
      option.textContent = `${proc.name} (${proc.id})`;
      select.append(option);
    }
    // An empty dropdown is not a state anybody can read. Which procedures can
    // be flown is a property of the connected vehicle, so say that.
    if (!options.length) {
      select.append(ArgazUI.el("option", { value: "", text: t("camp_no_procedure") }));
    }
    if (chosen) select.value = chosen;

    const running = CAMPAIGNS.active && CAMPAIGNS.active.running;
    $("btn-camp-start").disabled = !!running || !active || !options.length;
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
    setHead($("camp-table"), [t("camp_col_id"), t("camp_col_model"),
                              t("camp_col_procedure"), t("camp_col_runs"), ""]);
    if (!(CAMPAIGNS.campaigns || []).length) {
      body.append(ArgazUI.emptyRow(5, t("camp_none")));
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
    box.innerHTML = "";
    box.append(ArgazUI.el("p", { class: "loading", text: t("runs_comparing") }));
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
    setHead($("exp-table"), [t("exp_col_id"), t("exp_col_model"),
                             t("exp_col_policy"), t("exp_col_arms"), ""]);
    if (!(EXPERIMENTS.experiments || []).length) {
      body.append(ArgazUI.emptyRow(5, t("exp_none")));
      return;
    }
    for (const item of EXPERIMENTS.experiments) {
      const flown = experimentRunsOf(item.id);
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="runs-when"><b>${esc(item.id)}</b>`
        + `<small class="prose">${esc(item.question || "")}</small></td>`
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
    box.innerHTML = "";
    box.append(ArgazUI.el("p", { class: "loading", text: t("runs_comparing") }));
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
    // The Procedures page reads the declared set out of this document, so it
    // is the one other place a coverage load has to reach.
    renderProcedureCatalogue();
  }

  function renderCoverage() {
    const body = $("cov-table").querySelector("tbody");
    body.innerHTML = "";
    $("cov-detail").hidden = true;
    setHead($("cov-table"), [t("cov_dimension"), t("cov_covered"),
                              t("cov_fraction"), ""]);
    if (!COVERAGE) {
      body.append(ArgazUI.emptyRow(4, t("cov_none")));
      return;
    }
    const doc = COVERAGE.coverage;
    for (const dimension of doc.dimensions) {
      const tr = document.createElement("tr");
      const fraction = dimension.fraction === null ? "—"
        : `${Math.round(dimension.fraction * 100)}%`;
      // The bar is a proportion of a declared set, not a score, and the two
      // absolute numbers stay beside it for exactly that reason.
      const filled = dimension.fraction === null ? 0
        : Math.round(dimension.fraction * 100);
      tr.innerHTML = `<td class="runs-when"><b>${esc(dimension.label)}</b></td>`
        + `<td class="num">${dimension.covered} / ${dimension.declared}</td>`
        + `<td class="num">${esc(fraction)}`
        + `<span class="covbar${filled === 100 ? " full" : filled ? "" : " none"}">`
        + `<i style="width:${filled}%"></i></span></td>`;
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

    setHead($("runs-table"), [t("runs_col_when"), t("camp_col_model"),
                              t("camp_col_procedure"), t("runs_col_verdict"), ""]);

    const all = RUNS.runs || [];
    const more = $("btn-runs-more");
    if (!all.length) {
      const tr = document.createElement("tr");
      // `runs-empty` is how the panel's own tests tell "no runs" apart from a
      // run row; it stays on this element.
      tr.innerHTML = `<td colspan="5" class="empty runs-empty">${esc(t("runs_none"))}</td>`;
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
    // The sheet is a record out of the run browser, so the browser is what it
    // opens over: a deep link that left the operations screen underneath would
    // put a report on top of a running aircraft.
    ArgazNav.show("runs", { hash: false });
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
    ArgazNav.show("operations", { anchor: "panel-vehicles" });
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
    // …and the COMMAND tab is on the operations screen, so that is where the
    // operator is taken. A script running on a page nobody is looking at is
    // how output gets missed.
    ArgazNav.show("operations", { anchor: "panel-terminal" });
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
    // The portal is a module of the application, not an overlay on top of it:
    // reading a document and operating an aircraft are different activities,
    // and the shell says which one you are in.
    ArgazNav.show("docs", { hash: false });
    docsPage = pageId;
    // A deep link can arrive before anything has fetched the tree.
    if (!DOCS) {
      try { await loadDocs(); } catch (e) {
        console.error("ArgazUI: the documentation index could not be loaded", e);
      }
    }
    renderDocsTree();
    $("docs-content").innerHTML = `<p class="loading">${esc(t("docs_loading"))}</p>`;
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
        ArgazNav.show("docs", { hash: false });
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
    // The shell first: which module is on screen decides nothing about the
    // data, but every render below writes into one of them.
    ArgazNav.init({
      onChange: (view) => {
        // A terminal cannot measure itself while its section is hidden, so it
        // is refitted the moment the operations screen is shown again.
        if (view !== "operations") return;
        setTimeout(() => {
          TABS[activeTab].fit.fit();
          sendResize(activeTab);
        }, 0);
      },
    });

    switchTab("sim");
    connect();
    renderLinkChip();
    renderVehicleState();
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
      initPanel("err-faults", t("fault_catalogue"), loadFaults),
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
