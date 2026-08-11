"""Campaign aggregation: counts, spread, consistency, and what it refuses to say.

WHY THIS IS TESTED WITHOUT FLYING
---------------------------------
The aggregation is arithmetic over run directories, and the interesting cases
are the ones a real campaign produces rarely and at the worst moment: a flaky
run that must not become a pass, an iteration that never started, a procedure
that was edited half way through. Building those directories on disk is exact
and takes milliseconds; flying them would take an hour and still not produce
the third one on purpose.

`tests/test_tier1_campaign.py` flies a real one, so this is not the only thing
standing behind the feature.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argazui import campaign, failures

pytestmark = pytest.mark.tier1

CAMPAIGN = "20260810T120000Z_sitl_quad.copter_takeoff"


def write_run(root: Path, index: int, *, status="passed", flaky=False,
              metrics=None, started=None, procedure_hash="sha256:aaa",
              campaign_id=CAMPAIGN, dataflash=True) -> Path:
    """One run directory, exactly as `RunRecorder` would leave it."""
    directory = root / f"2026081{index}T1200{index:02d}Z_sitl_quad"
    directory.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": 4,
        "run_id": directory.name,
        "started_utc": started or f"2026-08-1{index}T12:00:0{index}Z",
        "finished_utc": f"2026-08-1{index}T12:05:0{index}Z",
        "seconds": 120.0 + index,
        "status": status,
        "advisory_count": 0,
        "campaign": {"schema": 1, "id": campaign_id, "index": index, "of": 5,
                     "model_id": "sitl_quad", "procedure_id": "copter_takeoff",
                     "values": {"alt": 15}, "note": ""},
        "flaky": ([{"procedure": "copter_takeoff", "reason": "attempt 1 failed"}]
                  if flaky else []),
        "model": {"id": "sitl_quad", "name": "SITL quad"},
        "metrics": metrics if metrics is not None else [],
        # Every identity field, present and known: `consistency()` asks
        # `fingerprint.differences()` whether the iterations really flew the
        # same thing, and an ABSENT field is reported as a difference on
        # purpose. A fixture missing one would make every campaign look
        # inconsistent for a reason that has nothing to do with the runs.
        "fingerprint": {"schema": 1, "procedure_hash": procedure_hash,
                        "model": {"config_hash": "sha256:model"},
                        "ardupilot": {"commit": "abc123",
                                      "firmware_commit": "abc123",
                                      "dirty": False,
                                      "dirty_digest": "clean"},
                        "argaz": {"commit": "def456", "dirty": False,
                                  "dirty_digest": "clean"},
                        "gazebo": {"version": "Gazebo Sim, version 8.9.0"}},
        "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                        "result": {"outcome": ("passed" if status == "passed"
                                               else "failed"),
                                   "steps": [], "expect": [], "faults": [],
                                   "params_changed": {}}}],
        "artefacts": {"dataflash": "00000001.BIN" if dataflash else None,
                      "dataflash_check": ({"complete": True, "error": ""}
                                          if dataflash else None),
                      "dataflash_absent_reason": (None if dataflash else
                                                  "the vehicle never armed")},
    }
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n",
                                           encoding="utf-8")
    return directory


def metric(key: str, value, procedure: str = "copter_takeoff", unit="s") -> dict:
    return {"key": key, "value": value, "unit": unit, "better": "lower",
            "scope": "procedure", "procedure": procedure, "detail": "",
            "source": "test", "identity": f"{key}@{procedure}"}


# ------------------------------------------------------------------- basics
def test_a_campaign_is_found_by_reading_its_runs(tmp_path):
    """No index file: a campaign that was interrupted still aggregates."""
    for index in (1, 2, 3):
        write_run(tmp_path, index)
    found = campaign.runs_of(CAMPAIGN, tmp_path)
    assert [entry["index"] for entry in found] == [1, 2, 3]

    listed = campaign.list_campaigns(tmp_path)
    assert len(listed) == 1
    assert listed[0]["recorded_runs"] == 3
    assert listed[0]["declared_runs"] == 5, "an interrupted campaign says so"


def test_runs_from_another_campaign_are_not_counted(tmp_path):
    write_run(tmp_path, 1)
    write_run(tmp_path, 2, campaign_id="20260810T130000Z_iris.copter_land")
    assert len(campaign.runs_of(CAMPAIGN, tmp_path)) == 1
    assert len(campaign.list_campaigns(tmp_path)) == 2


def test_counts_and_the_clean_pass_rate(tmp_path):
    write_run(tmp_path, 1)
    write_run(tmp_path, 2)
    write_run(tmp_path, 3, status="failed")
    write_run(tmp_path, 4, flaky=True)
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    assert document["counts"] == {"passed": 2, "failed": 1, "flaky": 1,
                                  "incomplete": 0}
    assert document["pass_rate"] == 0.5


def test_a_retry_is_never_counted_as_a_clean_pass(tmp_path):
    """The same rule the status table has. A pass rate that included retries
    would be measuring the harness's patience rather than the aircraft."""
    for index in (1, 2, 3):
        write_run(tmp_path, index, flaky=True)
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    assert document["counts"]["flaky"] == 3
    assert document["counts"]["passed"] == 0
    assert document["pass_rate"] == 0.0


