"""Terminal oturumu ve surec grubu yonetimi.

SUREC TEMIZLIGI KURALI
----------------------
`pkill -f <isim>` ASLA kullanilmaz. Onceki bir oturumda pkill'in wrapper
script'in kendi komut satirini eslestirip yanlis sureci oldurdugu bir hata
yasandi. Bunun yerine:

  * pty icindeki bash `start_new_session=True` ile ayri bir OTURUM (session)
    icinde baslatilir; boylece ArgazUI sunucusundan tamamen izole olur.
  * Durdururken /proc taranarak bu oturuma (SID) ait TUM surec gruplari
    bulunur ve `os.killpg` ile grup grup sonlandirilir.
  * Eslesme isimle degil, cekirdegin bildirdigi SID/PGID ile yapilir —
    yanlis sureci oldurmesi mumkun degildir.
"""
from __future__ import annotations

import errno
import fcntl
import os
import pty
import shlex
import signal
import struct
import subprocess
import termios
import threading
import time
from typing import Callable, Optional

from . import paths
from .i18n import t

VEHICLE_DIR = {"ArduCopter": "ArduCopter", "ArduPlane": "ArduPlane"}


# --------------------------------------------------------------------------- /proc
def _proc_stat(pid: int) -> Optional[tuple[int, int]]:
    """(pgid, sid) dondurur. comm alani parantez/bosluk icerebildigi icin
    ')' karakterinin son gorunumunden sonrasi ayristirilir."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            data = fh.read().decode("utf-8", "replace")
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None
    close = data.rfind(")")
    if close == -1:
        return None
    fields = data[close + 2:].split()
    if len(fields) < 4:
        return None
    try:
        return int(fields[2]), int(fields[3])   # pgrp, session
    except ValueError:
        return None


def pgids_in_session(sid: int, exclude_pgid: int) -> list[int]:
    """Verilen oturumdaki (exclude_pgid disindaki) tum surec gruplarini bulur."""
    found: set[int] = set()
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        st = _proc_stat(int(entry))
        if st is None:
            continue
        pgid, psid = st
        if psid == sid and pgid != exclude_pgid and pgid > 0:
            found.add(pgid)
    return sorted(found)


def _pgid_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# --------------------------------------------------------------------------- komutlar
def build_launch_commands(model: dict) -> list[str]:
    """Bir model tanimindan, terminale yazilacak kabuk komutlarini uretir.

    Komutlar kullanicinin elle yazacagi seyin AYNISI — terminalde gorunurler.
    """
    env_file = paths.ARGAZ / model.get("env", "env.sh")
    lines = [f"source {shlex.quote(str(env_file))}"]

    method = model["method"]
    if method == "ros2_launch":
        ros2 = model.get("ros2") or {}
        parts = ["ros2", "launch", ros2["package"], ros2["launch_file"], *ros2.get("args", [])]
        lines.append(" ".join(parts))
        return lines

    world = model.get("world")
    if world:
        lines.append(f"gz sim -v4 -r {world} &")
        lines.append("sleep 6")

    vehicle = model.get("vehicle") or "ArduPlane"

    # SITL'i ArgazUI'ye ait bir calisma klasorunde kosturuyoruz:
    #   * eeprom.bin / logs / terrain ardupilot agacina yazilmaz (salt-okunur kalir)
    #   * her model kendi eeprom'una sahip olur, birbirlerinin ayarini bozmaz
    #   * Lua gerektiren modeller icin scripts/ klasorunu buraya koyabiliyoruz
    rundir = paths.RUN_DIR / model["id"]
    lua = model.get("lua_scripts") or []
    if lua:
        lines.append(f"mkdir -p {shlex.quote(str(rundir / 'scripts'))}")
        for name in lua:
            src = paths.SITL_MODELS_SCRIPTS / name
            lines.append(f"cp -f {shlex.quote(str(src))} "
                         f"{shlex.quote(str(rundir / 'scripts'))}/")
    else:
        lines.append(f"mkdir -p {shlex.quote(str(rundir))}")
    lines.append(f"cd {shlex.quote(str(rundir))}")

    sitl = ["sim_vehicle.py", "-v", vehicle]
    if model.get("frame"):
        sitl += ["-f", model["frame"]]
    sitl += ["--model", "JSON"]
    if model.get("param_file"):
        # $SITL_MODELS quadplane_env.sh tarafindan export ediliyor
        sitl.append(f"--add-param-file={model['param_file']}")

    # SITL'e ozel parametre duzeltmeleri. Bazi model param dosyalari gercek bir
    # ucus kontrolcusunden alinmis dokumler ve SITL'de celiskili kaliyor
    # (ornek: Swan-K1 AHRS_EKF_TYPE=3 istiyor ama EK3_ENABLE=0 birakiyor).
    # EK3_ENABLE gibi parametreler ancak ACILISTA uygulanabildigi icin ikinci
    # bir param dosyasi olarak veriyoruz — modelin kendi dosyasi degismiyor.
    overrides = model.get("sitl_param_overrides") or {}
    if overrides:
        ovr_path = rundir / "argazui_overrides.parm"
        ovr_path.parent.mkdir(parents=True, exist_ok=True)
        body = ["# ArgazUI tarafindan uretildi — SITL uyumluluk duzeltmeleri.",
                f"# Model: {model['id']}",
                "# Bu dosyayi elle duzenleme; kaynak config/models.json ->",
                "# ilgili modelin 'sitl_param_overrides' alani.", ""]
        for key, val in overrides.items():
            body.append(f"{key.upper()},{val}")
        ovr_path.write_text("\n".join(body) + "\n")
        sitl.append(f"--add-param-file={ovr_path}")
    sitl += model.get("extra_sitl_args", [])
    sitl += ["--console", "--map"]
    # 14550 sim_vehicle.py'nin varsayilan cikisi (ArgazUI kullanir),
    # 14551'i gorev scriptleri icin biz ekliyoruz.
    sitl += ["--out", f"127.0.0.1:{paths.SCRIPT_MAVLINK_PORT}"]
    lines.append(" ".join(sitl))
    return lines


# --------------------------------------------------------------------------- terminal
class TerminalSession:
    """Kalici, etkilesimli bir pty + bash oturumu."""

    def __init__(self, on_output: Callable[[bytes], None]):
        self.on_output = on_output
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.sid: Optional[int] = None
        self.shell_pgid: Optional[int] = None
        self._reader: Optional[threading.Thread] = None
        self._alive = threading.Event()

    # -- yasam dongusu -----------------------------------------------------
    def start(self, rows: int = 30, cols: int = 110) -> None:
        if self.is_alive():
            return
        master, slave = pty.openpty()
        self._set_size(master, rows, cols)

        def _become_session_leader():
            # start_new_session zaten setsid() cagiriyor; pty'yi kontrol
            # terminali yapmak is kontrolu (job control) icin gerekli.
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["ARGAZUI"] = "1"
        # Gorev scriptlerinin kullanabilecegi baglanti bilgisi
        env["ARGAZ_MAVLINK_SCRIPT_PORT"] = str(paths.SCRIPT_MAVLINK_PORT)

        self.proc = subprocess.Popen(
            ["/bin/bash", "-i"],
            stdin=slave, stdout=slave, stderr=slave,
            cwd=str(paths.ARGAZ),
            env=env,
            start_new_session=True,
            preexec_fn=_become_session_leader,
        )
        os.close(slave)
        self.master_fd = master
        self.sid = self.proc.pid          # setsid sonrasi SID == PID
        self.shell_pgid = self.proc.pid
        self._alive.set()
        self._reader = threading.Thread(target=self._read_loop, name="pty-reader", daemon=True)
        self._reader.start()

    def is_alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def _read_loop(self) -> None:
        while self._alive.is_set() and self.master_fd is not None:
            try:
                data = os.read(self.master_fd, 65536)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):
                    break
                continue
            if not data:
                break
            try:
                self.on_output(data)
            except Exception:
                pass
        self._alive.clear()

    # -- giris/cikis -------------------------------------------------------
    def write(self, data: str) -> None:
        if self.master_fd is None:
            return
        os.write(self.master_fd, data.encode("utf-8", "replace"))

    def run_line(self, line: str) -> None:
        """Bir komutu 'kullanici yazmis gibi' terminale gonderir."""
        self.write(line.rstrip("\n") + "\n")

    def notice(self, text: str) -> None:
        """ArgazUI'nin kendi mesajini terminal akisina basar (kabuga gitmez)."""
        self.on_output(f"\r\n\x1b[36m[ArgazUI]\x1b[0m {text}\r\n".encode())

    @staticmethod
    def _set_size(fd: int, rows: int, cols: int) -> None:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def resize(self, rows: int, cols: int) -> None:
        if self.master_fd is not None:
            try:
                self._set_size(self.master_fd, rows, cols)
            except OSError:
                pass

    # -- surec temizligi ---------------------------------------------------
    def stop_children(self, log: Optional[Callable[[str], None]] = None) -> list[int]:
        """Bu terminal oturumundaki tum alt surec gruplarini sonlandirir.

        SIGINT (Ctrl+C esdegeri) -> SIGTERM -> SIGKILL sirasi izlenir.
        Kabugun kendi surec grubuna dokunulmaz.
        """
        log = log or (lambda s: None)
        if self.sid is None or self.shell_pgid is None:
            return []

        targets = pgids_in_session(self.sid, exclude_pgid=self.shell_pgid)
        if not targets:
            log(t("nothing_to_stop"))
            return []

        log(t("terminating", groups=", ".join(map(str, targets))))
        killed = list(targets)

        for sig, wait_s, name in ((signal.SIGINT, 6.0, "SIGINT"),
                                  (signal.SIGTERM, 4.0, "SIGTERM"),
                                  (signal.SIGKILL, 2.0, "SIGKILL")):
            targets = [p for p in targets if _pgid_alive(p)]
            if not targets:
                break
            for pgid in targets:
                try:
                    os.killpg(pgid, sig)
                except (ProcessLookupError, PermissionError):
                    pass
            log(t("signal_sent", signal=name, groups=", ".join(map(str, targets))))
            deadline = time.time() + wait_s
            while time.time() < deadline:
                if not any(_pgid_alive(p) for p in targets):
                    break
                time.sleep(0.2)

        remaining = [p for p in pgids_in_session(self.sid, self.shell_pgid) if _pgid_alive(p)]
        if remaining:
            log(t("still_running", groups=remaining))
        else:
            log(t("all_closed"))
        return killed

    def close(self) -> None:
        """Terminali tamamen kapatir (once cocuklar, sonra kabuk)."""
        self.stop_children()
        self._alive.clear()
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.shell_pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, TypeError):
                pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.shell_pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, TypeError):
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self.proc = None
