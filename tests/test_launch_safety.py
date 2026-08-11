"""Registry values are data, and a repeated run starts from a stated state.

TWO FINDINGS, ONE FILE, BECAUSE THEY ARE THE SAME BOUNDARY
----------------------------------------------------------
`build_launch_commands` turns a `models.json` entry into shell lines that are
typed into a real interactive bash session. Everything that crosses that
boundary is either quoted data or executable syntax, and until the v1.6
corrective release the paths were quoted and the registry fields were not — so
a model whose `frame` read `quad; touch /tmp/x` ran `touch`.

The same function decides what state the simulated vehicle boots from. SITL's
working directory is reused between runs, so without `-w` each run inherits
whatever the previous one left in `eeprom.bin` — which makes a repeatability
campaign's central claim ("the same configuration, N times") unverifiable,
because the environment fingerprint hashes the `.param` FILE and cannot see the
eeprom.

WHY THE QUOTING IS TESTED THROUGH A REAL SHELL
----------------------------------------------
Asserting on the generated string only proves it matches what the author
expected it to look like. `test_metacharacters_never_execute` runs the line
under `bash` with `sim_vehicle.py` replaced by a function that prints its
arguments, and asserts on what the shell actually parsed. That is the only
check that would have failed before the fix and passes after it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from argazui import paths, runs, session

pytestmark = pytest.mark.tier1

ROOT = Path(__file__).resolve().parent.parent


def _model(**overrides) -> dict:
    base = {"id": "probe", "name": "Probe", "vehicle_class": "Plane",
            "method": "gz_plus_sitl_paramfile", "vehicle": "ArduPlane",
            "world": "probe_runway.sdf",
            "param_file": "$SITL_MODELS/Gazebo/config/probe.param",
            "env": "env.sh"}
    return {**base, **overrides}


def _sitl_line(model: dict) -> str:
    return next(line for line in session.build_launch_commands(model)
                if "sim_vehicle.py" in line)


# --------------------------------------------------------------------- F-06
PAYLOADS = [
    "quad; touch PWNED",
    "$(touch PWNED)",
    "`touch PWNED`",
    "a && touch PWNED",
    "a | touch PWNED",
    "a > PWNED",
    "*",
    "~",
    "'; touch PWNED; '",
    'a" ; touch PWNED ; "',
]


@pytest.mark.parametrize("payload", PAYLOADS)
@pytest.mark.parametrize("field", ["frame", "world", "vehicle", "param_file"])
def test_metacharacters_never_execute(tmp_path, payload, field):
    """The real test: hand the generated line to bash and see what it parsed."""
    marker = tmp_path / "PWNED"
    injected = payload.replace("PWNED", str(marker))
    commands = session.build_launch_commands(_model(**{field: injected}))

    script = tmp_path / "probe.sh"
    body = ["set -u",
            "SITL_MODELS=/opt/models",
            "gz(){ printf 'GZ:%s\\n' \"$@\"; }",
            "sim_vehicle.py(){ printf 'ARG:%s\\n' \"$@\"; }",
            "sleep(){ :; }",
            "source(){ :; }",
            "cd(){ :; }",
            "mkdir(){ :; }"]
    # The launch lines themselves, minus the `source`/`mkdir`/`cd` which the
    # stubs above neutralise anyway.
    body += [line for line in commands]
    script.write_text("\n".join(body) + "\n", encoding="utf-8")

    result = subprocess.run(["bash", str(script)], capture_output=True,
                            text=True, timeout=30, cwd=str(tmp_path))
    assert not marker.exists(), (
        f"{field}={injected!r} executed through the shell\n"
        f"line: {commands}\nstdout: {result.stdout}")


def test_the_payload_survives_as_one_literal_argument(tmp_path):
    """Quoted is not enough — it has to still be the value the model declared."""
    payload = "quad; touch /tmp/x"
    script = tmp_path / "probe.sh"
    script.write_text(
        "SITL_MODELS=/opt/models\n"
        "sim_vehicle.py(){ printf 'ARG:%s\\n' \"$@\"; }\n"
        + _sitl_line(_model(frame=payload)) + "\n", encoding="utf-8")
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                         timeout=30).stdout
    assert f"ARG:{payload}\n" in out, out


def test_an_environment_variable_in_a_param_path_still_expands(tmp_path):
    """`$SITL_MODELS` is how every shipped model names its parameter file.

    Blind quoting would have "fixed" the injection by breaking every model in
    the registry, which is why this test sits directly beside the ones above.
    """
    script = tmp_path / "probe.sh"
    script.write_text(
        "SITL_MODELS=/opt/models\n"
        "sim_vehicle.py(){ printf 'ARG:%s\\n' \"$@\"; }\n"
        + _sitl_line(_model()) + "\n", encoding="utf-8")
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                         timeout=30).stdout
    assert "ARG:--add-param-file=/opt/models/Gazebo/config/probe.param\n" in out, out


@pytest.mark.parametrize("bad", ["a\nb", "a\rb", "a\0b"])
def test_a_value_that_cannot_be_one_line_is_refused(bad):
    """A newline would end the command the pty is being fed and start another."""
    with pytest.raises(session.LaunchError):
        session.build_launch_commands(_model(frame=bad))


def test_every_shipped_model_still_builds():
    """The registry this project actually ships must survive the validator."""
    registry = json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
    for model in registry.get("models", []):
        commands = session.build_launch_commands(model)
        assert commands and commands[0].startswith("source ")


def test_shell_word_is_idempotent_for_ordinary_values():
    for value in ("plane", "hexa", "gazebo-zephyr", "zephyr_runway.sdf",
                  "hexapod_copter.lua", "--speedup", "5"):
        assert session.shell_word(value) == value, value


# --------------------------------------------------------------------- F-07
def test_a_launch_wipes_the_simulated_eeprom_by_default():
    """Every run starts from the model's declared configuration, not the last."""
    assert " -w " in f" {_sitl_line(_model())} "


