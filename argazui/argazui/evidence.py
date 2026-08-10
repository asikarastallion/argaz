"""The evidence manifest: what a run should have left behind, and what it did.

WHY A RUN NEEDS ONE
-------------------
A run directory is a pile of files. Whether it is a *complete* pile has, until
now, been something a reader worked out by remembering what ought to be in one
— and the failure mode is quiet: a report that was never generated, a plot
directory that is empty, a parameter dump the analysis skipped. Every one of
those leaves a directory that looks fine, and every one of them means a claim
somewhere rests on evidence nobody can open.

So each run writes a manifest of the artefacts it was *expected* to produce,
with what actually happened to each.

THREE KINDS OF EXPECTATION, AND THE MIDDLE ONE IS THE POINT
-----------------------------------------------------------
    required     the run is not evidence without it. Absent -> evidence failure.
    conditional  required only when a stated condition held — the dataflash log
                 is required if the vehicle armed, and not otherwise, because
                 ArduPilot's default LOG_DISARMED=0 means a session that never
                 armed writes none and nothing was lost.
    optional     nice to have. Absent is fine — **but only with a stated
                 reason.** An optional artefact missing with no explanation is
                 reported as `unexplained`, because "there are no plots because
                 matplotlib is not installed" and "there are no plots" are
                 different facts and only one of them is an answer.

That last rule is the same one this project applies to a metric that could not
be measured and to a fingerprint field that could not be read. Absence with a
reason is evidence; absence without one is a gap.

WHAT IS RECORDED PER ARTEFACT
-----------------------------
Path, type, whether it exists, its size, a content hash, and which module at
which schema version produced it. The producer matters as much as the hash: a
`result.json` written by schema 3 and one written by schema 5 are both valid
and carry different fields, and a reviewer comparing two runs has to be able to
see which they are looking at without opening either.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA = 1

FILENAME = "evidence.json"

# Expectation levels.
REQUIRED, CONDITIONAL, OPTIONAL = "required", "conditional", "optional"

# Content is hashed up to this size. Above it the hash is `null` with a stated
# reason: a dataflash log from a long flight is tens of megabytes and hashing
# it costs a second, which is acceptable; hashing an arbitrarily large file on
# the STOP path is not, and a hash nobody waited for is not a hash.
MAX_HASH_BYTES = 256 * 1024 * 1024


def _sha256(path: Path) -> tuple[Optional[str], str]:
    """(hash, reason-it-is-absent). Never raises — a manifest must always write."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, f"could not be read: {exc}"
    if size > MAX_HASH_BYTES:
        return None, (f"{size / 1e6:.0f} MB is over the {MAX_HASH_BYTES / 1e6:.0f} MB "
                      f"hashing limit; the file is present and unhashed")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        return None, f"could not be read: {exc}"
    return "sha256:" + digest.hexdigest(), ""


# Why `result.json` is present in the manifest and deliberately unhashed.
#
# It is the document the manifest describes, and it is rewritten after the
# flight report completes — the advisory count, the metrics and the build
# record only exist once the dataflash log has been read. A hash taken at any
# one of those moments is wrong at the others, and a hash that is sometimes
# wrong is worse than an honest absence: it would fail an integrity check for a
# run that is perfectly intact.
SELF_DESCRIBING = ("the run record is rewritten when the flight report "
                   "completes, so a hash of it would be correct at one moment "
                   "and wrong at the next; its presence, size and schema are "
                   "recorded instead")


class Artefact:
    """One thing a run is expected to leave behind."""

    __slots__ = ("name", "path", "kind", "level", "producer", "schema_of",
                 "why", "condition", "purpose", "hashed")

    def __init__(self, name: str, path: str, kind: str, level: str,
                 producer: str, purpose: str,
                 schema_of: Optional[Callable[[], Any]] = None,
                 condition: Optional[Callable[[dict], bool]] = None,
                 why: Optional[Callable[[dict, Path], str]] = None,
                 hashed: bool = True) -> None:
        self.name = name
        self.path = path
        self.kind = kind
        self.level = level
        self.producer = producer
        self.purpose = purpose
        self.schema_of = schema_of
        self.condition = condition
        self.why = why
        self.hashed = hashed


def _result_schema() -> Any:
    from .runs import RESULT_SCHEMA
    return RESULT_SCHEMA


def _fingerprint_schema() -> Any:
    from .fingerprint import SCHEMA as value
    return value


