"""End-to-end fixtures: a real ArgazUI server, driven through a real browser.

WHY THIS LAYER EXISTS
---------------------
Every tier-1 test drives `RunRecorder` and `ProcedureRunner` directly. That is
the right way to test procedure logic, and it is why they were all green while
the application was unusable in a browser: FastAPI, the WebSocket and the page
were never exercised at all. A user found the regression instead.

So these tests do only what a user does. They start the server as a process,
open the page in headless Chromium, and assert on what the browser sees —
including, first of all, that the console is clean. Nothing here reaches into
Python objects; if it cannot be observed through HTTP, the WebSocket or the
DOM, it is not this layer's business.

The machinery lives in `harness.py`; this file is fixtures only.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request

import pytest

from harness import (ARGAZUI, Server, _free_port, sandbox_tree,   # noqa: F401
                     start_server)

@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Server:
    """A server shared by the read-only checks in one module."""
    tmp = tmp_path_factory.mktemp("e2e")
    running = start_server(tmp)
    yield running
    running.stop()


@pytest.fixture(scope="module")
def stale_server(tmp_path_factory) -> Server:
    """A stand-in for the server that actually bit the user.

    It serves the CURRENT interface files off disk — exactly as the real one
    does — but has no `/api/*` at all, which is what an ArgazUI older than the
    endpoints in question looks like from the browser. Reproducing the
    condition beats exposing a test hook in production code: the hook would
    prove the renderer works, this proves the detection works.
    """
    root = tmp_path_factory.mktemp("stale")
    shutil.copytree(ARGAZUI / "static", root / "static")
    # Served unstamped, because a server old enough to lack the endpoint is
    # also too old to stamp the page.
    shutil.copy2(ARGAZUI / "static" / "index.html", root / "index.html")

    port = _free_port(8900)
    log = root / "stale.log"
    handle = log.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(root), stdout=handle, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    server = Server(port, process, log, root)

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{server.url}/index.html", timeout=2):
                break
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.3)
    else:
        server.stop()
        raise RuntimeError("the stale stand-in server never answered")
    yield server
    server.stop()


@pytest.fixture
def browser_page():
    """A headless Chromium page that records every console error it sees.

    The recording is the point. An "e2e test" that drives the page without
    watching the console would have passed straight through the regression
    this suite exists to catch — the page looked populated, and the only
    evidence was an uncaught TypeError.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.console_errors = errors           # type: ignore[attr-defined]
        yield page
        browser.close()
