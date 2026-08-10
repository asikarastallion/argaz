"""Start the ArgazUI server, or work with an installation from the shell.

    ./start.sh                              # http://127.0.0.1:8770
    ./start.sh --port 9000
    python3 -m argazui doctor --json
    python3 -m argazui runs
    python3 -m argazui report runs/20260802T120000Z_skywalker_x8
    python3 -m argazui compare runs/20260803T101500Z_skywalker_x8 \\
            --baseline runs/20260802T120000Z_skywalker_x8
    python3 -m argazui campaign                     # list repeatability campaigns
    python3 -m argazui campaign 20260810T124500Z_iris.copter_takeoff
    python3 -m argazui coverage                     # what is declared and unrun
    python3 -m argazui trace runs/<run>             # intent -> evidence -> verdict
    python3 -m argazui experiment                   # declared experiments and their runs
    python3 -m argazui experiment copter_gps_loss_vs_nominal
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
                             "compare", "campaign", "coverage", "trace",
                             "experiment"),
                    default="serve")
    ap.add_argument("target", nargs="?",
                    help="report: a run directory or a .BIN dataflash log; "
                         "compare: the current run directory; "
                         "campaign: a campaign id (omit to list them); "
                         "trace: a run directory; "
                         "experiment: an experiment run id or a definition id "
                         "(omit to list them)")
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
                         "directories; repeat for more than one. "
                         "campaign: the runs root to search")
    ap.add_argument("--out", help="status: where to write the generated table; "
                                  "campaign: a directory for campaign.json/.md; "
                                  "experiment: a directory for "
                                  "experiment.json/.md")
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

    if args.command == "campaign":
        return _campaign(args.target, args.as_json, args.runs, args.out)

    if args.command == "coverage":
        return _coverage(args.as_json, args.runs, args.out)

    if args.command == "trace":
        return _trace(args.target, args.as_json)

    if args.command == "experiment":
        return _experiment(args.target, args.as_json, args.runs, args.out)

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


def _campaign(target: Optional[str], as_json: bool, roots: Optional[list],
              out: Optional[str]) -> int:
    """`argazui campaign [<id>]` — aggregate a repeatability campaign.

    With no id it lists the campaigns in the runs root. With one it recomputes
    the whole document from the run directories and writes `campaign.json` and
    `campaign.md` beside them.

    EXIT CODES
    ----------
        0  the campaign was aggregated, whatever its runs did
        1  the campaign exists and one or more of its runs did not pass
        2  no such campaign, or nothing to aggregate

    1 rather than 0 for a campaign with failures because this is meant for CI,
    and 2 is kept separate for the same reason `compare` keeps it: "there is no
    such campaign" is a different piece of news from "the aircraft failed".
    """
    from . import campaign as campaignlib

    root = Path(roots[0]) if roots else paths.RUNS_DIR

    if not target:
        found = campaignlib.list_campaigns(root)
        if as_json:
            print(json.dumps({"root": str(root), "campaigns": found}, indent=2))
            return 0 if found else 2
        if not found:
            print(f"No campaigns recorded under {root}.")
            return 2
        print(f"{'campaign':52s} {'model':20s} {'procedure':22s} runs")
        for entry in found:
            declared = entry.get("declared_runs")
            print(f"{entry['id']:52s} {str(entry['model_id'] or '-'):20s} "
                  f"{str(entry['procedure_id'] or '-'):22s} "
                  f"{entry['recorded_runs']}"
                  + (f"/{declared}" if declared else ""))
        print(f"\n{len(found)} campaign(s) under {root}")
        return 0

    document = campaignlib.aggregate(target, root)
    if not document["runs_recorded"]:
        print(f"ERROR: no run under {root} carries the campaign id "
              f"'{target}'.", file=sys.stderr)
        return 2

    directory = Path(out) if out else None
    as_json_path, as_text_path = campaignlib.write(
        target, document, root if directory is None else directory.parent)
    if directory is not None:
        # An explicit --out writes the pair there instead, so a CI job can
        # collect them without reaching into the runs tree.
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "campaign.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (directory / "campaign.md").write_text(campaignlib.render(document),
                                               encoding="utf-8")
        as_json_path, as_text_path = (directory / "campaign.json",
                                      directory / "campaign.md")

    if as_json:
        print(json.dumps(document, indent=2, ensure_ascii=False))
    else:
        print(campaignlib.render(document))
    print(f"wrote {as_json_path}\n      {as_text_path}", file=sys.stderr)

    counts = document["counts"]
    unclean = counts["failed"] + counts["flaky"] + counts["incomplete"]
    return 1 if unclean else 0


def _experiment(target: Optional[str], as_json: bool, roots: Optional[list],
                out: Optional[str]) -> int:
    """`argazui experiment [<id>]` — aggregate one controlled comparison.

    With no id it lists what this checkout declares and what has actually been
    flown, side by side. A declared experiment nobody has run is a question
    this project asked and never answered, and it is invisible in a listing
    that only shows results.

    With an id — either an experiment run id or a definition id, which resolves
    to its newest run — it recomputes the whole document from the run
    directories and writes `experiment.json` and `experiment.md`.

    EXIT CODES
    ----------
        0  the experiment was aggregated and nothing declared failed
        1  a declared criterion did not hold
        2  no such experiment, or nothing has been flown under that name

    1 rather than 0 for a failed criterion because this is meant for CI, and 2
    is kept separate for the same reason `compare` and `campaign` keep it:
    "there is no such experiment" is a different piece of news from "the
    comparison came out badly".

    An `incomplete` experiment exits 0. Arms short of their runs are a reason
    to fly more, not a reason to fail a build — and a project whose CI went red
    for declaring an experiment before it could be flown would learn to stop
    declaring them.
    """
    from . import analysis as analysislib
    from . import experiments as experimentlib

    root = Path(roots[0]) if roots else paths.RUNS_DIR

    if not target:
        try:
            declared = experimentlib.load_all()
        except experimentlib.ExperimentError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        flown = analysislib.list_experiment_runs(root)
        if as_json:
            print(json.dumps({
                "dir": str(paths.EXPERIMENTS_DIR), "root": str(root),
                "experiments": [item.as_dict() for item in declared.values()],
                "runs": flown}, indent=2, ensure_ascii=False))
            return 0 if declared or flown else 2
        if not declared:
            print(f"No experiments declared in {paths.EXPERIMENTS_DIR}.")
        else:
            print(f"{'experiment':34s} {'model':14s} {'policy':9s} arms  runs  flown")
            for item in declared.values():
                runs = [e for e in flown if e["experiment_id"] == item.id]
                print(f"{item.id:34s} {item.model_id:14s} {item.policy:9s} "
                      f"{len(item.arms):4d} {item.total_runs:5d} "
                      f"{len(runs):6d}")
            print(f"\n{len(declared)} experiment(s) in {paths.EXPERIMENTS_DIR}")
        unrun = [item.id for item in declared.values()
                 if not any(e["experiment_id"] == item.id for e in flown)]
        if unrun:
            print(f"\nDeclared and never flown: {', '.join(unrun)}")
        if flown:
            print(f"\n{'run':46s} {'experiment':30s} runs")
            for entry in flown:
                print(f"{entry['run']:46s} "
                      f"{str(entry['experiment_id'] or '-'):30s} "
                      f"{entry['recorded_runs']}")
        return 0 if (declared or flown) else 2

    resolved = target
    if not experimentlib.EXPERIMENT_RUN_PATTERN.match(target):
        candidates = [entry for entry in analysislib.list_experiment_runs(root)
                      if entry["experiment_id"] == target]
        if not candidates:
            print(f"ERROR: no run under {root} carries the experiment id "
                  f"'{target}'. Declared experiments are listed by "
                  f"`python3 -m argazui experiment`.", file=sys.stderr)
            return 2
        resolved = candidates[0]["run"]
        print(f"No experiment run given; using the newest run of '{target}': "
              f"{resolved}", file=sys.stderr)

    document = analysislib.collect(resolved, root)
    if not document["runs_recorded"]:
        print(f"ERROR: no run under {root} carries the experiment run id "
              f"'{resolved}'.", file=sys.stderr)
        return 2

    directory = Path(out) if out else None
    as_json_path, as_text_path = analysislib.write(
        resolved, document, root if directory is None else directory.parent)
    if directory is not None:
        # An explicit --out writes the pair there instead, so a CI job can
        # collect them without reaching into the runs tree.
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "experiment.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (directory / "experiment.md").write_text(analysislib.render(document),
                                                 encoding="utf-8")
        as_json_path, as_text_path = (directory / "experiment.json",
                                      directory / "experiment.md")

    if as_json:
        print(json.dumps(document, indent=2, ensure_ascii=False))
    else:
        print(analysislib.render(document))
    print(f"wrote {as_json_path}\n      {as_text_path}", file=sys.stderr)
    return 1 if document["verdict"] == analysislib.FAILED else 0


def _coverage(as_json: bool, roots: Optional[list], out: Optional[str]) -> int:
    """`argazui coverage` — what is declared, what was run, and what was not.

    Exit 0 always. Coverage is a measurement, not a gate: a project with an
    uncovered procedure has a gap, and turning that into a red build would
    make the honest thing to do — declaring a procedure before it can be flown
    — the thing that breaks CI.
    """
    from . import coverage as coveragelib

    roots = [Path(r) for r in (roots or [paths.RUNS_DIR])]
    document = coveragelib.collect(roots)
    target = Path(out) if out else (paths.ARGAZ / "docs" / "coverage.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(coveragelib.render(document), encoding="utf-8")

    if as_json:
        print(json.dumps(document, indent=2, ensure_ascii=False))
    else:
        print(coveragelib.render(document))
    uncovered = sum(len(d["uncovered"]) for d in document["dimensions"])
    print(f"wrote {target} — {uncovered} declared item(s) not covered by any "
          f"run under {', '.join(str(r) for r in roots)}", file=sys.stderr)
    return 0


def _trace(target: Optional[str], as_json: bool) -> int:
    """`argazui trace <run>` — the chain from intent to evidence, and its gaps.

    EXIT CODES
    ----------
        0  every link resolves
        1  the chain has a problem — a dangling reference, a duplicate id, an
           artefact the chain names and the manifest does not list
        2  the run could not be read

    1 rather than 0 for a broken chain because this is meant for CI: a
    traceability scheme nobody verifies degrades silently, and every one of the
    problems it reports still renders a table that looks right.
    """
    from . import evidence as evidencelib
    from . import trace as tracelib
    from .runs import list_runs, run_dir

    if not target:
        recent = list_runs(limit=1)
        if not recent:
            print(f"ERROR: no runs recorded yet under {paths.RUNS_DIR}.",
                  file=sys.stderr)
            return 2
        target = recent[0]["dir"]
        print(f"No run given; using the most recent: {recent[0]['run_id']}",
              file=sys.stderr)

    directory = Path(target).expanduser()
    path = directory / "result.json"
    if not path.is_file():
        print(f"ERROR: {directory} has no result.json.", file=sys.stderr)
        return 2
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {path} could not be read: {exc}", file=sys.stderr)
        return 2

    chain = tracelib.chain(result)
    problems = tracelib.integrity(result, chain)
    problems += [{"problem": item["problem"], "subject": item["artefact"],
                  "detail": item["detail"]}
                 for item in evidencelib.problems(evidencelib.read(directory))]

    if as_json:
        print(json.dumps({"chain": chain, "problems": problems}, indent=2,
                         ensure_ascii=False))
    else:
        print(f"run       {chain['run_id']}")
        print(f"intent    {chain['test_id']}")
        print(f"model     {chain['model_id']}")
        print(f"verdict   {chain['verdict']}")
        for procedure in chain["procedures"]:
            print(f"\n  procedure {procedure['procedure_id']} "
                  f"-> {procedure['verdict']}")
            for step in procedure["steps"]:
                print(f"    step      {step['step_id']:<40s} {step['status']}")
            for criterion in procedure["criteria"]:
                mark = ("passed" if criterion["passed"]
                        else "failed" if criterion["evaluated"]
                        else "not evaluated")
                print(f"    criterion {criterion['criterion_id']:<40s} {mark}")
            for fault in procedure["faults"]:
                print(f"    fault     {fault['fault_id']:<40s} "
                      f"{'passed' if fault['passed'] else 'failed'}")
        for metric in chain["metrics"]:
            state = "measured" if metric["measured"] else "not measured"
            print(f"  metric    {metric['metric_id']:<42s} {state}")
        print(f"\n  evidence  {len(chain['evidence'])} artefact(s) present")
        derived = tracelib.derived_ids(chain)
        if derived:
            print(f"\n  {len(derived)} identifier(s) derived from position "
                  f"rather than declared: {', '.join(derived[:6])}"
                  + (" …" if len(derived) > 6 else ""))
        if problems:
            print(f"\n{len(problems)} problem(s):")
            for item in problems:
                print(f"  - {item['problem']}: {item['subject']} — "
                      f"{item['detail']}")
        else:
            print("\nEvery link in the chain resolves.")
    return 1 if problems else 0


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
