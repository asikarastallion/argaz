"""Tier 1 — a real two-arm experiment, flown.

WHY THIS EXISTS ALONGSIDE THE TWO UNIT FILES
--------------------------------------------
`test_experiments.py` proves the definition is validated and that the runner
hands each arm to a campaign. `test_experiment_analysis.py` proves the
arithmetic over run directories. Both build their inputs rather than flying
them, which is exact and fast and cannot show the one thing v1.6's P0 actually
claims:

    scenario execution must produce the same run evidence model used by
    ordinary runs, and must not create a second execution engine.

That is only checkable by flying one. Two arms, one run each, on a real SITL:
what comes out has to be two ordinary run directories, each with its own
dataflash log and its own fingerprint, each stamped with BOTH its campaign and
its experiment — and the analysis has to find them by reading the runs alone.

ONE RUN PER ARM, NOT THE THREE THE SHIPPED FILE DECLARES
--------------------------------------------------------
Each iteration is a full SITL boot and a real takeoff. One per arm is the
smallest number that can show the two arms produce independent, correctly
stamped evidence, which is what this test is for. It is **not** a controlled
comparison and does not claim to be one: n=1 on both sides is exactly the case
`analysis.compare_metrics` marks `indicative` rather than `measured`, and the
assertions below check that it does.
"""
from __future__ import annotations

import json

import pytest

from argazui import analysis, campaign, experiments, procedures as procs
from argazui.mavlink_link import MavlinkLink
from argazui.procrunner import ProcedureRunner
from argazui.runs import RunRecorder

import sitl as sitl_mod

pytestmark = pytest.mark.tier1

QUAD = {
    "id": "sitl_quad_experiment", "name": "SITL quad frame",
    "vehicle_class": "Copter", "method": "sitl_frame",
    "vehicle": "ArduCopter", "frame": "quad",
}

# The experiment this test flies. Written here rather than shipped in
# argazui/experiments/ because it names a SITL frame that is deliberately not
# in the model registry — tier 1 flies SITL's own generic frames and may never
# report a result against a Gazebo model.
DEFINITION = """
schema: 1
id: tier1_takeoff_two_arms
name: {en: "Two arms, one run each", tr: "Iki kol, her birinde bir kosu"}
question:
  en: "Does the experiment layer produce ordinary, independently stamped runs?"
  tr: "Deney katmani siradan ve ayri ayri damgalanmis kosular uretiyor mu?"
model: sitl_quad_experiment
values: {alt: 12}
arms:
  - id: low
    procedure: copter_takeoff
    runs: 1
    role: reference
    label: {en: "12 m", tr: "12 m"}
  - id: high
    procedure: copter_takeoff
    runs: 1
    values: {alt: 18}
    label: {en: "18 m", tr: "18 m"}
metrics: [time_to_target_alt, tracking_error_roll_rms]
compare: {policy: arms, reference_arm: low}
accept:
  - id: both-arms-clean
    arm: low
    min_pass_rate: 1.0
limitations:
  out_of_scope:
    - en: "Any Gazebo model. This is a SITL frame and says nothing about one."
      tr: "Her Gazebo modeli. Bu bir SITL govdesidir ve hicbiri hakkinda bir sey soylemez."
"""


class Iteration:
    """One experiment iteration: boot, connect, record, and tear down.

    The tier-1 launcher. The server has its own, which drives the ordinary
    START/STOP path. What neither may vary is what happens between: one
    `RunRecorder` per iteration, BOTH stamps on it, and `ProcedureRunner` doing
    the flying.
    """

    def __init__(self, arm, definition: campaign.Definition, index: int,
                 experiment, run_id: str, runs_root, work_root,
                 test_id: str = "") -> None:
        name = f"experiment_{arm.id}_{index}"
        self.recorder = RunRecorder(
            model=QUAD, root=runs_root, work_dir=work_root / name,
            launch_commands=[f"# pytest experiment {run_id} arm {arm.id}"],
            campaign=definition.stamp(index),
            experiment=experiment.stamp(run_id, arm, index),
            test_id=test_id)
        try:
            self.sitl = sitl_mod.start(QUAD["vehicle"], QUAD["frame"],
                                       work_root / name)
        except sitl_mod.SitlUnavailable:
            self.recorder.finish(report=False)
            raise
        self.link = MavlinkLink(connection=self.sitl.connection,
                                on_event=self.recorder.event)
        self.link.start(vehicle=QUAD["vehicle"])
        if not self.link.wait_ready(timeout=sitl_mod.CONNECT_TIMEOUT):
            self.close()
            raise TimeoutError(f"no heartbeat from {self.sitl.connection}")

    def run(self, procedure_id: str, values: dict):
        procedure = procs.get(procedure_id)
        runner = ProcedureRunner(self.link, on_event=self.recorder.event)
        result = runner.run(procedure, values)
        self.recorder.add_procedure(procedure, result, values=values)
        return ({"run_id": self.recorder.run_id}, self.recorder.dir)

    def close(self) -> None:
        # Same order as the UI's STOP: SITL has to flush its dataflash log
        # before the run is finalised. The report is waited for because it is
        # what derives the metrics, and an experiment with no metrics would
        # compare nothing.
        self.link.stop()
        self.sitl.stop()
        self.recorder.finish(wait=True)


