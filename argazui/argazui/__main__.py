"""Start the ArgazUI server, or work with an installation from the shell.

    ./start.sh                              # http://127.0.0.1:8770
    ./start.sh --port 9000
    python3 -m argazui doctor --json
    python3 -m argazui runs
    python3 -m argazui report runs/20260802T120000Z_skywalker_x8
    python3 -m argazui compare runs/20260803T101500Z_skywalker_x8 \\
            --baseline runs/20260802T120000Z_skywalker_x8
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ArgazUI — ArduPilot SITL + Gazebo control panel")
    ap.add_argument("command", nargs="?",
                    choices=("serve", "doctor", "runs", "report", "status",
                             "compare"),
                    default="serve")
    ap.add_argument("target", nargs="?",
                    help="report: a run directory or a .BIN dataflash log; "
                         "compare: the current run directory")
    ap.add_argument("--argaz-root", help="simulation root (overrides ARGAZ_ROOT / argaz.toml)")
    ap.add_argument("--ardupilot-root", help="ArduPilot root")
    ap.add_argument("--sitl-models-root", help="SITL_Models root")
    ap.add_argument("--ardu-ws-root", help="ROS workspace root")
    ap.add_argument("--env-script", help="environment script to source for launches")
    ap.add_argument("--port", type=int, help="HTTP port")
    ap.add_argument("--mavlink-port", type=int, help="ArgazUI MAVLink port")
    ap.add_argument("--script-mavlink-port", type=int, help="mission script MAVLink port")
    ap.add_argument("--plotjuggler-port", type=int,
                    help="live telemetry mirror port (0 disables it)")
    ap.add_argument("--reload", action="store_true", help="Auto-reload for development")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine-readable doctor output")
    ap.add_argument("--tier", choices=("full", "tier1"), default="full",
                    help="doctor profile (default: full)")
    ap.add_argument("--runs", action="append", default=None,
                    help="status: a directory holding suite.json and run "
                         "directories; repeat for more than one")
    ap.add_argument("--out", help="status: where to write the generated table")
    ap.add_argument("--workflow", default="", help="status: which workflow produced this")
    ap.add_argument("--run-url", default="", help="status: link to that workflow run")
    ap.add_argument("--baseline",
                    help="compare: the run directory to compare against "
                         "(default: the newest earlier run of the same model)")
    ap.add_argument("--ignore-config-drift", action="store_true",
                    help="compare: compare even though the firmware, the "
                         "procedures or the model configuration changed — the "
                         "difference is still reported")
    args = ap.parse_args(argv)

    paths.configure(argaz_root=args.argaz_root, ardupilot_root=args.ardupilot_root,
                    sitl_models_root=args.sitl_models_root, ardu_ws_root=args.ardu_ws_root,
                    env_script=args.env_script, port=args.port,
                    mavlink_port=args.mavlink_port, script_mavlink_port=args.script_mavlink_port,
                    plotjuggler_port=args.plotjuggler_port)

    if args.command == "doctor":
        from .doctor import format_human, run
        report = run(args.tier)
        print(json.dumps(report, indent=2) if args.as_json else format_human(report))
        return 0 if report["ok"] else 1

    if args.command == "runs":
        return _list_runs(args.as_json)

    if args.command == "report":
        return _make_report(args.target, args.as_json)

    if args.command == "compare":
        return _compare(args.target, args.baseline, args.as_json,
                        args.ignore_config_drift, args.out)

    if args.command == "status":
        from pathlib import Path

        from .status import generate
        roots = [Path(r) for r in (args.runs or [paths.RUNS_DIR])]
        out = Path(args.out) if args.out else (paths.ARGAZ / "docs" / "status.md")
        readme = paths.ARGAZ / "README.md"
        text = generate(roots, out, workflow=args.workflow, run_url=args.run_url,
                        readme=readme if readme.is_file() else None)
        print(f"wrote {out} ({len(text.splitlines())} lines) from "
              + ", ".join(str(r) for r in roots), file=sys.stderr)
        return 0

    # A normal start checks its prerequisites first, so a user gets an
    # actionable error before a browser and two terminal PTYs have appeared.
    #
    # WHAT COUNTS AS FATAL, AND WHY IT IS NOT THE FULL PROFILE
    # --------------------------------------------------------
    # It used to be, and that made ArgazUI refuse to start on any machine
    # without Gazebo and ROS 2 — including the tier-1 container image, where
    # every e2e test died with "prerequisites are not ready" for assets none
    # of them use. It is also simply wrong for a user: the `sitl_only` launch
    # method needs no Gazebo at all, and a missing simulator is a reason some
    # models cannot fly, not a reason the application cannot run.
    #
    # So the tier-1 set — ArduPilot, the SITL binaries, the Python packages,
    # the ports — is fatal, and the Gazebo/ROS 2 findings are reported as
    # warnings on the way up. `argazui doctor` remains the complete report.
    from .doctor import run
    report = run("tier1")
    if not report["ok"]:
        print("ERROR: ArgazUI prerequisites are not ready. Run 'argazui doctor' for details.",
              file=sys.stderr)
        for check in report["checks"]:
            if check["critical"] and not check["ok"]:
                print(f"  - {check['name']}: {check['detail']}", file=sys.stderr)
        return 1

    full = run("full")
    missing = [c for c in full["checks"] if c["critical"] and not c["ok"]]
    if missing:
        print("ArgazUI: starting without the full simulation stack. Models that "
              "need it cannot be launched:", file=sys.stderr)
        for check in missing:
            print(f"  - {check['name']}: {check['detail']}", file=sys.stderr)
        print("  Run 'argazui doctor' for the complete report.", file=sys.stderr)

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
    if paths.PLOTJUGGLER_PORT:
        print(f"  Live plot       : udp {paths.PLOTJUGGLER_PORT} "
              f"(PlotJuggler UDP Server, protocol JSON)")
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


def _compare(target: Optional[str], baseline: Optional[str], as_json: bool,
             ignore_config_drift: bool, out: Optional[str]) -> int:
    """`argazui compare <run> --baseline <run>` — the CI-consumable comparison.

    EXIT CODES, BECAUSE THIS IS MEANT FOR CI
    ----------------------------------------
        0  no metric degraded past its threshold
        1  at least one did — this is the regression signal
        2  the runs could not be compared, or could not be read

    2 is separate from 1 on purpose. "These runs do not line up" is not the
    same news as "this build got worse", and a pipeline that treated them
    alike would eventually report a mis-specified baseline as a regression.
    """
    from .regression import RunNotReadable, compare, load_run, previous_run_for, write

    if not target:
        from .runs import list_runs
        recent = list_runs(limit=1)
        if not recent:
            print(f"ERROR: no runs recorded yet under {paths.RUNS_DIR}, and no "
                  f"run directory was given.", file=sys.stderr)
            return 2
        target = recent[0]["dir"]
        print(f"No current run given; using the most recent: {recent[0]['run_id']}",
              file=sys.stderr)

    try:
        current = load_run(Path(target).expanduser())
        if baseline:
            reference = load_run(Path(baseline).expanduser())
        else:
            reference = previous_run_for(current)
            if reference is None:
                print(f"ERROR: no earlier run of model "
                      f"'{current['model_id']}' with metrics was found under "
                      f"{paths.RUNS_DIR}. Name a baseline with --baseline.",
                      file=sys.stderr)
                return 2
            print(f"No baseline given; using the previous run of this model: "
                  f"{reference['run_id']}", file=sys.stderr)
    except RunNotReadable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    comparison = compare(reference, current,
                         ignore_config_drift=ignore_config_drift)
    directory = Path(out) if out else Path(current["dir"])
    as_json_path, as_text_path = write(directory, comparison)

    if as_json:
        print(json.dumps(comparison, indent=2, ensure_ascii=False))
    else:
        from .regression import render
        print(render(comparison))
    print(f"wrote {as_json_path}\n      {as_text_path}", file=sys.stderr)

    from .regression import NOT_COMPARABLE, REGRESSED
    if comparison["verdict"] == NOT_COMPARABLE:
        return 2
    return 1 if comparison["verdict"] == REGRESSED else 0


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
