"""Launch a real ArduPilot SITL binary for a test.

NO MOCK, EVER
-------------
The point of this suite is that a green test means a working button, so there
is no simulated autopilot anywhere in it. This module starts the same
`arducopter` / `arduplane` binary the user flies and talks to it over MAVLink.
If the binary is missing the test is *skipped* and the model is reported as
`untested` — never as passing.

WHY NOT sim_vehicle.py
----------------------
`sim_vehicle.py` builds, launches MAVProxy, opens a console and a map. A test
wants none of that, and MAVProxy in particular would put a second GCS on the
link. The binary is launched directly with the same arguments sim_vehicle.py
would compute, read out of ArduPilot's own `pysim/vehicleinfo.json` so the
frame-to-defaults mapping cannot drift from upstream.

PROCESS CLEANUP
---------------
Same rule as the rest of the project: never match on a process name. Each SITL
runs in its own session (`start_new_session=True`) and is terminated by
process group, so a stray `pkill -f arduplane` can never take out an unrelated
process — or the test runner itself.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from argazui import paths

# SITL's serial0 is a TCP server on this port, plus 10 per instance
# (ardupilot/libraries/AP_HAL_SITL/SITL_State.cpp).
BASE_TCP_PORT = 5760

# Wall-clock seconds to wait for the first heartbeat and for pre-arm health.
CONNECT_TIMEOUT = 90.0
PREARM_TIMEOUT = 180.0

# Faster than real time so the suite fits in a CI budget. Kept at 5 rather
# than 10 because RC overrides expire after RC_OVERRIDE_TIME (3 vehicle
# seconds): at speedup 10 the keepalive margin gets uncomfortably thin, and a
# VTOL takeoff that silently loses its throttle stick would look like a
# procedure bug. Override with ARGAZ_TEST_SPEEDUP.
DEFAULT_SPEEDUP = float(os.environ.get("ARGAZ_TEST_SPEEDUP", "5"))


class SitlUnavailable(Exception):
    """The binary or its default parameters are not present — skip, don't fail."""


def autotest_dir() -> Path:
    return paths.ARDUPILOT / "Tools" / "autotest"


