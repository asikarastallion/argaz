"""Start the ArgazUI server, or work with an installation from the shell.

    ./start.sh                              # http://127.0.0.1:8770
    ./start.sh --port 9000
    python3 -m argazui doctor --json
    python3 -m argazui runs
    python3 -m argazui report runs/20260802T120000Z_skywalker_x8
"""
import argparse
import json
import sys
from pathlib import Path

from . import paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ArgazUI — ArduPilot SITL + Gazebo control panel")
    ap.add_argument("command", nargs="?",
                    choices=("serve", "doctor", "runs", "report"), default="serve")
    ap.add_argument("target", nargs="?",
                    help="report: a run directory or a .BIN dataflash log")
    ap.add_argument("--argaz-root", help="simulation root (overrides ARGAZ_ROOT / argaz.toml)")
    ap.add_argument("--ardupilot-root", help="ArduPilot root")
    ap.add_argument("--sitl-models-root", help="SITL_Models root")
    ap.add_argument("--ardu-ws-root", help="ROS workspace root")
    ap.add_argument("--env-script", help="environment script to source for launches")
    ap.add_argument("--port", type=int, help="HTTP port")
    ap.add_argument("--mavlink-port", type=int, help="ArgazUI MAVLink port")
    ap.add_argument("--script-mavlink-port", type=int, help="mission script MAVLink port")
    ap.add_argument("--reload", action="store_true", help="Auto-reload for development")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable doctor output")
    ap.add_argument("--tier", choices=("full", "tier1"), default="full",
                    help="doctor profile (default: full)")
    args = ap.parse_args(argv)

    paths.configure(argaz_root=args.argaz_root, ardupilot_root=args.ardupilot_root,
                    sitl_models_root=args.sitl_models_root, ardu_ws_root=args.ardu_ws_root,
                    env_script=args.env_script, port=args.port,
                    mavlink_port=args.mavlink_port, script_mavlink_port=args.script_mavlink_port)

    if args.command == "doctor":
        from .doctor import format_human, run
        report = run(args.tier)
        print(json.dumps(report, indent=2) if args.as_json else format_human(report))
        return 0 if report["ok"] else 1

    if args.command == "runs":
        return _list_runs(args.as_json)

    if args.command == "report":
        return _make_report(args.target, args.as_json)

    # A normal start uses the full profile, but only prints critical failures so
    # a user gets an actionable error before a browser and two terminal PTYs
    # have appeared. `argazui doctor` remains the complete report.
    from .doctor import run
    report = run("full")
    if not report["ok"]:
        print("ERROR: ArgazUI prerequisites are not ready. Run 'argazui doctor' for details.",
              file=sys.stderr)
        for check in report["checks"]:
            if check["critical"] and not check["ok"]:
                print(f"  - {check['name']}: {check['detail']}", file=sys.stderr)
        return 1

    try:
        import uvicorn
    except ImportError:                                  # pragma: no cover
        print(f"ERROR: 'uvicorn' is not available in {sys.executable}. Run doctor for details.",
              file=sys.stderr)
        return 1

    print("=" * 62)
    print("  ArgazUI")
    print(f"  Open in browser : http://127.0.0.1:{paths.HTTP_PORT}")
    print(f"  argaz root      : {paths.ARGAZ}")
    print(f"  Mission scripts : {paths.SCRIPTS_DIR}")
    print(f"  MAVLink         : {paths.UI_MAVLINK_PORT} (interface) / "
          f"{paths.SCRIPT_MAVLINK_PORT} (scripts)")
    print("  Press Ctrl+C to stop")
    print("=" * 62)
    # When output is redirected to a file, block buffering would hide this
    # banner until the process exits; flush so the URL shows immediately.
    sys.stdout.flush()

    # localhost ONLY — never exposed to the network.
    # ws="wsproto": the system's older 'websockets' package is incompatible with
    # uvicorn's sans-io implementation, so we pick wsproto and leave it alone.
    uvicorn.run("argazui.app:app", host="127.0.0.1", port=paths.HTTP_PORT,
                reload=args.reload, log_level="warning", ws="wsproto")
    return 0


