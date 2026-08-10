"""The experiment definition: what it accepts, and everything it refuses.

WHY THE REFUSALS ARE MOST OF THIS FILE
--------------------------------------
An experiment file is read once and then produces a document that somebody
reviews as evidence. Every mistake this parser lets through becomes a sentence
in that document which is confidently wrong: an arm that flew a different
altitude from the one the file names, a criterion judging a metric the report
never shows, a delta measured from an arm that does not exist.

None of those crash. All of them render. So the validator is where they have to
be caught, and each test below is one such case.

`tests/test_tier1_experiment.py` flies a real one; this file never leaves the
parser.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from argazui import campaign, experiments, limitations, procedures as procs

pytestmark = pytest.mark.tier1


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def parse(tmp_path: Path, name: str, body: str):
    path = write(tmp_path, name, body)
    return experiments.parse(path.read_text(encoding="utf-8"), path)


MINIMAL = """
schema: 1
id: {id}
question: {{en: "Does it climb the same way twice?", tr: "Iki kez ayni sekilde tirmaniyor mu?"}}
model: iris
values: {{alt: 12}}
arms:
  - id: repeat
    procedure: copter_takeoff
    runs: 3
metrics: [time_to_target_alt]
compare: {{policy: repeats}}
"""

TWO_ARMS = """
schema: 1
id: {id}
question: {{en: "Does GPS loss change the climb?", tr: "GPS kaybi tirmanisi degistirir mi?"}}
model: iris
values: {{alt: 20}}
arms:
  - id: nominal
    procedure: copter_takeoff
    runs: 3
    role: reference
  - id: faulted
    procedure: copter_gps_loss
    runs: 3
metrics: [tracking_error_roll_rms]
compare: {{policy: arms, reference_arm: nominal}}
accept:
  - id: not-much-worse
    arm: faulted
    metric: tracking_error_roll_rms
    max_delta: 3.0
    delta_vs: nominal