def _report_schema() -> Any:
    # flightlog writes `"schema": 2` into report.json; named here rather than
    # duplicated as a literal so the two cannot drift.
    from .flightlog import REPORT_SCHEMA
    return REPORT_SCHEMA


def _regression_schema() -> Any:
    from .regression import SCHEMA as value
    return value


def _armed(result: dict) -> bool:
    """Did the vehicle arm? Read from the run's own record, not guessed."""
    artefacts = result.get("artefacts") or {}
    if artefacts.get("dataflash"):
        return True
    reason = artefacts.get("dataflash_absent_reason") or ""
    # `runs.py` writes one of exactly two sentences here, and the first of them
    # is the statement that the vehicle never armed.
    return "never armed" not in reason


def _dataflash_reason(result: dict, directory: Path) -> str:
    return ((result.get("artefacts") or {}).get("dataflash_absent_reason")
            or "no reason was recorded")


def _report_reason(result: dict, directory: Path) -> str:
    if not (result.get("artefacts") or {}).get("dataflash"):
        return ("the run archived no dataflash log, and the flight report is "
                "built from one")
    return ("the report was not generated; run "
            "`python3 -m argazui report <run>` to produce it from the log this "
            "run already archived")


def _plots_reason(result: dict, directory: Path) -> str:
    report = directory / "report.json"
    if not report.is_file():
        return "no flight report was generated, so no plots were attempted"
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "the flight report could not be read to say why"
    if document.get("plots"):
        return ""
    return ("matplotlib is not installed in the interpreter that generated the "
            "report; it is an optional dependency and everything else in the "
            "report comes from the log itself")


def _regression_reason(result: dict, directory: Path) -> str:
    return ("this run has not been compared against a baseline; run "
            "`python3 -m argazui compare <run> --baseline <run>` to produce it")


def _scenario_reason(result: dict, directory: Path) -> str:
    if not (result.get("procedures") or []):
        return ("no procedure ran during this session, so there is no flow to "
                "record verbatim")
    return "no reason was recorded"


# The catalogue. Ordered as a reviewer reads a run: what ran, what it did, what
# the autopilot recorded, what was made of it.
CATALOGUE: list[Artefact] = [
    Artefact("result", "result.json", "application/json", REQUIRED,
             "argazui.runs", "the run's own record: steps, criteria, verdict",
             schema_of=_result_schema, hashed=False),
    Artefact("scenario", "scenario.yaml", "text/yaml", REQUIRED,
             "argazui.runs",
             "the procedures that were executed, byte for byte",
             why=_scenario_reason),
    Artefact("console", "console.log", "text/plain", REQUIRED,
             "argazui.runs", "what the simulation terminal showed"),
    Artefact("mavlink_events", "mavlink_events.jsonl", "application/x-ndjson",
             REQUIRED, "argazui.runs",
             "modes, arm/disarm, ACKs, autopilot messages and a 1 Hz state sample"),
    Artefact("versions", "versions.txt", "text/plain", REQUIRED,
             "argazui.versions", "the software this run was produced with"),
    Artefact("fingerprint", "fingerprint.json", "application/json", REQUIRED,
             "argazui.fingerprint",
             "what produced this result, in a form a comparison can line up",
             schema_of=_fingerprint_schema),

    Artefact("dataflash", "", "application/octet-stream", CONDITIONAL,
             "ardupilot", "the autopilot's own log, at full rate",
             condition=_armed, why=_dataflash_reason),

    Artefact("report_json", "report.json", "application/json", OPTIONAL,
             "argazui.flightlog", "the post-flight analysis, machine-readable",
             schema_of=_report_schema, why=_report_reason),
    Artefact("report_md", "report.md", "text/markdown", OPTIONAL,
             "argazui.flightlog", "the post-flight analysis, for a person",
             why=_report_reason),
    Artefact("params_full", "params_full.txt", "text/plain", OPTIONAL,
             "argazui.flightlog", "every parameter, taken from the log",
             why=_report_reason),
    Artefact("params_diff", "params_diff.txt", "text/plain", OPTIONAL,
             "argazui.flightlog",
             "the parameters that differ from the firmware default",
             why=_report_reason),
    Artefact("plots", "plots/", "directory", OPTIONAL,
             "argazui.flightlog", "altitude and attitude-tracking figures",
             why=_plots_reason),
    Artefact("regression_json", "regression.json", "application/json", OPTIONAL,
             "argazui.regression", "this run measured against a named baseline",
             schema_of=_regression_schema, why=_regression_reason),
    Artefact("regression_md", "regression.md", "text/markdown", OPTIONAL,
             "argazui.regression", "the same comparison, for a person",
             why=_regression_reason),
]

