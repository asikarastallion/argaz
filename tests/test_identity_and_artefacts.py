"""Two runs are only comparable if something can show they are the same, and a
generated document is only evidence if it describes the code that is here.

F-08 — FINGERPRINT IDENTITY
---------------------------
`differences()` compared four fields. `dirty` was captured from the first
release and compared by nothing, so two runs flown from two different sets of
uncommitted changes on one SHA reported themselves as the same configuration.
So did two runs across a Gazebo upgrade, which changes the physics and moves no
commit anywhere.

F-03 — GENERATED ARTEFACTS
--------------------------
`docs/status.md` and `docs/coverage.md` are machine output and are committed.
v1.6 shipped with both still describing v1.5 — most visibly, `coverage.md`
carried four dimensions while `coverage.py` declared five, so the published
report told a reader the project measures something it no longer measures.

A byte-comparison against freshly generated output cannot be a test: both
documents are computed from whatever runs are on disk, which differs between a
developer's machine and a CI runner. What IS deterministic is their STRUCTURE —
every dimension the code declares must have a section, the schema the generator
writes must be the current one, and the README summary must agree with the
table it was generated from. That is exactly the staleness that shipped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from argazui import coverage, fingerprint, metrics, status

pytestmark = pytest.mark.tier1

ROOT = Path(__file__).resolve().parent.parent
STATUS_MD = ROOT / "docs" / "status.md"
COVERAGE_MD = ROOT / "docs" / "coverage.md"
README = ROOT / "README.md"


# ------------------------------------------------------------------- F-08
def _fp(**over) -> dict:
    base = {
        "argaz": {"commit": "a" * 40, "dirty": False, "dirty_digest": "clean"},
        "ardupilot": {"commit": "b" * 40, "dirty": False,
                      "dirty_digest": "clean", "firmware_commit": "b" * 12},
        "model": {"config_hash": "sha256:m"},
        "procedure_hash": "sha256:p",
        "gazebo": {"version": "Gazebo Sim, version 8.9.0"},
    }
    for dotted, value in over.items():
        node = base
        parts = dotted.split("__")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return base


def test_two_identical_clean_runs_are_comparable():
    """The premise. Adding fields must not make everything incomparable."""
    assert fingerprint.differences(_fp(), _fp()) == []


def test_two_different_dirty_trees_do_not_read_as_the_same_configuration():
    """`True == True` used to pass. Two dirty ArduPilot trees are not one tree.

    A boolean cannot say WHICH edits, so identity is a content digest of the
    uncommitted work — which also keeps the case below comparable.
    """
    fields = {d["field"] for d in fingerprint.differences(
        _fp(ardupilot__dirty=True, ardupilot__dirty_digest="sha256:aaa"),
        _fp(ardupilot__dirty=True, ardupilot__dirty_digest="sha256:bbb"))}
    assert "ardupilot.dirty_digest" in fields


def test_two_runs_from_the_same_dirty_tree_stay_comparable():
    """Development must not disable the layer that is most useful during it."""
    left = _fp(ardupilot__dirty=True, ardupilot__dirty_digest="sha256:same")
    right = _fp(ardupilot__dirty=True, ardupilot__dirty_digest="sha256:same")
    assert fingerprint.differences(left, right) == []


def test_a_clean_tree_and_a_dirty_one_are_not_the_same_configuration():
    fields = {d["field"] for d in fingerprint.differences(
        _fp(), _fp(ardupilot__dirty=True, ardupilot__dirty_digest="sha256:ccc"))}
    assert "ardupilot.dirty_digest" in fields


def test_argaz_is_not_an_identity_field():
    """The harness is not the aircraft, and half a rule is worse than none.

    `argaz.commit` has never been compared. Comparing only its dirty digest was
    an inconsistent half-rule, and because `/opt/argaz` is not a git checkout
    inside the tier-1 image it made EVERY comparison there incomparable — two
    tier-1 tests went red on a run that was otherwise fine.
    """
    compared = {dotted for dotted, _ in fingerprint.IDENTITY_FIELDS}
    assert not {d for d in compared if d.startswith("argaz.")}, (
        f"ArgazUI's own source is being compared: {sorted(compared)}")


# ------------------------------- an absent component does not block a comparison
def _container_fp(**over) -> dict:
    """A fingerprint as the tier-1 image produces one.

    `/opt/argaz` is not a git checkout there and Gazebo is not installed, so
    both fields are `null` for a STRUCTURAL reason rather than because anything
    went wrong — and they are null on both sides of every comparison made in
    that environment.
    """
    base = _fp()
    base["argaz"] = {"commit": None, "dirty": None, "dirty_digest": None}
    base["gazebo"] = {"version": None}
    for dotted, value in over.items():
        node, parts = base, dotted.split("__")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return base


def test_two_runs_in_an_environment_without_gazebo_are_comparable():
    """Tier 1 has no Gazebo by design; that must not refuse every comparison."""
    assert fingerprint.differences(_container_fp(), _container_fp()) == []


def test_gazebo_known_on_one_side_only_is_still_a_difference():
    """Unknown on BOTH sides does not discriminate. Unknown on one side does."""
    with_gz = _container_fp(gazebo__version="Gazebo Sim, version 8.14.0")
    fields = {d["field"] for d in
              fingerprint.differences(_container_fp(), with_gz)}
    assert "gazebo.version" in fields


def test_a_gazebo_upgrade_between_two_runs_that_had_one_is_still_caught():
    fields = {d["field"] for d in fingerprint.differences(
        _container_fp(gazebo__version="Gazebo Sim, version 8.14.0"),
        _container_fp(gazebo__version="Gazebo Sim, version 9.0.0"))}
    assert "gazebo.version" in fields


def test_only_genuinely_optional_components_get_the_exemption():
    """A blanket both-unknown exemption would silently widen every comparison.

    `ardupilot.firmware_commit` is null on both sides of any tier-1 comparison
    too — a run that never armed writes no log — and that has always been
    reported as incomparable. The exemption is a named set, not a rule.
    """
    assert fingerprint.OPTIONAL_IDENTITY == {"gazebo.version"}
    both_missing = _fp(ardupilot__firmware_commit=None)
    fields = {d["field"] for d in
              fingerprint.differences(both_missing, both_missing)}
    assert "ardupilot.firmware_commit" in fields


def test_a_gazebo_upgrade_is_a_configuration_difference():
    """The simulator is half the physics and moves no commit here."""
    diff = fingerprint.differences(
        _fp(), _fp(gazebo__version="Gazebo Sim, version 9.0.0"))
    assert [d["field"] for d in diff] == ["gazebo.version"]
    assert diff[0]["reason"] == "changed"


def test_an_unknown_identity_is_still_a_difference_not_a_match():
    """"Nothing can show these are the same" is the condition that matters."""
    diff = fingerprint.differences(_fp(), _fp(gazebo__version=None))
    assert [d["field"] for d in diff] == ["gazebo.version"]
    assert "unknown" in diff[0]["reason"]


def test_a_missing_checkout_is_recorded_as_unknown_with_a_reason(tmp_path):
    """No version is ever invented for a directory nothing could identify."""
    identity = fingerprint.git_identity(tmp_path)
    assert identity["commit"] is None and identity["dirty"] is None
    assert "not a git checkout" in identity["reason"]

    missing = fingerprint.git_identity(tmp_path / "nope")
    assert missing["commit"] is None
    assert "does not exist" in missing["reason"]


def test_every_identity_field_is_reachable_in_a_real_fingerprint():
    """A typo in the tuple would silently stop comparing that field."""
    manifest = fingerprint.capture(model={"id": "m"}, procedures=[])
    for dotted, _ in fingerprint.IDENTITY_FIELDS:
        node, missing = manifest, False
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                missing = True
                break
            node = node[part]
        assert not missing, f"{dotted} is compared but never captured"


# ------------------------------------------------------------------- F-03
@pytest.mark.skipif(not COVERAGE_MD.is_file(), reason="no generated coverage.md")
def test_the_published_coverage_report_has_every_dimension_the_code_declares():
    """The exact shape of the staleness that shipped with v1.6."""
    text = COVERAGE_MD.read_text(encoding="utf-8")
    missing = [name for name in coverage.DIMENSIONS
               if f"## {coverage.LABELS[name]['en']}" not in text]
    assert not missing, (
        f"docs/coverage.md is missing {missing}. Regenerate it: "
        f"python3 -m argazui coverage --runs runs --out docs/coverage.md")


@pytest.mark.skipif(not COVERAGE_MD.is_file(), reason="no generated coverage.md")
def test_the_published_coverage_report_names_no_dimension_the_code_dropped():
    text = COVERAGE_MD.read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (.+)$", text, re.MULTILINE))
    known = {coverage.LABELS[name]["en"] for name in coverage.DIMENSIONS}
    known.add("What a covered item does and does not mean")
    assert not headings - known, f"sections from an older generator: {headings - known}"


@pytest.mark.skipif(not STATUS_MD.is_file(), reason="no generated status.md")
def test_the_published_status_table_was_written_by_this_generator():
    text = STATUS_MD.read_text(encoding="utf-8")
    assert "GENERATED FILE — DO NOT EDIT BY HAND" in text
    for heading in ("# Model verification status", "## What tier 1 verified",
                    "## What was actually verified"):
        assert heading in text, heading


@pytest.mark.skipif(not (STATUS_MD.is_file() and README.is_file()),
                    reason="no generated artefacts")
def test_the_readme_summary_agrees_with_the_status_table():
    """Both are written by one generator from one dataset, in one pass.

    They disagreed for two days once, because a commit staged only the first.
    """
    summary = re.search(r"<!-- STATUS-SUMMARY:.*?-->(.*?)<!-- /STATUS-SUMMARY -->",
                        README.read_text(encoding="utf-8"), re.DOTALL)
    assert summary, "the README has no STATUS-SUMMARY block"
    stamp = re.search(r"generated (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)",
                      summary.group(1))
    assert stamp, f"the summary states no generation time: {summary.group(1)!r}"
    assert stamp.group(1) in STATUS_MD.read_text(encoding="utf-8"), (
        "README.md and docs/status.md were generated from different runs; "
        "regenerate both with `python3 -m argazui status`")


def test_the_generator_declares_the_schema_it_writes():
    """A bare number, asserted so a bump has to be a decision."""
    assert status.SCHEMA >= 4
    assert coverage.SCHEMA >= 1
    assert metrics.SCHEMA >= 2, (
        "metrics gained `clock` and `window`; a reader has to be able to tell "
        "a document that carries them from one that does not")
