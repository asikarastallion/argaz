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
        } else if (msg.type === "fleet") {
          // The Fleet page's state. Defined later in this file, so the guard
          // is needed for the moment before it is installed.
          if (window.__applyFleet) window.__applyFleet(msg.fleet);
        } else if (msg.type === "procedure") {
          applyProcedureEvent(msg);
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
    // `mode_settled` is computed on the VEHICLE's clock, per docs/thresholds.md.
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
  let PROCS = { capabilities: null, roles: {} };
  let procsError = "";

  async function loadProcedures() {
    // Called on every link/model change, so a transient failure degrades the
    // buttons to "no procedure matches" rather than breaking the page.
    try {
      PROCS = await getJSON("/api/procedures", (b) => b && typeof b.roles === "object");
      procsError = "";
    } catch (e) {
      console.error("ArgazUI: /api/procedures failed", e);
      PROCS = { capabilities: null, roles: {} };
      procsError = String(e.message || e);
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
  window.addEventListener("hashchange", openRunFromHash);

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
    setTimeout(() => { TABS[activeTab].fit.fit(); sendResize(activeTab); }, 200);
  })();
})();

/* ==========================================================================
   FLEET PAGE  (v1.3)

   THREE DISPLAY RULES, EACH OF WHICH IS A CORRECTNESS REQUIREMENT
   ---------------------------------------------------------------
   1. REVERTED is visually distinct from ACCEPTED. It is the outcome the whole
      project exists to surface — the autopilot said yes and the vehicle did
      not stay — and rendering it as a green tick would put back exactly the
      untruth v1.1 removed.
   2. A not-measured criterion never renders as a pass. Blank, zero and a grey
      dash that reads as "fine" are the same failure. The panel says what was
      not measured and why, in the words the report uses.
   3. The target of a command is never ambiguous. The button says how many
      vehicles it will reach BEFORE it is pressed.

   The single-vehicle page above is untouched.
   ========================================================================== */