BY_NAME = {artefact.name: artefact for artefact in CATALOGUE}


# ------------------------------------------------------------------- capture
def _describe(directory: Path, artefact: Artefact, relative: str,
              result: dict) -> dict:
    path = directory / relative if relative else None
    exists = bool(path and (path.is_dir() if artefact.kind == "directory"
                            else path.is_file()))

    row: dict[str, Any] = {
        "name": artefact.name,
        "path": relative,
        "type": artefact.kind,
        "level": artefact.level,
        "purpose": artefact.purpose,
        "producer": artefact.producer,
        "producer_schema": None,
        "exists": exists,
        "size_bytes": None,
        "hash": None,
        "hash_absent_reason": "",
        "absent_reason": "",
    }
    try:
        row["producer_schema"] = artefact.schema_of() if artefact.schema_of else None
    except Exception:                             # pragma: no cover - import guard
        row["producer_schema"] = None

    if not exists:
        if artefact.level == OPTIONAL or artefact.level == CONDITIONAL:
            row["absent_reason"] = (artefact.why(result, directory)
                                    if artefact.why else "")
        return row

    if artefact.kind == "directory":
        files = sorted(p for p in path.iterdir() if p.is_file())
        row["size_bytes"] = sum(p.stat().st_size for p in files)
        row["contains"] = [f"{relative}{p.name}" for p in files]
        # A directory that exists and is empty is absence wearing a folder.
        if not files:
            row["exists"] = False
            row["absent_reason"] = (artefact.why(result, directory)
                                    if artefact.why else "")
        return row

    row["size_bytes"] = path.stat().st_size
    if artefact.hashed:
        row["hash"], row["hash_absent_reason"] = _sha256(path)
    else:
        row["hash_absent_reason"] = SELF_DESCRIBING
    return row


def capture(directory: Path, result: dict) -> dict:
    """The manifest for one run directory.

    Reads the directory rather than trusting the run record: the point of the
    manifest is to catch the case where the record says an artefact was written
    and it is not there.
    """
    directory = Path(directory)
    rows: list[dict] = []

    for artefact in CATALOGUE:
        relative = artefact.path
        if artefact.name == "dataflash":
            relative = (result.get("artefacts") or {}).get("dataflash") or ""
            if not relative:
                found = sorted(directory.glob("*.BIN"))
                relative = found[0].name if found else ""
        required_here = artefact.level
        if artefact.level == CONDITIONAL:
            holds = artefact.condition(result) if artefact.condition else True
            required_here = REQUIRED if holds else OPTIONAL
        row = _describe(directory, artefact, relative, result)
        # The level as APPLIED to this run, beside the level as declared. A
        # reviewer needs both: "required because the vehicle armed" and
        # "required always" are different statements about the same row.
        row["level_declared"] = artefact.level
        row["level"] = required_here
        rows.append(row)

    missing = [row["name"] for row in rows
               if row["level"] == REQUIRED and not row["exists"]]
    unexplained = [row["name"] for row in rows
                   if row["level"] == OPTIONAL and not row["exists"]
                   and not row["absent_reason"]]

    return {
        "schema": SCHEMA,
        "run_id": result.get("run_id") or directory.name,
        "artefacts": rows,
        "counts": {
            "expected": len(rows),
            "present": sum(1 for row in rows if row["exists"]),
            "missing_required": len(missing),
            "absent_explained": sum(1 for row in rows if not row["exists"]
                                    and row["absent_reason"]),
            "absent_unexplained": len(unexplained),
        },
        "missing_required": missing,
        "absent_unexplained": unexplained,
        # The one line a reviewer reads first. False means at least one thing
        # this run's claims rest on is not in the directory.
        "complete": not missing,
    }


