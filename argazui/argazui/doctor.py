"""Installation diagnostics for ArgazUI.

The doctor is deliberately observational: it never installs packages, creates
upstream directories, or starts a simulator.  Its output is suitable for both
humans and automation through ``argazui doctor --json``.
"""
from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from . import paths


@dataclass
class Check:
    name: str
    ok: bool
    critical: bool
    detail: str
    fix: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _path_check(name: str, path: Path, *, critical: bool, description: str) -> Check:
    if path.is_dir() or path.is_file():
        return Check(name, True, critical, f"{description}: {path}")
    return Check(name, False, critical, f"{description} not found: {path}",
                 "Set the matching value in argaz.toml, an ARGAZ_* environment variable, or a CLI option.")


def _binary(name: str, candidates: list[Path]) -> Check:
    found = next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)
    if found is None:
        shown = ", ".join(str(p) for p in candidates)
        return Check(f"sitl_{name}", False, True, f"{name} SITL binary not found ({shown})",
                     "Build it with ./waf configure --board sitl && ./waf " + name + ".")
    try:
        result = subprocess.run([str(found), "--help"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=10, check=False)
        # SITL's option parser deliberately exits 1 for --help on several
        # ArduPilot releases. Seeing its complete option banner still proves
        # this executable starts on the present host; requiring exit 0 would
        # label a working SITL as broken.
        if result.returncode == 0 or "Options:" in result.stdout:
            first = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "responded")
            suffix = "" if result.returncode == 0 else f" (help exits {result.returncode} on this SITL)"
            return Check(f"sitl_{name}", True, True, f"{found} — {first[:160]}{suffix}")
        return Check(f"sitl_{name}", False, True,
                     f"{found} exists but --version exited {result.returncode}",
                     "Rebuild the SITL binary and inspect its output.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(f"sitl_{name}", False, True, f"{found} could not run: {exc}",
                     "Rebuild the SITL binary for this host.")


def _command(name: str, args: list[str], *, critical: bool) -> Check:
    binary = shutil.which(name)
    if not binary:
        return Check(name, False, critical, f"{name} is not on PATH", f"Install {name} and start a new shell.")
    try:
        result = subprocess.run([binary, *args], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=10, check=False)
        output = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "responded")
        return Check(name, result.returncode == 0, critical,
                     f"{binary} — {output[:160]}", "Check the installed version and its environment." if result.returncode else "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, False, critical, f"{binary} could not run: {exc}",
                     f"Repair the {name} installation.")


def _configured_command(name: str, args: list[str]) -> Check:
    """Run a prerequisite command after loading the configured launch env."""
    command = " ".join([name, *args])
    script = f'source "$1" && source "$2" && {command}'
    try:
        result = subprocess.run(["/bin/bash", "-lc", script, "argazui-doctor",
                                 str(paths.ENV_SH), str(paths.QUADPLANE_ENV_SH)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, False, True, f"{name} could not run after loading the configured environment: {exc}",
                     "Fix the environment script or install the missing program.")
    if result.returncode == 0:
        output = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "responded")
        return Check(name, True, True, f"configured environment: {output[:160]}")
    detail = next((line.strip() for line in result.stdout.splitlines() if line.strip()),
                  f"exit {result.returncode}")
    return Check(name, False, True, f"configured environment cannot run {name}: {detail[:160]}",
                 f"Install {name} and ensure the configured environment script exposes it.")


def _configured_ros_distro() -> Check:
    try:
        result = subprocess.run(
            ["/bin/bash", "-lc", 'source "$1" && printf "%s" "${ROS_DISTRO:-}"',
             "argazui-doctor", str(paths.ENV_SH)], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("ros_distro", False, True, f"could not read ROS_DISTRO: {exc}",
                     "Fix the configured environment script.")
    distro = result.stdout.strip() if result.returncode == 0 else ""
    return Check("ros_distro", distro == "jazzy", True,
                 f"ROS_DISTRO={distro or '(not set)'} (configured environment)",
                 "Source ROS 2 Jazzy from the configured environment script." if distro != "jazzy" else "")


def _writable(name: str, path: Path, description: str) -> Check:
    """Can ArgazUI create this directory and write into it?

    Not critical: a machine that cannot write run artefacts can still fly.
    But finding out at STOP — after the flight — is the wrong moment, so the
    doctor says it in advance.
    """
    probe = path / ".argazui-write-test"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check(name, True, False, f"{description}: {path}")
    except OSError as exc:
        return Check(name, False, False, f"{description} is not writable ({path}): {exc}",
                     "Point 'runs_root' at a writable directory in argaz.toml, or fix the "
                     "permissions on this one.")


def _package(name: str) -> Check:
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "installed")
        return Check(f"python_{name}", True, True, f"{name} {version}")
    except ImportError:
        return Check(f"python_{name}", False, True, f"Python package missing: {name}",
                     "Install the project requirements in the interpreter used by ArgazUI.")


