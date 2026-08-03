"""The commands ArgazUI types into the simulation terminal.

WHY THIS IS A TEST AND NOT A COMMENT
------------------------------------
Tier 2 flies models in a container, and a container has no display. If CI flew
them with commands of its own — `gz sim -s` here, `--console --map` there —
then a green tier-2 result would say nothing about the button a person
presses, and the single-source rule this project is built on would be broken
in the one place nobody looks.

So `build_launch_commands` produces both, and the headless difference is
exactly two things: Gazebo runs server-only, and MAVProxy opens no windows.
These checks pin that down, in both directions.
"""
from __future__ import annotations

import pytest

from argazui import session

pytestmark = pytest.mark.tier1

GAZEBO_MODEL = {
    "id": "probe_model", "name": "probe", "vehicle_class": "Copter",
    "method": "gz_plus_sitl_paramfile", "env": "quadplane_env.sh",
    "world": "probe_runway.sdf", "vehicle": "ArduCopter", "frame": "hexa",
    "param_file": None, "extra_sitl_args": [], "lua_scripts": [],
}


@pytest.fixture
def display(monkeypatch):
    def _set(value: str | None) -> None:
        monkeypatch.delenv("ARGAZ_HEADLESS", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        if value is None:
            monkeypatch.delenv("DISPLAY", raising=False)
        else:
            monkeypatch.setenv("DISPLAY", value)
    return _set


def test_with_a_display_gazebo_and_mavproxy_show_their_windows(display):
    display(":0")
    text = "\n".join(session.build_launch_commands(GAZEBO_MODEL))
    assert "gz sim -v4 -r probe_runway.sdf &" in text, text
    assert " -s " not in text, "server-only was forced on a machine with a display"
    assert "--console" in text and "--map" in text


def test_without_a_display_gazebo_runs_server_only_and_mavproxy_is_silent(display):
    """The container case.

    `gz sim -r` starts a render window as well as physics; with no X server it
    dies, and the vehicle then waits forever for a physics backend that is not
    there. MAVProxy's --console/--map are X11 windows too, and losing MAVProxy
    takes the 14550 fan-out with it — ArgazUI would show no link to a vehicle
    that is otherwise running perfectly.
    """
    display(None)
    text = "\n".join(session.build_launch_commands(GAZEBO_MODEL))
    assert "gz sim -v4 -r -s probe_runway.sdf &" in text, text
    assert "--console" not in text, "MAVProxy would open a window with no display"
    assert "--map" not in text


def test_the_override_wins_over_a_present_display(monkeypatch):
    """So the headless path can be exercised from a desktop."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("ARGAZ_HEADLESS", "1")
    assert session.headless()
    monkeypatch.setenv("ARGAZ_HEADLESS", "0")
    assert not session.headless(), "ARGAZ_HEADLESS=0 did not force the windowed path"


def test_everything_else_about_the_launch_is_identical(display):
    """The two forms must differ ONLY in the display-dependent parts.

    This is the assertion that keeps the single-source rule honest: if a future
    change makes the headless path diverge in frame, parameters or ports, a
    tier-2 pass would stop meaning that the button works.
    """
    display(":0")
    windowed = session.build_launch_commands(GAZEBO_MODEL)
    display(None)
    headless = session.build_launch_commands(GAZEBO_MODEL)

    def normalise(lines: list[str]) -> list[str]:
        out = []
        for line in lines:
            line = line.replace("gz sim -v4 -r -s ", "gz sim -v4 -r ")
            line = line.replace(" --console --map", "")
            out.append(line)
        return out

    assert normalise(windowed) == normalise(headless), (
        "the headless launch differs from the windowed one by more than the "
        "display-dependent flags:\n"
        + "\n".join(f"  windowed: {w}\n  headless: {h}"
                    for w, h in zip(normalise(windowed), normalise(headless))
                    if w != h))