def test_a_two_arm_experiment_produces_ordinary_stamped_runs(request, runs_root,
                                                             tmp_path):
    try:
        sitl_mod.binary_for(QUAD["vehicle"])
    except sitl_mod.SitlUnavailable as exc:
        pytest.skip(str(exc))

    path = tmp_path / "tier1_takeoff_two_arms.yaml"
    path.write_text(DEFINITION, encoding="utf-8")
    experiment = experiments.parse(DEFINITION, path)

    work_root = request.config.rootpath / "argazui" / "run"
    run_id = experiments.experiment_run_id(experiment.id)
    live: list[Iteration] = []

    def launch(arm, definition, index):
        iteration = Iteration(arm, definition, index, experiment, run_id,
                              runs_root, work_root, test_id=request.node.nodeid)
        live.append(iteration)
        return iteration

    def _teardown() -> None:
        for iteration in live:
            try:
                iteration.close()
            except Exception:
                pass
    request.addfinalizer(_teardown)

    runner = experiments.ExperimentRunner(experiment, run_id, launch)
    rows = runner.run()

    assert set(rows) == {"low", "high"}, f"an arm did not fly: {rows}"
    directories = {row["dir"] for arm in rows.values() for row in arm
                   if row["dir"]}
    assert len(directories) == 2, f"the arms shared a directory: {rows}"

    # ---- the P0 claim: ordinary runs, found by reading them ----------------
    entries = analysis.runs_of(run_id, runs_root)
    assert len(entries) == 2, (
        f"the experiment stamp did not reach every run\n"
        f"{json.dumps({k: v for k, v in rows.items()}, indent=2, default=str)}")
    for entry in entries:
        result = entry["data"]
        assert result["schema"] >= 6
        # BOTH stamps. An arm really is a campaign, and a run that dropped its
        # campaign id would vanish from every campaign tool in the project.
        assert result["campaign"]["id"], "an experiment run lost its campaign id"
        assert result["experiment"]["run"] == run_id
        assert result["experiment"]["arm"] in ("low", "high")
        # And the ordinary evidence model, unchanged.
        assert (entry["dir"] / "result.json").is_file()
        assert (entry["dir"] / "evidence.json").is_file()
        assert (entry["dir"] / "fingerprint.json").is_file()
        assert (entry["dir"] / "scenario.yaml").is_file()

    # ---- each arm aggregates as the campaign it is -------------------------
    for arm_id, definition in runner.campaigns.items():
        document = campaign.aggregate(definition.id, runs_root)
        assert document["runs_recorded"] == 1, (
            f"arm '{arm_id}' is not findable as a campaign")

    # ---- the experiment document -------------------------------------------
    document = analysis.collect(run_id, runs_root, experiment)
    assert document["runs_recorded"] == 2
    assert [arm["id"] for arm in document["arms"]] == ["low", "high"]
    assert not document["arms_short"], "an arm flew fewer runs than declared"

    # n=1 on both sides is exactly the case that must NOT read as measured.
    comparison = document["comparisons"][0]
    assert comparison["reference"] == "low"
    for row in comparison["metrics"]:
        if row["basis"] == analysis.NONE:
            continue
        assert row["basis"] == analysis.INDICATIVE, (
            f"{row['key']} was reported as measured from one run per arm")

    # The document is honest about what it is, and writes.
    text = analysis.render(document)
    assert "No p-value, confidence interval or effect size" in text
    as_json, as_text = analysis.write(run_id, document, runs_root)
    assert as_json.is_file() and as_text.is_file()
