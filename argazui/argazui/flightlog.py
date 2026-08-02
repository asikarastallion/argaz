"""Post-flight analysis of an ArduPilot dataflash (.BIN) log.

WHY THE LOG AND NOT THE LINK
----------------------------
Everything this module reports could in principle be gathered live over
MAVLink, and v1.0 would have had to. It is read from the dataflash instead for
three reasons:

  * The autopilot writes the log itself, at full internal rate. A telemetry
    stream is a lossy 4 Hz summary of it.
  * `PARM` records carry both the value AND the firmware default, so
    "different from default" is a fact the vehicle states rather than a guess
    ArgazUI would have to make from the model's `.param` files.
  * It costs nothing at STOP time. Dumping ~1400 parameters over MAVLink would
    add ten seconds to every shutdown.

The single pass below therefore produces the parameter files, the report and
the plots together — the log is only read once.

THRESHOLDS
----------
Every warning threshold is named in `THRESHOLDS` with the ArduPilot page it
comes from. Nothing here decides that a flight was "good"; it reports measured
numbers and flags the ones ArduPilot's own documentation calls out.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pymavlink import mavutil
from pymavlink.DFReader import DFReader_binary

# ArduPilot libraries/AP_Logger/AP_Logger.h, enum class LogEvent.
# Only the events that matter for a takeoff/landing report are named; an
# unknown id is reported as its number rather than dropped.
LOG_EVENTS = {
    10: "ARMED", 11: "DISARMED", 15: "AUTO_ARMED",
    17: "LAND_COMPLETE_MAYBE", 18: "LAND_COMPLETE", 19: "LOST_GPS",
    25: "SET_HOME", 28: "NOT_LANDED", 38: "SAVE_TRIM",
    41: "FENCE_ENABLE", 42: "FENCE_DISABLE",
    54: "MOTORS_EMERGENCY_STOPPED", 55: "MOTORS_EMERGENCY_STOP_CLEARED",
    56: "MOTORS_INTERLOCK_DISABLED", 57: "MOTORS_INTERLOCK_ENABLED",
    60: "EKF_ALT_RESET", 62: "EKF_YAW_RESET",
    76: "FENCE_ALT_MAX_ENABLE", 77: "FENCE_ALT_MAX_DISABLE",
    78: "FENCE_CIRCLE_ENABLE", 79: "FENCE_CIRCLE_DISABLE",
    80: "FENCE_ALT_MIN_ENABLE", 81: "FENCE_ALT_MIN_DISABLE",
    82: "FENCE_POLYGON_ENABLE", 83: "FENCE_POLYGON_DISABLE",
}

ARMED_EVENT, DISARMED_EVENT = 10, 11

THRESHOLDS = {
    # https://ardupilot.org/copter/docs/common-measuring-vibration.html
    # "below 30m/s/s is normally acceptable", clipping should be zero.
    "vibe_ms2": 30.0,
    # https://ardupilot.org/copter/docs/common-apm-navigation-extended-kalman-filter-overview.html
    # The XKF4 S* fields are normalised innovation test ratios: below 1.0 the
    # measurement is being accepted, and the EKF failsafe trips around 0.8.
    "ekf_test_ratio": 0.8,
    # Attitude tracking. Not an ArduPilot constant — a review trigger: more
    # than this between demanded and achieved attitude in flight is worth a
    # human look at the tuning.
    "attitude_error_deg": 15.0,
}

# Anything matching these in a STATUSTEXT/MSG record is surfaced in the report
# instead of being buried in a few hundred routine boot messages.
NOTABLE_MESSAGE_HINTS = (
    "error", "fail", "unhealthy", "warning", "bad ", "lost", "failsafe",
    "prearm", "arm:", "crash", "emergency", "glitch", "reset", "inconsistent",
)

MAX_SERIES_POINTS = 600      # report.json stays readable and small


def _mode_names(firmware: str, mav_type: Optional[int]) -> dict:
    """Mode number -> name, chosen the same way `mavlink_link` chooses it.

    The firmware string is preferred over MAV_TYPE for the reason documented in
    mavlink_link._mode_table(): some models report a MAV_TYPE that belongs to a
    different mode table than the firmware they actually run.
    """
    if "ArduCopter" in firmware or "APM:Copter" in firmware:
        return dict(mavutil.mode_mapping_acm)
    if "ArduPlane" in firmware or "APM:Plane" in firmware:
        return dict(mavutil.mode_mapping_apm)
    if mav_type is not None:
        table = mavutil.mode_mapping_bynumber(mav_type)
        if table:
            return dict(table)
    return {}


def _downsample(series: list, limit: int = MAX_SERIES_POINTS) -> list:
    if len(series) <= limit:
        return series
    step = len(series) / float(limit)
    return [series[int(i * step)] for i in range(limit)]


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    return {"min": round(min(values), 3), "max": round(max(values), 3),
            "mean": round(sum(values) / len(values), 3), "samples": len(values)}


class _Collector:
    """One pass over the log; every series it needs is gathered here."""

    def __init__(self) -> None:
        self.params: dict[str, tuple[float, Optional[float]]] = {}
        self.modes: list[dict] = []
        self.events: list[dict] = []
        self.messages: list[dict] = []
        self.firmware = ""
        self.mav_type: Optional[int] = None
        self.alt: list[tuple[float, float]] = []      # (t, relative alt m)
        self.att: list[tuple[float, float, float, float, float]] = []
        self.vibe: list[tuple[float, float, float, float, int]] = []
        self.ekf: list[tuple[float, float, float, float, float, float]] = []
        self.bat: list[tuple[float, float, float, float]] = []
        self.t0: Optional[float] = None
        self.t_end: float = 0.0
        self.counts: dict[str, int] = {}

    def _t(self, msg) -> float:
        us = getattr(msg, "TimeUS", None)
        if us is None:
            return self.t_end
        seconds = us / 1e6
        if self.t0 is None:
            self.t0 = seconds
        self.t_end = max(self.t_end, seconds - self.t0)
        return seconds - self.t0

    def absorb(self, msg) -> None:
        kind = msg.get_type()
        self.counts[kind] = self.counts.get(kind, 0) + 1

        if kind == "PARM":
            self.params[msg.Name] = (msg.Value, getattr(msg, "Default", None))
        elif kind == "VER":
            self.firmware = getattr(msg, "FWS", "") or self.firmware
        elif kind == "MODE":
            self._t(msg)
            self.modes.append({"t": round(self._t(msg), 2),
                               "number": int(msg.ModeNum),
                               "reason": int(getattr(msg, "Rsn", 0))})
        elif kind == "EV":
            self.events.append({"t": round(self._t(msg), 2), "id": int(msg.Id),
                                "name": LOG_EVENTS.get(int(msg.Id), f"EVENT_{msg.Id}")})
        elif kind == "MSG":
            text = str(msg.Message).strip()
            if not self.firmware and ("ArduPlane" in text or "ArduCopter" in text):
                self.firmware = text
            self.messages.append({"t": round(self._t(msg), 2), "text": text})
        elif kind == "POS":
            self.alt.append((self._t(msg), float(msg.RelHomeAlt)))
        elif kind == "CTUN":
            # Fallback altitude source. POS.RelHomeAlt is preferred and both
            # vehicles log it; CTUN.Alt is used only if POS is absent, which
            # happens when a log is cut before the EKF sets an origin.
            if not self.alt:
                alt = getattr(msg, "Alt", None)
                if alt is not None:
                    self.alt.append((self._t(msg), float(alt)))
        elif kind == "ATT":
            self.att.append((self._t(msg), float(msg.DesRoll), float(msg.Roll),
                             float(msg.DesPitch), float(msg.Pitch)))
        elif kind == "VIBE":
            self.vibe.append((self._t(msg), float(msg.VibeX), float(msg.VibeY),
                              float(msg.VibeZ), int(getattr(msg, "Clip", 0))))
        elif kind in ("XKF4", "NKF4"):
            self.ekf.append((self._t(msg), float(msg.SV), float(msg.SP),
                             float(msg.SH), float(msg.SM), float(msg.SVT)))
        elif kind == "BAT":
            self.bat.append((self._t(msg), float(msg.Volt), float(msg.Curr),
                             float(getattr(msg, "CurrTot", 0.0))))


def _armed_intervals(events: list[dict], end: float) -> list[dict]:
    """Turns ARMED/DISARMED events into closed intervals.

    Two edges matter and both happen routinely:

      * With the default LOG_DISARMED=0 the log *begins* at arming, and the
        ARMED event can land before the first record. A DISARMED with nothing
        open therefore means "armed since the start of the log", not a stray
        event to drop — reporting zero armed time for a flight that clearly
        flew would be worse than useless.
      * Stopping a model while it is still flying leaves the last interval
        open. It is closed at the end of the log and marked as such.
    """
    out: list[dict] = []
    start: Optional[float] = None
    open_since_start = False
    for ev in events:
        if ev["id"] == ARMED_EVENT and start is None:
            start = ev["t"]
        elif ev["id"] == DISARMED_EVENT:
            if start is None:
                start, open_since_start = 0.0, True
            out.append({"armed_at": start, "disarmed_at": ev["t"],
                        "seconds": round(ev["t"] - start, 1), "closed": True,
                        "armed_before_log": open_since_start})
            start, open_since_start = None, False
    if start is not None:
        out.append({"armed_at": start, "disarmed_at": round(end, 2),
                    "seconds": round(end - start, 1), "closed": False,
                    "armed_before_log": False})
    return out


def _write_params(collector: _Collector, out_dir: Path) -> dict:
    """Writes params_full.txt and params_diff.txt from the logged PARM records.

    `params_diff.txt` compares against the firmware default the autopilot
    records alongside each value, so it is a real "differs from default" list
    and not a diff against whichever `.param` file happened to be loaded.
    """
    full = out_dir / "params_full.txt"
    diff = out_dir / "params_diff.txt"
    names = sorted(collector.params)

    lines = ["# Full parameter set as recorded by the autopilot in its dataflash log.",
             "# Format: NAME,VALUE — loadable by MAVProxy/Mission Planner.",
             f"# {len(names)} parameters.", ""]
    for name in names:
        lines.append(f"{name},{collector.params[name][0]:.6g}")
    full.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _has_default(default: Optional[float]) -> bool:
        # A NaN default is the autopilot saying "this one has no meaningful
        # default" — BARO*_GND_PRESS is calibrated at boot, for instance.
        # Comparing against NaN always says "differs", which would fill the
        # diff with parameters that cannot differ from anything.
        return default is not None and not math.isnan(default)

    changed = [(n, v, d) for n, (v, d) in ((n, collector.params[n]) for n in names)
               if _has_default(d) and not math.isclose(v, d, rel_tol=1e-9, abs_tol=1e-9)]
    unknown = [n for n in names if not _has_default(collector.params[n][1])]

    dlines = ["# Parameters whose value differs from this firmware's built-in default.",
              "# The default column is the autopilot's own PARM.Default field, so this",
              "# is the vehicle's statement about itself — not a diff against a .param",
              "# file. Every difference here comes from the model's parameter files, an",
              "# ArgazUI run-scoped set_param, or the autopilot writing a value itself.",
              "",
              f"# {len(changed)} of {len(names)} parameters differ from default.", ""]
    if changed:
        width = max(len(n) for n, _, _ in changed)
        dlines.append(f"# {'NAME'.ljust(width)}  {'VALUE':>14}  {'DEFAULT':>14}")
        for name, value, default in changed:
            dlines.append(f"{name.ljust(width)}  {value:>14.6g}  {default:>14.6g}")
    if unknown:
        dlines += ["", f"# {len(unknown)} parameter(s) have no comparable default "
                       f"(calibrated at boot, or logged without one):",
                   "# " + ", ".join(unknown)]
    diff.write_text("\n".join(dlines) + "\n", encoding="utf-8")

    return {"total": len(names), "non_default": len(changed),
            "without_default": len(unknown),
            "files": {"full": full.name, "diff": diff.name}}


def _plots(collector: _Collector, modes: list[dict], intervals: list[dict],
           out_dir: Path) -> list[str]:
    """Altitude and attitude-tracking PNGs.

    matplotlib is optional on purpose: it is not in requirements.txt, and a
    machine without it still gets the complete report — only the two pictures
    are missing, and the report says so.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def _decorate(ax) -> None:
        for interval in intervals:
            ax.axvspan(interval["armed_at"], interval["disarmed_at"],
                       color="#4da3ff", alpha=0.10, lw=0)
        for change in modes:
            ax.axvline(change["t"], color="#8894a6", lw=0.8, ls=":")
            ax.annotate(change["name"], (change["t"], 1.01), xycoords=("data", "axes fraction"),
                        fontsize=7, rotation=90, color="#5a6472", va="bottom")
        ax.grid(alpha=0.25)
        ax.set_xlabel("time since log start (s)")

    # Mode labels are drawn just above the axes, so titles need room or they
    # land on top of them.
    title_pad = 26

    if collector.alt:
        fig, ax = plt.subplots(figsize=(10, 3.4), dpi=110)
        ax.plot([t for t, _ in collector.alt], [a for _, a in collector.alt],
                color="#1f7a4d", lw=1.4)
        ax.set_ylabel("altitude above home (m)")
        ax.set_title("Altitude profile", pad=title_pad)
        _decorate(ax)
        fig.tight_layout()
        path = plot_dir / "altitude.png"
        fig.savefig(path)
        plt.close(fig)
        written.append(f"plots/{path.name}")

    if collector.att:
        fig, axes = plt.subplots(2, 1, figsize=(10, 5.2), dpi=110, sharex=True)
        times = [row[0] for row in collector.att]
        for ax, (desired, actual, label) in zip(
                axes, ((1, 2, "roll"), (3, 4, "pitch"))):
            ax.plot(times, [row[desired] for row in collector.att],
                    color="#b0431f", lw=1.0, label=f"desired {label}")
            ax.plot(times, [row[actual] for row in collector.att],
                    color="#1f5fb0", lw=1.2, label=f"actual {label}")
            ax.set_ylabel(f"{label} (deg)")
            ax.legend(fontsize=8, loc="upper right")
            _decorate(ax)
        axes[0].set_title("Demanded vs achieved attitude", pad=title_pad)
        axes[0].set_xlabel("")
        fig.tight_layout()
        path = plot_dir / "attitude.png"
        fig.savefig(path)
        plt.close(fig)
        written.append(f"plots/{path.name}")

    return written


