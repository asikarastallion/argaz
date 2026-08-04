"""A vehicle really flies, driven from the browser.

Uses SITL's own frames rather than a Gazebo model: the point is that the
application layer works, not that any particular airframe does. Model coverage
belongs to tier 2 and nowhere else.
"""
from __future__ import annotations

import json

import pytest

from harness import assert_no_console_errors, open_page, start_server

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]

# A registry entry pointing at a SITL frame, injected through the same
# models.json the UI reads. `method: sitl_only` runs SITL's own physics with
# no Gazebo and no display, which is what makes this affordable in CI. It is a
# real launch method, not a test-only shim: the same entry works if you add it
# to models.json by hand.
E2E_MODEL = {
    "id": "e2e_plane",
    "name": "E2E SITL plane",
    "vehicle_class": "Plane",
    "method": "sitl_only",
    "env": "env.sh",
    "world": None,
    "vehicle": "ArduPlane",
    "frame": "plane",
    "param_file": None,
    "extra_sitl_args": [],
    "lua_scripts": [],
    "has_ros2": False,
    "ros2": None,
    "source": "injected by tests/e2e",
    "needs_review": False,
    "image": None,
}


@pytest.fixture(scope="module")
def flight_server(tmp_path_factory):
    """A server whose registry contains one Gazebo-free model.

    The entry is written into a sandbox copy of the application, not into the
    checkout. An earlier version edited `argazui/config/models.json` in place
    and restored it in `finally`; a run that ends in SIGKILL never gets there,
    and leaves a test fixture committed into someone's registry.
    """
    from harness import sandbox_tree

    tmp = tmp_path_factory.mktemp("e2e-flight")
    tree = sandbox_tree(tmp)
    registry_path = tree / "config" / "models.json"
    registry = json.loads(registry_path.read_bytes())
    registry["models"] = [E2E_MODEL] + [
        m for m in registry["models"] if m["id"] != E2E_MODEL["id"]]
    registry_path.write_bytes(
        json.dumps(registry, indent=2, ensure_ascii=False).encode() + b"\n")

    running = start_server(tmp, tree=tree)
    try:
        yield running
    finally:
        running.post("/api/stop")
        running.stop()


def test_flying_from_the_browser(browser_page, flight_server):
    """START, watch the status bar fill, click a button, see the vehicle obey.

    This is the sequence the user reported as completely dead, asserted from
    the browser rather than from Python.
    """
    page = open_page(browser_page, flight_server)
    assert page.eval_on_selector("#build-warning", "e => e.hidden"), (
        "the freshly started server reports a build mismatch: "
        + page.inner_text("#build-warning"))

    page.click(f'label[data-id="{E2E_MODEL["id"]}"] input[type=radio]')
    page.wait_for_timeout(300)
    page.click("#btn-start")

    # --------------------------------------------------- the status bar fills
    page.wait_for_function(
        "() => document.getElementById('pill-link').textContent.includes('connected')",
        timeout=180000)
    page.wait_for_function(
        "() => !document.getElementById('pill-mode').textContent.includes('—')",
        timeout=60000)

    assert E2E_MODEL["name"] in page.inner_text("#pill-model")
    mode_before = page.inner_text("#pill-mode")
    assert "—" not in mode_before

    # --------------------------------------------- the terminal is streaming
    assert len(page.eval_on_selector("#term-sim", "e => e.innerText")) > 50, (
        "the simulation terminal shows nothing while a vehicle is running")

    # ------------------------------------------------ buttons become enabled
    page.wait_for_function(
        "() => { const b = document.querySelectorAll('#buttons button');"
        "        return b.length > 0 && [...b].every(x => !x.disabled); }",
        timeout=60000)

    # ------------------------------- a click produces a real vehicle change
    page.click("#buttons button:has-text('FBWA')")
    page.wait_for_function(
        "() => document.getElementById('pill-mode').textContent.includes('FBWA')",
        timeout=30000)
    terminal = page.eval_on_selector("#term-sim", "e => e.innerText")
    assert "mode -> FBWA" in terminal, (
        "the autopilot's ACK never reached the terminal:\n" + terminal[-800:])

    assert_no_console_errors(page, "during the flight")


