"""The pinned model environment: which SITL_Models revision a run is entitled to.

WHY A PIN AND NOT A CHECKOUT
----------------------------
`ardupilot` is pinned by SHA in both Dockerfiles, with the reason written out
there: if the image tracked a branch, two builds of the same Dockerfile would
fly different autopilots and no two CI results could be compared. `SITL_Models`
— the source of every airframe, world and parameter file tier 2 exists to
verify — was cloned at HEAD, so exactly that comparison was already broken on
the half of the environment nobody had pinned.

The environment fingerprint has always RECORDED `sitl_models.commit`, so drift
was visible after the fact. Visible after the fact is not reproducibility: it
tells a reader that the experiment they are looking at cannot be repeated,
which is later than they needed to know.

WHAT THIS MODULE IS, AND WHAT IT IS NOT
---------------------------------------
It is a declaration and a check. It states, in `argaz.toml`, which revision of
which repository the model assets are supposed to be, resolves what they
actually are, and reports whether the two agree.

It is NOT a fetcher. Nothing here clones, checks out, pulls or modifies a
working tree. A verification tool that silently rearranged its own inputs to
make a check pass would be the exact failure this module exists to detect, and
the remedy for a mismatch is a person running `git checkout <sha>` in a
checkout they own. `reconcile_command()` prints that command; it never runs it.

THE ONE RULE
------------
A revision that can move is not an identity. `HEAD`, `main`, `master`,
`latest` and `current` name whatever is there today, so a run pinned to one of
them is pinned to nothing — and the finding this closes was precisely a clone
that tracked a moving ref. They are refused as configuration errors rather
than accepted and quietly under-delivered.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from . import paths
from .versions import CLEAN_TREE, git_identity

SCHEMA = 1

# ------------------------------------------------------------------- states
# Each is a different fact about the model environment, and only the first two
# permit a run that claims to be reproducible.
STATE_PINNED = "pinned"          # declared, resolved, and they are the same
STATE_UNPINNED = "unpinned"      # nothing is declared; the run says so
STATE_MISMATCH = "mismatch"      # declared and resolved, and they differ
STATE_UNRESOLVED = "unresolved"  # declared, but the checkout cannot say what it is
STATE_MODIFIED = "modified"      # the pinned revision, with uncommitted edits on it
STATE_INVALID = "invalid"        # the declaration itself names something that moves

STATES = (STATE_PINNED, STATE_UNPINNED, STATE_MISMATCH, STATE_UNRESOLVED,
          STATE_MODIFIED, STATE_INVALID)

# TWO THRESHOLDS, BECAUSE THERE ARE TWO QUESTIONS
# ------------------------------------------------
# "Is the declaration being honoured?" and "is this environment reproducible?"
# are not the same question, and collapsing them is how a check becomes either
# useless or unusable.
#
# SATISFIED answers the first. `unpinned` is in it because a developer working
# without a declaration has violated nothing — the run records the absence
# rather than inventing a pin. `modified` is in it for the reason v1.6.1 gave
# for using a digest instead of a `dirty` boolean: the declared revision WAS
# obtained, the edits on top of it are hashed into `identity`, so two runs
# with the same edits are still the same experiment. Refusing every working
# tree with edits would make the mechanism unusable during exactly the work it
# is most wanted for.
#
# REPRODUCIBLE answers the second, and only one state does: an exact immutable
# revision with nothing on top of it. That is what a release verification is
# entitled to demand, and it is what `argazui doctor --release` and the CI
# gate check.
SATISFIED = frozenset({STATE_PINNED, STATE_UNPINNED, STATE_MODIFIED})
REPRODUCIBLE = frozenset({STATE_PINNED})

# Refused as a `revision:`. Not a blocklist of strings that happen to be bad —
# these are the five names that mean "whatever is there now", which is the one
# thing a pin may not mean.
MOVING_REFS = ("head", "main", "master", "latest", "current")

_SHA = re.compile(r"^[0-9a-f]{7,40}$")
# A tag is the other immutable identity git offers. Deliberately narrow: a
# leading `v`, digits, dots, dashes and underscores. Anything else is either a
# branch or something this module should not be guessing about.
_TAG = re.compile(r"^v?[0-9][0-9A-Za-z._\-]*$")

REVISION_COMMIT = "commit"
REVISION_TAG = "tag"


class ModelEnvironmentError(RuntimeError):
    """The model environment is not the one the configuration declared.

    Raised only by callers that decided a mismatch must stop a run. This module
    itself never raises: `verify()` reports, and the layer that knows whether
    this is a release verification or a developer poking at a model decides
    what the report means.
    """


# -------------------------------------------------------------- declaration
def declaration() -> dict:
    """What `argaz.toml` (or the environment) says the model assets must be.

    Precedence follows `paths.py`'s published contract, so a CI job can pin a
    revision without editing a file that is under version control:

        ARGAZ_SITL_MODELS_REF  >  [model_environment].revision  >  nothing
    """
    table = getattr(paths, "MODEL_ENVIRONMENT", {}) or {}
    import os

    revision = (os.environ.get("ARGAZ_SITL_MODELS_REF")
                or table.get("revision") or "")
    return {
        "repository": str(table.get("repository") or "") or None,
        "revision": str(revision).strip() or None,
        "path": str(paths.SITL_MODELS),
    }


def revision_kind(revision: Optional[str]) -> Optional[str]:
    """`commit`, `tag`, or None when the value cannot identify anything fixed."""
    if not revision:
        return None
    value = revision.strip()
    if value.lower() in MOVING_REFS:
        return None
    if _SHA.match(value.lower()):
        return REVISION_COMMIT
    if _TAG.match(value):
        return REVISION_TAG
    return None


# ------------------------------------------------------------------ resolve
def resolve(root: Optional[Path] = None) -> dict:
    """What the model assets on disk actually are, or why they cannot say."""
    root = Path(root) if root else paths.SITL_MODELS
    identity = git_identity(root)
    return {
        "path": str(root),
        "commit": identity["commit"],
        "short_commit": identity.get("short_commit"),
        "describe": identity.get("describe"),
        "dirty": identity["dirty"],
        "dirty_digest": identity.get("dirty_digest"),
        "reason": identity.get("reason") or "",
    }


def content_identity(resolved: dict) -> Optional[str]:
    """One string naming exactly this model environment, or None.

    Two verifications of the same clean checkout at the same revision produce
    the same value; a working tree with edits on top of that revision produces
    a different one. This is what makes "the same pin gives the same model
    environment" a property a test can assert rather than a hope — the commit
    alone cannot, for the same reason `ardupilot.dirty_digest` had to be added
    to the fingerprint's identity fields in v1.6.1.
    """
    commit = resolved.get("commit")
    if not commit:
        return None
    digest = hashlib.sha256()
    digest.update(commit.encode("utf-8"))
    digest.update(b"\0")
    digest.update((resolved.get("dirty_digest") or CLEAN_TREE).encode("utf-8"))
    return "sha256:" + digest.hexdigest()[:32]


# ------------------------------------------------------------------- verify
def verify(root: Optional[Path] = None,
           declared: Optional[dict] = None) -> dict:
    """Declared against resolved, as one document a run record can carry.

    Returns `ok`, a `state` from STATES, both sides of the comparison, a
    content identity, and — when something is wrong — a `reason` written for
    the person who has to fix it rather than for a log parser.
    """
    declared = declaration() if declared is None else dict(declared)
    resolved = resolve(root)
    identity = content_identity(resolved)
    revision = declared.get("revision")
    kind = revision_kind(revision)

    def document(state: str, reason: str = "") -> dict:
        return {
            "schema": SCHEMA,
            "state": state,
            # Nothing contradicts the declaration.
            "ok": state in SATISFIED,
            # The environment is one immutable revision and nothing else.
            "reproducible": state in REPRODUCIBLE,
            "repository": declared.get("repository"),
            "revision": revision,
            "revision_kind": kind,
            "path": resolved["path"],
            "resolved_commit": resolved["commit"],
            "resolved_short_commit": resolved.get("short_commit"),
            "resolved_describe": resolved.get("describe"),
            "dirty": resolved["dirty"],
            "identity": identity,
            "reason": reason,
        }

    if not revision:
        return document(
            STATE_UNPINNED,
            "no model revision is declared. Set [model_environment].revision "
            "in argaz.toml (or ARGAZ_SITL_MODELS_REF) to the exact SITL_Models "
            "commit this verification is entitled to; until then two runs of "
            "the same scenario may have flown different aircraft.")

    if kind is None:
        return document(
            STATE_INVALID,
            f"[model_environment].revision is {revision!r}, which names "
            f"whatever is there today rather than one fixed revision. A pin "
            f"has to be an exact commit SHA or an immutable tag — "
            f"{', '.join(MOVING_REFS)} are refused.")

    if resolved["commit"] is None:
        return document(
            STATE_UNRESOLVED,
            f"{revision} is declared, but the model assets at "
            f"{resolved['path']} cannot be identified: {resolved['reason']}. "
            f"Nothing here guesses — an unidentifiable checkout is not "
            f"evidence that it is the right one.")

    if not _same_revision(revision, kind, resolved):
        return document(
            STATE_MISMATCH,
            f"the model assets at {resolved['path']} are at "
            f"{resolved['short_commit']}, and {revision} is declared. This run "
            f"would not be the experiment the configuration describes. "
            f"{reconcile_command(declared, resolved)}")

    if resolved["dirty"]:
        return document(
            STATE_MODIFIED,
            f"{resolved['path']} is at the declared revision {revision} with "
            f"uncommitted changes on top of it, so the airframes, worlds and "
            f"parameter files flown are not the ones that revision names.")

    return document(STATE_PINNED)


def _same_revision(revision: str, kind: str, resolved: dict) -> bool:
    """Does the checkout stand at the declared revision?

    A commit pin may be abbreviated — `git rev-parse --short` output is a
    perfectly ordinary way to write one down — so a prefix match is correct
    here and a full-string comparison would reject a legitimate declaration.
    A tag pin is compared against `git describe`, which reports the exact tag
    when HEAD is on it and appends a distance when it is not; requiring
    equality is therefore requiring "we are on the tag itself".
    """
    commit = (resolved.get("commit") or "").lower()
    if kind == REVISION_COMMIT:
        return commit.startswith(revision.strip().lower())
    describe = (resolved.get("describe") or "").strip()
    return describe == revision.strip()


def reconcile_command(declared: Optional[dict] = None,
                      resolved: Optional[dict] = None) -> str:
    """The command a person would run to make the checkout match the pin.

    Printed, never executed. See the module docstring: a tool that quietly
    rewrote its own inputs so a check would pass has removed the check.
    """
    declared = declaration() if declared is None else declared
    resolved = resolved or resolve()
    revision = declared.get("revision") or "<revision>"
    return (f"To reconcile: git -C {resolved['path']} fetch origin "
            f"{revision} && git -C {resolved['path']} checkout {revision}")


# --------------------------------------------------------------- for the run
def evidence(root: Optional[Path] = None) -> dict:
    """The block a run record carries, inside the existing fingerprint.

    Deliberately small and deliberately not a second metadata store: it names
    the repository, the declared revision, the commit that answered for it and
    the content identity, which are the four things §5 of the v1.7 brief asks
    every tier-2 run to record.
    """
    document = verify(root)
    return {
        "repository": document["repository"],
        "revision": document["revision"],
        "revision_kind": document["revision_kind"],
        "resolved_commit": document["resolved_commit"],
        "identity": document["identity"],
        "state": document["state"],
        "ok": document["ok"],
        "reproducible": document["reproducible"],
        "reason": document["reason"],
    }
