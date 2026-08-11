"""F-09 — the model environment is the revision the configuration declared.

WHAT THIS FILE HAS TO PROVE, FROM §5 OF THE v1.7 BRIEF
------------------------------------------------------
    1 the pinned revision is used
    2 the resolved identity is recorded
    3 unavailability produces an environment failure
    4 no silent fallback to latest/main/HEAD occurs
    5 the same pin produces the same model environment

Every one of them is asserted against real git checkouts built in a temporary
directory, not against a stubbed `git_identity`. Stubbing it would test this
file's idea of what git says, and the finding being closed is precisely that
nobody had checked what git actually said.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from argazui import fingerprint, modelenv, paths

pytestmark = pytest.mark.tier1


# --------------------------------------------------------------- a real repo
def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, text=True).stdout.strip()


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    """A checkout shaped like SITL_Models: two commits and a working tree."""
    root = tmp_path / "SITL_Models"
    (root / "Gazebo" / "config").mkdir(parents=True)
    (root / "Gazebo" / "config" / "a.param").write_text("Q_ENABLE 1\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "suite@argaz.invalid")
    _git(root, "config", "user.name", "argaz suite")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first")
    return root


@pytest.fixture
def second_commit(assets: Path) -> str:
    (assets / "Gazebo" / "config" / "b.param").write_text("Q_ENABLE 0\n")
    _git(assets, "add", "-A")
    _git(assets, "commit", "-q", "-m", "second")
    return _git(assets, "rev-parse", "HEAD")


def _declared(revision, repository="https://example.invalid/SITL_Models.git"):
    return {"repository": repository, "revision": revision, "path": ""}


# ------------------------------------------------------ 1. the pin is used
def test_a_checkout_at_the_declared_revision_is_pinned(assets):
    head = _git(assets, "rev-parse", "HEAD")
    document = modelenv.verify(assets, _declared(head))
    assert document["state"] == modelenv.STATE_PINNED
    assert document["ok"] is True
    assert document["reproducible"] is True
    assert document["resolved_commit"] == head


def test_an_abbreviated_commit_pin_is_honoured(assets):
    """`git rev-parse --short` output is a perfectly ordinary way to write one.

    A full-string comparison would report a legitimate declaration as a
    mismatch, which would teach people to stop declaring one.
    """
    head = _git(assets, "rev-parse", "HEAD")
    assert modelenv.verify(assets, _declared(head[:12]))["state"] == \
        modelenv.STATE_PINNED


def test_a_tag_pin_is_honoured_when_head_stands_on_the_tag(assets):
    _git(assets, "tag", "v1.0")
    assert modelenv.verify(assets, _declared("v1.0"))["state"] == \
        modelenv.STATE_PINNED


def test_a_tag_pin_is_a_mismatch_once_head_has_moved_past_it(assets,
                                                             second_commit):
    _git(assets, "tag", "v1.0", second_commit + "~1")
    document = modelenv.verify(assets, _declared("v1.0"))
    assert document["state"] == modelenv.STATE_MISMATCH
    assert document["ok"] is False


# --------------------------------------------- 2. the identity is recorded
def test_the_resolved_identity_is_recorded_beside_the_declaration(assets):
    head = _git(assets, "rev-parse", "HEAD")
    evidence = modelenv.verify(assets, _declared(head))
    for field in ("repository", "revision", "resolved_commit", "identity"):
        assert evidence[field], f"{field} is not recorded"
    assert evidence["identity"].startswith("sha256:")


def test_a_run_fingerprint_carries_the_pin(tmp_path):
    """Inside the existing fingerprint, not in a second metadata store."""
    manifest = fingerprint.capture(model={"id": "m"}, procedures=[])
    pin = (manifest.get("sitl_models") or {}).get("pin")
    assert pin is not None, "the fingerprint records no model-environment pin"
    for field in ("repository", "revision", "resolved_commit", "identity",
                  "state", "ok", "reason"):
        assert field in pin, field
    assert pin["state"] in modelenv.STATES


def test_the_pin_identity_is_an_identity_field():
    """A different airframe is a different aircraft, and it must block a
    comparison the same way a different firmware does."""
    assert "sitl_models.pin.identity" in dict(fingerprint.IDENTITY_FIELDS)


# --------------------------------- 3. unavailability is an environment fault
def test_an_unidentifiable_checkout_is_unresolved_and_not_ok(tmp_path):
    """Nothing is guessed. A directory that is not a checkout says so."""
    plain = tmp_path / "not-a-checkout"
    plain.mkdir()
    document = modelenv.verify(plain, _declared("0" * 40))
    assert document["state"] == modelenv.STATE_UNRESOLVED
    assert document["ok"] is False
    assert "cannot be identified" in document["reason"]


def test_a_missing_directory_is_unresolved_rather_than_pinned(tmp_path):
    document = modelenv.verify(tmp_path / "absent", _declared("0" * 40))
    assert document["state"] == modelenv.STATE_UNRESOLVED
    assert document["ok"] is False


def test_a_mismatch_names_the_command_that_would_reconcile_it(assets,
                                                              second_commit):
    """The remedy is printed and never run.

    A tool that rearranged its own inputs so a check would pass has removed the
    check. The message is what makes the refusal actionable instead of merely
    correct.
    """
    first = _git(assets, "rev-parse", "HEAD~1")
    document = modelenv.verify(assets, _declared(first))
    assert document["state"] == modelenv.STATE_MISMATCH
    assert document["ok"] is False
    assert "git" in document["reason"] and "checkout" in document["reason"]
    # And the checkout was NOT moved to satisfy the declaration.
    assert _git(assets, "rev-parse", "HEAD") == second_commit


def test_a_refused_model_environment_classifies_as_environment():
    """The category the brief names, and never `acceptance`.

    Asserted through the lifecycle taxonomy rather than by reading a constant,
    because that is the path a real refusal takes: tier 2 fails the run, the
    lifecycle records the rung, and `classify_run` reads it.
    """
    from argazui import failures, simlifecycle

    lifecycle = simlifecycle.Lifecycle(label="probe")
    lifecycle.fail(simlifecycle.ENVIRONMENT_FAILED, "wrong revision")
    failure = failures.classify_run({"lifecycle": lifecycle.as_dict(),
                                     "procedures": []})
    assert failure is not None
    assert failure.category == failures.ENVIRONMENT
    assert failure.category != failures.ACCEPTANCE


# ------------------------------------------------- 4. no silent fallback
@pytest.mark.parametrize("moving", list(modelenv.MOVING_REFS))
def test_a_moving_ref_is_refused_rather_than_accepted(assets, moving):
    """HEAD, main, master, latest and current name whatever is there today.

    This is the finding itself: the tier-2 image cloned a branch, so two builds
    of one Dockerfile could fly different aircraft. A configuration that wrote
    the same thing down must be refused rather than honoured.
    """
    document = modelenv.verify(assets, _declared(moving))
    assert document["state"] == modelenv.STATE_INVALID
    assert document["ok"] is False
    assert modelenv.revision_kind(moving) is None


@pytest.mark.parametrize("moving", ["HEAD", "Main", "MASTER", "latest"])
def test_moving_refs_are_refused_whatever_their_case(assets, moving):
    assert modelenv.verify(assets, _declared(moving))["state"] == \
        modelenv.STATE_INVALID


def test_no_declaration_is_reported_as_unpinned_rather_than_invented(assets):
    """A developer without a declaration has violated nothing.

    The run records the ABSENCE — which is the project's rule everywhere else
    — instead of a pin nobody wrote, and `reproducible` is False so a release
    gate still refuses it.
    """
    document = modelenv.verify(assets, _declared(None))
    assert document["state"] == modelenv.STATE_UNPINNED
    assert document["ok"] is True
    assert document["reproducible"] is False
    assert document["revision"] is None


def test_an_unpinned_environment_is_not_release_reproducible(assets):
    assert modelenv.REPRODUCIBLE == frozenset({modelenv.STATE_PINNED})
    for state in (modelenv.STATE_UNPINNED, modelenv.STATE_MODIFIED,
                  modelenv.STATE_MISMATCH, modelenv.STATE_UNRESOLVED,
                  modelenv.STATE_INVALID):
        assert state not in modelenv.REPRODUCIBLE


# ------------------------------- 5. the same pin gives the same environment
def test_the_same_pin_resolves_to_the_same_identity_every_time(assets):
    head = _git(assets, "rev-parse", "HEAD")
    first = modelenv.verify(assets, _declared(head))
    second = modelenv.verify(assets, _declared(head))
    assert first["identity"] == second["identity"]
    assert first["identity"] is not None


def test_a_different_revision_resolves_to_a_different_identity(assets,
                                                               second_commit):
    first = _git(assets, "rev-parse", "HEAD~1")
    at_head = modelenv.verify(assets, _declared(second_commit))["identity"]
    _git(assets, "checkout", "-q", first)
    at_first = modelenv.verify(assets, _declared(first))["identity"]
    assert at_head != at_first


def test_an_edited_working_tree_is_a_different_environment_at_the_same_commit(
        assets):
    """The commit alone cannot identify a working tree.

    Exactly the reasoning that made `ardupilot.dirty_digest` an identity field
    in v1.6.1, applied to the model assets: a `.param` edited on top of the
    pinned revision changes what flew, and moves no commit.
    """
    head = _git(assets, "rev-parse", "HEAD")
    clean = modelenv.verify(assets, _declared(head))
    (assets / "Gazebo" / "config" / "a.param").write_text("Q_ENABLE 0\n")
    edited = modelenv.verify(assets, _declared(head))

    assert clean["state"] == modelenv.STATE_PINNED
    assert edited["state"] == modelenv.STATE_MODIFIED
    assert edited["identity"] != clean["identity"], (
        "an edit on top of the pinned revision produced the same identity, so "
        "two runs that flew different parameter files would compare as one")
    # Usable, and not release-reproducible. The two thresholds, in one case.
    assert edited["ok"] is True
    assert edited["reproducible"] is False


def test_the_same_edits_on_the_same_revision_are_the_same_environment(assets):
    """The counterweight, and the reason a digest was chosen over a flag.

    Refusing every working tree with edits would make the mechanism unusable
    during exactly the work it is most wanted for. Two runs minutes apart from
    one work in progress differ in nothing and must compare as identical.
    """
    head = _git(assets, "rev-parse", "HEAD")
    (assets / "Gazebo" / "config" / "a.param").write_text("Q_ENABLE 0\n")
    first = modelenv.verify(assets, _declared(head))["identity"]
    second = modelenv.verify(assets, _declared(head))["identity"]
    assert first == second


# ------------------------------------------------------- the declared pin
def test_this_installation_declares_a_pin():
    """The shipped configuration names a revision, and it is immutable.

    `argaz.toml` is what the tier images copy, so this is the declaration a CI
    run verifies against. A release whose own configuration was unpinned would
    make every other assertion in this file decorative.
    """
    declared = modelenv.declaration()
    assert declared["revision"], (
        "argaz.toml declares no [model_environment].revision")
    assert modelenv.revision_kind(declared["revision"]) is not None, (
        f"{declared['revision']!r} is not an immutable revision")
    assert declared["repository"], "the declaration names no repository"


def test_the_image_pin_and_the_configured_pin_agree():
    """`Dockerfile.tier2` and `argaz.toml` must name the same revision.

    Two declarations of one fact drift, and the way this one would drift is
    silent: the image would fetch one revision and the suite inside it would
    verify against another, so the check would pass while measuring nothing.
    """
    dockerfile = paths.ARGAZ / "docker" / "Dockerfile.tier2"
    if not dockerfile.is_file():
        pytest.skip(f"{dockerfile} is not in this installation")
    text = dockerfile.read_text(encoding="utf-8")
    found = re.search(r"^ARG SITL_MODELS_REF=(\S+)", text, re.MULTILINE)
    assert found, "Dockerfile.tier2 declares no SITL_MODELS_REF"
    assert found.group(1) == modelenv.declaration()["revision"], (
        f"Dockerfile.tier2 fetches {found.group(1)} and argaz.toml declares "
        f"{modelenv.declaration()['revision']}")


def test_the_configuration_summary_records_the_revision_not_the_key_name():
    """A summary recording only that a key existed cannot repeat a run.

    This is the same defect the audit found in `[regression]`, where
    `source_summary` recorded the key NAMES and not their values, and it is not
    being repeated for the field that identifies the aircraft.
    """
    summary = paths.source_summary()
    assert summary["model_environment_revision"] == \
        modelenv.declaration()["revision"]
