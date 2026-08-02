"""The page works in a browser: console, terminals, status bar, panels.

Every assertion here is something a user would notice within ten seconds of
opening the page. They exist because all of it was broken once while the rest
of the suite was green.
"""
from __future__ import annotations

import subprocess

import pytest

from conftest import assert_no_console_errors, drift, open_page, start_server

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]


def test_page_loads_with_a_clean_console(browser_page, server):
    """The single most important assertion in the suite.

    The v1.1 regression produced exactly one observable symptom before the
    page went dead: `Uncaught (in promise) TypeError: Cannot read properties
    of undefined (reading 'length')`. A test that drove the page without
    reading the console would have sailed past it.
    """
    page = open_page(browser_page, server)
    assert page.title() == "ArgazUI"
    assert_no_console_errors(page, "while loading the page")


def test_both_terminal_websockets_connect_and_carry_data(browser_page, server):
    """Both tabs must actually stream. Neither did after the regression."""
    page = open_page(browser_page, server)
    page.wait_for_function(
        "() => document.getElementById('ws-state').textContent.includes('connected')",
        timeout=20000)

    # A command typed into the COMMAND tab must come back through the pty.
    page.click('.tab[data-stream="shell"]')
    page.wait_for_timeout(500)
    page.click("#term-shell")
    page.keyboard.type("echo argazui-e2e-marker\n")
    page.wait_for_function(
        "() => document.getElementById('term-shell').innerText"
        ".includes('argazui-e2e-marker')", timeout=20000)

    # And the SIMULATION tab carries its own stream, independently.
    page.click('.tab[data-stream="sim"]')
    page.wait_for_timeout(500)
    page.click("#term-sim")
    page.keyboard.type("echo argazui-sim-marker\n")
    page.wait_for_function(
        "() => document.getElementById('term-sim').innerText"
        ".includes('argazui-sim-marker')", timeout=20000)
    assert_no_console_errors(page, "after using both terminals")


def test_status_bar_states_a_reason_when_idle(browser_page, server):
    """No vehicle running is a state, not an absence of information.

    A bare "—" is what the user was left with; the bar must say why.
    """
    page = open_page(browser_page, server)
    link = page.inner_text("#pill-link")
    assert "—" not in link, f"the link chip is still a bare dash: {link!r}"
    assert page.get_attribute("#pill-link", "title"), "no explanation on the link chip"
    assert "START" in page.get_attribute("#pill-link", "title")


def test_disabled_buttons_say_why(browser_page, server):
    page = open_page(browser_page, server)
    page.click('label[data-id="skywalker_x8"] input[type=radio]')
    page.wait_for_timeout(600)
    buttons = page.eval_on_selector_all(
        "#buttons button", "els => els.map(e => ({d: e.disabled, tip: e.title}))")
    assert buttons, "no quick command buttons were rendered for a selected model"
    for button in buttons:
        if button["d"]:
            assert button["tip"], "a disabled button offers no explanation"


def test_runs_api_shape(server):
    """The contract the Flight Runs panel depends on."""
    body = server.api("/api/runs")
    assert isinstance(body.get("runs"), list), body
    assert "root" in body and "active" in body
    for run in body["runs"]:
        for key in ("run_id", "status", "procedures", "has_report", "advisory_count"):
            assert key in run, f"{key} missing from a run listing row: {run}"


def test_version_endpoint_reports_a_build_identity(server):
    body = server.api("/api/version")
    for key in ("version", "sha", "build_id", "started_utc", "restart_command",
                "digests_boot", "digests_now", "stale_layers"):
        assert key in body, f"{key} missing from /api/version: {body}"
    assert body["stale_layers"] == [], (
        "a freshly started server reports itself as stale: " + str(body))
    # The identity must be stamped into the page too, or the browser has
    # nothing to compare against.
    import urllib.request
    with urllib.request.urlopen(f"{server.url}/", timeout=10) as response:
        html = response.read().decode()
    assert f'content="{body["build_id"]}"' in html, "the page carries no build stamp"


# --------------------------------------------------------------- A3.1 regression
def test_banner_command_has_no_placeholder_and_parses_in_bash(browser_page, stale_server):
    """The recovery command must survive a copy-paste.

    A user pasted an earlier three-line block containing `<pid>` and got
    `bash: syntax error near unexpected token 'newline'`. A command that
    cannot be pasted is not a command. The banner is raised here by the real
    condition — a server with no /api/version — not by a test hook.
    """
    page = open_page(browser_page, stale_server)
    assert not page.eval_on_selector("#build-warning", "e => e.hidden"), (
        "no version warning against a server without /api/version")

    command = page.inner_text("#build-warning .build-fix")
    assert command.strip(), "the banner produced an empty command block"
    assert "<" not in command and ">" not in command, (
        f"the banner command contains a placeholder: {command!r}")

    # bash -n parses without executing. This is the exact check the paste failed.
    check = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True)
    assert check.returncode == 0, (
        f"the banner command is not valid bash: {command!r}\n{check.stderr}")


