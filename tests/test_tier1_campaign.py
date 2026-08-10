"""Tier 1 — a real repeatability campaign, flown.

WHY THIS EXISTS ALONGSIDE tests/test_campaign.py
------------------------------------------------
That file proves the arithmetic: counts, spread, consistency, what the document
refuses to say. It builds run directories rather than flying them, which is
exact and fast and cannot show the one thing that actually matters here — that
`CampaignRunner` really does produce N independent runs, each with its own
evidence, each stamped with the campaign, from the same `ProcedureRunner` the
button uses.

TWO ITERATIONS, NOT THE DEFAULT FIVE
------------------------------------
The default is 5 and this flies 2, because each iteration is a full SITL boot
and a real takeoff. Two is the smallest number that can show the runs are
independent — separate directories, separate logs, separate indices — which is
what this test is for. It is not a repeatability measurement and it does not
claim to be one; the spread it would report from two runs is exactly the one
`campaign.statistics` refuses to print.
"""
from __future__ import annotations

import json

import pytest

from argazui import campaign, procedures as procs
from argazui.mavlink_link import MavlinkLink
from argazui.procrunner import ProcedureRunner
from argazui.runs import RunRecorder

import sitl as sitl_mod

pytestmark = pytest.mark.tier1

QUAD = {
    "id": "sitl_quad_campaign", "name": "SITL quad frame", "vehicle_class": "Copter",
    "method": "sitl_frame", "vehicle": "ArduCopter", "frame": "quad",
}

RUNS = 2
TAKEOFF_VALUES = {"alt": 12}


class Iteration:
    """One campaign iteration: boot, connect, record, and tear down.

    This is the tier-1 launcher. The server has its own — it drives the
    ordinary START/STOP path — and tier 2 would have a third. What none of them
    may vary is what happens between: one `RunRecorder` per iteration, the
    campaign stamp on it, and `ProcedureRunner` doing the flying.
    """

    def __init__(self, definition: campaign.Definition, index: int,
                 runs_root, work_root) -> None:
        self.recorder = RunRecorder(
            model=QUAD, root=runs_root,
            work_dir=work_root / f"campaign_{index}",
            launch_commands=[f"# pytest campaign {definition.id} run {index}"],
            campaign=definition.stamp(index))
        try:
            self.sitl = sitl_mod.start(QUAD["vehicle"], QUAD["frame"],
                                       work_root / f"campaign_{index}")
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
        # Same order as the UI's STOP, for the same reason: SITL has to flush
        # its dataflash log before the run is finalised.
        #
        # The report is generated and waited for rather than skipped. It is
        # what fills in the firmware identity and the metrics, and without it
        # the consistency check below would report every iteration as
        # "firmware unknown on at least one side" — which is the correct answer
        # for a run whose log was never read, and not the one this test is
        # about.
        self.link.stop()
        self.sitl.stop()
        self.recorder.finish(wait=True)


def test_a_two_run_campaign_produces_two_independent_runs(request, runs_root):
    """The claim a campaign rests on: N runs, each with its own evidence."""
    try:
        sitl_mod.binary_for(QUAD["vehicle"])
    except sitl_mod.SitlUnavailable as exc:
        pytest.skip(str(exc))

    work_root = request.config.rootpath / "argazui" / "run"
    definition = campaign.Definition(
        id=campaign.campaign_id(QUAD["id"], "copter_takeoff"),
        model_id=QUAD["id"], procedure_id="copter_takeoff", runs=RUNS,
        values=dict(TAKEOFF_VALUES),
        note="tier-1 campaign test; 2 runs, not a repeatability measurement")

    live: list[Iteration] = []

    def launch(index: int) -> Iteration:
        iteration = Iteration(definition, index, runs_root, work_root)
        live.append(iteration)
        return iteration

    def _teardown() -> None:
        for iteration in live:
            try:
                iteration.close()
            except Exception:
                pass
    request.addfinalizer(_teardown)

    rows = campaign.CampaignRunner(definition, launch).run()
    assert len(rows) == RUNS

    # Independent evidence: two directories, two run ids, two dataflash logs.
    directories = {row["dir"] for row in rows if row["dir"]}
    assert len(directories) == RUNS, f"the iterations shared a directory: {rows}"

    document = campaign.aggregate(definition.id, runs_root, definition=definition)
    assert document["runs_recorded"] == RUNS, (
        f"the campaign stamp did not reach every run\n{json.dumps(rows, indent=2)}")
    assert sum(document["counts"].values()) == RUNS

    # Every iteration says which campaign it belonged to, and where in it.
    indices = sorted(row["index"] for row in document["runs"])
    assert indices == list(range(1, RUNS + 1))

    # The runs really were the same thing, which is a campaign's whole claim.
    assert document["consistency"]["checked"] is True
    assert document["consistency"]["identical"] is True, (
        f"two runs of one procedure disagreed on their fingerprints: "
        f"{document['consistency']['differences']}")

    # And the document is readable and honest about its sample size. Two
    # measured values have a standard deviation and it describes nothing, so
    # this campaign must not print one.
    text = campaign.render(document)
    assert f"{RUNS} run(s) is {RUNS} run(s)" in text
    assert "confidence interval" in text
    for row in document["metrics"]:
        if row["n"] < campaign.MIN_SAMPLES_FOR_SPREAD:
            assert row["stdev"] is None
            assert row["spread_reported"] is False