def _list_runs(as_json: bool) -> int:
    """`argazui runs` — the same listing the browser panel shows."""
    from .runs import list_runs
    found = list_runs()
    if as_json:
        print(json.dumps({"root": str(paths.RUNS_DIR), "runs": found}, indent=2))
        return 0
    if not found:
        print(f"No runs recorded yet under {paths.RUNS_DIR}.")
        return 0
    print(f"{'run':38s} {'status':13s} {'adv':>4s} {'dur':>7s}  procedures")
    for entry in found:
        procedures = ", ".join(
            f"{p['id']}" + ("" if p["outcome"] == "passed" else f" ({p['outcome']})")
            for p in entry["procedures"])
        seconds = f"{entry['seconds']:.0f}s" if entry.get("seconds") else "-"
        count = entry.get("advisory_count")
        advisories = "-" if count is None else str(count)
        print(f"{entry['run_id']:38s} {entry['status']:13s} {advisories:>4s} "
              f"{seconds:>7s}  {procedures or '-'}")
    print(f"\n{len(found)} run(s) under {paths.RUNS_DIR}")
    return 0


def _make_report(target: str, as_json: bool) -> int:
    """`argazui report <run-dir|log.BIN>` — regenerate a post-flight report.

    Accepting a bare `.BIN` matters: a log recovered from a real flight
    controller, or one from a session that predates v1.1, can be analysed
    without inventing a run directory for it.
    """
    if not target:
        # Default to the newest run. Without this the documented example had
        # to carry a `<run_id>` placeholder, and a command that cannot be
        # pasted is not a command — a user hit exactly that and got a bash
        # syntax error.
        from .runs import list_runs
        recent = list_runs(limit=1)
        if not recent:
            print(f"ERROR: no runs recorded yet under {paths.RUNS_DIR}, and no "
                  f"run directory or .BIN log was given.", file=sys.stderr)
            return 2
        target = recent[0]["dir"]
        print(f"No target given; using the most recent run: {recent[0]['run_id']}")
    path = Path(target).expanduser()
    if not path.exists():
        print(f"ERROR: {path} does not exist.", file=sys.stderr)
        return 2

    from .flightlog import analyse
    from .runs import describe_run, regenerate_report, run_dir

    if path.is_dir():
        # A directory inside the configured runs root keeps its run metadata;
        # any other directory is treated as "the log lives in here".
        if run_dir(path.name) is not None:
            result = regenerate_report(path.name)
            if not result["ok"]:
                print(f"ERROR: {result['text']}", file=sys.stderr)
                return 1
            report = json.loads((path / "report.json").read_text(encoding="utf-8"))
        else:
            logs = sorted(path.glob("*.BIN")) or sorted(path.rglob("*.BIN"))
            if not logs:
                print(f"ERROR: no .BIN log found under {path}.", file=sys.stderr)
                return 1
            report = analyse(logs[0], path)
    else:
        report = analyse(path, path.parent)

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    out = Path(report["log"]["path"]).parent if path.is_file() else path
    print(f"Wrote {out / 'report.md'}")
    print(f"      {out / 'report.json'}")
    print(f"      {out / 'params_full.txt'}  ({report['params']['total']} parameters)")
    print(f"      {out / 'params_diff.txt'}  "
          f"({report['params']['non_default']} differ from default)")
    print(f"  build: {report['build']['text']}")
    # Advisories are health findings, never a verdict. The exit code stays 0
    # for them: `argazui report` reads a log, it does not judge a flight.
    for advisory in report["advisories"]:
        print(f"  ! advisory {advisory['code']}: {advisory['detail']}")
    if not report["advisories"]:
        print("  no measurement crossed a review threshold")
    if path.is_dir() and run_dir(path.name) is not None:
        row = describe_run(path)
        print(f"  acceptance status: {row['status']}  "
              f"(advisories: {row['advisory_count']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