def test_failures_are_counted_by_category(tmp_path):
    write_run(tmp_path, 1)
    write_run(tmp_path, 2, status="failed")
    write_run(tmp_path, 3, dataflash=False)
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    assert document["failure_categories"].get(failures.EVIDENCE) == 1
    assert document["failure_categories"].get(failures.PROCEDURE) == 1


# --------------------------------------------------------------- statistics
def test_mean_min_max_across_the_campaign(tmp_path):
    for index, value in enumerate((10.0, 12.0, 14.0), start=1):
        write_run(tmp_path, index,
                  metrics=[metric("time_to_target_alt", value)])
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    row = next(m for m in document["metrics"] if m["key"] == "time_to_target_alt")
    assert row["n"] == 3
    assert row["mean"] == 12.0
    assert row["min"] == 10.0 and row["max"] == 14.0
    assert row["stdev"] == pytest.approx(2.0)
    assert row["unit"] == "s"


def test_a_spread_is_not_reported_from_two_values(tmp_path):
    """Two numbers have a standard deviation and it describes nothing.

    `—` has to mean "not enough runs to say", and a reader must be able to tell
    that from "no variation" — so `spread_reported` states which it is.
    """
    for index, value in enumerate((10.0, 14.0), start=1):
        write_run(tmp_path, index,
                  metrics=[metric("time_to_target_alt", value)])
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    row = document["metrics"][0]
    assert row["n"] == 2
    assert row["stdev"] is None
    assert row["spread_reported"] is False
    assert row["mean"] == 12.0, "a mean of two values is still a mean"


def test_a_metric_that_could_not_be_measured_is_counted_separately(tmp_path):
    """`null` with a reason, not omitted — the same rule metrics.py has."""
    write_run(tmp_path, 1, metrics=[metric("time_to_target_alt", 10.0)])
    write_run(tmp_path, 2, metrics=[metric("time_to_target_alt", None)])
    write_run(tmp_path, 3, metrics=[metric("time_to_target_alt", 12.0)])
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    row = document["metrics"][0]
    assert row["n"] == 2
    assert row["not_measured"] == 1
    assert row["mean"] == 11.0, "the unmeasured run must not drag the mean"


def test_statistics_of_nothing_are_none_rather_than_zero():
    stats = campaign.statistics([])
    assert stats["n"] == 0
    assert stats["mean"] is None and stats["min"] is None and stats["max"] is None
    assert stats["stdev"] is None


def test_a_single_value_has_no_spread():
    """A spread of zero is a claim that the quantity does not vary."""
    assert campaign.statistics([7.0])["stdev"] is None


# -------------------------------------------------------------- consistency
def test_identical_runs_pass_the_consistency_check(tmp_path):
    for index in (1, 2, 3):
        write_run(tmp_path, index)
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    assert document["consistency"]["identical"] is True
    assert document["consistency"]["differences"] == []


def test_an_edited_procedure_mid_campaign_is_reported(tmp_path):
    """A campaign claims "the same thing, N times", and that is checkable.

    A spread caused by an edit half way through is not a spread caused by the
    aircraft, and reporting it as one is the whole failure mode the fingerprint
    exists to prevent.
    """
    write_run(tmp_path, 1, procedure_hash="sha256:aaa")
    write_run(tmp_path, 2, procedure_hash="sha256:aaa")
    write_run(tmp_path, 3, procedure_hash="sha256:bbb")
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    assert document["consistency"]["identical"] is False
    fields = [d["field"] for d in document["consistency"]["differences"]]
    assert "procedure_hash" in fields
    # And it has to say so in words, above the metrics, not only in JSON.
    assert "were not identical" in campaign.render(document)