def test_the_sitl_only_path_wipes_too():
    assert " -w " in f" {_sitl_line(_model(method='sitl_only'))} "


def test_a_model_may_opt_out_of_wiping_in_so_many_words():
    """State persistence is allowed, and it has to be declared to happen."""
    assert " -w " not in f" {_sitl_line(_model(persist_eeprom=True))} "
    assert session.wipes_eeprom(_model()) is True
    assert session.wipes_eeprom(_model(persist_eeprom=True)) is False


def test_every_shipped_model_starts_from_a_wiped_eeprom():
    registry = json.loads(paths.MODELS_JSON.read_text(encoding="utf-8"))
    for model in registry.get("models", []):
        if model.get("method") == "ros2_launch":
            continue        # ArgazUI does not compose its SITL command line
        assert " -w " in f" {_sitl_line(model)} ", model["id"]


def test_the_run_record_states_the_initial_state(tmp_path):
    """A campaign's claim of N identical repetitions has to be checkable.

    `eeprom_wiped` is read back out of the launch commands the run actually
    used, so it reports what was typed rather than what was intended.
    """
    model = _model()
    commands = session.build_launch_commands(model)
    recorder = runs.RunRecorder(model=model, root=tmp_path,
                                launch_commands=commands,
                                work_dir=tmp_path / "work")
    result = recorder.finish(report=False)
    state = result["initial_state"]
    assert state["eeprom_wiped"] is True
    assert any("sim_vehicle.py" in line for line in state["launch_commands"])


def test_two_iterations_of_a_campaign_declare_the_same_initial_state(tmp_path):
    """The property a repeatability campaign rests on, asserted directly."""
    model = _model()
    states = []
    for _ in range(2):
        recorder = runs.RunRecorder(
            model=model, root=tmp_path,
            launch_commands=session.build_launch_commands(model),
            work_dir=tmp_path / "work",
            campaign={"id": "c1", "index": len(states) + 1, "of": 2})
        states.append(recorder.finish(report=False)["initial_state"])
    assert states[0] == states[1]
    assert states[0]["eeprom_wiped"] is True


def test_a_ros2_model_says_it_did_not_wipe_rather_than_claiming_it_did(tmp_path):
    """None is the third answer: not wiped, and not ours to wipe."""
    recorder = runs.RunRecorder(
        model=_model(method="ros2_launch",
                     ros2={"package": "ardupilot_gz_bringup",
                           "launch_file": "iris.launch.py"}),
        root=tmp_path,
        launch_commands=session.build_launch_commands(
            _model(method="ros2_launch",
                   ros2={"package": "ardupilot_gz_bringup",
                         "launch_file": "iris.launch.py"})),
        work_dir=tmp_path / "work")
    assert recorder.finish(report=False)["initial_state"]["eeprom_wiped"] is None
