"""Experiment analysis: distributions, deltas, verdicts, and the refusals.

WHY THIS IS TESTED WITHOUT FLYING
---------------------------------
The analysis is arithmetic over run directories, and the cases that matter are
the ones a real experiment produces rarely and at the worst moment: an arm that
measured nothing, a criterion that could not be judged, an experiment cancelled
after its first arm, a definition that has been renamed since the runs were
flown. Building those directories on disk is exact and takes milliseconds;
flying them would take an afternoon and still not produce the fourth on purpose.

`tests/test_tier1_experiment.py` flies a real one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from argazui import analysis, campaign, experiments, limitations

pytestmark = pytest.mark.tier1

RUN = "20260810T120000Z_e1"

DEFINITION = """
schema: 1
id: e1
question: {en: "Does GPS loss change the climb?", tr: "GPS kaybi tirmanisi degistirir mi?"}
model: iris
values: {alt: 20}
arms:
  - id: nominal
    procedure: copter_takeoff
    runs: 3
    role: reference
  - id: faulted
    procedure: copter_gps_loss
    runs: 3
metrics: [tracking_error_roll_rms, time_to_target_alt]
compare: {policy: arms, reference_arm: nominal}
accept:
  - id: nominal-clean
    arm: nominal
    min_pass_rate: 1.0
  - id: roll-not-much-worse
    arm: faulted
    metric: tracking_error_roll_rms
    max_delta: 3.0
    delta_vs: nominal
  - id: climb-in-range
    arm: faulted
    metric: time_to_target_alt
    max: 40
"""

REPEATS = """
schema: 1
id: e2
question: {en: "Does it climb the same way twice?", tr: "Iki kez ayni mi?"}
model: iris
values: {alt: 12}
arms:
  - id: repeat
    procedure: copter_takeoff
    runs: 3
