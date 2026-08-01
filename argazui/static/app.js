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
      nav_help: "HOW TO USE", nav_about: "CONTACT",
      nav_help_title: "How to Use", nav_about_title: "Contact & Project",
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
      hint_pick: "Pick a model. The buttons change with the vehicle class " +
                 "(Copter/Plane/VTOL).",
      hint_buttons: "Buttons are sent over MAVLink (port 14550). Results appear in " +
                    "the terminal. Edit config/buttons.json to add your own.",
      hint_scripts: "Scripts must connect to the MAVLink output on port {script} " +
                    "(the interface uses {ui}, so they do not clash).",
      no_scripts: "— scripts/ folder is empty —",
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
      proc_alternatives: "alternatives:",
      proc_source: "from",
      confirm_proc: "This runs the procedure below. Each step is verified "
        + "against the vehicle's actual state, not just the ACK.",
      proc_no_match: "no procedure fits this vehicle",
      hint_sim: "Gazebo / SITL / MAVProxy run here. For models launched with " +
                "sim_vehicle.py you can type MAVProxy commands directly.",
      hint_shell: "Plain bash shell — mission scripts run here, and you can type " +
                  "any command.",
    },
    tr: {
      tagline: "ArduPilot SITL + Gazebo kontrol paneli",
      nav_help: "NASIL KULLANILIR", nav_about: "İLETİŞİM",
      nav_help_title: "Nasıl Kullanılır", nav_about_title: "İletişim & Proje",
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
      hint_pick: "Bir model seç. Butonlar aracın sınıfına (Copter/Plane/VTOL) göre " +
                 "değişir.",
      hint_buttons: "Butonlar MAVLink üzerinden gönderilir (port 14550). Sonuçlar " +
                    "terminalde görünür. config/buttons.json ile yeni buton ekleyebilirsin.",
      hint_scripts: "Scriptler {script} portundaki MAVLink çıkışına bağlanmalı " +
                    "(arayüz {ui} portunu kullanıyor, çakışmasın).",
      no_scripts: "— scripts/ klasörü boş —",
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
      proc_alternatives: "alternatifler:",
      proc_source: "kaynak",
      confirm_proc: "Aşağıdaki prosedür çalıştırılacak. Her adım sadece ACK'e "
        + "değil, aracın gerçek durumuna karşı doğrulanır.",
      proc_no_match: "bu araca uyan prosedür yok",
      hint_sim: "Gazebo / SITL / MAVProxy burada çalışır. sim_vehicle.py ile açılan " +
                "modellerde MAVProxy komutlarını buraya yazabilirsin.",
      hint_shell: "Boş bash kabuğu — görev scriptleri burada çalışır, elle komut da " +
                  "yazabilirsin.",
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
    if (lastStatus) { $("buttons").dataset.key = ""; applyStatus(lastStatus); }

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

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      for (const n of Object.keys(TABS)) sendResize(n);
      TABS.sim.term.write(`\r\n\x1b[36m[ArgazUI]\x1b[0m ${t("ui_connected")}\r\n`);
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "out") {
        const cfg = TABS[msg.stream || "sim"];
        if (!cfg) return;
        const bin = atob(msg.data);
        const buf = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
        cfg.term.write(buf);
      } else if (msg.type === "status") {
        applyStatus(msg.status);
      } else if (msg.type === "procedure") {
        applyProcedureEvent(msg);
      }
    };
    ws.onclose = () => {
      TABS[activeTab].term.write(`\r\n\x1b[31m[ArgazUI]\x1b[0m ${t("ui_lost")}\r\n`);
      setTimeout(connect, 2000);
    };
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

    const model = $("pill-model");
    model.textContent = `${t("vehicle")}: ` + (s.active_model_name || "—");
    model.className = "pill wide " + (active ? "on" : "off");

    const link = $("pill-link");
    link.textContent = linked ? t("link_connected", { sysid: v.sysid }) : t("link_none");
    link.className = "pill " + (linked ? "on" : "off");

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
    renderButtons(cls, !!active);
    $("script-hint").textContent =
      t("hint_scripts", { script: s.script_port, ui: s.ui_port });
  }

  // ----------------------------------------------------------------- models
  async function loadModels() {
    const reg = await (await fetch("/api/models")).json();
    MODELS = reg.models || [];
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
    BUTTONS = await (await fetch("/api/buttons")).json();
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
    $("cmd-hint").textContent = t("hint_buttons");

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
        btn.title = t("proc_no_match");
      } else if (isProc) {
        btn.title = [desc, `${t("proc_source")}: ${proc.id}.yaml`, proc.description]
          .filter(Boolean).join("\n\n");
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
  let PROCS = { capabilities: null, roles: {} };

  async function loadProcedures() {
    try {
      PROCS = await (await fetch("/api/procedures")).json();
    } catch (e) {
      PROCS = { capabilities: null, roles: {} };
    }
    $("buttons").dataset.key = "";     // force a re-render with the new inputs
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
    $("proc-expect").innerHTML = "";
    $("proc-hint").textContent = "";
    $("proc-panel").hidden = false;
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
      const row = document.createElement("div");
      row.className = "expect " + (e.passed ? "passed" : "failed");
      row.innerHTML = `<span class="mark">${e.passed ? "✓" : "✕"}</span>`
        + `<span class="what">${esc(e.label)}</span>`
        + `<span class="detail">${esc(e.text || "")}</span>`;
      if (!$("proc-expect").childElementCount) {
        const h = document.createElement("div");
        h.className = "expect-head";
        h.textContent = t("proc_accept");
        $("proc-expect").append(h);
      }
      $("proc-expect").append(row);
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

  // ---------------------------------------------------------------- scripts
  let SCRIPTS = { scripts: [], dir: "" };

  async function loadScripts() {
    SCRIPTS = await (await fetch("/api/scripts")).json();
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

  // ------------------------------------------------------------------ start
  (async () => {
    await loadButtons();
    await loadModels();
    await loadScripts();
    await applyLang(LANG);
    switchTab("sim");
    connect();
    setTimeout(() => { TABS[activeTab].fit.fit(); sendResize(activeTab); }, 200);
  })();
})();