def test_the_live_plot_line_says_where_to_listen_and_that_it_is_flowing(
        browser_page, flight_server):
    """The address a user pastes into PlotJuggler, from the page itself.

    `tests/test_telemetry_mirror.py` proves the port carries telemetry. This
    proves the interface tells someone where it is — the two halves of a
    feature whose entire value is a number a person has to copy correctly.

    It does not prove PlotJuggler draws anything; nothing here can see a
    rendered window. That row stays ✗ in docs/manual-checklist.md.
    """
    page = open_page(browser_page, flight_server)
    info = flight_server.api("/api/status")["plotjuggler"]
    assert info["enabled"] and info["running"], info

    assert not page.eval_on_selector("#livestream", "e => e.hidden"), (
        "a vehicle is running but the LIVE PLOT line is hidden")

    # Address and port are two separate, separately copyable values. This is
    # not cosmetic: a combined "127.0.0.1:14552" token is what gets pasted into
    # PlotJuggler's Address box, where a host:port string parses as no address
    # at all — it then reports a bind failure for a socket that is receiving
    # perfectly, and pressing OK on that dialog destroys it. The maintainer hit
    # exactly this. See USAGE.md 5d.
    assert page.inner_text("#ls-addr").strip() == info["host"]
    assert page.inner_text("#ls-port").strip() == str(info["port"])
    combined = f"{info['host']}:{info['port']}"
    warning = page.inner_text("#ls-warn")
    assert combined in warning, (
        "the strip does not warn against pasting host:port into Address")
    # Everywhere except inside that warning, the combined form must not appear.
    assert combined not in page.inner_text("#livestream").replace(warning, ""), (
        f"the LIVE PLOT strip presents {combined!r} as a value to copy again")

    # The `on` class is set only once messages have actually left the mirror,
    # so this waits for the stream rather than for the label. Independent of
    # the interface language, unlike the text beside it.
    page.wait_for_function("() => !!document.querySelector('#ls-state.on')",
                           timeout=30000)
    assert str(info["port"]) in page.inner_text("#ls-hint"), (
        "the hint does not name the port it tells the user to type")
    assert_no_console_errors(page, "with the live plot line shown")


def test_the_run_appears_in_the_panel_after_stop(browser_page, flight_server):
    """STOP archives the session and the panel shows it."""
    page = open_page(browser_page, flight_server)
    before = page.eval_on_selector_all("#runs-table tbody tr", "els => els.length")

    page.click("#btn-stop")
    page.click("#modal-ok")

    page.wait_for_function(
        "() => document.getElementById('pill-link').textContent.includes('not started')",
        timeout=120000)
    # The panel refreshes itself when the active model clears.
    page.wait_for_function(
        f"() => document.querySelectorAll('#runs-table tbody tr').length >= {max(before, 1)}",
        timeout=60000)

    rows = page.eval_on_selector_all(
        "#runs-table tbody tr", "els => els.map(e => e.innerText)")
    assert any(E2E_MODEL["id"] in row for row in rows), (
        f"the finished run is not listed:\n" + "\n".join(rows))

    body = flight_server.api("/api/runs")
    assert any(r["model"].get("id") == E2E_MODEL["id"] for r in body["runs"]), body

    # The live plot port belongs to the session, not to the server: STOP has
    # to close it, or a PlotJuggler left connected would keep showing the last
    # flight's numbers as though they were current.
    assert not flight_server.api("/api/status")["plotjuggler"]["running"]
    assert page.query_selector("#ls-state.on") is None, (
        "the LIVE PLOT line still reports a running stream after STOP")

    assert_no_console_errors(page, "after stopping the vehicle")
