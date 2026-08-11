"""What produced a result: one machine-readable manifest per run.

WHY A RUN NEEDS ONE
-------------------
`versions.txt` already answered "which software?" as a flat list of strings for
a human to read. That is enough to look at and not enough to compare. Two runs
of the same model can differ by an ArduPilot commit, an edited procedure, a
changed parameter file or a different Gazebo — and unless each run states all
of them in a form a program can line up, a comparison between them is a guess
wearing a table.

So every run captures this. It is what makes regression.py able to say *"these
two are comparable"* instead of assuming it.

UNKNOWN IS AN ANSWER, AND IT COMES WITH A REASON
------------------------------------------------
No field here is ever filled in with something plausible. A component that
cannot be identified is `null`, and the reason appears in `unknown` — "SITL
models root is not a git checkout", "gz is not installed". A fingerprint that
quietly omitted the field would read exactly like one taken on a machine where
the component was fine, and the whole point of the manifest is that those two
situations must not look the same.

WHAT IS HASHED, AND WHY THOSE THINGS
------------------------------------
Content hashes cover the two inputs that change most often and move no version
number when they do:

  * the procedures that were executed, hashed from the verbatim YAML the run
    recorded, so an edited acceptance criterion is visible as a different run;
  * the model's registry entry and its parameter files, because a changed
    `.param` file changes the aircraft without changing any commit.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import paths
from .versions import build_id, command_version, git_identity

SCHEMA = 1

# The file each run leaves behind, beside result.json.
FILENAME = "fingerprint.json"


def _sha256(*chunks: bytes) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def normalise(text: str) -> str:
    """The form of a document that gets hashed.

    Trailing whitespace is not content, and it is exactly what differs between
    the YAML a live run holds in memory and the copy it writes into
    `scenario.yaml`. Without this, a freshly flown run and a regenerated report
    of the *same flight* produced different procedure hashes — and therefore
    refused to be compared with each other, which is the one thing the hash
    exists to allow.
    """
    return (text or "").rstrip() + "\n" if (text or "").strip() else ""


def _procedure_hash(procedures: list[dict]) -> str:
    """One hash over every procedure that ran, in a stable order.

    The id is folded in alongside the text so that two procedures swapping
    files cannot produce the same digest as the pair the other way round.
    """
    parts: list[bytes] = []
    for entry in sorted(procedures, key=lambda p: (p.get("id") or "")):
        parts.append((entry.get("id") or "").encode("utf-8"))
        parts.append(b"\0")
        parts.append(normalise(entry.get("text")).encode("utf-8"))
        parts.append(b"\0")
    return _sha256(*parts)


def _model_hash(model: dict) -> tuple[str, list[str], list[str]]:
    """Hash of the model's registry entry plus every parameter file it names.

    Returns the digest, the files that went into it, and the ones that were
    named but could not be read — the last of those is reported rather than
    ignored, because a parameter file that is missing today was part of the
    aircraft yesterday.
    """
    canonical = json.dumps(model, sort_keys=True, ensure_ascii=False).encode("utf-8")
    parts: list[bytes] = [canonical, b"\0"]
    included: list[str] = []
    missing: list[str] = []

    names = model.get("param_file") or []
    if isinstance(names, str):
        names = [names]
    for name in names:
        candidate = Path(name)
        for base in (candidate, paths.SITL_MODELS_CONFIG / candidate.name,
                     paths.ARDUPILOT / candidate):
            try:
                if base.is_file():
                    parts.extend((base.name.encode("utf-8"), b"\0",
                                  base.read_bytes(), b"\0"))
                    included.append(str(base))
                    break
            except OSError:
                continue
        else:
            missing.append(str(candidate))
    return _sha256(*parts), included, missing


# Asking `gz` for its version costs about a second — it is a wrapper script
# that starts a process. A fingerprint is taken at least twice per run, and the
# unit tests take dozens, so the answer is remembered for the life of the
# process.
#
# THE TRADE, STATED
# Installing Gazebo while the server is running would leave this cached as
# unknown until a restart. That is the same staleness `versions.py` already has
# for the boot-time digests, it is visible (the field says unknown, with a
# reason), and it is worth a second off every STOP.
_VERSION_CACHE: dict[str, tuple[str, str]] = {}


def _tool_version(key: str, args: list[str]) -> tuple[str, str]:
    if key not in _VERSION_CACHE:
        _VERSION_CACHE[key] = command_version(args)
    return _VERSION_CACHE[key]


def _runtime() -> dict:
    try:
        from pymavlink import __version__ as pymavlink_version
    except Exception:                                # pragma: no cover - import guard
        pymavlink_version = None
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "pymavlink": pymavlink_version,
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
    }


def capture(model: Optional[dict] = None,
            procedures: Optional[list[dict]] = None,
            firmware: str = "",
            scenario: Optional[list[dict]] = None) -> dict:
    """The manifest for one run.

    `procedures` is a list of `{"id", "schema", "file", "text"}` — the verbatim
    YAML the run executed, which is the only version of a procedure that can
    honestly be hashed: the file on disk may already have been edited.

    `scenario` is the faults those procedures declared (v1.4). It is recorded
    for a reader, NOT as a separate identity field, and the distinction is
    deliberate: the `failures:` block is part of the procedure text, so
    `procedure_hash` already covers it byte for byte. A second hash over the
    same content could only ever disagree with the first, and a comparison
    refused because two hashes of one thing differ would be a bug wearing the
    costume of a safety check.
    """
    model = model or {}
    procedures = procedures or []
    unknown: list[dict] = []

    def _note(field: str, reason: str) -> None:
        unknown.append({"field": field, "reason": reason})

    from . import __version__

    # ------------------------------------------------------------------ argaz
    argaz_root = Path(__file__).resolve().parent.parent.parent
    argaz_git = git_identity(argaz_root)
    if argaz_git["commit"] is None:
        _note("argaz.commit", argaz_git["reason"])
    argaz = {"version": __version__, "commit": argaz_git["commit"],
             "short_commit": argaz_git.get("short_commit"),
             "describe": argaz_git["describe"], "dirty": argaz_git["dirty"],
             "dirty_digest": argaz_git.get("dirty_digest"),
             "root": argaz_git["root"]}

    # -------------------------------------------------------------- ardupilot
    build = build_id(firmware)
    ardupilot_git = git_identity(paths.ARDUPILOT)
    if ardupilot_git["commit"] is None:
        _note("ardupilot.commit", ardupilot_git["reason"])
    if not build.firmware:
        _note("ardupilot.firmware",
              "the dataflash log carried no firmware string; a run whose "
              "vehicle never armed writes no log to carry one")
    ardupilot = {
        "commit": ardupilot_git["commit"],
        "short_commit": ardupilot_git.get("short_commit"),
        "describe": ardupilot_git["describe"],
        "dirty": ardupilot_git["dirty"],
        "dirty_digest": ardupilot_git.get("dirty_digest"),
        "root": ardupilot_git["root"],
        "firmware": build.firmware or None,
        "firmware_commit": build.firmware_hash or None,
        # None is a third answer and not a soft "no": a report generated from a
        # log alone genuinely cannot say whether the binary matches a checkout.
        "firmware_matches_checkout": build.firmware_matches_checkout,
        "text": build.text(),
    }

    # ------------------------------------------------------------ sitl models
    models_git = git_identity(paths.SITL_MODELS)
    if models_git["commit"] is None:
        _note("sitl_models.commit", models_git["reason"])
    sitl_models = {"commit": models_git["commit"],
                   "short_commit": models_git.get("short_commit"),
                   "describe": models_git["describe"],
                   "dirty": models_git["dirty"],
                   "dirty_digest": models_git.get("dirty_digest"),
                   "root": models_git["root"]}

    # ------------------------------------------------------------ simulators
    gz_version, gz_reason = _tool_version("gz", ["gz", "sim", "--version"])
    if not gz_version:
        _note("gazebo.version", gz_reason)
    ros_distro = os.environ.get("ROS_DISTRO") or None
    if not ros_distro:
        _note("ros.distro", "ROS_DISTRO is not set in the server's environment; "
                            "a launch method that does not use ROS 2 sets nothing")

    # ------------------------------------------------------------ the subject
    model_hash, param_files, missing_params = _model_hash(model)
    for name in missing_params:
        _note("model.param_file", f"{name} is named by the model but could not be read")

    procedure_entries = [{"id": p.get("id"), "schema": p.get("schema"),
                          "file": p.get("file"),
                          "hash": _sha256(normalise(p.get("text")).encode("utf-8"))}
                         for p in procedures]
    if not procedure_entries:
        _note("procedures", "no procedure ran during this session, so there is "
                            "no flow to hash")

    return {
        "schema": SCHEMA,
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "argaz": argaz,
        "ardupilot": ardupilot,
        "sitl_models": sitl_models,
        "gazebo": {"version": gz_version or None},
        "ros": {"distro": ros_distro},
        "runtime": _runtime(),
        "model": {
            "id": model.get("id"), "name": model.get("name"),
            "vehicle_class": model.get("vehicle_class"),
            "method": model.get("method"), "vehicle": model.get("vehicle"),
            "frame": model.get("frame"), "world": model.get("world"),
            "config_hash": model_hash,
            "param_files": param_files,
        },
        "procedures": procedure_entries,
        "procedure_hash": _procedure_hash(
            [{"id": p.get("id"), "text": p.get("text")} for p in procedures]),
        # Off-nominal conditions this run was configured to inject. `[]` means
        # a nominal flight; what actually happened to the aircraft is in
        # result.json under each procedure's `faults`, because a declaration
        # and an injection are two different facts.
        "scenario": {"faults": list(scenario or []),
                     "covered_by": "procedure_hash"},
        "config": paths.source_summary(),
        "unknown": unknown,
    }


def write(directory: Path, manifest: dict) -> Path:
    path = Path(directory) / FILENAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def read(directory: Path) -> dict:
    """A stored fingerprint, or an empty one for a run recorded before v1.3."""
    path = Path(directory) / FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------- comparison
# The fields that have to match before two runs may be compared on their
# numbers. Each is a thing that changes what the aircraft or the test IS, as
# opposed to how well it did — see regression.py, which refuses to compare
# across any of them unless it is told to in so many words.
IDENTITY_FIELDS = (
    ("model.config_hash", "the model's registry entry or one of its parameter files"),
    ("procedure_hash", "the procedures that were executed"),
    ("ardupilot.commit", "the ArduPilot checkout"),
    ("ardupilot.firmware_commit", "the firmware binary that flew"),
    # ---------------------------------------------- added by v1.6 corrective
    # A COMMIT DOES NOT IDENTIFY A WORKING TREE
    # ----------------------------------------
    # `dirty` was captured from the first release and compared by nothing, so
    # two runs flown from two different sets of uncommitted changes on the same
    # SHA reported themselves as the same configuration and were compared on
    # their numbers. `dirty: true` on either side is not a claim that the trees
    # differ — it is a statement that the commit alone cannot show they are the
    # same, which is exactly the condition a comparison must not be made
    # silently across. `ignore_config_drift` is how someone says they know.
    ("argaz.dirty_digest", "uncommitted changes in the ArgazUI checkout"),
    ("ardupilot.dirty_digest", "uncommitted changes in the ArduPilot checkout"),
    # The simulator is half the physics. A Gazebo upgrade between two runs
    # changes what the aircraft flew through, and it moves no commit here.
    ("gazebo.version", "the Gazebo that provided the physics"),
)


def field(manifest: dict, dotted: str) -> Any:
    """`fingerprint.field(fp, "ardupilot.commit")`, tolerating what is absent."""
    node: Any = manifest
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def differences(baseline: dict, current: dict) -> list[dict]:
    """Identity fields on which two runs disagree.

    A field that is unknown on either side is reported as a difference too. It
    is not a claim that they differ — it is a statement that nothing here can
    show they are the same, which is exactly the condition a comparison must
    not be made silently across.
    """
    out: list[dict] = []
    for dotted, description in IDENTITY_FIELDS:
        before, after = field(baseline, dotted), field(current, dotted)
        if before is None or after is None:
            out.append({"field": dotted, "what": description,
                        "baseline": before, "current": after,
                        "reason": "unknown on at least one side"})
        elif dotted.endswith(".dirty_digest") and before != after:
            # Two dirty trees are not shown to be the same tree by both being
            # dirty, and two runs from ONE dirty tree are perfectly comparable.
            # A boolean cannot tell those apart; the digest can, and it says
            # which of the two cases this is.
            out.append({"field": dotted, "what": description,
                        "baseline": before, "current": after,
                        "reason": ("different uncommitted changes; the commit "
                                   "alone cannot identify what flew")})
        elif before != after:
            out.append({"field": dotted, "what": description,
                        "baseline": before, "current": after,
                        "reason": "changed"})
    return out
