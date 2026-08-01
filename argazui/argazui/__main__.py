"""Start the ArgazUI server.

    ./start.sh                    # http://127.0.0.1:8770
    ./start.sh --port 9000
"""
import argparse
import json
import sys

from . import paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ArgazUI — ArduPilot SITL + Gazebo control panel")
    ap.add_argument("command", nargs="?", choices=("serve", "doctor"), default="serve")
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


if __name__ == "__main__":
    sys.exit(main())
