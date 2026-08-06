"""Characterisation tests — what the single-vehicle path does TODAY.

WHY THIS FILE EXISTS
--------------------
v1.3 adds a fleet engine beside the single-vehicle path, and the first rule of
that work is that the single-vehicle path does not change. "Does not change"
is not a thing anyone can check by reading a diff: the launch commands are
assembled from a registry entry, a config file and an environment probe, and a
refactor three layers down can move one of them without touching
`session.py` at all.

So this file pins the observable output of that path to a golden record, taken
before any fleet code existed. It asserts nothing about whether the current
behaviour is *right* — the other tier-1 tests do that. It asserts only that it
is the *same*. A diff here during v1.3 means the fleet work reached into the
single-vehicle path, which is exactly the thing that must not happen silently.

WHAT IS FROZEN, AND WHY EACH ONE
--------------------------------
`launch commands`  every registered model, headless and not. The world
                   composer (L2) and the supervisor (L3) both build launch
                   command lines; the temptation to "unify" them with this
                   function is the single most likely way v1.2 breaks.

`path resolution`  the precedence contract (CLI > env > argaz.toml > default).
                   L1 adds `fleet.max_vehicles` to argaz.toml, and a mistake
                   in how that key is read can change how every existing key
                   is read.

`procedure choice` which procedure a capability profile selects. L4 runs the
                   v1.1 procedure engine once per vehicle; a change to
                   selection would silently re-aim every fleet takeoff AND
                   every single-vehicle one.

`run artefacts`    the result schema and the run-directory naming rule. L6
                   writes fleet artefacts into the same `runs/` tree, and
                   `list_runs` decides what belongs there by name.

REGENERATING THE GOLDEN FILE
----------------------------
    python3 -m pytest tests/test_characterisation.py --regenerate-golden

Do that only when a change to the single-vehicle path is *intended*, and say
so in the commit message. Regenerating it to make a red test green is the one
use this file does not have.

IF YOU MUTATE THE SOURCE TO CHECK THAT THIS FILE STILL BITES, PURGE __pycache__
------------------------------------------------------------------------------
Proving a characterisation test can still fail means editing the code, running
the suite, and putting the code back. That sequence has a trap, and it cost a
whole baseline run here before it was understood:

    CPython invalidates a .pyc by comparing the source's mtime IN WHOLE
    SECONDS and its size in bytes.

`sleep 6` -> `sleep 7` -> `sleep 6` is the same size, and an edit-and-revert
inside one shell command is the same second. The .pyc written from the mutated
source then looks valid forever, and `session.py` on disk says one thing while
every import says the other. `git diff` is clean, the file reads correctly, and
the tests keep failing against a version of the code that no longer exists.

So after any mutate-and-revert:

    find argazui tests -name __pycache__ -type d -exec rm -rf {} +

or set PYTHONDONTWRITEBYTECODE=1 for the whole experiment.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from argazui import paths
from argazui import procedures as procs
from argazui import runs as runlib
from argazui import session

pytestmark = pytest.mark.tier1

GOLDEN = Path(__file__).resolve().parent / "golden" / "single_vehicle.json"


# --------------------------------------------------------------------- helpers
def _tokens() -> list[tuple[str, str]]:
    """Absolute paths that differ per machine, longest first.

    Longest first matters: ARGAZ is a prefix of every other root, so replacing
    it first would leave `<ARGAZ>/argazui/run` where `<RUN_DIR>` belongs and
    the golden file would encode this checkout's directory layout instead of
    the behaviour.
    """
    pairs = [
        ("<RUN_DIR>", paths.RUN_DIR),
        ("<SITL_MODELS>", paths.SITL_MODELS),
        ("<ARDUPILOT>", paths.ARDUPILOT),
        ("<ARDU_WS>", paths.ARDU_WS),
        ("<QUADPLANE_ENV>", paths.QUADPLANE_ENV_SH),
        ("<ENV_SH>", paths.ENV_SH),
        ("<RUNS_DIR>", paths.RUNS_DIR),
        ("<ARGAZ>", paths.ARGAZ),
    ]
    return sorted(((token, str(value)) for token, value in pairs),
                  key=lambda pair: len(pair[1]), reverse=True)


def normalise(text: str) -> str:
    """Machine-specific paths and ports out, stable tokens in."""
    for token, value in _tokens():
        text = text.replace(value, token)
    # The mission-script port is configuration, not behaviour.
    return re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:<SCRIPT_PORT>", text)


def _registry() -> list[dict]:
    document = json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
    return document["models"]


def _launch_snapshot(monkeypatch, headless: bool) -> dict:
    monkeypatch.setenv("ARGAZ_HEADLESS", "1" if headless else "0")
    out = {}
    for model in _registry():
        out[model["id"]] = [normalise(line)
                            for line in session.build_launch_commands(model)]
    return out


# Capability profiles the probe can actually produce, one per airframe kind
# this project flies. Named so a failure says which aircraft changed.
CAPABILITY_PROFILES = {
    "copter": {"autopilot": "ArduCopter", "quadplane": False, "tailsitter": False,
               "fw_takeoff_allowed": False, "arm_vtol_only": False},
    "plane": {"autopilot": "ArduPlane", "quadplane": False, "tailsitter": False,
              "fw_takeoff_allowed": False, "arm_vtol_only": False},
    "quadplane": {"autopilot": "ArduPlane", "quadplane": True, "tailsitter": False,
                  "fw_takeoff_allowed": False, "arm_vtol_only": False},
    "quadplane_fw_takeoff": {"autopilot": "ArduPlane", "quadplane": True,
                             "tailsitter": False, "fw_takeoff_allowed": True,
                             "arm_vtol_only": False},
    "tailsitter": {"autopilot": "ArduPlane", "quadplane": True, "tailsitter": True,
                   "fw_takeoff_allowed": False, "arm_vtol_only": False},
    "tailsitter_armvtol": {"autopilot": "ArduPlane", "quadplane": True,
                           "tailsitter": True, "fw_takeoff_allowed": False,
                           "arm_vtol_only": True},
}


def _procedure_snapshot() -> dict:
    out = {}
    for name, caps in CAPABILITY_PROFILES.items():
        chosen = {}
        for role in procs.ROLES:
            proc = procs.select(role, caps)
            chosen[role] = proc.id if proc else None
        chosen["candidates"] = {
            role: [p.id for p in procs.candidates(role, caps)] for role in procs.ROLES}
        out[name] = chosen
    return out


def _artefact_snapshot() -> dict:
    """The parts of the run-artefact contract other layers depend on."""
    return {
        "result_schema": runlib.RESULT_SCHEMA,
        "statuses": list(runlib.STATUSES),
        "run_id_pattern": runlib.RUN_ID_PATTERN.pattern,
        "procedure_roles": list(procs.ROLES),
        "step_types": list(procs.STEP_TYPES),
        "condition_keys": list(procs.CONDITION_KEYS),
        "capability_keys": list(procs.CAPABILITY_KEYS),
    }


def build_snapshot(monkeypatch) -> dict:
    return {
        "launch_headless": _launch_snapshot(monkeypatch, headless=True),
        "launch_with_display": _launch_snapshot(monkeypatch, headless=False),
        "procedures": _procedure_snapshot(),
        "artefacts": _artefact_snapshot(),
    }


@pytest.fixture(scope="module")
def golden() -> dict:
    if not GOLDEN.is_file():
        pytest.fail(f"golden record missing: {GOLDEN}\n"
                    f"Generate it with --regenerate-golden on a known-good tree.")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the checks
def test_every_registered_model_still_launches_the_same_way(monkeypatch, golden):
    """The exact shell lines, per model, headless.

    Compared per model rather than as one blob so a failure names the model
    and the line instead of printing eleven launch scripts.
    """
    current = _launch_snapshot(monkeypatch, headless=True)
    recorded = golden["launch_headless"]

    assert sorted(current) == sorted(recorded), (
        "the set of registered models changed — a model was added or removed. "
        "That is a registry change, not a launch-path change; regenerate the "
        "golden record deliberately.")
    for model_id in sorted(recorded):
        assert current[model_id] == recorded[model_id], (
            f"launch commands for {model_id!r} changed:\n"
            f"  was: {recorded[model_id]}\n"
            f"  now: {current[model_id]}")


def test_the_display_path_still_differs_only_where_it_did(monkeypatch, golden):
    """A machine with a display gets the same two additions and no others."""
    current = _launch_snapshot(monkeypatch, headless=False)
    recorded = golden["launch_with_display"]
    for model_id in sorted(recorded):
        assert current[model_id] == recorded[model_id], (
            f"windowed launch commands for {model_id!r} changed:\n"
            f"  was: {recorded[model_id]}\n"
            f"  now: {current[model_id]}")


def test_capability_profiles_still_choose_the_same_procedures(golden):
    current = _procedure_snapshot()
    recorded = golden["procedures"]
    for profile in sorted(recorded):
        assert current[profile] == recorded[profile], (
            f"procedure selection changed for the {profile!r} airframe:\n"
            f"  was: {recorded[profile]}\n"
            f"  now: {current[profile]}")


def test_the_run_artefact_contract_is_unchanged(golden):
    """Schema numbers and vocabularies other layers read.

    A fleet run writes into the same `runs/` tree. If `RUN_ID_PATTERN` or the
    status vocabulary moves, every existing run directory changes meaning —
    including the ones docs/status.md is generated from.
    """
    assert _artefact_snapshot() == golden["artefacts"]


def test_path_precedence_is_still_cli_over_env_over_toml(monkeypatch, tmp_path):
    """The contract paths.py documents, exercised rather than read.

    Not a golden comparison: the answer is a rule, and stating the rule as
    three assertions is clearer than three recorded strings.
    """
    config = tmp_path / "argaz.toml"
    config.write_text('ardupilot_root = "from_toml"\nport = 9001\n', encoding="utf-8")
    monkeypatch.setenv("ARGAZ_CONFIG", str(config))

    try:
        monkeypatch.delenv("ARGAZ_ARDUPILOT_ROOT", raising=False)
        paths.configure()
        assert paths.ARDUPILOT == (tmp_path / "from_toml").resolve()
        assert paths.HTTP_PORT == 9001

        monkeypatch.setenv("ARGAZ_ARDUPILOT_ROOT", str(tmp_path / "from_env"))
        paths.configure()
        assert paths.ARDUPILOT == (tmp_path / "from_env").resolve(), \
            "environment must win over argaz.toml"

        paths.configure(ardupilot_root=str(tmp_path / "from_cli"))
        assert paths.ARDUPILOT == (tmp_path / "from_cli").resolve(), \
            "a CLI override must win over both"
    finally:
        # Every later test in this session reads these module-level constants.
        monkeypatch.undo()
        paths.configure()


def test_building_launch_commands_is_repeatable(monkeypatch):
    """Same registry, same environment, same lines — twice.

    `build_launch_commands` writes `argazui_overrides.parm` for models that
    declare `sitl_param_overrides`, so it is not a pure function. This pins
    that the side effect does not feed back into the output.
    """
    first = _launch_snapshot(monkeypatch, headless=True)
    second = _launch_snapshot(monkeypatch, headless=True)
    assert first == second


# ---------------------------------------------------------------- regeneration
# `--regenerate-golden` is declared in conftest.py: pytest only reads
# pytest_addoption from conftest files and plugins, never from a test module.
def test_regenerate(request, monkeypatch):
    """Rewrites the golden record. Skipped unless explicitly asked for."""
    if not request.config.getoption("--regenerate-golden", default=False):
        pytest.skip("run with --regenerate-golden to rewrite the golden record")
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(
        json.dumps(build_snapshot(monkeypatch), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"\nwrote {GOLDEN}")