metrics: [time_to_target_alt]
compare: {policy: repeats}
"""


@pytest.fixture
def definition(tmp_path) -> experiments.Experiment:
    path = tmp_path / "e1.yaml"
    path.write_text(DEFINITION, encoding="utf-8")
    return experiments.parse(DEFINITION, path)


def campaign_id(arm: str) -> str:
    return f"20260810T120000Z_iris.copter_takeoff-{arm}"


def write_run(root: Path, experiment, arm: str, index: int, *,
              status="passed", flaky=False, metrics=None, run=RUN,
              evidence_complete=True, missing=None) -> Path:
    """One run directory, exactly as an experiment iteration would leave it."""
    directory = root / f"20260810T12{index:02d}00Z_iris_{arm}"
    directory.mkdir(parents=True, exist_ok=True)
    rows = [{"key": key, "value": value, "unit": "s", "better": "lower",
             "scope": "procedure", "procedure": "copter_takeoff",
             "detail": "", "source": "test", "identity": f"{key}@copter_takeoff"}
            for key, value in (metrics or {}).items()]
    result = {
        "schema": 6,
        "run_id": directory.name,
        "started_utc": f"2026-08-10T12:{index:02d}:00Z",
        "status": status,
        "advisory_count": 0,
        "campaign": {"schema": 1, "id": campaign_id(arm), "index": index,
                     "of": 3, "model_id": "iris",
                     "procedure_id": "copter_takeoff", "values": {}, "note": ""},
        "experiment": experiment.stamp(run, experiment.arm(arm), index),
        "flaky": ([{"procedure": "copter_takeoff", "reason": "attempt 1"}]
                  if flaky else []),
        "model": {"id": "iris", "name": "Iris"},
        "metrics": rows,
        "fingerprint": {"schema": 1, "procedure_hash": "sha256:a",
                        "model": {"config_hash": "sha256:m"},
                        "ardupilot": {"commit": "abc", "firmware_commit": "abc"}},
        "procedures": [{"procedure": "copter_takeoff", "role": "takeoff",
                        "result": {"outcome": ("passed" if status == "passed"
                                               else "failed"),
                                   "steps": [], "expect": [], "faults": [],
                                   "params_changed": {}}}],
        "evidence": {"schema": 1, "complete": evidence_complete,
                     "missing_required": list(missing or [])},
        "artefacts": {"dataflash": "1.BIN",
                      "dataflash_check": {"complete": True, "error": ""},
                      "dataflash_absent_reason": None},
    }
    (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n",
                                           encoding="utf-8")
    return directory


def build(root: Path, experiment, *, nominal=(1.0, 1.2, 1.1),
          faulted=(5.5, 6.0, 5.8), climb=12.0) -> None:
    for index, value in enumerate(nominal, start=1):
        write_run(root, experiment, "nominal", index,
                  metrics={"tracking_error_roll_rms": value,
                           "time_to_target_alt": climb})
    for index, value in enumerate(faulted, start=4):
        write_run(root, experiment, "faulted", index,
                  metrics={"tracking_error_roll_rms": value,
                           "time_to_target_alt": climb})


# ------------------------------------------------------------------ discovery
def test_the_runs_of_an_experiment_are_found_by_reading_them(tmp_path, definition):
    build(tmp_path, definition)
    entries = analysis.runs_of(RUN, tmp_path)
    assert len(entries) == 6
    assert {entry["arm"] for entry in entries} == {"nominal", "faulted"}
    # And every one of them also carries its campaign id, because an arm IS a
    # campaign and campaign tooling has to keep finding it.
    assert all(entry["campaign_id"] for entry in entries)


def test_runs_of_another_experiment_are_not_counted(tmp_path, definition):
    build(tmp_path, definition)
    write_run(tmp_path, definition, "nominal", 9, run="20260101T000000Z_other")
    assert len(analysis.runs_of(RUN, tmp_path)) == 6
    assert len(analysis.list_experiment_runs(tmp_path)) == 2


def test_an_ordinary_run_is_not_mistaken_for_an_experiment(tmp_path, definition):
    build(tmp_path, definition)
    plain = tmp_path / "20260810T130000Z_iris"
    plain.mkdir()
    (plain / "result.json").write_text(json.dumps(
        {"schema": 6, "run_id": plain.name, "status": "passed"}), encoding="utf-8")
    assert len(analysis.runs_of(RUN, tmp_path)) == 6


# ---------------------------------------------------------------- the document
def test_each_arm_is_aggregated_as_the_campaign_it_is(tmp_path, definition):
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    nominal = next(a for a in document["arms"] if a["id"] == "nominal")
    assert nominal["campaign_id"] == campaign_id("nominal")
    assert nominal["recorded_runs"] == 3
    assert nominal["counts"][campaign.PASSED] == 3
    assert nominal["pass_rate"] == 1.0
    assert nominal["role"] == experiments.REFERENCE


def test_metrics_are_grouped_by_key_not_by_key_and_procedure(tmp_path, definition):
    """The one place this project's metric identity deliberately inverts.

    The arms fly different procedures on purpose, and the whole question is
    what the same quantity did under the two conditions.
    """
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    faulted = next(a for a in document["arms"] if a["id"] == "faulted")
    row = next(m for m in faulted["metrics"]
               if m["key"] == "tracking_error_roll_rms")
    assert row["n"] == 3
    assert row["mean"] == pytest.approx(5.7667, abs=1e-3)
    assert row["procedures"], "the report must still say where each number came from"


def test_a_delta_between_the_arms_is_reported_with_n_on_both_sides(tmp_path,
                                                                   definition):
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    comparison = document["comparisons"][0]
    assert comparison["reference"] == "nominal"
    row = next(m for m in comparison["metrics"]
               if m["key"] == "tracking_error_roll_rms")
    assert row["delta"] == pytest.approx(4.6667, abs=1e-3)
    assert row["reference"]["n"] == 3 and row["current"]["n"] == 3
    assert row["basis"] == analysis.MEASURED
    assert row["ranges_overlap"] is False


def test_overlapping_ranges_are_reported_as_overlapping(tmp_path, definition):
    build(tmp_path, definition, faulted=(1.05, 1.15, 1.10))
    document = analysis.collect(RUN, tmp_path, definition)
    row = next(m for m in document["comparisons"][0]["metrics"]
               if m["key"] == "tracking_error_roll_rms")
    assert row["ranges_overlap"] is True


def test_a_delta_from_too_few_runs_is_indicative_rather_than_measured(tmp_path,
                                                                     definition):
    """Below three measured values neither side has a reported spread.

    The same threshold campaigns use, and the row says so rather than printing
    a difference that looks as solid as one from twenty runs.
    """
    build(tmp_path, definition, nominal=(1.0, 1.2), faulted=(5.5, 6.0))
    document = analysis.collect(RUN, tmp_path, definition)
    row = next(m for m in document["comparisons"][0]["metrics"]
               if m["key"] == "tracking_error_roll_rms")
    assert row["basis"] == analysis.INDICATIVE
    assert row["delta"] is not None, "an indicative delta is still reported"
    assert str(campaign.MIN_SAMPLES_FOR_SPREAD) in row["reason"]


def test_a_metric_no_run_measured_produces_no_delta(tmp_path, definition):
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    row = next(m for m in document["comparisons"][0]["metrics"]
               if m["key"] == "time_to_target_alt")
    assert row["delta"] == 0.0     # both arms measured it, and identically
    # A key nothing measured is the interesting case; take it away entirely.
    for path in tmp_path.rglob("result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["metrics"] = [m for m in data["metrics"]
                           if m["key"] != "time_to_target_alt"]
        path.write_text(json.dumps(data), encoding="utf-8")
    document = analysis.collect(RUN, tmp_path, definition)
    row = next(m for m in document["comparisons"][0]["metrics"]
               if m["key"] == "time_to_target_alt")
    assert row["delta"] is None
    assert row["basis"] == analysis.NONE
    assert "nothing to take a difference of" in row["reason"]


def test_the_repeats_policy_compares_nothing(tmp_path):
    path = tmp_path / "e2.yaml"
    path.write_text(REPEATS, encoding="utf-8")
    item = experiments.parse(REPEATS, path)
    for index in (1, 2, 3):
        write_run(tmp_path, item, "repeat", index, run="20260810T120000Z_e2",
                  metrics={"time_to_target_alt": 10.0 + index})
    document = analysis.collect("20260810T120000Z_e2", tmp_path, item)
    assert document["comparisons"] == []
    row = document["arms"][0]["metrics"][0]
    assert row["n"] == 3 and row["mean"] == pytest.approx(12.0)


# ----------------------------------------------------------------- acceptance
def test_a_criterion_that_holds_and_one_that_does_not(tmp_path, definition):
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    by_id = {row["criterion_id"]: row for row in document["acceptance"]["criteria"]}
    assert by_id["nominal-clean"]["passed"] is True
    assert by_id["roll-not-much-worse"]["passed"] is False
    assert by_id["roll-not-much-worse"]["evaluated"] is True
    assert document["verdict"] == analysis.FAILED


def test_a_retry_is_never_counted_as_a_clean_pass(tmp_path, definition):
    """The same rule the status table and campaigns already have."""
    build(tmp_path, definition)
    path = next(tmp_path.glob("*_nominal/result.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["flaky"] = [{"procedure": "copter_takeoff", "reason": "attempt 1"}]
    path.write_text(json.dumps(data), encoding="utf-8")

    document = analysis.collect(RUN, tmp_path, definition)
    row = next(r for r in document["acceptance"]["criteria"]
               if r["criterion_id"] == "nominal-clean")
    assert row["passed"] is False, "a flaky run bought a clean pass"


def test_a_criterion_nothing_measured_is_not_judged_and_never_a_pass(tmp_path,
                                                                     definition):
    """"No run measured this" and "this held" are different facts."""
    build(tmp_path, definition)
    for path in tmp_path.rglob("result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["metrics"] = [m for m in data["metrics"]
                           if m["key"] != "time_to_target_alt"]
        path.write_text(json.dumps(data), encoding="utf-8")

    document = analysis.collect(RUN, tmp_path, definition)
    row = next(r for r in document["acceptance"]["criteria"]
               if r["criterion_id"] == "climb-in-range")
    assert row["evaluated"] is False
    assert row["passed"] is False
    assert "not judged" in row["text"]
    assert document["acceptance"]["not_evaluated"] == 1


def test_a_range_criterion_is_judged_on_the_arms_mean(tmp_path, definition):
    build(tmp_path, definition, climb=55.0)
    document = analysis.collect(RUN, tmp_path, definition)
    row = next(r for r in document["acceptance"]["criteria"]
               if r["criterion_id"] == "climb-in-range")
    assert row["evaluated"] is True and row["passed"] is False
    assert row["observed"] == pytest.approx(55.0)


# -------------------------------------------------------------------- verdicts
def test_an_experiment_nothing_flew_is_not_run(tmp_path, definition):
    document = analysis.collect(RUN, tmp_path, definition)
    assert document["verdict"] == analysis.NOT_RUN
    assert document["runs_recorded"] == 0


def test_an_arm_short_of_its_runs_makes_the_experiment_incomplete(tmp_path,
                                                                  definition):
    build(tmp_path, definition, nominal=(1.0, 1.1), faulted=(1.2, 1.3, 1.2))
    document = analysis.collect(RUN, tmp_path, definition)
    assert document["arms_short"] == ["nominal"]
    assert document["verdict"] == analysis.INCOMPLETE


def test_a_failed_criterion_outranks_an_incomplete_arm(tmp_path, definition):
    """A criterion that was judged and did not hold is still a result.

    The document prints n beside it, so a reader can see how much it rests on.
    """
    build(tmp_path, definition, nominal=(1.0, 1.1), faulted=(9.0, 9.2, 9.1))
    document = analysis.collect(RUN, tmp_path, definition)
    assert document["arms_short"] == ["nominal"]
    assert document["verdict"] == analysis.FAILED


def test_an_experiment_with_no_criteria_asserts_nothing(tmp_path):
    path = tmp_path / "e2.yaml"
    path.write_text(REPEATS, encoding="utf-8")
    item = experiments.parse(REPEATS, path)
    for index in (1, 2, 3):
        write_run(tmp_path, item, "repeat", index, run="20260810T120000Z_e2",
                  metrics={"time_to_target_alt": 10.0})
    document = analysis.collect("20260810T120000Z_e2", tmp_path, item)
    assert document["verdict"] == analysis.NOT_JUDGED
    assert "asserts nothing" in analysis.render(document)


def test_everything_holding_passes(tmp_path, definition):
    build(tmp_path, definition, faulted=(1.2, 1.3, 1.25))
    document = analysis.collect(RUN, tmp_path, definition)
    assert document["verdict"] == analysis.PASSED, \
        json.dumps(document["acceptance"]["criteria"], indent=2)


# -------------------------------------------------------------------- evidence
def test_a_run_with_incomplete_evidence_is_named(tmp_path, definition):
    build(tmp_path, definition)
    path = next(tmp_path.glob("*_faulted/result.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["evidence"] = {"complete": False, "missing_required": ["dataflash"]}
    path.write_text(json.dumps(data), encoding="utf-8")

    document = analysis.collect(RUN, tmp_path, definition)
    assert len(document["evidence"]["incomplete"]) == 1
    assert document["evidence"]["missing_required"] == ["dataflash"]
    assert "Incomplete evidence" in analysis.render(document)


def test_a_run_recorded_before_manifests_is_unknown_rather_than_complete(
        tmp_path, definition):
    build(tmp_path, definition)
    path = next(tmp_path.glob("*_nominal/result.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("evidence")
    path.write_text(json.dumps(data), encoding="utf-8")

    document = analysis.collect(RUN, tmp_path, definition)
    assert len(document["evidence"]["unknown"]) == 1
    assert document["evidence"]["incomplete"] == []


# ------------------------------------------------------------------- document
def test_the_document_has_the_ten_sections_in_order(tmp_path, definition):
    """A fixed order is checkable, which is why it is fixed."""
    build(tmp_path, definition)
    text = analysis.render(analysis.collect(RUN, tmp_path, definition))
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert [h.split(".")[0] for h in headings] == [f"## {n}" for n in range(1, 11)]
    assert "## 10. Limitations and non-claims" in text


def test_the_document_refuses_to_compute_statistics_it_cannot_support(
        tmp_path, definition):
    build(tmp_path, definition)
    text = analysis.render(analysis.collect(RUN, tmp_path, definition))
    assert "No p-value, confidence interval or effect size" in text
    assert "not a significance test" in text
    for forbidden in ("p = 0.", "95% confident", "statistically significant"):
        assert forbidden not in text


def test_the_document_states_the_declared_and_the_standing_limitations(
        tmp_path, definition):
    build(tmp_path, definition)
    text = analysis.render(analysis.collect(RUN, tmp_path, definition))
    for category in limitations.CATEGORIES:
        assert limitations.label_for(category) in text
    assert "*(standing)*" in text
    assert "declared no limitations of its own" in text, (
        "this definition declares none, and the document has to say so")


def test_the_document_can_be_written_and_read_back(tmp_path, definition):
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, definition)
    as_json, as_text = analysis.write(RUN, document, tmp_path)
    assert as_json.is_file() and as_text.is_file()
    assert json.loads(as_json.read_text(encoding="utf-8"))["id"] == RUN
    # Beside the runs, not among them — the same rule campaigns follow.
    assert as_json.parent.parent.name == analysis.EXPERIMENTS_DIRNAME


def test_a_document_survives_its_definition_being_renamed(tmp_path, definition):
    """The runs are the evidence; the file is not.

    A document produced without its definition reports what was flown and says
    plainly that it cannot report what was asked.
    """
    build(tmp_path, definition)
    document = analysis.collect(RUN, tmp_path, experiment=None)
    assert document["definition_available"] is False
    assert document["runs_recorded"] == 6
    assert {arm["id"] for arm in document["arms"]} == {"nominal", "faulted"}
    assert "not in this checkout" in analysis.render(document)


# -------------------------------------------------------------------- baseline
def test_the_baseline_policy_compares_an_arm_with_its_own_earlier_run(tmp_path):
    body = REPEATS.replace("compare: {policy: repeats}",
                           "compare: {policy: baseline}")
    path = tmp_path / "e2.yaml"
    path.write_text(body, encoding="utf-8")
    item = experiments.parse(body, path)

    earlier, later = "20260810T100000Z_e2", "20260810T120000Z_e2"
    for index, value in enumerate((10.0, 10.2, 10.1), start=1):
        write_run(tmp_path, item, "repeat", index, run=earlier,
                  metrics={"time_to_target_alt": value})
    for index, value in enumerate((14.0, 14.2, 14.1), start=4):
        write_run(tmp_path, item, "repeat", index, run=later,
                  metrics={"time_to_target_alt": value})

    assert analysis.previous_run_of("e2", later, tmp_path) == earlier
    document = analysis.collect(later, tmp_path, item)
    assert len(document["comparisons"]) == 1
    row = document["comparisons"][0]["metrics"][0]
    assert row["delta"] == pytest.approx(4.0, abs=1e-6)
    assert document["comparisons"][0]["baseline_run"] == earlier


def test_a_baseline_compares_the_previous_run_only_not_the_whole_history(tmp_path):
    """Three runs, one comparison — and the older pair is not walked.

    The baseline this document rests on has a baseline of its own. Collected
    without care, a long history would be walked end to end once per document,
    for numbers no reader asked for.
    """
    body = REPEATS.replace("compare: {policy: repeats}",
                           "compare: {policy: baseline}")
    path = tmp_path / "e2.yaml"
    path.write_text(body, encoding="utf-8")
    item = experiments.parse(body, path)

    runs = ["20260810T080000Z_e2", "20260810T100000Z_e2", "20260810T120000Z_e2"]
    for offset, run in enumerate(runs):
        for index in (1, 2, 3):
            write_run(tmp_path, item, "repeat", index + offset * 3, run=run,
                      metrics={"time_to_target_alt": 10.0 + offset})

    document = analysis.collect(runs[-1], tmp_path, item)
    assert len(document["comparisons"]) == 1
    assert document["comparisons"][0]["baseline_run"] == runs[-2]
    assert document["comparisons"][0]["metrics"][0]["delta"] == pytest.approx(1.0)

    # Collected as somebody else's baseline, a document reports its
    # distributions and no comparison at all.
    baseline = analysis.collect(runs[-2], tmp_path, item, compare=False)
    assert baseline["comparisons"] == []
    assert baseline["arms"][0]["metrics"][0]["n"] == 3


def test_a_baseline_policy_with_no_earlier_run_says_so(tmp_path):
    body = REPEATS.replace("compare: {policy: repeats}",
                           "compare: {policy: baseline}")
    path = tmp_path / "e2.yaml"
    path.write_text(body, encoding="utf-8")
    item = experiments.parse(body, path)
    for index in (1, 2, 3):
        write_run(tmp_path, item, "repeat", index, run="20260810T120000Z_e2",
                  metrics={"time_to_target_alt": 10.0})
    document = analysis.collect("20260810T120000Z_e2", tmp_path, item)
    assert document["comparisons"] == []
    assert "No earlier run of this experiment" in analysis.render(document)