"""


# ------------------------------------------------------------- the shipped set
def test_every_shipped_experiment_parses():
    """The files in argazui/experiments/ are release artefacts, like procedures."""
    loaded = experiments.load_all()
    assert loaded, "no experiment is shipped, so nothing exercises this format"
    for identifier, item in loaded.items():
        assert item.id == identifier
        assert item.asks("en") and item.asks("tr"), (
            f"{identifier} does not state its question in both languages")
        assert item.arms, f"{identifier} has no arms"
        assert item.metrics, f"{identifier} measures nothing"


def test_every_shipped_experiment_names_procedures_that_exist():
    known = procs.load_all()
    for item in experiments.load_all().values():
        for arm in item.arms:
            assert arm.procedure_id in known, (
                f"{item.id}: arm '{arm.id}' names a procedure that is not in "
                f"argazui/procedures/")


def test_every_shipped_arm_is_expressible_as_a_campaign():
    """The whole of "do not create a second execution engine", asserted."""
    for item in experiments.load_all().values():
        for arm in item.arms:
            definition = experiments.campaign_for(item, arm)
            assert isinstance(definition, campaign.Definition)
            assert campaign.CAMPAIGN_ID_PATTERN.match(definition.id), (
                f"{definition.id} is not a campaign id, so campaign tooling "
                f"would not find this arm")
            assert definition.runs == arm.runs
            assert definition.procedure_id == arm.procedure_id


# --------------------------------------------------------------------- basics
def test_a_minimal_experiment_parses(tmp_path):
    item = parse(tmp_path, "e1", MINIMAL.format(id="e1"))
    assert item.model_id == "iris"
    assert item.policy == experiments.REPEATS
    assert item.total_runs == 3
    assert item.values_for(item.arms[0]) == {"alt": 12}


def test_an_arm_may_override_the_experiments_values(tmp_path):
    item = parse(tmp_path, "e1", MINIMAL.format(id="e1").replace(
        "    runs: 3", "    runs: 3\n    values: {alt: 30}"))
    assert item.values == {"alt": 12}
    assert item.values_for(item.arms[0]) == {"alt": 30}


def test_the_id_must_equal_the_filename(tmp_path):
    with pytest.raises(experiments.ExperimentError, match="filename stem"):
        parse(tmp_path, "e1", MINIMAL.format(id="something_else"))


def test_an_unknown_schema_is_refused(tmp_path):
    with pytest.raises(experiments.ExperimentError, match="schema"):
        parse(tmp_path, "e1", MINIMAL.format(id="e1").replace("schema: 1",
                                                              "schema: 9"))


def test_a_question_is_required(tmp_path):
    """An experiment with no stated question is a batch of runs."""
    body = "\n".join(line for line in MINIMAL.format(id="e1").splitlines()
                     if not line.startswith("question:"))
    with pytest.raises(experiments.ExperimentError, match="question"):
        parse(tmp_path, "e1", body)


def test_an_experiment_measuring_nothing_is_refused(tmp_path):
    with pytest.raises(experiments.ExperimentError, match="at least one"):
        parse(tmp_path, "e1",
              MINIMAL.format(id="e1").replace("metrics: [time_to_target_alt]",
                                              "metrics: []"))


def test_an_unknown_metric_names_the_known_ones(tmp_path):
    with pytest.raises(experiments.ExperimentError, match="time_to_target_alt"):
        parse(tmp_path, "e1",
              MINIMAL.format(id="e1").replace("time_to_target_alt",
                                              "climb_niceness"))


# ----------------------------------------------------------------------- arms
def test_an_arm_naming_a_procedure_that_does_not_exist_is_refused(tmp_path):
    """An experiment composes procedures; it cannot describe a flight."""
    with pytest.raises(experiments.ExperimentError, match="no procedure named"):
        parse(tmp_path, "e1", MINIMAL.format(id="e1").replace(
            "procedure: copter_takeoff", "procedure: copter_backflip"))


def test_an_input_the_procedure_does_not_declare_is_refused(tmp_path):
    """The silent, expensive typo: the procedure would fly its default.

    Every number in the report would be about that flight, and the document
    would say the experiment configured something else.
    """
    with pytest.raises(experiments.ExperimentError, match="not an input"):
        parse(tmp_path, "e1",
              MINIMAL.format(id="e1").replace("values: {alt: 12}",
                                              "values: {altitude: 12}"))


def test_two_arms_may_not_share_an_id(tmp_path):
    body = TWO_ARMS.format(id="e1").replace("  - id: faulted", "  - id: nominal")
    with pytest.raises(experiments.ExperimentError, match="share the id"):
        parse(tmp_path, "e1", body)


def test_a_run_count_outside_the_bounds_is_refused(tmp_path):
    for count in ("0", "500"):
        with pytest.raises(experiments.ExperimentError, match="runs"):
            parse(tmp_path, "e1",
                  MINIMAL.format(id="e1").replace("runs: 3", f"runs: {count}"))


def test_a_single_run_arm_is_allowed(tmp_path):
    """It is honest: the analysis reports n=1 and refuses to print a spread."""
    item = parse(tmp_path, "e1", MINIMAL.format(id="e1").replace("runs: 3",
                                                                 "runs: 1"))
    assert item.arms[0].runs == 1


def test_more_arms_than_the_ceiling_are_refused(tmp_path):
    arms = "\n".join(f"  - {{id: a{i}, procedure: copter_takeoff, runs: 2}}"
                     for i in range(experiments.MAX_ARMS + 1))
    body = MINIMAL.format(id="e1").split("arms:")[0] + f"arms:\n{arms}\n" + \
        "metrics: [time_to_target_alt]\ncompare: {policy: repeats}\n"
    with pytest.raises(experiments.ExperimentError, match="at most"):
        parse(tmp_path, "e1", body)


# -------------------------------------------------------------------- compare
def test_compare_is_required(tmp_path):
    body = MINIMAL.format(id="e1").replace("compare: {policy: repeats}", "")
    with pytest.raises(experiments.ExperimentError, match="'compare' is required"):
        parse(tmp_path, "e1", body)


def test_repeats_with_two_arms_is_refused(tmp_path):
    """Two arms and a `repeats` policy is a comparison somebody did not declare."""
    body = TWO_ARMS.format(id="e1").replace(
        "compare: {policy: arms, reference_arm: nominal}",
        "compare: {policy: repeats}")
    with pytest.raises(experiments.ExperimentError, match="repeats"):
        parse(tmp_path, "e1", body)


def test_arms_without_a_reference_arm_is_refused(tmp_path):
    body = TWO_ARMS.format(id="e1").replace(
        "compare: {policy: arms, reference_arm: nominal}",
        "compare: {policy: arms}")
    with pytest.raises(experiments.ExperimentError, match="reference_arm"):
        parse(tmp_path, "e1", body)


def test_the_reference_arm_and_the_role_must_agree(tmp_path):
    """Two statements of the same fact that disagree is two answers.

    Which side a delta is measured from cannot depend on which of the two a
    reader happened to look at.
    """
    body = TWO_ARMS.format(id="e1").replace("reference_arm: nominal",
                                            "reference_arm: faulted")
    with pytest.raises(experiments.ExperimentError, match="role"):
        parse(tmp_path, "e1", body)


def test_a_baseline_policy_refuses_a_reference_arm(tmp_path):
    body = TWO_ARMS.format(id="e1").replace(
        "compare: {policy: arms, reference_arm: nominal}",
        "compare: {policy: baseline, reference_arm: nominal}")
    with pytest.raises(experiments.ExperimentError, match="own earlier run"):
        parse(tmp_path, "e1", body)


# ----------------------------------------------------------------- acceptance
def test_a_criterion_may_only_judge_a_declared_metric(tmp_path):
    """Otherwise its verdict rests on a number the report does not show."""
    body = TWO_ARMS.format(id="e1").replace(
        "metric: tracking_error_roll_rms\n    max_delta",
        "metric: peak_angular_rate\n    max_delta")
    with pytest.raises(experiments.ExperimentError, match="metrics"):
        parse(tmp_path, "e1", body)


def test_a_criterion_naming_an_arm_that_does_not_exist_is_refused(tmp_path):
    body = TWO_ARMS.format(id="e1").replace("    arm: faulted", "    arm: other")
    with pytest.raises(experiments.ExperimentError, match="not an arm"):
        parse(tmp_path, "e1", body)


def test_a_delta_against_the_same_arm_is_refused(tmp_path):
    body = TWO_ARMS.format(id="e1").replace("delta_vs: nominal",
                                            "delta_vs: faulted")
    with pytest.raises(experiments.ExperimentError, match="itself"):
        parse(tmp_path, "e1", body)


def test_a_criterion_judging_two_things_at_once_is_refused(tmp_path):
    """A verdict has to have one reason."""
    body = TWO_ARMS.format(id="e1").replace(
        "    max_delta: 3.0", "    max_delta: 3.0\n    min_pass_rate: 1.0")
    with pytest.raises(experiments.ExperimentError, match="exactly one"):
        parse(tmp_path, "e1", body)


def test_a_pass_rate_criterion_may_not_carry_a_metric(tmp_path):
    body = TWO_ARMS.format(id="e1").replace(
        "    metric: tracking_error_roll_rms\n    max_delta: 3.0\n"
        "    delta_vs: nominal",
        "    metric: tracking_error_roll_rms\n    min_pass_rate: 1.0")
    with pytest.raises(experiments.ExperimentError, match="pass-rate"):
        parse(tmp_path, "e1", body)


def test_a_pass_rate_outside_zero_to_one_is_refused(tmp_path):
    body = TWO_ARMS.format(id="e1").replace(
        "    metric: tracking_error_roll_rms\n    max_delta: 3.0\n"
        "    delta_vs: nominal", "    min_pass_rate: 95")
    with pytest.raises(experiments.ExperimentError, match="between 0 and 1"):
        parse(tmp_path, "e1", body)


def test_an_inverted_range_is_refused(tmp_path):
    body = TWO_ARMS.format(id="e1").replace(
        "    max_delta: 3.0\n    delta_vs: nominal", "    min: 10\n    max: 5")
    with pytest.raises(experiments.ExperimentError, match="above max"):
        parse(tmp_path, "e1", body)


def test_criteria_without_declared_ids_get_positional_ones(tmp_path):
    body = TWO_ARMS.format(id="e1").replace("  - id: not-much-worse\n    arm:",
                                            "  - arm:")
    item = parse(tmp_path, "e1", body)
    assert item.accept[0].id == "a1"


# ---------------------------------------------------------------- limitations
def test_declared_limitations_are_kept_per_category(tmp_path):
    body = MINIMAL.format(id="e1") + """
