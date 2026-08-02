"""The one place that says which software produced a result.

WHY THIS MODULE EXISTS
----------------------
v1.1 phase 3 printed two different answers to "which ArduPilot?" —
`report.md` said `ArduPlane V4.8.0-dev` (what the binary reports about itself)
while `versions.txt` said `ArduPilot-4.6.0-beta1-7768-g0b38722bd5` (what the
source checkout describes as). Both were true and neither was comparable, so
no two runs could be lined up against each other.

There is now one canonical record, `BuildId`, and one canonical string:

    ArduPlane V4.8.0-dev @ 0b38722bd5a4 (ArduPilot-4.6.0-beta1-7768-g0b38722bd5)
    └ firmware, from the log ┘ └ checkout HEAD ┘ └ git describe ────────────┘

THE MISMATCH CHECK IS THE POINT
-------------------------------
The firmware string carries the commit the *binary* was built from; the
checkout SHA is what the source tree is at *now*. When they disagree, the run
was flown by a stale binary and comparing it against another run's results is
meaningless. `BuildId.firmware_matches_checkout` reports that, and the flight
report raises it as an advisory rather than leaving it for someone to notice.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from . import paths

# "ArduPlane V4.8.0-dev (0b38722b)" and "APM:Copter V4.5.7 (abcd1234)" both
# appear in dataflash logs depending on firmware age.
_FIRMWARE = re.compile(r"^(?P<name>.+?)\s*\((?P<hash>[0-9a-f]{6,})\)\s*$", re.IGNORECASE)

UNKNOWN = "(unknown)"


def _git(root: Path, *args: str, timeout: float = 10.0) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _command_output(args: list[str], timeout: float = 10.0) -> str:
    """First non-empty line of a command, or a stated reason it is missing."""
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(unavailable: {exc})"
    if result.returncode != 0:
        return f"(exit {result.returncode})"
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()),
                "(no output)")


@dataclass
class BuildId:
    """Which ArduPilot flew a run, from both sides: binary and source tree."""

    firmware: str = ""          # "ArduPlane V4.8.0-dev", as the binary reports it
    firmware_hash: str = ""     # the commit hash embedded in that string
    sha: str = ""               # full HEAD of the ArduPilot checkout
    describe: str = ""          # git describe --tags --always --dirty
    root: str = ""              # which checkout was inspected

    @property
    def short_sha(self) -> str:
        return self.sha[:12] if self.sha else ""

    @property
    def firmware_matches_checkout(self) -> Optional[bool]:
        """True/False, or None when there is nothing to compare.

        None is a real third answer: a report generated from a log alone (no
        checkout available) genuinely cannot say, and must not claim a match.
        """
        if not self.firmware_hash or not self.sha:
            return None
        return self.sha.lower().startswith(self.firmware_hash.lower())

    def text(self) -> str:
        """The canonical one-line form used everywhere a version is shown."""
        firmware = self.firmware or UNKNOWN
        if not self.sha:
            return f"{firmware} @ {self.firmware_hash or UNKNOWN} (no source checkout)"
        suffix = f" ({self.describe})" if self.describe else ""
        if self.firmware_matches_checkout is False:
            return (f"{firmware} @ {self.firmware_hash} "
                    f"— MISMATCH, checkout is {self.short_sha}{suffix}")
        return f"{firmware} @ {self.short_sha}{suffix}"

    def as_dict(self) -> dict:
        out = asdict(self)
        out["short_sha"] = self.short_sha
        out["firmware_matches_checkout"] = self.firmware_matches_checkout
        out["text"] = self.text()
        return out


def parse_firmware(text: str) -> tuple[str, str]:
    """Splits "ArduPlane V4.8.0-dev (0b38722b)" into its name and commit hash."""
    match = _FIRMWARE.match((text or "").strip())
    if not match:
        return (text or "").strip(), ""
    return match.group("name").strip(), match.group("hash").lower()


def build_id(firmware: str = "", root: Optional[Path] = None) -> BuildId:
    """The canonical build record for a run.

    `firmware` is the string the autopilot wrote into its own log; the rest is
    read from the ArduPilot checkout ArgazUI is configured to use.
    """
    root = Path(root) if root else paths.ARDUPILOT
    name, commit = parse_firmware(firmware)
    if (root / ".git").exists():
        sha = _git(root, "rev-parse", "HEAD")
        describe = _git(root, "describe", "--tags", "--always", "--dirty")
    else:
        sha = describe = ""
    return BuildId(firmware=name, firmware_hash=commit, sha=sha,
                   describe=describe, root=str(root))


def environment(firmware: str = "") -> dict[str, str]:
    """Everything needed to reproduce a run, as a flat name = value mapping.

    A missing component is recorded as unavailable rather than omitted: a
    record that silently drops the Gazebo version reads the same whether
    Gazebo was absent or simply never asked.
    """
    from . import __version__

    build = build_id(firmware)
    try:
        from pymavlink import __version__ as pymavlink_version
    except Exception:
        pymavlink_version = "(unavailable)"

    return {
        "ardupilot": build.text(),
        "ardupilot_sha": build.sha or "(not a git checkout)",
        "ardupilot_describe": build.describe or "(not a git checkout)",
        "ardupilot_firmware": build.firmware or UNKNOWN,
        "ardupilot_root": build.root,
        "argazui": __version__,
        "gz_sim": _command_output(["gz", "sim", "--version"]),
        "ros_distro": os.environ.get("ROS_DISTRO", "(not set in the server environment)"),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "pymavlink": pymavlink_version,
        "host": f"{_platform()}",
    }


def _platform() -> str:
    import platform
    return f"{platform.system()} {platform.release()} ({platform.machine()})"
