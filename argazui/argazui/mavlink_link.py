"""MAVLink komut kanali.

NEDEN pty stdin degil de MAVLink?
--------------------------------
Iris (ros2_launch) yolunda MAVProxy'yi ArgazUI degil, ROS2 launch baslatiyor ve
`--non-interactive` bayragiyla basliyor (kaynak: ardupilot_sitl/src/ardupilot_sitl/
launch.py, MAVProxyLaunch.generate_action). Yani o MAVProxy stdin'den komut
OKUMUYOR — terminale "mode guided" yazmak Iris'te hicbir sey yapmaz.

Buna karsilik her iki baslatma yolu da MAVLink cikisi veriyor:
  - ros2_launch      : mavproxy.py --out 127.0.0.1:14550 --out 127.0.0.1:14551
  - sim_vehicle.py   : varsayilan --out 127.0.0.1:14550 (+ ArgazUI 14551 ekliyor)

Bu yuzden butonlar MAVLink uzerinden calisiyor: her modelde ayni sekilde,
ACK geri bildirimiyle. Kullanicinin terminale elle yazdigi seyler yine pty'ye
gider (sim_vehicle.py yolunda MAVProxy etkilesimlidir ve oradan komut alir).

Port ayrimi:
  14550 -> ArgazUI (bu modul)
  14551 -> kullanicinin gorev scriptleri
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Callable, Optional

from pymavlink import mavutil

from .i18n import t

ARM_MAGIC = 21196  # ArduPilot "force" arm/disarm sihirli sayisi

# Bir komut reddedildiginde otopilotun gerekcesi STATUSTEXT ile gelir.
# Bu kaliplari iceren son mesajlari kullaniciya geri gosteriyoruz.
REJECT_HINTS = ("prearm", "arm:", "disarm", "denied", "failed", "not armed",
                "check", "unhealthy", "calibrat", "gps", "ekf", "rc ", "mode")

# ARM reddi GECICI mi kalici mi? Asagidakiler acilistan hemen sonra gorulen ve
# birkac saniye icinde kendiliginden gecen durumlar — bunlarda kisa sure
# yeniden deniyoruz (kullanicinin elle tekrar tekrar basmasi yerine).
# Gercek dunyada olculdu: "AHRS: waiting for home" bazi modellerde 30 sn'yi
# buluyor (BiCopter), Skywalker X8 quad'da ~10 sn.
TRANSIENT_ARM_HINTS = (
    "waiting for home", "ahrs", "ekf", "accels inconsistent", "gyros inconsistent",
    "compass", "gps", "3d fix", "initialising", "initializing", "not healthy",
    "baro", "position", "speed", "alt disparity", "logging",
)
ARM_RETRY_WINDOW = 35.0     # saniye
ARM_RETRY_INTERVAL = 2.5


@dataclass
class VehicleState:
    connected: bool = False
    mode: str = "-"
    armed: bool = False
    alt: float = 0.0
    groundspeed: float = 0.0
    sysid: int = 0
    last_heartbeat: float = 0.0
    # ARM oncesi kontrollerin durumu (SYS_STATUS prearm saglik biti).
    # Arac acildiktan ~10 sn sonra True olur; oncesinde ARM reddedilir.
    prearm_ok: bool = False
    prearm_known: bool = False

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "armed": self.armed,
            "alt": round(self.alt, 1),
            "groundspeed": round(self.groundspeed, 1),
            "sysid": self.sysid,
            "prearm_ok": self.prearm_ok,
            "prearm_known": self.prearm_known,
        }


@dataclass
class _Job:
    command: str
    result: Queue = field(default_factory=Queue)


def substitute(template: str, values: dict) -> str:
    """{ad} ve {ad*carpan} yer tutucularini doldurur."""
    def repl(m: re.Match) -> str:
        name, mult = m.group(1), m.group(2)
        if name not in values:
            raise KeyError(name)
        val = float(values[name])
        if mult:
            val *= float(mult)
        return str(int(val)) if val == int(val) else str(val)

    return re.sub(r"\{(\w+)(?:\*([\d.]+))?\}", repl, template)


class MavlinkLink:
    """Tek bir SITL aracina baglanan, thread'li MAVLink istemcisi.

    Tum pymavlink erisimi tek bir worker thread'inde olur (pymavlink
    baglantisi thread-safe degil). Disaridan `send(cmd)` cagrilir, komut
    kuyruga girer, worker calistirir ve sonucu geri dondurur.
    """

    def __init__(self, port: int = 14550, on_log: Optional[Callable[[str], None]] = None):
        self.port = port
        self.on_log = on_log or (lambda s: None)
        # Aktif modelin otopilot tipi ("ArduCopter" / "ArduPlane").
        # Mod tablosunu MAV_TYPE'dan tahmin etmek yerine buradan seciyoruz —
        # bkz. _mode_table(): BiCopter gibi modeller yanlis MAV_TYPE bildiriyor.
        self.vehicle: Optional[str] = None
        self.state = VehicleState()
        self._conn: Optional[mavutil.mavfile] = None
        self._jobs: "Queue[_Job]" = Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Reddedilen komutun gerekcesini gosterebilmek icin son STATUSTEXT'ler
        self._recent_status: deque = deque(maxlen=60)

    # ---------------------------------------------------------------- mod tablosu
    def _mode_table(self) -> dict:
        """Mod ADI -> numara tablosu.

        pymavlink'in `conn.mode_mapping()` fonksiyonu tabloyu aracin bildirdigi
        MAV_TYPE'a gore secer. Bu bazi modellerde YANLIS sonuc verir: BiCopter
        ArduCopter ile ucar ama kendini Plane tipi olarak bildirir, dolayisiyla
        MAVProxy/pymavlink Plane mod isimlerini gosterir (SITL_Models
        BiCopter.md bunu ayrica belgeliyor). Bu durumda "GUIDED" istegi Plane'in
        GUIDED numarasina cevrilir ve arac bambaska bir moda gecer.

        Bu yuzden tabloyu, kayit defterindeki otopilot tipinden seciyoruz.
        """
        table = None
        if self.vehicle == "ArduCopter":
            table = mavutil.mode_mapping_acm
        elif self.vehicle == "ArduPlane":
            table = mavutil.mode_mapping_apm
        if table:
            return {name: num for num, name in table.items()}
        return self._conn.mode_mapping() or {}      # bilinmiyorsa pymavlink'e birak

    def _mode_name(self, custom_mode: int, msg) -> str:
        """Mod numarasini dogru tabloya gore isme cevirir.

        mavutil.mode_string_v10() de MAV_TYPE'a bakar, dolayisiyla BiCopter'da
        yanlis isim uretir (Copter GUIDED'i "ACRO" diye gosterir). Ekranda
        dogru ismi gosterebilmek icin kendi tablomuzu kullaniyoruz.
        """
        if self.vehicle == "ArduCopter":
            return mavutil.mode_mapping_acm.get(custom_mode) or f"MOD {custom_mode}"
        if self.vehicle == "ArduPlane":
            return mavutil.mode_mapping_apm.get(custom_mode) or f"MOD {custom_mode}"
        return mavutil.mode_string_v10(msg)

    # ---------------------------------------------------------------- yasam dongusu
    def start(self, vehicle: Optional[str] = None) -> None:
        self.vehicle = vehicle
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mavlink-link", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self.state = VehicleState()

    def _run(self) -> None:
        try:
            self._conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{self.port}")
        except Exception as exc:
            self.on_log(t("mavlink_open_fail", port=self.port, err=exc))
            return

        while not self._stop.is_set():
            self._pump(0.2)
            try:
                job = self._jobs.get_nowait()
            except Empty:
                continue
            try:
                job.result.put(self._execute(job.command))
            except Exception as exc:                      # komut hatasi UI'yi dusurmesin
                job.result.put({"ok": False, "text": t("cmd_error", err=exc)})

    # ---------------------------------------------------------------- mesaj pompasi
    def _pump(self, seconds: float) -> None:
        """Gelen mesajlari okuyup arac durumunu gunceller."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            msg = self._conn.recv_match(blocking=True, timeout=0.05)
            if msg is None:
                break
            self._absorb(msg)
        if self.state.connected and time.time() - self.state.last_heartbeat > 5:
            self.state.connected = False

    def _absorb(self, msg) -> None:
        t = msg.get_type()
        if t == "HEARTBEAT":
            # Yer istasyonlarinin kendi heartbeat'ini arac sanmayalim
            if msg.get_srcComponent() == mavutil.mavlink.MAV_COMP_ID_MISSIONPLANNER:
                return
            self.state.connected = True
            self.state.last_heartbeat = time.time()
            self.state.sysid = msg.get_srcSystem()
            self.state.mode = self._mode_name(msg.custom_mode, msg)
            self.state.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        elif t == "GLOBAL_POSITION_INT":
            self.state.alt = msg.relative_alt / 1000.0
        elif t == "VFR_HUD":
            self.state.groundspeed = msg.groundspeed
        elif t == "SYS_STATUS":
            bit = mavutil.mavlink.MAV_SYS_STATUS_PREARM_CHECK
            if msg.onboard_control_sensors_enabled & bit:
                self.state.prearm_known = True
                self.state.prearm_ok = bool(msg.onboard_control_sensors_health & bit)
        elif t == "STATUSTEXT":
            text = msg.text.strip() if isinstance(msg.text, str) else msg.text.decode(errors="replace")
            if text:
                self._recent_status.append((time.time(), text))
                self.on_log(f"[SITL] {text}")

    def _recent_reasons(self, since: float) -> list[str]:
        """Komut reddine gerekce olabilecek son otopilot mesajlari."""
        out = []
        for ts, text in self._recent_status:
            if ts < since:
                continue
            low = text.lower()
            if any(h in low for h in REJECT_HINTS) and text not in out:
                out.append(text)
        return out[-4:]

    def _recv_until(self, match_fn, timeout: float):
        """Belirli bir mesaji beklerken durum guncellemesini surdurur."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self._conn.recv_match(blocking=True, timeout=0.2)
            if msg is None:
                continue
            self._absorb(msg)
            if match_fn(msg):
                return msg
        return None

    # ---------------------------------------------------------------- genel API
    def send(self, command: str, timeout: Optional[float] = None) -> dict:
        """Bir MAVProxy soz dizimli komutu calistirir, sonucu dondurur."""
        if timeout is None:
            # ARM gecici sebeplerde yeniden deniyor; ona daha genis sure gerek.
            head = command.strip().split(" ")[0].lower() if command.strip() else ""
            timeout = ARM_RETRY_WINDOW + 25.0 if head == "arm" else 15.0
        if not self._thread or not self._thread.is_alive():
            return {"ok": False, "text": t("no_link")}
        job = _Job(command=command.strip())
        self._jobs.put(job)
        try:
            return job.result.get(timeout=timeout)
        except Empty:
            return {"ok": False, "text": t("cmd_timeout", cmd=command)}

    def wait_ready(self, timeout: float = 120.0) -> bool:
        """Ilk heartbeat gelene kadar bekler (worker thread'de degil, disaridan)."""
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop.is_set():
            if self.state.connected:
                return True
            time.sleep(0.5)
        return False

    # ---------------------------------------------------------------- komut yorumlayici
    def _execute(self, cmd: str) -> dict:
        parts = cmd.split()
        if not parts:
            return {"ok": False, "text": t("empty_cmd")}
        head = parts[0].lower()

        if not self.state.connected and head != "wait":
            return {"ok": False, "text": t("no_link_vehicle")}

        if head == "mode":
            return self._do_mode(parts[1:])
        if head == "arm":
            return self._do_arm(parts[1:], arm=True)
        if head == "disarm":
            return self._do_arm(parts[1:], arm=False)
        if head == "takeoff":
            return self._do_takeoff(parts[1:])
        if head == "param":
            return self._do_param(parts[1:])
        if head == "rc":
            return self._do_rc(parts[1:])
        return {
            "ok": False,
            "unsupported": True,
            "text": t("unsupported", cmd=cmd),
        }

    def _target(self):
        return self._conn.target_system, self._conn.target_component

    def _do_mode(self, args) -> dict:
        if not args:
            return {"ok": False, "text": t("usage_mode")}
        want = args[0].upper()
        mapping = self._mode_table()
        if want not in mapping:
            available = ", ".join(sorted(mapping))
            return {"ok": False, "text": t("bad_mode", mode=want, available=available)}
        want_num = mapping[want]
        sent_at = time.time() - 1.0
        self._conn.set_mode(want_num)
        # Dogrulamayi ISIM yerine NUMARA ile yapiyoruz: bazi modeller mod
        # isimlerini yanlis tabloya gore bildiriyor (bkz. _mode_table).
        hb = self._recv_until(
            lambda m: m.get_type() == "HEARTBEAT" and m.custom_mode == want_num,
            timeout=5.0,
        )
        if hb is None:
            text = t("mode_unconfirmed", mode=want, current=self.state.mode)
            reasons = self._recent_reasons(sent_at)
            if reasons:
                text += t("reason_prefix") + " | ".join(reasons)
            return {"ok": False, "text": text}
        return {"ok": True, "text": t("mode_ok", mode=want)}

    def _param_get(self, name: str, timeout: float = 5.0) -> Optional[float]:
        self._conn.mav.param_request_read_send(*self._target(), name.encode("utf-8"), -1)
        msg = self._recv_until(
            lambda m: m.get_type() == "PARAM_VALUE" and m.param_id.rstrip("\x00") == name,
            timeout=timeout,
        )
        return None if msg is None else msg.param_value

    def _try_center_rc(self, reject_text: str) -> Optional[str]:
        """"Pitch (RC2) is not neutral" turu redleri kendiliginden duzeltir.

        Bazi modellerin param dosyasi kumanda kanallarina 1500 disi bir TRIM
        veriyor (ornek: Weight-Shift Aircraft'ta RC2_TRIM=1552). SITL'in sanal
        kumandasi 1500'de durdugu icin otopilot "cubuk ortada degil" deyip ARM
        vermiyor. Cozum: ilgili kanali kendi TRIM degerine getirmek — yani
        cubugu gercekten notr konuma almak. Modelin parametreleri degismez.
        """
        if "neutral" not in reject_text.lower():
            return None
        m = re.search(r"RC(\d+)", reject_text, re.IGNORECASE)
        if not m:
            return None
        ch = int(m.group(1))
        trim = self._param_get(f"RC{ch}_TRIM")
        if trim is None:
            return None
        chans = [0] * 18
        chans[ch - 1] = int(trim)
        self._conn.mav.rc_channels_override_send(*self._target(), *chans)
        self._recv_until(lambda m: False, timeout=1.0)
        return t("rc_centered", chan=ch, trim=f"{trim:g}")

    def _try_accel_cal(self, reject_text: str) -> Optional[str]:
        """"3D Accel calibration needed" redini basit ivmeolcer kalibrasyonuyla asar.

        Bazi modellerin param dosyasinda birincil ivmeolcerin ofsetleri tamamen
        sifir ve olcegi 1.0 (ornek: Swan-K1). ArduPilot bunu "hic kalibre
        edilmemis" sayar ve ARM vermez. SITL'de arac pistte duz durdugu icin
        MAV_CMD_PREFLIGHT_CALIBRATION'in "basit" ivmeolcer kalibrasyonu (param5=4)
        dogru sonucu verir — MAVProxy'deki `accelcalsimple` komutunun aynisi.
        """
        low = reject_text.lower()
        if "accel" not in low or "calibration" not in low:
            return None
        self._conn.mav.command_long_send(
            *self._target(), mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION, 0,
            0, 0, 0, 0, 4, 0, 0,        # param5=4 -> basit ivmeolcer kalibrasyonu
        )
        ack = self._recv_until(
            lambda m: (m.get_type() == "COMMAND_ACK"
                       and m.command == mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION),
            timeout=10.0,
        )
        if ack is None or ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            return None
        self._recv_until(lambda m: False, timeout=3.0)   # kalibrasyon otursun
        return t("accel_calibrated")

    def _send_arm(self, arm: bool, force: bool) -> dict:
        sys_id, comp_id = self._target()
        self._conn.mav.command_long_send(
            sys_id, comp_id, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1 if arm else 0, ARM_MAGIC if force else 0, 0, 0, 0, 0, 0,
        )
        return self._await_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                               "ARM" if arm else "DISARM")

    def _do_arm(self, args, arm: bool) -> dict:
        force = any(a.lower() == "force" for a in args)
        res = self._send_arm(arm, force)
        if res["ok"] or not arm:
            return res

        # 1) Kendiliginden duzeltilebilen redler: notr olmayan kumanda cubugu,
        #    kalibre edilmemis ivmeolcer. Her biri bir kez denenir.
        for fixer in (self._try_center_rc, self._try_accel_cal):
            note = fixer(res["text"])
            if not note:
                continue
            self.on_log(note)
            retry = self._send_arm(arm, force)
            if retry["ok"]:
                return {"ok": True, "text": t("arm_fixed_ok", note=note)}
            res = retry

        # 2) ARM reddedildi. Gerekce gecici bir acilis durumuysa (ev konumu
        # bekleniyor, EKF oturuyor...) kullaniciya tekrar tekrar bastirmak
        # yerine kisa bir sure biz bekleyip yeniden deniyoruz.
        low = res["text"].lower()
        if not any(h in low for h in TRANSIENT_ARM_HINTS):
            return res                       # kalici sebep — dokunma

        self.on_log(t("arm_retry_start", seconds=ARM_RETRY_WINDOW))
        deadline = time.time() + ARM_RETRY_WINDOW
        attempts = 1
        while time.time() < deadline:
            self._recv_until(lambda m: False, timeout=ARM_RETRY_INTERVAL)
            if self.state.armed:             # baska bir yoldan armlandiysa
                return {"ok": True, "text": t("ack_accepted", label="ARM")}
            attempts += 1
            res = self._send_arm(arm, force)
            if res["ok"]:
                return {"ok": True, "text": t("arm_retry_ok", attempts=attempts)}
            low = res["text"].lower()
            if not any(h in low for h in TRANSIENT_ARM_HINTS):
                return res                   # sebep degisti, artik kalici

        res["text"] += t("arm_retry_giveup", attempts=attempts, seconds=ARM_RETRY_WINDOW)
        return res

    def _do_takeoff(self, args) -> dict:
        if not args:
            return {"ok": False, "text": t("usage_takeoff")}
        try:
            alt = float(args[0])
        except ValueError:
            return {"ok": False, "text": t("bad_altitude", value=args[0])}
        sys_id, comp_id = self._target()
        self._conn.mav.command_long_send(
            sys_id, comp_id, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, alt,
        )
        return self._await_ack(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, f"TAKEOFF {alt:g}m")

    def _do_param(self, args) -> dict:
        if len(args) >= 3 and args[0].lower() == "set":
            name, raw = args[1].upper(), args[2]
            try:
                value = float(raw)
            except ValueError:
                return {"ok": False, "text": t("bad_param_value", value=raw)}
            self._conn.mav.param_set_send(
                *self._target(), name.encode("utf-8"), value,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            msg = self._recv_until(
                lambda m: m.get_type() == "PARAM_VALUE"
                and m.param_id.rstrip("\x00") == name,
                timeout=5.0,
            )
            if msg is None:
                return {"ok": False, "text": t("param_no_ack", name=name)}
            return {"ok": True, "text": t("param_ok", name=name, value=f"{msg.param_value:g}")}
        if len(args) >= 2 and args[0].lower() in ("fetch", "show", "get"):
            name = args[1].upper()
            self._conn.mav.param_request_read_send(*self._target(), name.encode("utf-8"), -1)
            msg = self._recv_until(
                lambda m: m.get_type() == "PARAM_VALUE" and m.param_id.rstrip("\x00") == name,
                timeout=5.0,
            )
            if msg is None:
                return {"ok": False, "text": t("param_unreadable", name=name)}
            return {"ok": True, "text": f"param {name} = {msg.param_value:g}"}
        return {"ok": False, "text": t("usage_param")}

    def _do_rc(self, args) -> dict:
        if len(args) < 2:
            return {"ok": False, "text": t("usage_rc")}
        try:
            chan, pwm = int(args[0]), int(args[1])
        except ValueError:
            return {"ok": False, "text": t("rc_int")}
        if not 1 <= chan <= 18:
            return {"ok": False, "text": t("rc_range")}
        chans = [0] * 18
        chans[chan - 1] = pwm
        self._conn.mav.rc_channels_override_send(*self._target(), *chans)
        return {"ok": True, "text": t("rc_ok", chan=chan, pwm=pwm)}

    def _await_ack(self, command_id: int, label: str) -> dict:
        sent_at = time.time() - 3.0        # komut oncesi uyarilari da yakala
        ack = self._recv_until(
            lambda m: m.get_type() == "COMMAND_ACK" and m.command == command_id,
            timeout=10.0,
        )
        if ack is None:
            return {"ok": False, "text": t("ack_missing", label=label)}
        if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            return {"ok": True, "text": t("ack_accepted", label=label)}

        result_name = mavutil.mavlink.enums["MAV_RESULT"][ack.result].name
        # Gerekce STATUSTEXT'i cogu zaman ACK'ten hemen SONRA gelir; bekleyelim.
        self._recv_until(lambda m: False, timeout=1.5)
        reasons = self._recent_reasons(sent_at)
        text = t("ack_rejected", label=label, result=result_name)
        if reasons:
            text += " — otopilot: " + " | ".join(reasons)
        else:
            text += t("reason_unknown")
        return {"ok": False, "text": text}