def test_the_banner_command_reports_cleanly_when_nothing_listens(browser_page, stale_server):
    """The fallback command's empty case must not be a bash error either.

    Its first version produced `kill: '': not a pid or valid job spec` when no
    process held the port — an error message about the wrong thing entirely.
    """
    page = open_page(browser_page, stale_server)
    command = page.inner_text("#build-warning .build-fix")
    # Port 9 (discard) is reserved and nothing will be listening on it here.
    probe = command.replace(f":{stale_server.port}", ":9") \
                   .replace(f"port {stale_server.port}", "port 9")
    result = subprocess.run(["bash", "-c", probe], capture_output=True, text=True)
    assert result.returncode != 0, "the command claimed success with no listener"
    assert "nothing is listening" in (result.stderr + result.stdout), (
        f"unhelpful failure with no listener: {result.stderr!r}")
    assert "not a pid" not in result.stderr, (
        f"the empty case still produces a bash error about an empty pid: {result.stderr!r}")


def test_a_stale_backend_is_reported_and_does_not_kill_the_page(browser_page, stale_server):
    """The original regression, end to end.

    Today's interface against yesterday's API: the version warning appears,
    the failing panel shows its own banner, and — the part that was broken —
    the rest of the page is still alive.
    """
    page = open_page(browser_page, stale_server)
    assert not page.eval_on_selector("#build-warning", "e => e.hidden")
    assert "could not be loaded" in page.inner_text("#err-runs"), (
        "the Flight Runs panel did not report its own failure")

    # The crux. connect() must have RUN despite a panel failing — that is the
    # whole regression. This stand-in has no /ws, so the socket cannot reach
    # "connected"; what matters is that it was attempted and reported, rather
    # than the chip being stuck in its initial placeholder because the startup
    # chain died before connect() was ever called.
    chip = page.inner_text("#ws-state")
    assert "disconnected" in chip, (
        f"the WebSocket was never attempted — a failing panel killed the "
        f"startup chain again. ws-state reads {chip!r}")
    # Panel isolation: the model list came from the same static files and must
    # still have rendered.
    assert page.eval_on_selector_all("#list-Plane li", "els => els.length") > 0, (
        "one failing panel took the model list down with it")
    assert page.inner_text("#pill-link").strip(), "the status bar went blank"


# --------------------------------------------------------------- A3.3 regression
def test_editing_server_code_raises_the_version_warning(browser_page, tmp_path):
    """Server code going stale must be visible, and named as such.

    The commit-based identity cannot see this: nothing is committed, so both
    sides report the same sha and the same dirty flag. It is also the everyday
    case — edit a file, forget to restart — and the layer that actually breaks
    the API contract.
    """
    running = start_server(tmp_path)
    try:
        assert running.api("/api/version")["stale_layers"] == []
        drift(running, "argazui/i18n.py", "# e2e: server-code drift probe")

        body = running.api("/api/version")
        assert "code" in body["stale_layers"], (
            f"editing a .py file did not register as stale: {body['stale_layers']}")

        page = open_page(browser_page, running)
        assert not page.eval_on_selector("#build-warning", "e => e.hidden"), (
            "the page did not warn that the server is running superseded code")
        text = page.inner_text("#build-warning")
        assert "server code" in text, f"the warning does not name the layer: {text!r}"
    finally:
        running.stop()


def test_editing_interface_files_names_that_layer_instead(browser_page, tmp_path):
    """And an interface-file change is reported as a different problem.

    "your fix is not running" and "this page is newer than the API answering
    it" need different reactions, so the warning must not blur them.
    """
    running = start_server(tmp_path)
    try:
        assert running.api("/api/version")["stale_layers"] == []
        drift(running, "static/style.css", "/* e2e: interface drift probe */")

        body = running.api("/api/version")
        assert body["stale_layers"] == ["ui"], body["stale_layers"]

        page = open_page(browser_page, running)
        text = page.inner_text("#build-warning")
        assert "interface files" in text, f"the warning does not name the layer: {text!r}"
        assert "server code" not in text, (
            "an interface change was reported as a server-code change")
    finally:
        running.stop()


def test_hot_reloaded_layers_do_not_demand_a_restart(tmp_path):
    """A procedure change is live immediately, so warning would be a lie.

    procedures.load_all() re-reads on mtime change and the config JSON is read
    per request. Telling someone to restart for those would be a false alarm,
    and false alarms are how a warning stops being read.
    """
    running = start_server(tmp_path)
    try:
        drift(running, "procedures/copter_takeoff.yaml", "# e2e: hot layer probe")
        body = running.api("/api/version")
        assert "procedures" in body["changed_layers"], body
        assert "procedures" not in body["stale_layers"], (
            "a hot-reloaded layer was reported as requiring a restart")
    finally:
        running.stop()
