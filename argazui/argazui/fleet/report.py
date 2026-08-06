"""`fleet_report.md` — a run explaining itself, including what it did not prove.

THE SECTION THAT MATTERS MOST IS THE ONE ABOUT ABSENCES
-------------------------------------------------------
A report is read for its verdict, and a verdict is read as "it worked". So the
easiest way for this file to lie is by omission: six criteria, four ticks and
two blanks, reads as a good run to anyone skimming.

Every report therefore carries an explicit section — **"What this run did not
claim"** — naming in plain words each criterion that could not be evaluated
and why. If a run measured nothing, that section is the report.

EVERY CLAIM NAMES WHAT AUTHORISED IT
------------------------------------
Separation was allowed to speak because the world-pose message carries every
model's position under one stamp, not because Gazebo happened to be running.
That distinction is the whole of phase 5, and it is worthless if a reader
cannot see it without opening the source. Each criterion carries its
`authorised_by` line into the report.

VERSIONS COME FROM `versions.environment()` AND NOWHERE ELSE
------------------------------------------------------------
There is exactly one answer to "which software produced this result", and
`versions.py` is it. v1.1 phase 3 had two, they disagreed, and no two runs
could be compared. This module reads that record; it does not assemble a
second one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import criteria as crit

SCHEMA_VERSION = 1

_MARK = {crit.PASSED: "PASS", crit.FAILED: "FAIL",
         crit.NOT_MEASURED: "NOT MEASURED"}


def _table(rows: list, headers: list) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|")
                                     for c in row) + " |")
    return "\n".join(out)


def render(spec, criteria: list, *, run_id: str = "",
           environment: Optional[dict] = None,
           teardown=None, commands: Optional[list] = None,
           wiring: Optional[dict] = None,
           allocation=None,
           timeline_events: int = 0) -> str:
    """The human-readable summary of one fleet run."""
    from .. import versions

    environment = environment if environment is not None else versions.environment()
    verdict = crit.fleet_verdict(criteria)
    unmeasured = [c for c in criteria if c.outcome == crit.NOT_MEASURED]
    failed = [c for c in criteria if c.outcome == crit.FAILED]

    lines: list = []
    lines.append(f"# Fleet run — {spec.name}")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")

    if verdict == crit.FLEET_INCOMPLETE:
        lines.append("> INCOMPLETE is not a pass. Everything that was measured "
                     "held, but at least one criterion could not be evaluated, "
                     "so this run has not been tested against it. See "
                     "*What this run did not claim*.")
        lines.append("")
    elif verdict == crit.FLEET_FAILED:
        lines.append(f"> {len(failed)} criterion/criteria did not hold. The "
                     f"detail column says what was measured, not merely that "
                     f"a limit was crossed.")
        lines.append("")

    # ---------------------------------------------------- unverified models
    if getattr(spec, "allow_unverified", False):
        lines.append("## ⚠ Unverified models were allowed")
        lines.append("")
        lines.append(f"This fleet ran with `allow_unverified = true`. Stated "
                     f"reason:")
        lines.append("")
        lines.append(f"> {spec.unverified_reason or '(none given)'}")
        lines.append("")
        lines.append("At least one model in this fleet has not passed tier 2, "
                     "so nothing here is evidence that it works.")
        lines.append("")

    # ---------------------------------------------------------- the fleet
    lines.append("## The fleet")
    lines.append("")
    rows = [[v.id, v.sysid, v.model or v.frame or "?", v.role or "—",
             (f"{v.spawn.east_m:g} E, {v.spawn.north_m:g} N"
              if v.spawn else "—")]
            for v in spec.vehicles]
    lines.append(_table(rows, ["vehicle", "sysid", "model/frame", "role",
                               "spawn"]))
    lines.append("")
    lines.append(f"- world: `{spec.world or 'none (SITL-only)'}`")
    lines.append(f"- formation: `{spec.formation}`")
    lines.append(f"- run id: `{run_id or '(unset)'}`")
    if allocation is not None:
        ports = ", ".join(f"{v.vehicle_id}→{v.serial0_port}/{v.fdm_port}"
                          for v in allocation.vehicles)
        lines.append(f"- ports (SERIAL0/FDM): {ports}")
    lines.append("")

    # ------------------------------------------------------------ criteria
    lines.append("## Acceptance criteria")
    lines.append("")
    lines.append("Threshold criteria are judged on **seconds spent outside** "
                 "the band against a declared tolerance, never on the worst "
                 "single sample. A peak is one sample; duration is the signal.")
    lines.append("")
    rows = [[_MARK[c.outcome], c.title, c.detail or c.reason or "—"]
            for c in criteria]
    lines.append(_table(rows, ["", "criterion", "what was measured"]))
    lines.append("")

    # ------------------------------------------- what authorised each claim
    authorised = [c for c in criteria if c.authorised_by]
    if authorised:
        lines.append("### What authorised each claim")
        lines.append("")
        for c in authorised:
            lines.append(f"- **{c.title}** — {c.authorised_by}")
        lines.append("")

    # ------------------------------------------------ the absences, in words
    lines.append("## What this run did not claim")
    lines.append("")
    if not unmeasured:
        lines.append("Every criterion was evaluated. Nothing was left "
                     "unmeasured.")
    else:
        lines.append("The following could not be evaluated. They are **not** "
                     "passes, and nothing below should be read as evidence "
                     "about them:")
        lines.append("")
        for c in unmeasured:
            lines.append(f"- **{c.title}** — {c.reason}")
    lines.append("")

    # ------------------------------------------------------------- wiring
    if wiring is not None:
        lines.append("## Cross-wiring check")
        lines.append("")
        lines.append("Ran before any acceptance criterion. Proves each "
                     "autopilot drives its own model — without it, every "
                     "measurement could describe a fleet that does not exist.")
        lines.append("")
        lines.append(f"**{'PASS' if wiring.get('ok') else 'FAIL'}** — "
                     f"{wiring.get('reason', '')}")
        lines.append("")
        checks = wiring.get("checks") or []
        if checks:
            rows = [[c["vehicle"], f"{c['moved_m']:.2f} m",
                     ", ".join(f"{k} {v:.2f} m"
                               for k, v in sorted(c["others"].items())) or "—"]
                    for c in checks]
            lines.append(_table(rows, ["commanded", "it moved",
                                       "every other model moved"]))
            lines.append("")

    # ----------------------------------------------------------- commands
    if commands:
        lines.append("## Group commands")
        lines.append("")
        lines.append("An ACK is not a result. Every row carries both the "
                     "acknowledgement and whether the state it should produce "
                     "still held afterwards.")
        lines.append("")
        for result in commands:
            document = result if isinstance(result, dict) else result.as_dict()
            lines.append(f"### `{document['command']}` — "
                         f"{document['verdict']} "
                         f"(policy `{document['policy']}`)")
            lines.append("")
            rows = [[r["vehicle"], r["outcome"], r["ack"] or "—",
                     f"{r['t_ms']} ms",
                     (r["reason"] or r["observed"] or "—")[:120]]
                    for r in document["results"]]
            lines.append(_table(rows, ["vehicle", "outcome", "ack", "t",
                                       "detail"]))
            lines.append("")

    # ----------------------------------------------------------- teardown
    if teardown is not None:
        document = teardown if isinstance(teardown, dict) else teardown.as_dict()
        lines.append("## Teardown")
        lines.append("")
        lines.append(f"- orphan processes: {document.get('orphans') or 'none'}")
        lines.append(f"- port lease released: "
                     f"{document.get('lease_released')}")
        lines.append(f"- simulation server: {document.get('sim_server', '—')}")
        lines.append("")

    # ------------------------------------------------------ reproducibility
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("From `versions.environment()`, the one canonical record of "
                 "which software produced a result.")
    lines.append("")
    lines.append(_table([[k, v] for k, v in sorted(environment.items())],
                        ["", ""]))
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"Generated "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} "
                 f"from {timeline_events} recorded events. "
                 f"A fleet run says nothing about whether any MODEL is "
                 f"supported — `docs/status.md` reads model rows from tier-2 "
                 f"tests alone.")
    lines.append("")
    return "\n".join(lines)


def write(path: Path, *args, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(*args, **kwargs), encoding="utf-8")
    return path
