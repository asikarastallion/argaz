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
  14552 -> canli telemetri aynasi (bkz. telemetry_mirror.py)

The mirror is fed from `_absorb`, which is the single place every received
message already passes through. It decodes nothing of its own — see that
module for why the live plot is JSON rather than MAVLink.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Callable, Optional

from pymavlink import mavutil

from .i18n import t
from .telemetry_mirror import TelemetryMirror

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

# How long a vehicle's mode must have been still before a mode command is
# safe to send. In VEHICLE seconds.
#
# MEASURED, NOT CHOSEN
# --------------------
# ArduPlane reads its flight-mode switch shortly after RC input first becomes
# valid, and overwrites any mode commanded in that window with no NAK and no
# STATUSTEXT. Recorded instances of the overwrite:
#
#     RC valid 6.75  ->  FBWA commanded 6.85  ->  back to MANUAL 6.99
#     INITIALISING   ->  FBWA commanded 6.42  ->  back to MANUAL 6.50
#
# So the window that matters is ~100-150 ms wide and closes as soon as the
# switch has been read once. Two seconds is more than an order of magnitude
# of margin and still shorter than the pre-arm wait a user already sits
# through, so it costs nothing they will notice.
MODE_SETTLE_S = 2.0


@dataclass
class VehicleState:
    """What the vehicle has told us, and — separately — what it has not.

    EVERY FIELD HAS A DEFAULT, AND A DEFAULT IS NOT A MEASUREMENT
    ------------------------------------------------------------
    `alt` starts at 0.0 because a float has to start somewhere. It does NOT
    mean the aircraft is on the ground, and the two readings are
    indistinguishable by value alone: a landed aircraft and a position stream
    that never arrived both present `alt == 0.0`.

    That is not a theoretical concern. It produced a real false PASS — the
    criterion `alt_below: 3` in every landing procedure evaluated true against
    a field nothing had ever written to, and the run record said
    "on the ground — alt=0.0m" for a flight whose GLOBAL_POSITION_INT never
    arrived. ArduCopter reaching this state is documented in
    `_request_streams` below; a `mavlink_degradation` fault reaches it on
    purpose.

    So every group of fields carries a `*_known` flag that is set when — and
    only when — the message backing it has actually been absorbed. The flags
    are monotonic: once a signal has been seen the flag stays set, because they
    answer "has this ever been measured", not "is it fresh". Freshness is
    `connected` and `heartbeat_age`.

    `procrunner.CONDITION_EVIDENCE` maps each acceptance condition to the flag
    it rests on, and a condition whose flag is clear cannot be satisfied. See
    `ProcedureRunner._check`.
    """

    # Is the link live NOW? Cleared after 5 s without a heartbeat.
    connected: bool = False
    mode: str = "-"
    armed: bool = False
    alt: float = 0.0
    groundspeed: float = 0.0
    # Dikey hiz (VFR_HUD.climb). Kalkis prosedurleri "ACK geldi" yerine
    # "arac gercekten tirmaniyor" diyebilmek icin bunu kullaniyor.
    climb: float = 0.0
    sysid: int = 0
    last_heartbeat: float = 0.0
    # Has a vehicle HEARTBEAT ever been absorbed? Distinct from `connected`,
    # which is about the last five seconds: `armed` and `mode` are meaningful
    # the moment one heartbeat has arrived and stay meaningful afterwards, even
    # across a deliberate blackout.
    heartbeat_known: bool = False
    # Has GLOBAL_POSITION_INT ever arrived? Backs `alt`, and therefore
    # `alt_above` / `alt_below`.
    position_known: bool = False
    # Has VFR_HUD ever arrived? Backs `groundspeed` and `climb`.
    vfr_known: bool = False
    # ARM oncesi kontrollerin durumu (SYS_STATUS prearm saglik biti).
    # Arac acildiktan ~10 sn sonra True olur; oncesinde ARM reddedilir.
    prearm_ok: bool = False
    prearm_known: bool = False
    # Attitude, in degrees and degrees per second. Present because acceptance
    # criteria judge HOW the aircraft flew, not only where it ended up: an
    # altitude reading cannot tell a controlled climb from a tumble that
    # happened to gain height. See StabilityWatch.
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    roll_rate: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0
    attitude_known: bool = False
    # The vehicle's OWN clock, in seconds since it booted (ATTITUDE.time_boot_ms).
    # 0.0 means nothing has been observed yet, which is not the same as "the
    # vehicle has been running for no time": temporal acceptance criteria treat
    # the two differently, because a duration measured against a clock that has
    # never ticked is not a measurement. See procrunner._Window.
    vehicle_clock_s: float = 0.0
    # When the mode last moved, on that same clock. `None` means nothing has
    # been observed yet, which is NOT the same as "it has been still" — see
    # `mode_settled`.
    mode_changed_at_s: Optional[float] = None

    @property
    def mode_settled(self) -> bool:
        """Has the mode stopped moving on its own?

        False until a mode change has actually been observed: absence of data
        is not evidence of stillness, and a vehicle that has never reported a
        mode is exactly the one in the middle of starting up.
        """
        if self.mode_changed_at_s is None or not self.vehicle_clock_s:
            return False
        return (self.vehicle_clock_s - self.mode_changed_at_s) >= MODE_SETTLE_S

    def known(self) -> dict:
        """Which telemetry groups have actually been observed at least once.

        The one place the knowledge state is enumerated. `procrunner` maps
        conditions onto these names, the interface renders them, and the run
        record carries them — so "we never measured this" is a fact that
        travels with the evidence instead of being reconstructed later from a
        zero.
        """
        return {"heartbeat": self.heartbeat_known,
                "position": self.position_known,
                "vfr": self.vfr_known,
                "attitude": self.attitude_known,
                "prearm": self.prearm_known}

    @property
    def max_angular_rate(self) -> float:
        """Largest of |p|, |q|, |r| in deg/s — body frame, no singularity.

        Body rates are used rather than Euler-angle change because Euler angles
        are degenerate at a vertical attitude: with the nose near +90° pitch,
        roll and yaw describe the same rotation and the reported roll swings
        across its whole range while the aircraft sits still.
        """
        return max(abs(self.roll_rate), abs(self.pitch_rate), abs(self.yaw_rate))

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "mode": self.mode,
            "armed": self.armed,
            "alt": round(self.alt, 1),
            "groundspeed": round(self.groundspeed, 1),
            "climb": round(self.climb, 1),
            "roll": round(self.roll, 1),
            "pitch": round(self.pitch, 1),
            "sysid": self.sysid,
            "prearm_ok": self.prearm_ok,
            "prearm_known": self.prearm_known,
            # Which signals have actually been observed. Sent to the interface
            # so a panel can show "—" for a quantity nothing has measured
            # instead of a zero that reads like a reading.
            "known": self.known(),
            # Seconds since the last vehicle heartbeat, or None if none has
            # ever arrived. The interface needs this to say WHY the link is
            # down instead of showing a bare dash: "no heartbeat for 12 s" and
            # "never heard from the vehicle" are different problems.
            "heartbeat_age": (None if not self.last_heartbeat
                              else round(time.time() - self.last_heartbeat, 1)),
            # Whether a mode command is safe to send yet. The interface gates
            # its command buttons on this; see MODE_SETTLE_S.
            "mode_settled": self.mode_settled,
        }