def _vehicle_info() -> dict:
    path = autotest_dir() / "pysim" / "vehicleinfo.json"
    if not path.is_file():
        raise SitlUnavailable(f"ArduPilot frame table not found at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SitlUnavailable(f"cannot read {path}: {exc}") from exc


def binary_for(vehicle: str) -> Path:
    """The built SITL executable, or a skip reason."""
    name = {"ArduCopter": "arducopter", "ArduPlane": "arduplane"}.get(vehicle)
    if name is None:
        raise SitlUnavailable(f"no SITL binary is known for vehicle {vehicle!r}")
    for candidate in (paths.ARDUPILOT / "build" / "sitl" / "bin" / name,
                      paths.ARDUPILOT / vehicle / name):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise SitlUnavailable(
        f"{name} is not built. Run ./waf configure --board sitl && ./waf "
        f"{name.replace('ardu', '')} in {paths.ARDUPILOT}")


def frame_options(vehicle: str, frame: str) -> dict:
    """Resolves a frame the way sim_vehicle.py does, from upstream's own table."""
    info = _vehicle_info()
    frames = (info.get(vehicle) or {}).get("frames") or {}
    entry = frames.get(frame)
    if entry is None:
        # Upstream matches a prefix when the exact frame is absent; mirror it
        # rather than reimplementing a guess.
        for prefix in ("quadplane", "plane-elevon", "plane-vtail", "plane",
                       "octa", "tri", "y6", "heli", "hexa"):
            if frame.startswith(prefix) and prefix in frames:
                entry = frames[prefix]
                break
    if entry is None:
        raise SitlUnavailable(f"{vehicle} has no SITL frame called {frame!r}")
    resolved = dict(entry)
    resolved.setdefault("model", frame)
    return resolved


def default_param_files(frame: dict) -> list[Path]:
    names = frame.get("default_params_filename") or []
    if isinstance(names, str):
        names = [names]
    out = []
    for name in names:
        path = autotest_dir() / name
        if not path.is_file():
            raise SitlUnavailable(f"default parameter file missing: {path}")
        out.append(path)
    return out


def _free_instance(start: int = 0, limit: int = 12) -> int:
    """An instance number whose TCP port nothing is listening on."""
    for instance in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", BASE_TCP_PORT + 10 * instance)) != 0:
                return instance
    raise SitlUnavailable("no free SITL instance port in range")


@dataclass
class Sitl:
    """A running SITL process and the connection string that reaches it."""

    vehicle: str
    frame: str
    work_dir: Path
    instance: int
    process: subprocess.Popen
    log: Path
    speedup: float
    extra_params: list[Path] = field(default_factory=list)

    @property
    def connection(self) -> str:
        return f"tcp:127.0.0.1:{BASE_TCP_PORT + 10 * self.instance}"

    def alive(self) -> bool:
        return self.process.poll() is None

    def tail(self, lines: int = 25) -> str:
        try:
            return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no SITL output captured)"

    def stop(self) -> None:
        """SIGINT then SIGTERM then SIGKILL, by process group.

        The graceful signals matter: SITL closes and flushes its dataflash log
        on shutdown, and a test that asserts on the `.BIN` needs that to have
        happened.
        """
        if self.process.poll() is not None:
            return
        pgid = os.getpgid(self.process.pid)
        for sig, wait in ((signal.SIGINT, 5.0), (signal.SIGTERM, 3.0),
                          (signal.SIGKILL, 2.0)):
            try:
                os.killpg(pgid, sig)
            except (ProcessLookupError, PermissionError):
                return
            try:
                self.process.wait(timeout=wait)
                return
            except subprocess.TimeoutExpired:
                continue


def start(vehicle: str, frame: str, work_dir: Path,
          speedup: float = DEFAULT_SPEEDUP,
          extra_params: Optional[list[Path]] = None,
          home: Optional[str] = None) -> Sitl:
    """Boots one SITL instance in `work_dir` and returns a handle to it.

    `-w` wipes the simulated eeprom so every test starts from the frame's
    documented defaults rather than from whatever a previous run happened to
    leave behind.
    """
    binary = binary_for(vehicle)
    frame_info = frame_options(vehicle, frame)
    defaults = default_param_files(frame_info) + list(extra_params or [])

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    instance = _free_instance()

    command = [
        str(binary),
        "--model", str(frame_info["model"]),
        "--speedup", str(speedup),
        f"-I{instance}",
        "-w",
    ]
    if defaults:
        command += ["--defaults", ",".join(str(p) for p in defaults)]
    if home:
        command += ["--home", home]

    log = work_dir / "sitl.log"
    handle = log.open("wb")
    process = subprocess.Popen(command, cwd=str(work_dir), stdout=handle,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               start_new_session=True)
    (work_dir / "sitl_command.txt").write_text(" ".join(command) + "\n", encoding="utf-8")

    sitl = Sitl(vehicle=vehicle, frame=frame, work_dir=work_dir, instance=instance,
                process=process, log=log, speedup=speedup,
                extra_params=list(extra_params or []))

    # Wait for the TCP port rather than sleeping a fixed amount: on a loaded
    # CI runner the binary can take several seconds to open it.
    deadline = time.time() + 30
    while time.time() < deadline:
        if not sitl.alive():
            raise SitlUnavailable(f"SITL exited immediately:\n{sitl.tail()}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", BASE_TCP_PORT + 10 * instance)) == 0:
                return sitl
        time.sleep(0.5)
    sitl.stop()
    raise SitlUnavailable(
        f"SITL did not open {sitl.connection} within 30 s:\n{sitl.tail()}")