def _markdown(report: dict) -> str:
    """Renders report.json as the human-readable report.md."""
    out: list[str] = []
    add = out.append
    meta = report.get("meta") or {}

    add(f"# Flight report — {meta.get('run_id') or report['log']['file']}")
    add("")
    add(f"Generated {report['generated_utc']} by ArgazUI {meta.get('argazui_version', '?')}.")
    add("")

    add("## Flight")
    add("")
    add("| | |")
    add("|---|---|")
    if meta.get("model_name"):
        add(f"| Model | {meta['model_name']} (`{meta.get('model_id', '')}`) |")
    if meta.get("procedures"):
        add(f"| Procedures | {', '.join(meta['procedures'])} |")
    add(f"| Firmware | {report['log']['firmware'] or 'unknown'} |")
    add(f"| Log | `{report['log']['file']}` ({report['log']['size_bytes'] / 1e6:.1f} MB) |")
    add(f"| Log duration | {report['log']['seconds']:.1f} s |")
    add(f"| Armed time | {report['armed']['total_seconds']:.1f} s "
        f"over {len(report['armed']['intervals'])} interval(s) |")
    alt = report["altitude"]
    add(f"| Maximum altitude | {alt.get('max', 0):.1f} m above home |" if alt
        else "| Maximum altitude | not logged |")
    add("")

    warnings = report["warnings"]
    add("## Verdict")
    add("")
    if warnings:
        add(f"{len(warnings)} item(s) flagged for review:")
        add("")
        for item in warnings:
            add(f"- **{item['what']}** — {item['detail']} "
                f"(threshold {item['threshold']}, source: {item['source']})")
    else:
        add("Nothing crossed a review threshold. Vibration, EKF innovation test "
            "ratios, attitude tracking and battery stayed inside the limits listed "
            "under *Thresholds* below.")
    add("")

    add("## Mode timeline")
    add("")
    if report["modes"]:
        add("| t (s) | mode | reason code |")
        add("|---:|---|---:|")
        for change in report["modes"]:
            add(f"| {change['t']:.1f} | {change['name']} | {change['reason']} |")
    else:
        add("No MODE records in this log.")
    add("")

    add("## Arm / disarm")
    add("")
    if report["armed"]["intervals"]:
        add("| armed at (s) | disarmed at (s) | duration (s) | |")
        add("|---:|---:|---:|---|")
        for interval in report["armed"]["intervals"]:
            note = ""
            if interval.get("armed_before_log"):
                note = "armed before logging started (LOG_DISARMED=0)"
            elif not interval["closed"]:
                note = "still armed at the end of the log"
            add(f"| {interval['armed_at']:.1f} | {interval['disarmed_at']:.1f} "
                f"| {interval['seconds']:.1f} | {note} |")
    else:
        add("The vehicle never armed in this log.")
    add("")

    add("## Measurements")
    add("")
    add("| Quantity | Value |")
    add("|---|---|")
    if alt:
        add(f"| Altitude above home | max {alt['max']:.1f} m, min {alt['min']:.1f} m, "
            f"mean {alt['mean']:.1f} m |")
    att = report["attitude_error"]
    if att:
        add(f"| Roll error (desired − actual) | max {att['roll_max']:.1f}°, "
            f"RMS {att['roll_rms']:.1f}° |")
        add(f"| Pitch error (desired − actual) | max {att['pitch_max']:.1f}°, "
            f"RMS {att['pitch_rms']:.1f}° |")
    vibe = report["vibration"]
    if vibe:
        add(f"| Vibration | X {vibe['x_max']:.1f}, Y {vibe['y_max']:.1f}, "
            f"Z {vibe['z_max']:.1f} m/s/s peak; {vibe['clip_total']} clipping event(s) |")
    ekf = report["ekf"]
    if ekf:
        add(f"| EKF test ratios (peak) | velocity {ekf['sv_max']:.2f}, "
            f"position {ekf['sp_max']:.2f}, height {ekf['sh_max']:.2f}, "
            f"magnetometer {ekf['sm_max']:.2f}, airspeed {ekf['svt_max']:.2f} |")
    bat = report["battery"]
    if bat:
        add(f"| Battery | {bat['volt_start']:.2f} V → {bat['volt_end']:.2f} V "
            f"(min {bat['volt_min']:.2f} V), {bat['consumed_mah']:.0f} mAh consumed |")
    add("")

    params = report.get("params") or {}
    if params:
        add("## Parameters")
        add("")
        add(f"{params['non_default']} of {params['total']} parameters differ from the "
            f"firmware default — see [`{params['files']['diff']}`]"
            f"({params['files']['diff']}). The complete set is in "
            f"[`{params['files']['full']}`]({params['files']['full']}).")
        add("")

    if report["notable_messages"]:
        add("## Autopilot messages worth reading")
        add("")
        for message in report["notable_messages"]:
            add(f"- `{message['t']:.1f}s` {message['text']}")
        add("")

    if report["plots"]:
        add("## Plots")
        add("")
        for plot in report["plots"]:
            add(f"![{Path(plot).stem}]({plot})")
            add("")
    else:
        add("## Plots")
        add("")
        add("No plots were produced — matplotlib is not installed in the interpreter "
            "that generated this report. It is an optional dependency; everything "
            "above comes from the log itself.")
        add("")

    add("## Thresholds")
    add("")
    add("| Quantity | Threshold | Source |")
    add("|---|---:|---|")
    add(f"| Vibration (any axis) | {THRESHOLDS['vibe_ms2']:.0f} m/s/s | "
        "ardupilot.org — Measuring Vibration |")
    add(f"| EKF innovation test ratio | {THRESHOLDS['ekf_test_ratio']:.1f} | "
        "ardupilot.org — EKF overview (failsafe region) |")
    add(f"| Attitude tracking error | {THRESHOLDS['attitude_error_deg']:.0f}° | "
        "ArgazUI review trigger, not an ArduPilot limit |")
    add("")

    add("## Open this log yourself")
    add("")
    add("```")
    add(f"MAVExplorer.py {report['log']['file']}")
    add("```")
    add("")
    return "\n".join(out)