(function () {
  const $ = (id) => document.getElementById(id);
  let fleetState = null;
  let selected = new Set();
  let targetMode = "all";

  /* ------------------------------------------------------------ page tabs */
  document.querySelectorAll(".pagetab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pagetab").forEach((b) =>
        b.classList.toggle("active", b === btn));
      const want = btn.dataset.page;
      $("page-single").hidden = want !== "single";
      $("page-fleet").hidden = want !== "fleet";
    });
  });

  /* -------------------------------------------------------- fleet picker */
  async function loadFleets() {
    let data;
    try {
      data = await (await fetch("/api/fleets")).json();
    } catch (e) {
      $("err-fleet").hidden = false;
      $("err-fleet").textContent = "could not list fleets: " + e;
      return;
    }
    $("fleet-dir").textContent = data.directory || "";
    const sel = $("fleet-select");
    sel.innerHTML = "";
    (data.fleets || []).forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.name;
      opt.textContent = f.name + (f.ok ? "" : "  — invalid");
      opt.dataset.ok = f.ok ? "1" : "0";
      sel.appendChild(opt);
    });
    sel._fleets = data.fleets || [];
    renderBadge();
  }

  function currentFleet() {
    const sel = $("fleet-select");
    return (sel._fleets || []).find((f) => f.name === sel.value) || null;
  }

  /* A fleet that does not validate says WHY, and cannot be started. */
  function renderBadge() {
    const f = currentFleet();
    const box = $("fleet-badge");
    box.innerHTML = "";
    if (!f) { $("btn-fleet-start").disabled = true; return; }

    const badge = document.createElement("span");
    badge.className = "badge " + (f.ok ? "ok" : "bad");
    badge.id = "fleet-validation";
    badge.textContent = f.ok ? "VALID" : "INVALID";
    box.appendChild(badge);

    const meta = document.createElement("span");
    meta.className = "badge-meta";
    meta.textContent = `${f.vehicles} vehicles · ${f.gazebo ? "Gazebo" : "SITL only"}`;
    box.appendChild(meta);

    (f.errors || []).forEach((e) => {
      const p = document.createElement("p");
      p.className = "badge-reason error";
      p.textContent = e;
      box.appendChild(p);
    });
    (f.warnings || []).forEach((w) => {
      const p = document.createElement("p");
      p.className = "badge-reason warn";
      p.textContent = w;
      box.appendChild(p);
    });
    $("btn-fleet-start").disabled = !f.ok;
  }

  $("fleet-select").addEventListener("change", renderBadge);
  $("btn-fleet-refresh").addEventListener("click", loadFleets);

  $("btn-fleet-start").addEventListener("click", async () => {
    const f = currentFleet();
    if (!f) return;
    $("btn-fleet-start").disabled = true;
    await fetch("/api/fleet/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: f.name }),
    });
  });

  $("btn-fleet-stop").addEventListener("click", async () => {
    await fetch("/api/fleet/stop", { method: "POST" });
  });

  /* ------------------------------------------------------- target bar (3) */
  document.querySelectorAll(".tgt").forEach((btn) => {
    btn.addEventListener("click", () => {
      targetMode = btn.dataset.target;
      document.querySelectorAll(".tgt").forEach((b) =>
        b.classList.toggle("active", b === btn));
      renderTarget();
    });
  });

  function targetIds() {
    if (!fleetState || !fleetState.vehicles.length) return [];
    if (targetMode === "all") return fleetState.vehicles.map((v) => v.id);
    return fleetState.vehicles.map((v) => v.id).filter((id) => selected.has(id));
  }

  /* RULE 3: the count is on the buttons themselves, before they are pressed. */
  function renderTarget() {
    const ids = targetIds();
    const total = fleetState ? fleetState.vehicles.length : 0;
    const label = !fleetState || !total
      ? "no fleet"
      : (ids.length === 0
          ? `0 of ${total} vehicles — nothing will be commanded`
          : `${ids.length} of ${total} vehicles: ${ids.join(", ")}`);
    $("target-count").textContent = label;
    $("target-count").dataset.count = String(ids.length);

    document.querySelectorAll(".fleetcmd").forEach((btn) => {
      const base = btn.dataset.cmd;
      btn.textContent = ids.length ? `${base} → ${ids.length}` : `${base} → none`;
      btn.disabled = !fleetState || !fleetState.running || ids.length === 0;
      btn.title = ids.length ? `will command: ${ids.join(", ")}`
                             : "no vehicles targeted";
    });
  }

  document.querySelectorAll(".fleetcmd").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ids = targetIds();
      if (!ids.length) return;
      $("fleet-cmd-hint").textContent =
        `sending ${btn.dataset.cmd} to ${ids.length}: ${ids.join(", ")}…`;
      const res = await (await fetch("/api/fleet/command", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: btn.dataset.cmd, target: ids,
          policy: $("fleet-policy").value || null,
        }),
      })).json();
      if (!res.ok) $("fleet-cmd-hint").textContent = res.text || "command failed";
      else renderAck(res.result);
    });
  });

  /* -------------------------------------------------------- vehicle grid */
  function renderGrid() {
    const grid = $("fleet-grid");
    if (!fleetState || !fleetState.vehicles.length) {
      grid.innerHTML = "";
      $("fleet-grid-hint").hidden = false;
      $("fleet-grid-hint").textContent = fleetState && fleetState.starting
        ? "fleet starting…" : (fleetState && fleetState.error
          ? "fleet failed to start: " + fleetState.error : "No fleet running.");
      return;
    }
    $("fleet-grid-hint").hidden = true;
    grid.innerHTML = "";
    fleetState.vehicles.forEach((v) => {
      const card = document.createElement("div");
      card.className = "vcard" + (v.link_stale ? " stale" : "");
      card.dataset.vehicle = v.id;

      const head = document.createElement("div");
      head.className = "vcard-head";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.className = "vsel";
      box.dataset.vehicle = v.id;
      box.checked = selected.has(v.id);
      box.addEventListener("change", () => {
        if (box.checked) selected.add(v.id); else selected.delete(v.id);
        renderTarget();
      });
      head.appendChild(box);
      const title = document.createElement("b");
      title.textContent = `${v.id}  ·  sysid ${v.sysid}`;
      head.appendChild(title);
      card.appendChild(head);

      const rows = [
        ["model", v.model],
        ["mode", v.mode || "—"],
        ["armed", v.armed ? "ARMED" : "disarmed"],
        ["alt", v.alt === null || v.alt === undefined ? "—" : v.alt.toFixed(1) + " m"],
        ["pre-arm", !v.prearm_known ? "unknown" : (v.prearm_ok ? "ready" : "not ready")],
        ["link", v.heartbeat_age === null || v.heartbeat_age === undefined
          ? "no heartbeat yet" : v.heartbeat_age.toFixed(1) + " s ago"],
      ];
      rows.forEach(([k, val]) => {
        const line = document.createElement("div");
        line.className = "vrow";
        line.innerHTML = `<span>${k}</span><b class="v-${k.replace(/[^a-z]/g, "")}">${val}</b>`;
        card.appendChild(line);
      });

      const attach = document.createElement("button");
      attach.className = "btn link vattach";
      attach.textContent = fleetState.console_vehicle === v.id
        ? "detach console" : "attach console";
      attach.addEventListener("click", async () => {
        await fetch("/api/fleet/attach", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            vehicle: fleetState.console_vehicle === v.id ? "" : v.id }),
        });
      });
      card.appendChild(attach);
      grid.appendChild(card);
    });
  }

  /* ------------------------------------------------- ACK matrix — RULE 1 */
  const OUTCOME_CLASS = {
    ACCEPTED: "ok",
    REVERTED: "reverted",   // distinct from ok AND from bad, deliberately
    DENIED: "bad",
    TIMEOUT: "warn",
    NO_LINK: "warn",
  };

  function renderAck(result) {
    const box = $("ack-matrix");
    box.innerHTML = "";
    if (!result) {
      box.innerHTML = '<p class="hint">No group command sent yet.</p>';
      $("ack-title").textContent = "";
      return;
    }
    $("ack-title").textContent =
      `${result.command} · ${result.policy} · ${result.verdict}`;

    const verdict = document.createElement("div");
    verdict.id = "ack-verdict";
    verdict.className = "verdict " + (result.verdict === "PASSED" ? "ok"
      : result.verdict === "PARTIAL" ? "warn" : "bad");
    verdict.textContent = result.verdict;
    box.appendChild(verdict);

    const table = document.createElement("table");
    table.className = "tbl ack";
    table.innerHTML =
      "<tr><th>vehicle</th><th>outcome</th><th>ack</th><th>t</th><th>detail</th></tr>";
    (result.results || []).forEach((r) => {
      const tr = document.createElement("tr");
      tr.dataset.vehicle = r.vehicle;
      tr.dataset.outcome = r.outcome;
      const cls = OUTCOME_CLASS[r.outcome] || "warn";
      // RULE 1: the outcome cell carries its own class AND its own words. A
      // REVERTED row is never green and never says only "ACCEPTED".
      tr.innerHTML =
        `<td>${r.vehicle}</td>` +
        `<td class="outcome ${cls}"><span class="dot"></span>${r.outcome}</td>` +
        `<td>${r.ack || "—"}</td>` +
        `<td>${r.t_ms} ms</td>` +
        `<td>${(r.reason || r.observed || "—").slice(0, 160)}</td>`;
      table.appendChild(tr);
    });
    box.appendChild(table);
  }

  /* --------------------------------- measured-or-absent panels — RULE 2 */
  function renderMeasure(el, title, body) {
    el.innerHTML = "";
    el.appendChild(body);
  }

  /* A panel that was not measured says so in words. It never shows a number,
     a zero, or a dash that could be read as "fine". */
  function notMeasured(reason) {
    const wrap = document.createElement("div");
    wrap.className = "not-measured";
    const tag = document.createElement("span");
    tag.className = "badge notmeasured";
    tag.textContent = "NOT MEASURED";
    wrap.appendChild(tag);
    const why = document.createElement("p");
    why.className = "not-measured-reason";
    why.textContent = reason || "no reason was given, which is itself a defect";
    wrap.appendChild(why);
    return wrap;
  }

  function renderSeparation() {
    const el = $("sep-panel");
    const s = fleetState && fleetState.separation;
    if (!s || !s.measured) {
      el.dataset.measured = "false";
      renderMeasure(el, "separation", notMeasured(s ? s.reason : "no fleet is running"));
      return;
    }
    el.dataset.measured = "true";
    const wrap = document.createElement("div");
    const min = s.minimum_m === null ? "—" : s.minimum_m.toFixed(2);
    const cur = s.current_m === null ? "—" : s.current_m.toFixed(2);
    const bad = s.violations > 0;
    wrap.innerHTML =
      `<div class="gauge ${bad ? "bad" : "ok"}" id="sep-current">${cur} m</div>` +
      `<p class="hint">minimum this run <b id="sep-min">${min} m</b> against a ` +
      `limit of ${s.limit_m} m — ${s.violations} violation(s)</p>`;
    const spark = document.createElement("div");
    spark.className = "spark";
    spark.id = "sep-spark";
    (s.series || []).forEach(([, d]) => {
      const bar = document.createElement("i");
      const h = Math.max(2, Math.min(40, (d / (s.limit_m * 3)) * 40));
      bar.style.height = h + "px";
      if (d < s.limit_m) bar.className = "bad";
      spark.appendChild(bar);
    });
    wrap.appendChild(spark);
    renderMeasure(el, "separation", wrap);
  }

  function renderRtf() {
    const el = $("rtf-panel");
    const r = fleetState && fleetState.rtf;
    if (!r || !r.measured) {
      el.dataset.measured = "false";
      renderMeasure(el, "rtf", notMeasured(r ? r.reason : "no fleet is running"));
      return;
    }
    el.dataset.measured = "true";
    const wrap = document.createElement("div");
    const below = r.rtf !== null && r.floor !== undefined && r.rtf < r.floor;
    wrap.innerHTML =
      `<div class="gauge ${below ? "bad" : "ok"}" id="rtf-current">` +
      `${r.rtf === null ? "—" : r.rtf.toFixed(2)}x</div>` +
      `<p class="hint">floor ${r.floor} — judged over seconds spent below it, ` +
      `not on the worst single sample</p>`;
    renderMeasure(el, "rtf", wrap);
  }

  /* ------------------------------------------------------------- transcript */
  function renderTranscript() {
    const el = $("term-launch");
    if (!el) return;
    const lines = (fleetState && fleetState.launch_transcript) || [];
    el.textContent = lines.length ? lines.join("\n")
      : "# the exact commands each vehicle was started with appear here";
  }

  /* ------------------------------------------------------------- apply state */
  function applyFleet(state) {
    fleetState = state;
    $("fleet-run-id").textContent = state.run_id || "";
    const pol = $("fleet-policy");
    if (pol.options.length !== (state.policies || []).length) {
      pol.innerHTML = "";
      (state.policies || []).forEach((p) => {
        const o = document.createElement("option");
        o.value = p; o.textContent = p;
        if (p === state.default_policy) o.selected = true;
        pol.appendChild(o);
      });
    }
    const known = new Set(state.vehicles.map((v) => v.id));
    [...selected].forEach((id) => { if (!known.has(id)) selected.delete(id); });

    renderGrid();
    renderTarget();
    renderAck(state.last_command);
    renderSeparation();
    renderRtf();
    renderTranscript();
    $("err-fleet").hidden = !state.error;
    if (state.error) $("err-fleet").textContent = state.error;
  }

  window.__applyFleet = applyFleet;   // used by the websocket handler and tests

  /* the third terminal tab is a transcript, not an xterm */
  document.querySelectorAll(".tab[data-stream]").forEach((tab) => {
    tab.addEventListener("click", () => {
      const want = tab.dataset.stream;
      const launch = $("term-launch");
      if (launch) launch.hidden = want !== "launch";
      if (want === "launch") {
        const sim = $("term-sim"), sh = $("term-shell");
        if (sim) sim.hidden = true;
        if (sh) sh.hidden = true;
        document.querySelectorAll(".tab[data-stream]").forEach((b) =>
          b.classList.toggle("active", b === tab));
      }
    });
  });

  loadFleets();
})();
