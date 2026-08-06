"""L6 (minimum) — what a fleet run leaves behind.

Phase 5 needs the traces its gate asks for; phase 6 builds the human report on
top of these files. The rule they all follow is the one the rest of the
project follows: **a file that was not measured says so, rather than being
absent or being filled with a plausible number.**

    fleet.json       the spec snapshot, resolved ports, version stamps, and
                     which measurement authorised each monitor
    timeline.jsonl   every event, ordered on the router's monotonic clock
    rtf.csv          t, rtf, sim_time  — empty with a stated reason when there
                     is no physics server
    separation.csv   t, pair, distance_m — empty with a stated reason when the
                     time base does not support the claim
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1

# Written beside a trace that has no rows, so an empty file is never ambiguous
# between "nothing happened" and "nothing was measured".
REASON_SUFFIX = ".reason.txt"


def _write_reason(path: Path, reason: str) -> None:
    path.with_suffix(path.suffix + REASON_SUFFIX).write_text(
        reason.rstrip() + "\n", encoding="utf-8")


def write_rtf_csv(path: Path, samples: list,
                  reason: str = "") -> Path:
    """`t, rtf, sim_time_s`. `samples` is a list of (t, rtf, sim_time)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t_s", "rtf", "sim_time_s"])
        for row in samples:
            writer.writerow([round(row[0], 3),
                             "" if row[1] is None else round(row[1], 4),
                             "" if row[2] is None else round(row[2], 3)])
    if not samples:
        _write_reason(path, reason or
                      "no real-time factor was recorded, and no reason was "
                      "given for its absence")
    return path


def write_separation_csv(path: Path, rows: list, reason: str = "") -> Path:
    """`t, pair, distance_m`, exactly as the monitor produced them."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t_s", "pair", "distance_m"])
        for row in rows:
            writer.writerow(list(row))
    if not rows:
        _write_reason(path, reason or
                      "no separation was recorded, and no reason was given "
                      "for its absence")
    return path


def write_fleet_json(path: Path, spec, allocation,
                     authorisations: Optional[dict] = None,
                     extra: Optional[dict] = None) -> Path:
    """The snapshot that makes a run reproducible and its claims traceable.

    `authorisations` is the part worth reading twice. Every monitor that
    produced numbers records WHY it was allowed to — the measurement that
    justified it — so a reader can tell a measured claim from a configured
    one without leaving the run directory.
    """
    from .. import versions

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fleet": spec.as_dict(),
        "allocation": allocation.as_dict() if allocation else None,
        "authorisations": authorisations or {},
        "environment": versions.environment(),
    }
    if extra:
        document.update(extra)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def separation_authorisation(measuring: bool, source: str, reason: str) -> dict:
    """How the separation monitor's permission to speak is recorded.

    The presence of Gazebo is not evidence. The measurement is.
    """
    return {
        "measured": bool(measuring),
        "source": source,
        "justification": reason,
    }