def write(directory: Path, manifest: dict) -> Path:
    path = Path(directory) / FILENAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def read(directory: Path) -> dict:
    """A stored manifest, or an empty one for a run recorded before v1.5."""
    try:
        return json.loads((Path(directory) / FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def problems(manifest: dict) -> list[dict]:
    """What a reviewer should be told about this run's evidence."""
    out: list[dict] = []
    for row in manifest.get("artefacts") or []:
        if row["exists"]:
            continue
        if row["level"] == REQUIRED:
            out.append({"problem": "missing-required", "artefact": row["name"],
                        "path": row["path"],
                        "detail": row.get("absent_reason")
                                  or f"{row['purpose']} — nothing was written"})
        elif not row.get("absent_reason"):
            out.append({"problem": "absent-unexplained", "artefact": row["name"],
                        "path": row["path"],
                        "detail": "optional, and absent with no stated reason"})
    return out


def for_report(manifest: dict) -> dict:
    """The manifest as the flight report embeds it — everything but the hashes.

    WHY THE HASHES ARE LEFT OUT OF THE REPORT
    -----------------------------------------
    `report.json` and `report.md` are themselves artefacts the manifest
    describes, so a manifest embedded in them is taken before their final
    write. Keeping the hashes here would mean two documents disagreeing about
    the digest of a third, and the disagreement would be an artefact of the
    order they were written in rather than of anything being wrong.

    So the digests live in exactly one place — `evidence.json`, captured last —
    and what the report carries is everything a reader needs to see whether the
    evidence is complete: the paths, the levels, what is present, and why
    anything absent is absent. None of that changes between the two captures.
    """
    if not manifest:
        return {}
    return {
        **{key: value for key, value in manifest.items() if key != "artefacts"},
        "hashes_in": FILENAME,
        "artefacts": [
            {key: value for key, value in row.items()
             if key not in ("hash", "hash_absent_reason")}
            for row in manifest.get("artefacts") or []
        ],
    }


def render(manifest: dict) -> list[str]:
    """The manifest as report.md renders it. Returns markdown lines."""
    lines: list[str] = []
    if not manifest:
        return ["No evidence manifest was written for this run.", ""]

    counts = manifest["counts"]
    lines += [
        f"{counts['present']} of {counts['expected']} expected artefacts are "
        f"present. "
        + ("**Every required artefact is here.**" if manifest["complete"]
           else f"**{counts['missing_required']} required artefact(s) are "
                f"missing** — the claims below rest on evidence that is not in "
                f"this directory."),
        "",
    ]
    has_hashes = any("hash" in row for row in manifest.get("artefacts") or [])
    lines += [
        ("| Artefact | Level | Present | Size | Hash | Produced by |"
         if has_hashes else "| Artefact | Level | Present | Size | Produced by |"),
        ("|---|---|---|---:|---|---|" if has_hashes
         else "|---|---|---|---:|---|"),
    ]
    for row in manifest["artefacts"]:
        size = "—" if row["size_bytes"] is None else f"{row['size_bytes']:,} B"
        producer = row["producer"] + (f" (schema {row['producer_schema']})"
                                      if row["producer_schema"] is not None else "")
        present = "yes" if row["exists"] else (
            "**NO**" if row["level"] == REQUIRED else "no")
        note = ""
        if not row["exists"]:
            note = (f"<br><sub>{row['absent_reason']}</sub>"
                    if row["absent_reason"]
                    else "<br><sub>**no reason recorded**</sub>")
        columns = [f"| `{row['path'] or row['name']}`"
                   f"<br><sub>{row['purpose']}</sub> ",
                   f"| {row['level']} | {present}{note} | {size} "]
        if "hash" in row:
            digest = row["hash"][:23] + "…" if row["hash"] else (
                f"*{row['hash_absent_reason']}*"
                if row["hash_absent_reason"] else "—")
            columns.append(f"| {digest} ")
        columns.append(f"| {producer} |")
        lines.append("".join(columns))
    lines.append("")
    if manifest.get("hashes_in"):
        lines.append(
            f"Content hashes are in `{manifest['hashes_in']}`, which is written "
            f"after this report and is the authority on them. They are not "
            f"repeated here: this document is one of the artefacts they cover, "
            f"so a copy taken before its own last write would disagree with "
            f"the real one for no reason but the order the two were written "
            f"in.")
        lines.append("")
    lines.append(
        "An **optional** artefact that is absent is only acceptable with a "
        "stated reason. One absent without one is listed as such: \"there are "
        "no plots because matplotlib is not installed\" and \"there are no "
        "plots\" are different facts, and only the first is an answer.")
    lines.append("")
    return lines
