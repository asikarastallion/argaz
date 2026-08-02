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
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ARGAZUI = ROOT / "argazui"

pytest.importorskip("playwright.sync_api",
                    reason="playwright is not installed; e2e cannot run")


def _free_port(start: int = 8820) -> int:
    for port in range(start, start + 60):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free HTTP port for the e2e server")


class Server:
    """One ArgazUI process, started the way a user starts it."""

    def __init__(self, port: int, process: subprocess.Popen, log: Path,
                 static_root: Path) -> None:
        self.port = port
        self.process = process
        self.log = log
        self.static_root = static_root

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def api(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.url}{path}", timeout=10) as response:
            return json.loads(response.read().decode())

    def post(self, path: str, payload: Optional[dict] = None) -> dict:
        data = json.dumps(payload or {}).encode()
        request = urllib.request.Request(
            f"{self.url}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode())

    def tail(self, lines: int = 30) -> str:
        try:
            return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no server output)"

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        # Same rule as everywhere else in this project: by process group, never
        # by name. The server owns two pty sessions and possibly a simulator.
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            self.process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def start_server(tmp_path: Path, port: Optional[int] = None,
                 static_root: Optional[Path] = None,
                 env_extra: Optional[dict] = None) -> Server:
    """Launches `python -m argazui` and waits until it answers."""
    port = port or _free_port()
    log = tmp_path / f"server-{port}.log"
    env = os.environ.copy()
    env["ARGAZ_RUNS_ROOT"] = str(tmp_path / "runs")
    env.update(env_extra or {})

    handle = log.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "argazui", "--port", str(port)],
        cwd=str(ARGAZUI), stdout=handle, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True, env=env)

    server = Server(port, process, log, static_root or (ARGAZUI / "static"))
    deadline = time.time() + 60
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the server exited immediately:\n{server.tail()}")
        try:
            with urllib.request.urlopen(f"{server.url}/api/status", timeout=2):
                return server
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.5)
    server.stop()
    raise RuntimeError(f"the server never answered on {server.url}:\n{server.tail()}")


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
    server = Server(port, process, log, root / "static")

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
def edited_static_file():
    """Appends a harmless line to a served file, then restores it byte for byte.

    Used to create genuine drift against a running server rather than faking
    the condition.
    """
    target = ARGAZUI / "static" / "style.css"
    original = target.read_bytes()

    def _edit(marker: str = "/* e2e drift probe */") -> None:
        target.write_bytes(original + f"\n{marker}\n".encode())

    yield _edit
    target.write_bytes(original)


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


def open_page(page, server: Server, wait_ms: int = 2500):
    page.goto(server.url, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)
    return page


def assert_no_console_errors(page, context: str = "") -> None:
    errors = getattr(page, "console_errors", [])
    assert not errors, (
        f"the browser console reported {len(errors)} error(s){' ' + context if context else ''}:\n"
        + "\n".join(f"  - {e}" for e in errors))
