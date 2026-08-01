"""Start the ArgazUI server.

    ./start.sh                    # http://127.0.0.1:8770
    ./start.sh --port 9000
"""
import argparse
import sys

try:
    import uvicorn
except ImportError:                                  # pragma: no cover
    # Most common cause: venv-ardupilot is activated only from .profile, so it
    # is not active in non-login shells (such as the VS Code terminal).
    sys.exit(
        f"ERROR: 'uvicorn' is not available in this Python interpreter:\n"
        f"    {sys.executable}\n\n"
        "Fix: launch ArgazUI with ./start.sh — it finds the right interpreter\n"
        "itself. Or install the packages:\n"
        "    ~/venv-ardupilot/bin/pip install fastapi uvicorn wsproto\n"
    )

from . import paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ArgazUI — ArduPilot SITL + Gazebo control panel")
    ap.add_argument("--port", type=int, default=8770, help="HTTP port (default 8770)")
    ap.add_argument("--reload", action="store_true", help="Auto-reload for development")
    args = ap.parse_args(argv)

    if not paths.ENV_SH.is_file():
        print(f"ERROR: {paths.ENV_SH} not found. ArgazUI must live inside the "
              f"argaz root directory.", file=sys.stderr)
        return 1

    print("=" * 62)
    print("  ArgazUI")
    print(f"  Open in browser : http://127.0.0.1:{args.port}")
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
    uvicorn.run("argazui.app:app", host="127.0.0.1", port=args.port,
                reload=args.reload, log_level="warning", ws="wsproto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
