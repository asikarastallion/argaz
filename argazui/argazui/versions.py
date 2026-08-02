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
from datetime import datetime, timezone
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


# --------------------------------------------------------------------------- build id
# Fixed for the life of the process: the moment this module is imported is the
# moment the server started, and the interface uses it to say how long an old
# server has been running.
_STARTED = datetime.now(timezone.utc)


# The four things the server reads off disk, and what a change to each means
# while it is running. Only the first two can go stale — that distinction is
# the whole value of reporting them separately, because "restart now" and
# "already live" are opposite instructions.
#
#   code        argazui/**/*.py       imported once  -> STALE until restart
#   ui          static/**             served per request, but built against
#                                     whatever API the running code has
#   procedures  procedures/*.yaml     re-read on mtime change (procedures.py
#                                     `_dir_stamp`) -> already live
#   config      config/*.json         re-read on every request (app.registry,
#                                     app.buttons) -> already live
STALE_ON_CHANGE = ("code", "ui")


def _digest_of(root: Path, patterns: tuple[str, ...]) -> str:
    import hashlib

    if not root.is_dir():
        return "absent"
    digest = hashlib.sha256()
    seen: list[Path] = []
    for pattern in patterns:
        seen.extend(p for p in root.glob(pattern) if p.is_file())
    for path in sorted(set(seen)):
        digest.update(str(path.relative_to(root)).encode())
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()[:12]


def source_digests() -> dict[str, str]:
    """Content hashes of everything the server reads off disk, per layer.

    WHY CONTENT HASHES AND NOT JUST THE GIT SHA
    -------------------------------------------
    The commit-based build id only moves at a commit boundary, but the thing
    that goes wrong all day is smaller: you edit a file, the server keeps
    running with its old Python loaded, and both sides still report the same
    commit and the same `dirty` flag.

    The first version of this hashed only `static/`, which left the original
    failure invisible inside a commit — the user's stale backend was caught
    only because it was old enough to lack `/api/version` at all. Server code
    is the layer that actually breaks the API contract, so it is hashed too.
    """
    from . import paths

    package = Path(__file__).resolve().parent
    return {
        "code": _digest_of(package, ("*.py", "**/*.py")),
        "ui": _digest_of(paths.STATIC_DIR, ("**/*",)),
        "procedures": _digest_of(paths.PROCEDURES_DIR, ("*.yaml",)),
        "config": _digest_of(paths.CONFIG_DIR, ("*.json",)),
    }


def static_digest() -> str:
    """Back-compatible single value: the interface-file layer."""
    return source_digests()["ui"]


# What the server had on disk when it started.
_AT_BOOT: dict[str, str] = {}


def pin_static_digest() -> dict[str, str]:
    """Records the on-disk state right now, once.

    Called from the FastAPI startup event so the values are fixed before any
    request can arrive. Computing them lazily on first use was a real defect:
    the first use IS a request, by which time a file may already have changed,
    so boot and current would agree and the drift check would stay silent in
    precisely the situation it was written for.
    """
    global _AT_BOOT
    if not _AT_BOOT:
        _AT_BOOT = source_digests()
    return _AT_BOOT


def _boot_digests() -> dict[str, str]:
    # Outside a server (the CLI, the tests) there is no boot moment; fall back
    # to the current state rather than inventing a mismatch.
    return _AT_BOOT or source_digests()


def argazui_build() -> dict:
    """Which ArgazUI is answering, and since when.

    WHY THE INTERFACE NEEDS THIS
    ----------------------------
    `index.html` and `app.js` are served from disk, so a server left running
    from an earlier checkout hands the browser TODAY's interface while
    answering with YESTERDAY's API. That is exactly how the v1.1 regression
    reached a user: the page loaded fine, called an endpoint the old server had
    never heard of, and the failure looked like a bug in the page. The browser
    compares this identity against the one embedded in the HTML it was served
    and says so when they differ.
    """
    from . import __version__

    root = Path(__file__).resolve().parent.parent.parent
    sha = _git(root, "rev-parse", "HEAD") if (root / ".git").exists() else ""
    dirty = bool(_git(root, "status", "--porcelain")) if sha else False
    boot = _boot_digests()
    now = source_digests()
    # Only the layers that actually go stale belong in the identity. Including
    # the hot-reloaded ones would fire a "restart the server" warning every
    # time someone edited a procedure that took effect immediately — a false
    # alarm, and false alarms are how a warning stops being read.
    stale = sorted(layer for layer in STALE_ON_CHANGE if boot.get(layer) != now.get(layer))
    argazui_dir = Path(__file__).resolve().parent.parent
    return {
        "version": __version__,
        "sha": sha or UNKNOWN,
        "short_sha": (sha[:12] if sha else UNKNOWN),
        "dirty": dirty,
        "started_utc": _STARTED.strftime("%Y-%m-%dT%H:%M:%SZ"),
        # The identity the browser compares: the commit, uncommitted changes
        # anywhere in the tree, and the two layers that cannot hot-reload.
        "build_id": (f"{__version__}+{(sha[:12] if sha else 'nogit')}"
                     f"{'+dirty' if dirty else ''}"
                     f"+code{boot.get('code', '?')}+ui{boot.get('ui', '?')}"),
        "digests_boot": boot,
        "digests_now": now,
        "stale_layers": stale,
        "changed_layers": sorted(k for k in now if boot.get(k) != now.get(k)),
        # Kept for readers of the earlier shape.
        "static_digest_boot": boot.get("ui", ""),
        "static_digest_now": now.get("ui", ""),
        "static_changed_since_boot": "ui" in stale,
        # Where this server lives, so the browser can print a command that
        # runs verbatim instead of one containing a placeholder.
        "argazui_dir": str(argazui_dir),
        "restart_command": f"{argazui_dir / 'start.sh'} --replace",
    }