# ------------------------------------------------------------------ document
def test_the_document_states_the_sample_size_next_to_its_claims(tmp_path):
    """Five runs is five runs. No confidence interval, no reliability figure."""
    for index in (1, 2, 3):
        write_run(tmp_path, index,
                  metrics=[metric("time_to_target_alt", 10.0 + index)])
    text = campaign.render(campaign.aggregate(CAMPAIGN, tmp_path))
    assert "3 run(s) is 3 run(s)" in text
    assert "confidence interval" in text
    for forbidden in ("p-value of", "reliability of", "95% confident"):
        assert forbidden not in text


def test_the_document_can_be_written_and_read_back(tmp_path):
    write_run(tmp_path, 1)
    write_run(tmp_path, 2)
    document = campaign.aggregate(CAMPAIGN, tmp_path)
    as_json, as_text = campaign.write(CAMPAIGN, document, tmp_path)
    assert as_json.is_file() and as_text.is_file()
    assert json.loads(as_json.read_text(encoding="utf-8"))["id"] == CAMPAIGN
    assert CAMPAIGN in as_text.read_text(encoding="utf-8")
    # Beside the runs, not among them: nothing that lists run directories may
    # start reporting a campaign as a mysterious extra flight.
    assert as_json.parent.parent.name == campaign.CAMPAIGNS_DIRNAME


def test_an_unknown_campaign_aggregates_to_nothing_rather_than_failing(tmp_path):
    document = campaign.aggregate("20260101T000000Z_nothing.here", tmp_path)
    assert document["runs_recorded"] == 0
    assert document["pass_rate"] is None


def test_the_campaign_id_carries_the_model_and_the_procedure():
    identifier = campaign.campaign_id("sitl_quad", "copter_takeoff")
    assert identifier.endswith("_sitl_quad.copter_takeoff")
    assert campaign.CAMPAIGN_ID_PATTERN.match(identifier)


def test_a_campaign_id_cannot_carry_a_path_separator():
    """It reaches `directory_for()` from an HTTP route, so it is untrusted."""
    identifier = campaign.campaign_id("../../etc", "passwd")
    assert "/" not in identifier
    assert campaign.CAMPAIGN_ID_PATTERN.match(identifier)


# ------------------------------------------------------------------ executor
class _FakeSession:
    def __init__(self, index: int, root: Path, fail: bool) -> None:
        self.index, self.root, self.fail = index, root, fail
        self.closed = False

    def run(self, procedure_id: str, values: dict):
        directory = write_run(self.root, self.index,
                              status="failed" if self.fail else "passed")
        return ({"run_id": directory.name}, directory)

    def close(self) -> None:
        self.closed = True


def test_the_executor_runs_every_iteration_and_closes_each(tmp_path):
    definition = campaign.Definition(id=CAMPAIGN, model_id="sitl_quad",
                                     procedure_id="copter_takeoff", runs=3)
    sessions: list = []

    def launch(index: int):
        session = _FakeSession(index, tmp_path, fail=False)
        sessions.append(session)
        return session

    runner = campaign.CampaignRunner(definition, launch)
    rows = runner.run()
    assert len(rows) == 3
    assert all(session.closed for session in sessions), "a session was leaked"
    assert campaign.aggregate(CAMPAIGN, tmp_path)["counts"]["passed"] == 3


def test_an_iteration_that_could_not_start_is_recorded_and_the_campaign_goes_on(tmp_path):
    """"Three of five starts failed" is a repeatability result.

    Stopping at the first one would hide exactly the thing the campaign was run
    to measure.
    """
    definition = campaign.Definition(id=CAMPAIGN, model_id="sitl_quad",
                                     procedure_id="copter_takeoff", runs=3)

    def launch(index: int):
        if index == 2:
            raise RuntimeError("no MAVLink heartbeat within 300s")
        return _FakeSession(index, tmp_path, fail=False)

    rows = campaign.CampaignRunner(definition, launch).run()
    assert len(rows) == 3
    broken = rows[1]
    assert broken["verdict"] == campaign.INCOMPLETE
    assert broken["failure"]["category"] == failures.ENVIRONMENT
    assert broken["failure"]["code"] == "iteration-launch-failed"
    assert rows[2]["run_id"], "the campaign stopped at the first bad start"


def test_cancelling_stops_before_the_next_iteration(tmp_path):
    definition = campaign.Definition(id=CAMPAIGN, model_id="sitl_quad",
                                     procedure_id="copter_takeoff", runs=5)
    runner = None

    def launch(index: int):
        if index == 2:
            runner.cancel()
        return _FakeSession(index, tmp_path, fail=False)

    runner = campaign.CampaignRunner(definition, launch)
    rows = runner.run()
    assert len(rows) == 2, "cancellation did not take effect"