limitations:
  assumptions:
    - {en: Still air., tr: Durgun hava.}
  out_of_scope:
    - Any wind at all.
"""
    item = parse(tmp_path, "e1", body)
    assert len(item.limitations[limitations.ASSUMPTIONS]) == 1
    assert item.limitations[limitations.ASSUMPTIONS][0]["tr"] == "Durgun hava."
    # A bare string is accepted and used for both languages.
    assert item.limitations[limitations.OUT_OF_SCOPE][0]["en"] == "Any wind at all."
    assert limitations.declared_count(item.limitations) == 2


def test_an_unknown_limitation_category_is_refused(tmp_path):
    """A limit filed under a name the report never prints is never read."""
    body = MINIMAL.format(id="e1") + "\nlimitations:\n  notes:\n    - Something.\n"
    with pytest.raises(experiments.ExperimentError, match="unknown category"):
        parse(tmp_path, "e1", body)


def test_an_empty_limitation_category_is_refused(tmp_path):
    body = MINIMAL.format(id="e1") + "\nlimitations:\n  assumptions: []\n"
    with pytest.raises(experiments.ExperimentError, match="non-empty"):
        parse(tmp_path, "e1", body)


def test_the_standing_limitations_cannot_be_dropped_by_a_definition(tmp_path):
    """The point of a standing limit: a file cannot leave it out.

    A document that could omit "nothing here was measured on hardware" by
    leaving a key out would omit it, and its reader would not know.
    """
    item = parse(tmp_path, "e1", MINIMAL.format(id="e1"))
    assert limitations.declared_count(item.limitations) == 0
    stated = limitations.statements(item.limitations, "en")
    assert stated, "an experiment with no declared limits printed nothing at all"
    for category in limitations.CATEGORIES:
        assert any(row["category"] == category for row in stated), (
            f"nothing at all is said about {category}")
    assert any("SITL" in row["text"] for row in stated)


def test_the_standing_limitations_exist_in_both_languages():
    for category, rows in limitations.STANDING.items():
        assert category in limitations.CATEGORIES
        for text in rows:
            assert text.get("en") and text.get("tr"), (
                f"a standing limitation in {category} is missing a language")
            assert text["en"] != text["tr"], (
                f"a standing limitation in {category} is the English text "
                f"pasted into Turkish")
    for category in limitations.CATEGORIES:
        for entry in (limitations.LABELS[category], limitations.WHAT[category]):
            assert entry.get("en") and entry.get("tr")


# ------------------------------------------------------------------- registry
def test_the_registry_reloads_when_a_file_changes(tmp_path):
    write(tmp_path, "e1", MINIMAL.format(id="e1"))
    assert set(experiments.load_all(tmp_path, force=True)) == {"e1"}
    write(tmp_path, "e2", MINIMAL.format(id="e2"))
    assert set(experiments.load_all(tmp_path)) == {"e1", "e2"}


def test_an_experiment_run_id_carries_the_experiment_and_sorts_by_time():
    identifier = experiments.experiment_run_id("copter_gps_loss_vs_nominal")
    assert identifier.endswith("_copter_gps_loss_vs_nominal")
    assert experiments.EXPERIMENT_RUN_PATTERN.match(identifier)


def test_an_experiment_run_id_cannot_carry_a_path_separator():
    """It reaches a directory name from an HTTP route, so it is untrusted."""
    identifier = experiments.experiment_run_id("../../etc/passwd")
    assert "/" not in identifier
    assert experiments.EXPERIMENT_RUN_PATTERN.match(identifier)


# ------------------------------------------------------------------- executor
class _FakeSession:
    """Stands in for a booted aircraft. Records what it was asked to fly."""

    def __init__(self, arm, definition, index, log: list) -> None:
        self.log = log
        self.arm, self.definition, self.index = arm, definition, index
        self.closed = False

    def run(self, procedure_id: str, values: dict):
        self.log.append({"arm": self.arm.id, "index": self.index,
                         "procedure": procedure_id, "values": dict(values),
                         "campaign": self.definition.id})
        return ({"run_id": f"{self.arm.id}-{self.index}"}, Path("/tmp"))

    def close(self) -> None:
        self.closed = True


def test_the_runner_flies_every_arm_in_order_through_a_campaign(tmp_path):
    """The P0 claim: an experiment executes by handing arms to CampaignRunner."""
    item = parse(tmp_path, "e1", TWO_ARMS.format(id="e1"))
    log: list = []
    sessions: list = []

    def launch(arm, definition, index):
        session = _FakeSession(arm, definition, index, log)
        sessions.append(session)
        return session

    runner = experiments.ExperimentRunner(item, "20260810T120000Z_e1", launch)
    rows = runner.run()

    assert [entry["arm"] for entry in log] == \
        ["nominal"] * 3 + ["faulted"] * 3, "the arms did not run in file order"
    assert [entry["index"] for entry in log] == [1, 2, 3, 1, 2, 3]
    assert all(session.closed for session in sessions), "a session was leaked"
    assert set(rows) == {"nominal", "faulted"}
    # Each arm was flown as its own campaign, with its own id.
    assert len({entry["campaign"] for entry in log}) == 2


def test_every_iteration_gets_the_experiments_configuration(tmp_path):
    item = parse(tmp_path, "e1", TWO_ARMS.format(id="e1"))
    log: list = []
    experiments.ExperimentRunner(
        item, "20260810T120000Z_e1",
        lambda arm, definition, index: _FakeSession(arm, definition, index, log)
    ).run()
    assert all(entry["values"] == {"alt": 20} for entry in log)


def test_a_run_is_stamped_with_its_experiment_and_arm(tmp_path):
    item = parse(tmp_path, "e1", TWO_ARMS.format(id="e1"))
    stamp = item.stamp("20260810T120000Z_e1", item.arm("faulted"), 2)
    assert stamp["run"] == "20260810T120000Z_e1"
    assert stamp["arm"] == "faulted"
    assert stamp["arm_role"] == experiments.TREATMENT
    assert stamp["index"] == 2 and stamp["of"] == 3
    assert stamp["procedure_id"] == "copter_gps_loss"
    assert stamp["policy"] == experiments.ARMS


def test_a_campaigns_own_events_are_forwarded_unchanged(tmp_path):
    """An arm IS a campaign, and its progress must arrive as campaign progress.

    Two things depend on this. A reader watching the terminal should see one
    vocabulary for one thing rather than an experiment translation of it. And
    the server routes on `type`: an event that arrived as an experiment event
    *and* as a campaign event would be broadcast twice, and a campaign of ten
    runs would render as twenty.
    """
    item = parse(tmp_path, "e1", TWO_ARMS.format(id="e1"))
    seen: list = []
    experiments.ExperimentRunner(
        item, "20260810T120000Z_e1",
        lambda arm, definition, index: _FakeSession(arm, definition, index, []),
        on_progress=seen.append).run()

    kinds = {event["type"] for event in seen}
    assert kinds == {"experiment", "campaign"}
    for event in seen:
        if event["type"] == "campaign":
            # Untranslated: still carrying the campaign's own keys.
            assert "campaign" in event
            assert "experiment" not in event
        else:
            assert event["run"] == "20260810T120000Z_e1"
    assert [e["event"] for e in seen if e["type"] == "experiment"][:2] == \
        ["start", "arm_start"]


def test_cancelling_stops_before_the_next_arm(tmp_path):
    item = parse(tmp_path, "e1", TWO_ARMS.format(id="e1"))
    log: list = []
    runner = None

    def launch(arm, definition, index):
        if arm.id == "nominal" and index == 3:
            runner.cancel()
        return _FakeSession(arm, definition, index, log)

    runner = experiments.ExperimentRunner(item, "20260810T120000Z_e1", launch)
    runner.run()
    assert "faulted" not in {entry["arm"] for entry in log}, (
        "cancellation did not stop the experiment before its second arm")