def analyse(bin_path: Path, out_dir: Optional[Path] = None,
            meta: Optional[dict] = None, plots: bool = True) -> dict:
    """Reads one dataflash log and writes report.json, report.md and the params files.

    Returns the report dictionary. Raises OSError if the log cannot be read;
    a truncated log (the normal result of killing SITL) is not an error — the
    reader stops at the last complete record and the report covers what was
    written.
    """
    bin_path = Path(bin_path)
    out_dir = Path(out_dir) if out_dir else bin_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = DFReader_binary(str(bin_path))
    collector = _Collector()
    while True:
        try:
            msg = reader.recv_msg()
        except Exception:
            break                      # truncated tail — keep what was parsed
        if msg is None:
            break
        collector.absorb(msg)

    collector.mav_type = getattr(reader, "mav_type", None)
    mode_table = _mode_names(collector.firmware, collector.mav_type)

    # Collapse repeated MODE records (the autopilot re-logs the current mode)
    # so the timeline shows changes rather than heartbeats.
    modes: list[dict] = []
    for change in collector.modes:
        name = mode_table.get(change["number"], f"MODE {change['number']}")
        if modes and modes[-1]["name"] == name:
            continue
        modes.append({**change, "name": name})

    intervals = _armed_intervals(collector.events, collector.t_end)
    armed_total = sum(i["seconds"] for i in intervals)

    alt_values = [a for _, a in collector.alt]
    altitude = _stats(alt_values)
    if altitude:
        altitude["series"] = _downsample([[round(t, 2), round(a, 2)]
                                          for t, a in collector.alt])

    attitude: dict[str, Any] = {}
    if collector.att:
        roll_err = [row[1] - row[2] for row in collector.att]
        pitch_err = [row[3] - row[4] for row in collector.att]

        def _rms(values: list[float]) -> float:
            return math.sqrt(sum(v * v for v in values) / len(values))

        attitude = {
            "roll_max": round(max(abs(v) for v in roll_err), 2),
            "roll_rms": round(_rms(roll_err), 2),
            "pitch_max": round(max(abs(v) for v in pitch_err), 2),
            "pitch_rms": round(_rms(pitch_err), 2),
            "series": _downsample([[round(row[0], 2), round(row[1], 2), round(row[2], 2),
                                    round(row[3], 2), round(row[4], 2)]
                                   for row in collector.att]),
        }

    vibration: dict[str, Any] = {}
    if collector.vibe:
        vibration = {
            "x_max": round(max(row[1] for row in collector.vibe), 2),
            "y_max": round(max(row[2] for row in collector.vibe), 2),
            "z_max": round(max(row[3] for row in collector.vibe), 2),
            "clip_total": max(row[4] for row in collector.vibe),
        }

    ekf: dict[str, Any] = {}
    if collector.ekf:
        ekf = {
            "sv_max": round(max(row[1] for row in collector.ekf), 3),
            "sp_max": round(max(row[2] for row in collector.ekf), 3),
            "sh_max": round(max(row[3] for row in collector.ekf), 3),
            "sm_max": round(max(row[4] for row in collector.ekf), 3),
            "svt_max": round(max(row[5] for row in collector.ekf), 3),
        }

    battery: dict[str, Any] = {}
    if collector.bat:
        volts = [row[1] for row in collector.bat]
        battery = {
            "volt_start": round(volts[0], 2), "volt_end": round(volts[-1], 2),
            "volt_min": round(min(volts), 2),
            "current_max": round(max(row[2] for row in collector.bat), 2),
            "consumed_mah": round(max(row[3] for row in collector.bat), 1),
        }

    warnings: list[dict] = []
    if vibration:
        worst = max(vibration["x_max"], vibration["y_max"], vibration["z_max"])
        if worst > THRESHOLDS["vibe_ms2"]:
            warnings.append({"what": "Vibration", "detail": f"peak {worst:.1f} m/s/s",
                             "threshold": f"{THRESHOLDS['vibe_ms2']:.0f} m/s/s",
                             "source": "ardupilot.org — Measuring Vibration"})
        if vibration["clip_total"]:
            warnings.append({"what": "Accelerometer clipping",
                             "detail": f"{vibration['clip_total']} event(s)",
                             "threshold": "0", "source": "ardupilot.org — Measuring Vibration"})
    if ekf:
        for key, label in (("sv_max", "velocity"), ("sp_max", "position"),
                           ("sh_max", "height"), ("sm_max", "magnetometer"),
                           ("svt_max", "airspeed")):
            if ekf[key] > THRESHOLDS["ekf_test_ratio"]:
                warnings.append({"what": f"EKF {label} innovation",
                                 "detail": f"test ratio peaked at {ekf[key]:.2f}",
                                 "threshold": f"{THRESHOLDS['ekf_test_ratio']:.1f}",
                                 "source": "ardupilot.org — EKF overview"})
    if attitude:
        for axis in ("roll", "pitch"):
            if attitude[f"{axis}_max"] > THRESHOLDS["attitude_error_deg"]:
                warnings.append({"what": f"{axis.capitalize()} tracking error",
                                 "detail": f"peaked at {attitude[f'{axis}_max']:.1f}° "
                                           f"(RMS {attitude[f'{axis}_rms']:.1f}°)",
                                 "threshold": f"{THRESHOLDS['attitude_error_deg']:.0f}°",
                                 "source": "ArgazUI review trigger"})

    notable = []
    for message in collector.messages:
        low = message["text"].lower()
        if any(hint in low for hint in NOTABLE_MESSAGE_HINTS):
            notable.append(message)

    params = _write_params(collector, out_dir)
    plot_files = _plots(collector, modes, intervals, out_dir) if plots else []

    report = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "meta": meta or {},
        "log": {
            "file": bin_path.name,
            "path": str(bin_path),
            "size_bytes": bin_path.stat().st_size,
            "seconds": round(collector.t_end, 1),
            "firmware": collector.firmware,
            "mav_type": collector.mav_type,
            "message_counts": dict(sorted(collector.counts.items(),
                                          key=lambda kv: -kv[1])[:20]),
        },
        "modes": modes,
        "events": collector.events,
        "armed": {"intervals": intervals, "total_seconds": round(armed_total, 1)},
        "altitude": altitude,
        "attitude_error": attitude,
        "vibration": vibration,
        "ekf": ekf,
        "battery": battery,
        "params": params,
        "notable_messages": notable[:40],
        "warnings": warnings,
        "plots": plot_files,
        "thresholds": THRESHOLDS,
    }

    _write_atomic(out_dir / "report.json",
                  json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    _write_atomic(out_dir / "report.md", _markdown(report))
    return report


def _write_atomic(path: Path, text: str) -> None:
    """Writes through a temporary file so a reader never sees a half report.

    The runs API lists a report as present the moment the file exists, and
    report generation runs in a background thread — without the rename a
    browser could fetch a truncated document.
    """
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def newest_log(directory: Path, newer_than: Optional[float] = None) -> Optional[Path]:
    """The most recently modified `.BIN` under `directory`, optionally time-filtered.

    SITL writes into `<working dir>/logs/`; the filter exists so that stopping
    a model does not pick up the log of a previous session that is still
    sitting in the same working directory.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return None
    candidates = []
    for path in directory.rglob("*.BIN"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newer_than is not None and mtime < newer_than:
            continue
        candidates.append((mtime, path))
    if not candidates:
        return None
    return max(candidates)[1]