# Attitude is now something a procedure may accept or reject, so it has to
# arrive fast enough to judge. MAV_DATA_STREAM_ALL at 4 Hz was chosen when the
# only questions were "what mode" and "how high"; at 4 Hz a 2 Hz oscillation
# and a steady hover are indistinguishable, and the aircraft this criterion
# was written for oscillates at roughly that rate.
ATTITUDE_STREAM_HZ = 10


class StabilityWatch:
    """Records how the airframe behaved, not just where it ended up.

    WHY THIS EXISTS
    ---------------
    `tailsitter_takeoff` passed three times while the aircraft was tumbling.
    It reached altitude, stayed armed and reported QHOVER — and those were the
    only three things the acceptance criteria looked at. Altitude is a side
    effect of a thrust vector that happened to point roughly up for a while;
    nothing in the criteria could tell a controlled climb from a fall upwards.

    So the attitude envelope is measured continuously for the whole of a
    procedure, and criteria are evaluated against it afterwards.

    WHY TIME OUTSIDE A BAND, RATHER THAN A PEAK
    -------------------------------------------
    A peak is one sample: a gust, a mode change or a single noisy reading
    makes it useless as a verdict. What separates a tumble from a manoeuvre is
    how LONG the aircraft stays outside its band, so every limit is judged
    against accumulated seconds and each procedure declares how many of those
    seconds it forgives.

    WHY THE VEHICLE'S CLOCK AND NOT OURS
    ------------------------------------
    Every sample is weighted by the interval between its own timestamp and the
    previous one, taken from ATTITUDE.time_boot_ms. Wall-clock timing was tried
    first and is wrong twice over: telemetry arrives in bursts whenever the
    receive buffer is drained, so a hundred messages covering ten seconds of
    flight all land within a few milliseconds and contribute almost nothing;
    and under SITL speedup a wall-clock second is not a second of flight at
    all. The limits in a procedure are about the aircraft, so they are counted
    on the aircraft's clock — which also makes them mean the same thing at
    speedup 1 and speedup 10.
    """

    __slots__ = ("_samples", "_last")

    # An interval longer than this is a gap in the telemetry, not a long
    # stretch of flight in one attitude. It is counted at this value rather
    # than in full so that a dropout can neither manufacture nor excuse time
    # outside a band.
    MAX_GAP = 0.5

    def __init__(self) -> None:
        self._samples: list[tuple] = []      # (t, roll, pitch, max|rate|, dt)
        self._last: Optional[float] = None

    def reset(self) -> None:
        self._samples = []
        self._last = None

    def add(self, when: float, roll: float, pitch: float,
            rates: tuple[float, float, float]) -> None:
        """`when` is vehicle time in seconds (ATTITUDE.time_boot_ms / 1000)."""
        # The first sample of a window has no predecessor and so carries no
        # time. That is the only honest weight for an interval nobody observed.
        dt = 0.0
        if self._last is not None and when > self._last:
            dt = min(when - self._last, self.MAX_GAP)
        self._samples.append((when, roll, pitch, max(abs(r) for r in rates), dt))
        self._last = when

    # ------------------------------------------------------------------ queries
    @property
    def seconds(self) -> float:
        return sum(s[4] for s in self._samples)

    def outside_seconds(self, axis: str, low: float, high: float) -> float:
        index = 1 if axis == "roll" else 2
        return sum(s[4] for s in self._samples if not (low <= s[index] <= high))

    def rate_above_seconds(self, limit: float) -> float:
        return sum(s[4] for s in self._samples if s[3] > limit)

    def report(self) -> dict:
        """The measured envelope, for the run record and the flight report."""
        if not self._samples:
            return {"samples": 0, "seconds": 0.0}
        rolls = [s[1] for s in self._samples]
        pitches = [s[2] for s in self._samples]
        rates = sorted(s[3] for s in self._samples)
        return {
            "samples": len(self._samples),
            "seconds": round(self.seconds, 1),
            "roll_min": round(min(rolls), 1), "roll_max": round(max(rolls), 1),
            "pitch_min": round(min(pitches), 1), "pitch_max": round(max(pitches), 1),
            "rate_peak": round(rates[-1], 1),
            "rate_p95": round(rates[int(len(rates) * 0.95) - 1 if len(rates) > 1 else 0], 1),
            "rate_median": round(rates[len(rates) // 2], 1),
        }


# RC_OVERRIDE_TIME defaults to 3.0 s (ArduPilot
# libraries/RC_Channel/RC_Channels_VarInfo.h): an override that is not resent
# expires and the vehicle falls back to the real RC input. In SITL that input
# is the throttle at 1000, so a one-shot "stick up" override would stop a VTOL
# climb after three seconds. Anything holding a stick has to keep saying so.
#
# 0.25 s rather than 0.5: RC_OVERRIDE_TIME counts VEHICLE seconds, so under
# SITL speedup the wall-clock budget shrinks by the same factor. At speedup 5
# the 3 s timeout arrives after 0.6 wall-clock seconds, which a 0.5 s
# keepalive only just meets — a held VTOL throttle would drop out and look
# like a procedure bug rather than a timing one. At speedup 1 the extra
# packets cost nothing.
RC_KEEPALIVE_INTERVAL = 0.25

# ---------------------------------------------------------------- derived from
# The value above is now only the fallback. The interval is DERIVED, because a
# constant cannot be right on two machines at once:
#
#   * `RC_OVERRIDE_TIME` is a parameter. It ships at 3.0 s but a model's
#     parameter file may set anything, and 0 disables overrides entirely while
#     -1 makes them never expire. Guessing 3.0 is wrong for those aircraft.
#   * The timeout is counted in VEHICLE seconds. Under SITL speedup the
#     wall-clock budget shrinks by the same factor: at speedup 10 a 3-second
#     timeout arrives after 0.3 s of real time, which a 0.25 s keepalive only
#     just meets — a held VTOL throttle drops out mid-climb and reads as a
#     procedure bug rather than a timing one.
#
# So the timeout is read from the vehicle, the speedup is measured from its own
# clock, and the interval is whatever fits REFRESHES times into the resulting
# wall-clock budget. Four rather than two: one lost packet must not be enough
# to lose the stick.
RC_OVERRIDE_TIME_PARAM = "RC_OVERRIDE_TIME"
RC_OVERRIDE_TIME_DEFAULT = 3.0          # ArduPilot's own default, vehicle seconds
RC_KEEPALIVE_REFRESHES = 4
# Floor: below this the traffic costs more than the safety is worth. Ceiling:
# above it a slow link would look idle to the autopilot for too long.
RC_KEEPALIVE_MIN = 0.05
RC_KEEPALIVE_MAX = 1.0


def keepalive_interval(override_time: Optional[float], speedup: float) -> float:
    """How often a held RC override must be resent, in wall-clock seconds.

    `override_time` is the vehicle's `RC_OVERRIDE_TIME`; None means it has not
    been read yet. Its two special values are honoured rather than treated as
    numbers: -1 never expires, so refreshing is only politeness, and 0 disables
    overrides altogether — in both cases the slowest sensible rate is right.
    """
    if override_time is None:
        override_time = RC_OVERRIDE_TIME_DEFAULT
    if override_time <= 0:
        # 0 = overrides disabled, -1 = never expires. Nothing to outrun.
        return RC_KEEPALIVE_MAX
    speedup = speedup if speedup and speedup > 0 else 1.0
    wall_budget = override_time / speedup
    interval = max(RC_KEEPALIVE_MIN, wall_budget / RC_KEEPALIVE_REFRESHES)
    # The floor exists to stop pointless traffic, not to override physics. A
    # short RC_OVERRIDE_TIME at a high speedup can make the whole budget
    # smaller than the floor, and honouring the floor there would send the
    # refresh AFTER the stick had already been dropped — a keepalive that
    # guarantees the thing it exists to prevent. The budget wins.
    return min(interval, wall_budget, RC_KEEPALIVE_MAX)

# ArgazUI konusan bir yer istasyonudur, o halde heartbeat de gondermelidir.
# Gondermezse otopilot GCS'i kaybettigini dusunup failsafe'e giriyor — gercek
# bir kosuda gorulmustu: QLAND sirasinda "GCS Failsafe On: switched to QLand".
# MAVProxy'li yolda bunu MAVProxy yapiyordu; testler MAVProxy'siz kostugu icin
# eksikligi ancak orada ortaya cikti.
GCS_HEARTBEAT_INTERVAL = 1.0

# Kosu kaydina (runs.py) yazilan periyodik durum ornegi. Mod/arm/ACK gibi
# olaylar zaten degistiklerinde kaydediliyor; bu ornek irtifa ve hiz gibi
# SUREKLI degisen buyukluklerin zaman serisini birakiyor. 1 Hz bilincli bir
# secim: dataflash log zaten tam hizda kayit tutuyor, buradaki dosya insan
# tarafindan okunabilir kalmali.
EVENT_STATE_INTERVAL = 1.0


@dataclass
class _Job:
    command: str = ""
    # A procedure step submits a callable instead of a command string; it runs
    # on the same worker thread, so it may touch the pymavlink connection.
    fn: Optional[Callable] = None
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

    def __init__(self, port: int = 14550, on_log: Optional[Callable[[str], None]] = None,
                 connection: Optional[str] = None,
                 on_event: Optional[Callable[[dict], None]] = None,
                 mirror_port: int = 0):
        self.port = port
        # Varsayilan: MAVProxy'nin 14550'ye verdigi UDP cikisi (UI yolu).
        # Testler MAVProxy'siz kosarken SITL'in kendi TCP portuna baglanabilsin
        # diye baglanti dizesi disaridan verilebiliyor. Degisen sadece TASIYICI;
        # prosedurler ve motor iki durumda da ayni.
        self.connection = connection or f"udpin:127.0.0.1:{port}"
        self.on_log = on_log or (lambda s: None)
        # Kosu kaydinin olay akisi. Varsayilan bos: MAVLink katmani bir kosu
        # kaydi olup olmadigini bilmez, sadece "sunlar oldu" der.
        self.on_event = on_event or (lambda e: None)
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
        # Aktif RC override'lari (kanal -> pwm) ve son gonderim zamani.
        # Bkz. RC_KEEPALIVE_INTERVAL: override'lar surekli tazelenmezse
        # ArduPilot 3 saniye sonra gercek kumandaya geri doner.
        self._rc_overrides: dict[int, int] = {}
        self._rc_last_sent: float = 0.0
        # RC_OVERRIDE_TIME as the vehicle reports it, read once when the first
        # override is sent; None until then. See keepalive_interval().
        self._rc_override_time: Optional[float] = None
        # How fast simulated time runs, measured from the vehicle's own clock.
        self._clock_ref: Optional[tuple] = None
        self._speedup: float = 1.0
        self._hb_last_sent: float = 0.0
        self._state_sampled: float = 0.0
        self._streams_requested: bool = False
        # The attitude envelope for the procedure currently running. Owned by
        # the link because `_absorb` is the one place every message passes
        # through; scoped by the runner, which resets it before its first step.
        self.stability = StabilityWatch()
        # Live telemetry out to a plotting tool. Owned here for the same reason
        # as the stability watch: `_absorb` sees every message exactly once.
        # Its lifetime is this link's — opened by start(), closed by stop().
        self.mirror = TelemetryMirror(port=mirror_port, on_log=self.on_log)
        # A declared, simulation-only link fault (v1.4). None means the link is
        # behaving normally, which is the only state anything outside
        # `faults.LinkInjector` ever sets it to. See `set_link_fault`.
        self._link_fault: Optional[dict] = None
        self._rx_seen: int = 0
        self._rx_dropped: int = 0

    def emit(self, kind: str, **payload) -> None:
        """Bir olayi kosu kaydina bildirir; hicbir zaman cagirana hata dondurmez."""
        try:
            self.on_event({"kind": kind, **payload})
        except Exception:
            pass

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
        # Before the worker exists, so no message can arrive with the mirror
        # half-open. Failing to open one is never a reason not to fly.
        if self.mirror.enabled and self.mirror.open():
            self.on_log(t("mirror_open", host=self.mirror.host, port=self.mirror.port))
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mavlink-link", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        # After the join, not before: the worker is the only thread that sends
        # on the mirror, so closing it here cannot race a send in progress.
        self.mirror.close()
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self._rc_overrides.clear()
        self._streams_requested = False
        self._state_sampled = 0.0
        # A link fault must not outlive the link that carried it. The runner
        # already clears it from a `finally`; this is the second guarantee, for
        # the case where the whole session is torn down mid-fault.
        self._link_fault = None
        self.state = VehicleState()

    def _run(self) -> None:
        # Baglantiyi ACMAYI yeniden deniyoruz. UDP'de ilk denemede acilir, ama
        # TCP'de (SITL'in kendi 5760 portu) arac daha derleniyor olabilir ve
        # baglanti reddedilir; tek denemede pes etmek link'i sessizce olduruyordu.
        deadline = time.time() + 180.0
        last_exc: Optional[Exception] = None
        while not self._stop.is_set() and time.time() < deadline:
            try:
                self._conn = mavutil.mavlink_connection(self.connection)
                break
            except Exception as exc:
                last_exc = exc
                self._stop.wait(2.0)
        if self._conn is None:
            self.on_log(t("mavlink_open_fail", port=self.connection, err=last_exc))
            return

        while not self._stop.is_set():
            self._pump(0.2)
            try:
                job = self._jobs.get_nowait()
            except Empty:
                continue
            try:
                job.result.put(job.fn(self) if job.fn else self._execute(job.command))
            except Exception as exc:                      # komut hatasi UI'yi dusurmesin
                job.result.put({"ok": False, "text": t("cmd_error", err=exc)})

    # ---------------------------------------------------------------- mesaj pompasi
    # -------------------------------------------------------- injected faults
    # A scenario may declare that the link to the ground station is interrupted
    # or lossy (see faults.py). Both are implemented here, in exactly two
    # places, and both are simulation-only in the strongest sense available:
    # nothing below writes to the vehicle, and the fault is a flag in this
    # process that a `finally` in the runner always clears.
    #
    # WHY SUPPRESSING THE HEARTBEAT IS THE WHOLE MECHANISM
    # ----------------------------------------------------
    # ArduPilot's GCS failsafe keys on `sysid_mygcs_seen`, which is called from
    # exactly three handlers: HEARTBEAT, RC_CHANNELS_OVERRIDE and
    # MANUAL_CONTROL (ardupilot/libraries/GCS_MAVLink/GCS_Common.cpp). ArgazUI
    # sends the first two and never the third, so withholding them is a
    # complete model of "the ground station went away" rather than an
    # approximation of one. A parameter read issued while the fault is active
    # would still leave this process — it just does not reset the failsafe
    # timer, and no step runs inside a fault window in any case.

    def set_link_fault(self, drop_one_in: int = 1, block_tx: bool = False) -> None:
        """Degrade this link deterministically. Only `faults.py` calls this.

        `drop_one_in` counts RECEIVED messages: 1 discards every one, 2 every
        second, and so on. It is a count and not a probability so that two runs
        of the same scenario lose the same packets.
        """
        self._link_fault = {"drop_one_in": max(1, int(drop_one_in)),
                            "block_tx": bool(block_tx)}
        self._rx_seen = self._rx_dropped = 0
        self.emit("link_fault", state="applied", **self._link_fault)

    def clear_link_fault(self) -> dict:
        """Restore normal behaviour and report what the fault actually did."""
        record = {"received": self._rx_seen, "discarded": self._rx_dropped,
                  **(self._link_fault or {})}
        self._link_fault = None
        self.emit("link_fault", state="cleared", **record)
        return record

    @property
    def link_fault(self) -> Optional[dict]:
        return dict(self._link_fault) if self._link_fault else None

    def _drop_received(self) -> bool:
        """Is this received message discarded by an injected link fault?"""
        if not self._link_fault:
            return False
        self._rx_seen += 1
        if self._rx_seen % self._link_fault["drop_one_in"] == 0:
            self._rx_dropped += 1
            return True
        return False

    def _tx_blocked(self) -> bool:
        return bool(self._link_fault and self._link_fault["block_tx"])

    def _pump(self, seconds: float) -> None:
        """Gelen mesajlari okuyup arac durumunu gunceller."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            self._housekeeping()
            msg = self._conn.recv_match(blocking=True, timeout=0.05)
            if msg is None:
                break
            # Read and thrown away rather than left in the socket: a link that
            # is down does not queue traffic up for later, and delivering a
            # burst of stale state the moment the fault clears would make the
            # recovery criteria judge the wrong instant.
            if not self._drop_received():
                self._absorb(msg)
        if self.state.connected and time.time() - self.state.last_heartbeat > 5:
            self.state.connected = False

    def _housekeeping(self) -> None:
        """Her okuma dongusunde: GCS heartbeat'i ve RC override tazelemesi.

        Ikisi de "gondermeyi birakirsan otopilot davranisini degistirir"
        turunden; bu yuzden mesaj pompasinin icinde, her bekleyisin altinda
        calisiyorlar.
        """
        if self._tx_blocked():
            # An injected interruption. Both suppressed items are precisely the
            # ones ArduPilot counts as contact from its ground station, so this
            # branch is the fault rather than a side effect of it.
            return
        now = time.time()
        if now - self._hb_last_sent >= GCS_HEARTBEAT_INTERVAL:
            try:
                self._conn.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_GCS,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            except Exception:
                pass
            self._hb_last_sent = now
        if self._rc_overrides and now - self._rc_last_sent >= self.keepalive_interval():
            self._rc_send_current()
        if self.state.connected and now - self._state_sampled >= EVENT_STATE_INTERVAL:
            self._state_sampled = now
            self.emit("state", **self.state.as_dict())

    def _request_streams(self) -> None:
        """Telemetri akislarini ister (ilk heartbeat'ten sonra, bir kez).

        MAVProxy'li yolda akislari MAVProxy istiyordu ve ArgazUI onun 14550
        ciktisini dinledigi icin sorun gorunmuyordu. MAVProxy'siz baglanan
        testlerde ArduCopter irtifayi hic yollamadi: kalkis gercekten oldugu
        halde GLOBAL_POSITION_INT gelmedigi icin "alt=0.0" gorunuyordu.
        Kabul kriterleri olculen duruma dayandigina gore o durumun akmasini
        istemek de bu modulun isi.
        """
        if self._streams_requested:
            return
        try:
            self._conn.mav.request_data_stream_send(
                *self._target(), mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
            # ATTITUDE (EXTRA1) faster than the rest — see ATTITUDE_STREAM_HZ.
            # Asked for after STREAM_ALL so it wins on the overlapping stream.
            self._conn.mav.request_data_stream_send(
                *self._target(), mavutil.mavlink.MAV_DATA_STREAM_EXTRA1,
                ATTITUDE_STREAM_HZ, 1)
            self._streams_requested = True
        except Exception:
            pass

    def _rc_send_current(self) -> None:
        chans = [0] * 18            # 0 = bu kanalda override yok
        for ch, pwm in self._rc_overrides.items():
            chans[ch - 1] = int(pwm)
        self._conn.mav.rc_channels_override_send(*self._target(), *chans)
        self._rc_last_sent = time.time()

    def _absorb(self, msg) -> None:
        t = msg.get_type()
        if t == "HEARTBEAT":
            # Yer istasyonlarinin kendi heartbeat'ini arac sanmayalim
            # (MAVProxy'ninki ve GCS_HEARTBEAT_INTERVAL ile bizim gonderdigimiz).
            if (msg.get_srcComponent() == mavutil.mavlink.MAV_COMP_ID_MISSIONPLANNER
                    or msg.type == mavutil.mavlink.MAV_TYPE_GCS):
                return
            was_connected, was_mode = self.state.connected, self.state.mode
            was_armed = self.state.armed
            self.state.connected = True
            # Monotonic, unlike `connected`: once the vehicle has identified
            # itself, `armed` and `mode` are measurements rather than defaults,
            # and they stay measurements across a blackout.
            self.state.heartbeat_known = True
            self.state.last_heartbeat = time.time()
            self._request_streams()
            self.state.sysid = msg.get_srcSystem()
            self.state.mode = self._mode_name(msg.custom_mode, msg)
            self.state.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            # Degisimleri kosu kaydina yaz. Otopilotun KENDI degistirdigi mod
            # (failsafe, gorev sonu) da boylece kayda giriyor — sadece bizim
            # gonderdiklerimiz degil.
            if not was_connected:
                self.emit("connected", sysid=self.state.sysid, mode=self.state.mode)
            if self.state.mode != was_mode:
                self._note_mode_change()
                self.emit("mode", mode=self.state.mode, previous=was_mode,
                          alt=round(self.state.alt, 1))
            if self.state.armed != was_armed:
                self.emit("armed" if self.state.armed else "disarmed",
                          mode=self.state.mode, alt=round(self.state.alt, 1))
        elif t == "ATTITUDE":
            self.state.roll = math.degrees(msg.roll)
            self.state.pitch = math.degrees(msg.pitch)
            self.state.yaw = math.degrees(msg.yaw)
            self.state.roll_rate = math.degrees(msg.rollspeed)
            self.state.pitch_rate = math.degrees(msg.pitchspeed)
            self.state.yaw_rate = math.degrees(msg.yawspeed)
            self.state.attitude_known = True
            self._note_vehicle_clock(getattr(msg, "time_boot_ms", 0) / 1000.0)
            self.stability.add(getattr(msg, "time_boot_ms", 0) / 1000.0,
                               self.state.roll, self.state.pitch,
                               (self.state.roll_rate, self.state.pitch_rate,
                                self.state.yaw_rate))
        elif t == "GLOBAL_POSITION_INT":
            self.state.alt = msg.relative_alt / 1000.0
            self.state.position_known = True
        elif t == "VFR_HUD":
            self.state.groundspeed = msg.groundspeed
            self.state.climb = msg.climb
            self.state.vfr_known = True
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
                self.emit("statustext", severity=int(getattr(msg, "severity", 6)),
                          text=text)

        # Mirrored last, and from here rather than from the receive loop, so it
        # sees exactly what the link itself accepted: the ground-station
        # heartbeats filtered out at the top of this method have already
        # returned, and a plot of "the vehicle" does not get MAVProxy's own
        # HEARTBEAT overwriting the aircraft's mode with a GCS's zero.
        self.mirror.send(msg)

    # ------------------------------------------------------------- vehicle clock
    # How long a measurement window must be before it is believed. Short
    # windows are dominated by the bursts telemetry arrives in.
    SPEEDUP_WINDOW = 5.0

    def _note_mode_change(self, vehicle_s: Optional[float] = None) -> None:
        """Record that the mode moved, on the vehicle's own clock.

        Called from `_absorb` whenever a heartbeat reports a different mode —
        including the ones the vehicle makes on its own during start-up, which
        is the entire point. `mode_settled` then answers whether it has been
        still long enough for a mode command to survive.
        """
        when = vehicle_s if vehicle_s is not None else self.state.vehicle_clock_s
        self.state.mode_changed_at_s = when
        if vehicle_s is not None:
            self.state.vehicle_clock_s = max(self.state.vehicle_clock_s, vehicle_s)

    def _note_vehicle_clock(self, vehicle_s: float) -> None:
        """Measure how fast simulated time runs, from the vehicle's own clock.

        Nothing tells a ground station the SITL speedup — it is a command-line
        argument to a process ArgazUI only sees the output of. But the vehicle
        timestamps its own telemetry, so the ratio between that clock and ours
        IS the speedup, and it is the number the RC keepalive needs.
        """
        if vehicle_s <= 0:
            return
        # Kept as state, not only as a speedup reference: temporal acceptance
        # criteria (`within`, `for`, `never`) are measured on this clock, so
        # "10 seconds" means the same at speedup 1 and speedup 10.
        self.state.vehicle_clock_s = vehicle_s
        now = time.time()
        if self._clock_ref is None:
            self._clock_ref = (now, vehicle_s)
            return
        wall_before, vehicle_before = self._clock_ref
        wall_delta = now - wall_before
        vehicle_delta = vehicle_s - vehicle_before
        if wall_delta >= self.SPEEDUP_WINDOW and vehicle_delta > 0:
            self._speedup = vehicle_delta / wall_delta
            self._clock_ref = (now, vehicle_s)      # slide, do not accumulate

    @property
    def speedup(self) -> float:
        """Measured ratio of simulated time to wall-clock time (1.0 until known)."""
        return self._speedup

    def keepalive_interval(self) -> float:
        """Wall-clock seconds between refreshes of a held RC override."""
        return keepalive_interval(self._rc_override_time, self._speedup)

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
            self._housekeeping()
            msg = self._conn.recv_match(blocking=True, timeout=0.2)
            if msg is None:
                continue
            if self._drop_received():
                # Dropped before it is looked at, including by `match_fn`: a
                # message the link did not receive cannot satisfy a wait.
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

    def submit(self, fn: Callable[["MavlinkLink"], dict], timeout: float,
               label: str = "step") -> dict:
        """Bir prosedur adimini worker thread'inde calistirir.

        Tum pymavlink erisimi tek thread'de kalmali; prosedur motoru da bu
        yuzden adimlarini komut kuyruguna veriyor. Adim icindeki bekleyisler
        `_recv_until` uzerinden gittigi icin mesaj pompasi durmuyor: arac
        durumu ve RC keepalive'i adim boyunca akmaya devam ediyor.
        """
        if not self._thread or not self._thread.is_alive():
            return {"ok": False, "text": t("no_link")}
        job = _Job(fn=fn)
        self._jobs.put(job)
        try:
            return job.result.get(timeout=timeout + 10.0)
        except Empty:
            return {"ok": False, "text": t("cmd_timeout", cmd=label)}

    def is_running(self) -> bool:
        """Is the link's worker thread alive? (i.e. has START been pressed)"""
        return bool(self._thread and self._thread.is_alive())

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
        self._rc_overrides[ch] = int(trim)
        self._rc_send_current()
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
        label = "ARM" if arm else "DISARM"
        res = self._await_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, label)
        if not res["ok"]:
            return res
        # ACK basari sayilmaz — heartbeat'in armed bayragi degisene kadar bekle.
        # HEARTBEAT 1 Hz gelirken ACK aninda donuyor; bunu beklemeden donunce
        # `state.armed` bayat kaliyordu ve prosedurdeki `when: {armed: false}`
        # kosulu, arm BASARILI olmasina ragmen dogru sanilip ZORLA arm adimini
        # da calistiriyordu (Swan-K1 / SkyCat kosusunda gorulduldu).
        flag = mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        hb = self._recv_until(
            lambda m: (m.get_type() == "HEARTBEAT"
                       and m.get_srcComponent() != mavutil.mavlink.MAV_COMP_ID_MISSIONPLANNER
                       and m.type != mavutil.mavlink.MAV_TYPE_GCS
                       and bool(m.base_mode & flag) == arm),
            timeout=5.0,
        )
        if hb is None:
            return {"ok": False, "text": t("arm_state_unconfirmed", label=label)}
        return res

    def _do_arm(self, args, arm: bool, recover: bool = True) -> dict:
        """ARM/DISARM.

        `recover=False` iken v1.0'dan gelen otomatik kurtarma (RC ortalama,
        ivmeolcer kalibrasyonu, gecici redlerde yeniden deneme) atlanir.
        Prosedurler bunu, "once normal arm dene, olmazsa ZORLA" gibi kendi
        yedegini kuran adimlarda kullaniyor — orada ikinci bir kurtarma
        turu sadece bekleme suresini uzatirdi.
        """
        force = any(a.lower() == "force" for a in args)
        res = self._send_arm(arm, force)
        if res["ok"] or not arm or not recover:
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
            # Kosuya ozel her parametre yazimi kayda gecer; boylece run
            # dizinindeki olay akisi hangi degerin ne zaman degistigini soyler.
            self.emit("param_set", name=name, value=msg.param_value)
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
        return self._do_rc_channels({chan: pwm})

    # ---------------------------------------------------------------- prosedur ilkelleri
    # Asagidakiler prosedur motorunun (procrunner.py) worker thread'inde
    # cagirdigi ilkeller. Hepsi `submit()` uzerinden gelir, yani pymavlink
    # baglantisina dokunmalari guvenlidir.
    def _do_rc_channels(self, channels: dict) -> dict:
        """Verilen kanallari override eder; digerlerine dokunmaz.

        Override'lar `_rc_keepalive` tarafindan tazelenir, cunku ArduPilot
        RC_OVERRIDE_TIME (varsayilan 3 sn) sonunda gercek kumandaya doner.
        """
        for ch, pwm in channels.items():
            ch, pwm = int(ch), int(pwm)
            if not 1 <= ch <= 18:
                return {"ok": False, "text": t("rc_range")}
            self._rc_overrides[ch] = pwm
        # Read once, here rather than at connect: this is the first moment the
        # answer changes anything, and a model's parameter file may have moved
        # it away from the 3.0 s default.
        if self._rc_override_time is None:
            self._rc_override_time = self._param_get(RC_OVERRIDE_TIME_PARAM,
                                                     timeout=3.0)
        self._rc_send_current()
        shown = ", ".join(f"RC{c}={p}" for c, p in sorted(channels.items()))
        return {"ok": True, "text": t("rc_override_ok", channels=shown)}

    def _do_rc_release(self) -> dict:
        """Tum override'lari birakir (0 = bu kanalda override yok)."""
        had = bool(self._rc_overrides)
        self._rc_overrides.clear()
        self._conn.mav.rc_channels_override_send(*self._target(), *([0] * 18))
        self._rc_last_sent = time.time()
        return {"ok": True, "text": t("rc_released") if had else t("rc_nothing_held")}

    def _do_send_command(self, command_id: int, ctype: str, frame: Optional[int],
                         params: dict, accept: list[int], label: str) -> dict:
        sys_id, comp_id = self._target()
        p = {f"p{i}": float(params.get(f"p{i}", 0) or 0) for i in range(1, 8)}
        if ctype == "int":
            self._conn.mav.command_int_send(
                sys_id, comp_id, frame if frame is not None else 0, command_id, 0, 0,
                p["p1"], p["p2"], p["p3"], p["p4"],
                int(float(params.get("x", 0) or 0)), int(float(params.get("y", 0) or 0)),
                float(params.get("z", 0) or 0),
            )
        else:
            self._conn.mav.command_long_send(
                sys_id, comp_id, command_id, 0,
                p["p1"], p["p2"], p["p3"], p["p4"], p["p5"], p["p6"], p["p7"],
            )
        return self._await_ack(command_id, label, accept=accept)

    def _do_upload_mission(self, items: list[dict]) -> dict:
        """Gorev listesini araca yukler (MISSION_COUNT -> REQUEST -> ITEM_INT -> ACK).

        Sifirinci madde ArduPilot'ta EV konumudur; gercek maddeler 1'den baslar,
        bu yuzden listenin basina ev icin bir yer tutucu koyuyoruz.
        """
        count = len(items) + 1
        self._conn.mav.mission_count_send(
            *self._target(), count, mavutil.mavlink.MAV_MISSION_TYPE_MISSION)

        deadline = time.time() + 30.0
        while time.time() < deadline:
            req = self._recv_until(
                lambda m: m.get_type() in ("MISSION_REQUEST", "MISSION_REQUEST_INT",
                                           "MISSION_ACK"),
                timeout=5.0,
            )
            if req is None:
                return {"ok": False, "text": t("mission_no_request")}
            if req.get_type() == "MISSION_ACK":
                if req.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    return {"ok": True, "text": t("mission_uploaded", count=len(items))}
                name = mavutil.mavlink.enums["MAV_MISSION_RESULT"][req.type].name
                return {"ok": False, "text": t("mission_rejected", result=name)}

            seq = req.seq
            # seq 0 = ev konumu; araca kendi evini geri veriyoruz.
            item = {"command": mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    "frame": mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT} \
                if seq == 0 else items[seq - 1]
            self._conn.mav.mission_item_int_send(
                *self._target(), seq,
                int(item.get("frame", mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT)),
                int(item["command"]),
                1 if seq == 0 else 0, 1,
                float(item.get("p1", 0) or 0), float(item.get("p2", 0) or 0),
                float(item.get("p3", 0) or 0), float(item.get("p4", 0) or 0),
                int(float(item.get("x", 0) or 0) * 1e7),
                int(float(item.get("y", 0) or 0) * 1e7),
                float(item.get("z", 0) or 0),
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        return {"ok": False, "text": t("mission_timeout")}

    def _await_ack(self, command_id: int, label: str,
                   accept: Optional[list[int]] = None) -> dict:
        accept = accept or [mavutil.mavlink.MAV_RESULT_ACCEPTED]
        sent_at = time.time() - 3.0        # komut oncesi uyarilari da yakala
        ack = self._recv_until(
            lambda m: m.get_type() == "COMMAND_ACK" and m.command == command_id,
            timeout=10.0,
        )
        if ack is None:
            self.emit("command_ack", command=label, result="NO_ACK", accepted=False)
            return {"ok": False, "text": t("ack_missing", label=label)}
        if ack.result in accept:
            self.emit("command_ack", command=label, accepted=True,
                      result=mavutil.mavlink.enums["MAV_RESULT"][ack.result].name)
            return {"ok": True, "text": t("ack_accepted", label=label)}

        result_name = mavutil.mavlink.enums["MAV_RESULT"][ack.result].name
        self.emit("command_ack", command=label, result=result_name, accepted=False)
        # Gerekce STATUSTEXT'i cogu zaman ACK'ten hemen SONRA gelir; bekleyelim.
        self._recv_until(lambda m: False, timeout=1.5)
        reasons = self._recent_reasons(sent_at)
        text = t("ack_rejected", label=label, result=result_name)
        if reasons:
            text += " — otopilot: " + " | ".join(reasons)
        else:
            text += t("reason_unknown")
        return {"ok": False, "text": text}
