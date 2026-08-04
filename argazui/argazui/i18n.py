"""Message catalogue for backend strings shown to the user.

The UI language is a single global setting (ArgazUI is a single-user local
tool). The browser sets it with POST /api/lang; every message the backend
pushes to the terminal or returns from a command goes through `t()`.

Default language is English; Turkish is available from the language switch
in the top bar.
"""
from __future__ import annotations

import threading

DEFAULT_LANG = "en"
LANGUAGES = ("en", "tr")

_lock = threading.Lock()
_current = DEFAULT_LANG

CATALOG: dict[str, dict[str, str]] = {
    # -------------------------------------------------- session / lifecycle
    "not_in_registry":   {"en": "'{id}' is not in the registry",
                          "tr": "'{id}' kayit defterinde yok"},
    "closing_previous":  {"en": "Closing the previous session ({id})...",
                          "tr": "Onceki oturum ({id}) kapatiliyor..."},
    "starting":          {"en": "STARTING: {name}  [{method}]",
                          "tr": "BASLATILIYOR: {name}  [{method}]"},
    "starting_short":    {"en": "Starting {name}",
                          "tr": "{name} baslatiliyor"},
    "stopping":          {"en": "STOPPING...",
                          "tr": "DURDURULUYOR..."},
    "stopped":           {"en": "stopped",
                          "tr": "durduruldu"},
    "shell_prefix":      {"en": "(command terminal) {msg}",
                          "tr": "(komut terminali) {msg}"},
    "registry_rescanned": {"en": "Registry refreshed: {count} models "
                                 "({skipped} out-of-scope entries skipped)",
                           "tr": "Kayit defteri yenilendi: {count} model "
                                 "({skipped} kapsam disi giris atlandi)"},

    # -------------------------------------------------- MAVLink link
    "waiting_mavlink":   {"en": "Waiting for MAVLink (udp 127.0.0.1:{port})...",
                          "tr": "MAVLink bekleniyor (udp 127.0.0.1:{port})..."},
    "mavlink_ready":     {"en": "MAVLink ready — sysid {sysid}, mode {mode}. "
                                "Quick command buttons are active.",
                          "tr": "MAVLink hazir — sysid {sysid}, mod {mode}. "
                                "Hizli komut butonlari aktif."},
    "mavlink_failed":    {"en": "Could not establish a MAVLink connection. Check the "
                                "errors in the terminal; if the vehicle did start, "
                                "try STOP then START.",
                          "tr": "MAVLink baglantisi kurulamadi. Terminaldeki hatalari "
                                "kontrol et; arac gercekten basladiysa DURDUR + "
                                "BASLAT dene."},
    "mavlink_open_fail": {"en": "Could not open the MAVLink connection (port {port}): {err}",
                          "tr": "MAVLink baglantisi acilamadi (port {port}): {err}"},
    "mirror_open":       {"en": "Live telemetry is being mirrored to udp {host}:{port} "
                                "— point PlotJuggler's UDP Server at that port "
                                "(protocol: JSON) to plot this flight as it happens.",
                          "tr": "Canli telemetri udp {host}:{port} adresine "
                                "aynalaniyor — PlotJuggler'da UDP Server'i bu porta "
                                "yonlendir (protokol: JSON) ve ucusu aninda cizdir."},
    "no_link":           {"en": "no MAVLink connection (press START first)",
                          "tr": "MAVLink baglantisi yok (once BASLAT)"},
    "no_link_vehicle":   {"en": "no MAVLink connection to the vehicle",
                          "tr": "araca MAVLink baglantisi yok"},
    "cmd_timeout":       {"en": "'{cmd}' timed out",
                          "tr": "'{cmd}' zaman asimina ugradi"},
    "cmd_error":         {"en": "command error: {err}",
                          "tr": "komut hatasi: {err}"},
    "empty_cmd":         {"en": "empty command",
                          "tr": "bos komut"},
    "unsupported":       {"en": "'{cmd}' is not known to the ArgazUI MAVLink "
                                "interpreter. Supported: mode / arm / disarm / "
                                "takeoff / param set / rc",
                          "tr": "'{cmd}' ArgazUI MAVLink yorumlayicisinda tanimli "
                                "degil. Desteklenen: mode / arm / disarm / takeoff / "
                                "param set / rc"},
    "sent_to_terminal":  {"en": "'{cmd}' sent to the simulation terminal",
                          "tr": "'{cmd}' simulasyon terminaline gonderildi"},
    "missing_input":     {"en": "missing input: {name}",
                          "tr": "eksik giris: {name}"},

    # -------------------------------------------------- commands
    "usage_mode":        {"en": "usage: mode <MODE>",
                          "tr": "kullanim: mode <MOD>"},
    "bad_mode":          {"en": "'{mode}' is not a valid mode for this vehicle. "
                                "Available: {available}",
                          "tr": "'{mode}' bu arac icin gecersiz mod. Mevcut: {available}"},
    "mode_unconfirmed":  {"en": "could not confirm mode {mode} (currently: {current})",
                          "tr": "mod {mode} olarak dogrulanamadi (su an: {current})"},
    "mode_ok":           {"en": "mode -> {mode}",
                          "tr": "mod -> {mode}"},
    "usage_takeoff":     {"en": "usage: takeoff <altitude_m>",
                          "tr": "kullanim: takeoff <irtifa_m>"},
    "bad_altitude":      {"en": "invalid altitude: {value}",
                          "tr": "gecersiz irtifa: {value}"},
    "usage_param":       {"en": "usage: param set <NAME> <VALUE>  |  param fetch <NAME>",
                          "tr": "kullanim: param set <AD> <DEGER>  |  param fetch <AD>"},
    "bad_param_value":   {"en": "invalid parameter value: {value}",
                          "tr": "gecersiz parametre degeri: {value}"},
    "param_no_ack":      {"en": "no confirmation received for {name}",
                          "tr": "{name} icin onay gelmedi"},
    "param_unreadable":  {"en": "could not read {name}",
                          "tr": "{name} okunamadi"},
    "param_ok":          {"en": "param {name} = {value}",
                          "tr": "param {name} = {value}"},
    "usage_rc":          {"en": "usage: rc <channel 1-18> <pwm>",
                          "tr": "kullanim: rc <kanal 1-18> <pwm>"},
    "rc_int":            {"en": "channel and pwm must be integers",
                          "tr": "kanal ve pwm tam sayi olmali"},
    "rc_range":          {"en": "channel must be between 1 and 18",
                          "tr": "kanal 1-18 arasinda olmali"},
    "rc_ok":             {"en": "rc {chan} -> {pwm}",
                          "tr": "rc {chan} -> {pwm}"},

    # -------------------------------------------------- arm / ack
    "ack_missing":       {"en": "{label}: no ACK received",
                          "tr": "{label}: ACK gelmedi"},
    "ack_accepted":      {"en": "{label}: accepted",
                          "tr": "{label}: kabul edildi"},
    "ack_rejected":      {"en": "{label}: REJECTED ({result})",
                          "tr": "{label}: REDDEDILDI ({result})"},
    "reason_prefix":     {"en": " — autopilot: ",
                          "tr": " — otopilot: "},
    "reason_unknown":    {"en": " — no reason reported (check the messages in the "
                                "SIMULATION terminal)",
                          "tr": " — gerekce bildirilmedi (SIMULASYON terminalindeki "
                                "mesajlara bak)"},
    "arm_state_unconfirmed": {"en": "{label}: the command was accepted but the vehicle "
                                    "never reported the new armed state",
                              "tr": "{label}: komut kabul edildi ama arac yeni arm "
                                    "durumunu hic bildirmedi"},
    "rc_centered":       {"en": "RC{chan} moved to neutral (TRIM={trim})",
                          "tr": "RC{chan} notr konuma (TRIM={trim}) alindi"},
    "accel_calibrated":  {"en": "simple accelerometer calibration performed "
                                "(accelcalsimple)",
                          "tr": "basit ivmeolcer kalibrasyonu yapildi (accelcalsimple)"},
    "arm_retry_start":   {"en": "ARM rejected (transient reason). Will keep retrying "
                                "for {seconds:.0f}s until the vehicle is ready...",
                          "tr": "ARM reddedildi (gecici sebep). {seconds:.0f} sn boyunca "
                                "arac hazir olunca yeniden denenecek..."},
    "arm_retry_ok":      {"en": "ARM: accepted (on attempt {attempts}, after waiting "
                                "for the vehicle to become ready)",
                          "tr": "ARM: kabul edildi ({attempts}. denemede, arac hazir "
                                "olana kadar beklendi)"},
    "arm_fixed_ok":      {"en": "ARM: accepted ({note})",
                          "tr": "ARM: kabul edildi ({note})"},
    "arm_retry_giveup":  {"en": "  >>> tried {attempts} times over {seconds:.0f}s, the "
                                "vehicle did not become ready. Watch the 'READY' "
                                "indicator in the top bar; the autopilot messages in "
                                "the SIMULATION terminal explain why.",
                          "tr": "  >>> {seconds:.0f} sn boyunca {attempts} kez denendi, "
                                "arac hazir olmadi. Ust cubuktaki 'HAZIR' gostergesini "
                                "izle; SIMULASYON terminalindeki otopilot mesajlari "
                                "sebebi gosterir."},

    # -------------------------------------------------- scripts
    "bad_script":        {"en": "invalid script: {name}",
                          "tr": "gecersiz script: {name}"},
    "running_script":    {"en": "Running script: {name} (MAVLink port {port})",
                          "tr": "Script calistiriliyor: {name} (MAVLink portu {port})"},
    "script_started":    {"en": "{name} started in the command terminal",
                          "tr": "{name} komut terminalinde baslatildi"},

    # -------------------------------------------------- process cleanup
    "nothing_to_stop":   {"en": "No running processes to shut down.",
                          "tr": "Kapatilacak calisan surec bulunamadi."},
    "terminating":       {"en": "Shutting down (process groups: {groups})",
                          "tr": "Sonlandiriliyor (surec gruplari: {groups})"},
    "signal_sent":       {"en": "  {signal} -> {groups}",
                          "tr": "  {signal} -> {groups}"},
    "still_running":     {"en": "WARNING: process groups still running: {groups}",
                          "tr": "UYARI: hala calisan surec grubu var: {groups}"},
    "all_closed":        {"en": "All processes have exited.",
                          "tr": "Tum surecler kapandi."},

    # -------------------------------------------------- rc / mission primitives
    "rc_override_ok":    {"en": "stick override: {channels}",
                          "tr": "cubuk override: {channels}"},
    "rc_released":       {"en": "stick overrides released",
                          "tr": "cubuk override'lari birakildi"},
    "rc_nothing_held":   {"en": "no stick override was active",
                          "tr": "aktif cubuk override'i yoktu"},
    "mission_uploaded":  {"en": "mission uploaded ({count} item(s))",
                          "tr": "gorev yuklendi ({count} madde)"},
    "mission_rejected":  {"en": "the vehicle rejected the mission ({result})",
                          "tr": "arac gorevi reddetti ({result})"},
    "mission_no_request": {"en": "the vehicle did not ask for the mission items",
                           "tr": "arac gorev maddelerini istemedi"},
    "mission_timeout":   {"en": "mission upload timed out",
                          "tr": "gorev yuklemesi zaman asimina ugradi"},

    # -------------------------------------------------- procedure engine
    "proc_running":      {"en": "PROCEDURE: {name}",
                          "tr": "PROSEDUR: {name}"},
    "proc_step":         {"en": "  [{index}/{total}] {label}",
                          "tr": "  [{index}/{total}] {label}"},
    "proc_passed":       {"en": "PROCEDURE PASSED: {name} — every acceptance "
                                "criterion was met",
                          "tr": "PROSEDUR GECTI: {name} — tum kabul kriterleri "
                                "saglandi"},
    "proc_failed":       {"en": "PROCEDURE FAILED: {name}",
                          "tr": "PROSEDUR BASARISIZ: {name}"},
    "proc_slept":        {"en": "waited {seconds}s",
                          "tr": "{seconds} sn beklendi"},
    "proc_skipped":      {"en": "skipped — its condition does not hold ({seen})",
                          "tr": "atlandi — kosulu saglanmiyor ({seen})"},
    "proc_cancelled":    {"en": "the procedure was cancelled",
                          "tr": "prosedur iptal edildi"},
    "proc_wait_timeout": {"en": "the expected state did not arrive within {seconds}s "
                                "— last seen: {seen}",
                          "tr": "beklenen duruma {seconds} sn icinde ulasilmadi "
                                "— son gorulen: {seen}"},
    "proc_overall_timeout": {"en": "the procedure exceeded its overall timeout "
                                   "of {seconds}s",
                             "tr": "prosedur toplam {seconds} sn sinirini asti"},
    "proc_param_out_of_range": {"en": "{name} is {value}, which is outside the range "
                                      "this procedure needs",
                                "tr": "{name} = {value}, bu prosedurun ihtiyac duydugu "
                                      "araligin disinda"},
    "proc_not_evaluated": {"en": "not evaluated — the procedure stopped earlier",
                           "tr": "degerlendirilmedi — prosedur daha once durdu"},
    # Attitude envelope criteria. Stated in seconds spent outside a band,
    # because that is what the verdict is actually based on.
    "stab_axis":         {"en": "{axis} outside [{low},{high}]° for {outside}s",
                          "tr": "{axis} [{low},{high}]° disinda {outside} sn"},
    "stab_rate":         {"en": "turn rate above {limit}°/s for {above}s "
                                "(peak {peak}°/s)",
                          "tr": "donus hizi {limit}°/sn ustunde {above} sn "
                                "(tepe {peak}°/sn)"},
    "stab_summary":      {"en": "{detail} — allowed {tolerance}s each, "
                                "measured over {measured}s",
                          "tr": "{detail} — her biri icin {tolerance} sn izin var, "
                                "{measured} sn boyunca olculdu"},
    "stab_no_data":      {"en": "attitude was measured for only {measured}s of the "
                                "{needed}s this criterion needs — not judged as "
                                "stable, judged as unmeasured",
                          "tr": "tutum yalnizca {measured} sn olculdu, bu kriter "
                                "{needed} sn istiyor — kararli sayilmadi, "
                                "olculmemis sayildi"},
    "proc_unknown_step": {"en": "unimplemented step type: {kind}",
                          "tr": "uygulanmamis adim tipi: {kind}"},
    "proc_unknown_enum": {"en": "unknown MAVLink name: {name}",
                          "tr": "bilinmeyen MAVLink adi: {name}"},
    "proc_unknown_placeholder": {"en": "the procedure refers to an unknown value: {name}",
                                 "tr": "prosedur bilinmeyen bir degere basvuruyor: {name}"},
    "proc_none_for_vehicle": {"en": "No {role} procedure fits this vehicle "
                                    "(capabilities: {caps}). See argazui/procedures/.",
                              "tr": "Bu araca uyan bir {role} proseduru yok "
                                    "(yetenekler: {caps}). argazui/procedures/ klasorune bak."},
    "proc_not_found":    {"en": "there is no procedure named '{id}'",
                          "tr": "'{id}' adinda bir prosedur yok"},
    "proc_busy":         {"en": "a procedure is already running",
                          "tr": "zaten calisan bir prosedur var"},
    "proc_no_vehicle":   {"en": "no vehicle is connected — press START first",
                          "tr": "bagli arac yok — once BASLAT"},
    "proc_caps":         {"en": "Vehicle capabilities read from the aircraft: {caps}",
                          "tr": "Aractan okunan yetenekler: {caps}"},
    "proc_selected":     {"en": "{role}: using '{id}' ({name})",
                          "tr": "{role}: '{id}' kullaniliyor ({name})"},
    "proc_params_restored": {"en": "run-scoped parameters restored: {names}",
                             "tr": "kosuya ozel parametreler geri alindi: {names}"},
    "proc_override_failed": {"en": "could not apply the declared override {name} = "
                                   "{value}: {text}",
                             "tr": "beyan edilen {name} = {value} override'i "
                                   "uygulanamadi: {text}"},
    "proc_override_applied": {"en": "override {name} = {value} (was {previous}) — {reason}",
                              "tr": "override {name} = {value} (onceki: {previous}) "
                                    "— {reason}"},
    "proc_restore_failed": {"en": "WARNING: {name} could NOT be restored to {value}. "
                                  "The vehicle is still running with the value this "
                                  "procedure set.",
                            "tr": "UYARI: {name} degeri {value} olarak GERI ALINAMADI. "
                                  "Arac hala bu prosedurun yazdigi degerle calisiyor."},
    "proc_internal_error": {"en": "the procedure could not be evaluated (this is a "
                                  "fault in ArgazUI or the link, not a verdict about "
                                  "the aircraft): {err}",
                            "tr": "prosedur degerlendirilemedi (bu ArgazUI ya da "
                                  "baglantidaki bir arizadir, arac hakkinda bir hukum "
                                  "degildir): {err}"},

    # -------------------------------------------------- run artefacts
    "run_started":       {"en": "Recording this session as run '{id}' "
                                "(console, MAVLink events, parameters, dataflash).",
                          "tr": "Bu oturum '{id}' kosusu olarak kaydediliyor "
                                "(konsol, MAVLink olaylari, parametreler, dataflash)."},
    "run_failed":        {"en": "Could not open a run directory, so this session will "
                                "not be archived: {err}",
                          "tr": "Kosu dizini acilamadi, bu oturum arsivlenmeyecek: {err}"},
    "run_saved":         {"en": "Run '{id}' saved ({status}) -> {path}",
                          "tr": "Kosu '{id}' kaydedildi ({status}) -> {path}"},
    "run_report_ready":  {"en": "Flight report ready for run '{id}' — {advisories} "
                                "advisory item(s). Advisories are health findings; "
                                "they do not change the run's pass/fail result.",
                          "tr": "'{id}' kosusunun ucus raporu hazir — {advisories} "
                                "danisma uyarisi. Bu uyarilar saglik bulgusudur; "
                                "kosunun gecti/kaldi sonucunu degistirmez."},
    "run_unknown":       {"en": "there is no run named '{id}'",
                          "tr": "'{id}' adinda bir kosu yok"},
    "run_no_report":     {"en": "run '{id}' has no flight report — it may still be "
                                "generating, or the session left no dataflash log",
                          "tr": "'{id}' kosusunun ucus raporu yok — hala uretiliyor "
                                "olabilir ya da oturum dataflash logu birakmamis"},
    "run_report_slow":   {"en": "run '{id}': the flight report was still being "
                                "generated after {seconds}s and was not waited "
                                "for any longer — the run directory may lack "
                                "report.json",
                          "tr": "'{id}' kosusu: ucus raporu {seconds} sn sonra hala "
                                "uretiliyordu ve daha fazla beklenmedi — kosu "
                                "klasorunde report.json eksik olabilir"},
    "run_no_file":       {"en": "no such file in this run: {name}",
                          "tr": "bu kosuda boyle bir dosya yok: {name}"},
    "run_bin_copy_failed": {"en": "the dataflash log at {path} could not be copied "
                                  "into the run directory: {err}",
                            "tr": "{path} konumundaki dataflash logu kosu dizinine "
                                  "kopyalanamadi: {err}"},
    "run_bin_truncated": {"en": "WARNING: the dataflash log {name} looks truncated "
                                "({detail}). The report still covers what was "
                                "written, but the flight was not fully recorded.",
                          "tr": "UYARI: {name} dataflash logu yarim gorunuyor "
                                "({detail}). Rapor yazilabilmis kismi kapsiyor ama "
                                "ucus tam olarak kaydedilmemis."},
    "stop_noise":        {"en": "Two messages above are expected during shutdown and "
                                "are harmless: Gazebo's 'gz' wrapper reports "
                                "Errno::ESRCH because ArgazUI already stopped its "
                                "children by process group, and MAVProxy's log_writer "
                                "thread raises while closing its own telemetry log "
                                "(mav.tlog). Neither writes the autopilot's dataflash "
                                "log — that is written by SITL itself, and every run "
                                "now records whether it closed complete.",
                          "tr": "Yukaridaki iki mesaj kapanista beklenir ve zararsizdir: "
                                "Gazebo'nun 'gz' sarmalayicisi Errno::ESRCH veriyor "
                                "cunku ArgazUI cocuk surecleri zaten surec grubuyla "
                                "kapatti; MAVProxy'nin log_writer thread'i ise kendi "
                                "telemetri logunu (mav.tlog) kapatirken hata veriyor. "
                                "Ikisi de otopilotun dataflash logunu yazmiyor — onu "
                                "SITL'in kendisi yaziyor ve her kosu artik o logun "
                                "eksiksiz kapanip kapanmadigini kaydediyor."},

    # -------------------------------------------------- misc
    "ui_connected":      {"en": "interface connected.",
                          "tr": "arayuz baglandi."},
}


def set_language(lang: str) -> str:
    global _current
    with _lock:
        _current = lang if lang in LANGUAGES else DEFAULT_LANG
        return _current


def get_language() -> str:
    return _current


def t(key: str, **kwargs) -> str:
    """Look up a message in the active language and format it."""
    entry = CATALOG.get(key)
    if entry is None:
        return key                      # eksik anahtar gorunur olsun
    text = entry.get(_current) or entry.get(DEFAULT_LANG, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text