def _port(port: int, label: str, kind: int = socket.SOCK_STREAM) -> Check:
    try:
        sock = socket.socket(socket.AF_INET, kind)
    except OSError as exc:
        # Some locked-down CI sandboxes disallow creating sockets altogether.
        # That is a diagnostic result, not a doctor crash (and JSON must still
        # be machine-readable in exactly that environment).
        return Check(f"port_{label}", False, True, f"cannot create socket to check port {port}: {exc}",
                     "Run doctor on the target host, where it can inspect local ports.")
    try:
        sock.bind(("127.0.0.1", port))
        return Check(f"port_{label}", True, True, f"127.0.0.1:{port} is available")
    except OSError as exc:
        fix = "Stop the process using this port or choose a different configured port."
        if label == "http":
            # This exact situation cost a user a debugging session: an ArgazUI
            # left running from a previous day still held 8770, start.sh
            # refused to launch a replacement, and the browser kept talking to
            # the OLD backend while loading the NEW static files from disk.
            # Say so, rather than leaving them to work it out.
            # Every command here must run verbatim when pasted — no <pid>.
            script = Path(__file__).resolve().parent.parent / "start.sh"
            fix = ("Something is already listening on this port — very likely an older "
                   "ArgazUI. Your browser would load the current interface files but "
                   "talk to that older server, which is worse than no server at all. "
                   f"Take it over with:  {script} --replace   "
                   f"or leave it alone and use:  {script} --port {port + 1}")
        return Check(f"port_{label}", False, True,
                     f"127.0.0.1:{port} is unavailable: {exc}", fix)
    finally:
        sock.close()


def run(tier: str = "full") -> dict:
    """Return all checks. ``tier1`` intentionally excludes Gazebo/ROS assets."""
    if tier not in ("full", "tier1"):
        raise ValueError("tier must be 'full' or 'tier1'")

    checks = [
        _path_check("ardupilot_root", paths.ARDUPILOT, critical=True, description="ArduPilot root"),
        _binary("copter", [paths.ARDUPILOT / "build" / "sitl" / "bin" / "arducopter",
                            paths.ARDUPILOT / "ArduCopter" / "arducopter"]),
        _binary("plane", [paths.ARDUPILOT / "build" / "sitl" / "bin" / "arduplane",
                           paths.ARDUPILOT / "ArduPlane" / "arduplane"]),
        _path_check("env_script", paths.ENV_SH, critical=True, description="environment script"),
        _path_check("quadplane_env_script", paths.QUADPLANE_ENV_SH, critical=True,
                    description="quadplane environment script"),
        *[_package(name) for name in ("fastapi", "uvicorn", "pymavlink", "yaml")],
        _writable("runs_root", paths.RUNS_DIR, "run artefact directory"),
        _port(paths.HTTP_PORT, "http"),
        _port(paths.UI_MAVLINK_PORT, "mavlink", socket.SOCK_DGRAM),
        _port(paths.SCRIPT_MAVLINK_PORT, "script_mavlink", socket.SOCK_DGRAM),
    ]
    if tier == "full":
        checks.extend([
            _path_check("ardu_ws_root", paths.ARDU_WS, critical=True, description="ROS workspace root"),
            _path_check("sitl_models_root", paths.SITL_MODELS, critical=True, description="SITL_Models root"),
            _path_check("sitl_models_gazebo", paths.SITL_MODELS / "Gazebo", critical=True,
                        description="SITL_Models Gazebo assets"),
            _configured_command("gz", ["sim", "--version"]),
            _configured_command("ros2", ["--help"]),
        ])
        checks.append(_configured_ros_distro())

    critical_ok = all(check.ok for check in checks if check.critical)
    return {"ok": critical_ok, "tier": tier, "config": paths.source_summary(),
            "checks": [check.as_dict() for check in checks]}


def format_human(report: dict) -> str:
    lines = [f"ArgazUI doctor ({report['tier']})", ""]
    for check in report["checks"]:
        marker = "OK  " if check["ok"] else "FAIL"
        lines.append(f"{marker}  {check['name']}: {check['detail']}")
        if not check["ok"] and check["fix"]:
            lines.append(f"      Fix: {check['fix']}")
    lines.extend(["", "Result: " + ("ready" if report["ok"] else "not ready")])
    return "\n".join(lines)
