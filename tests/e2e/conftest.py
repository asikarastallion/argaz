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


# Copied per server; `run/` is SITL's working tree and can be gigabytes.
_SANDBOX_IGNORE = shutil.ignore_patterns("run", "__pycache__", "*.py[co]")


def sandbox_tree(tmp_path: Path) -> Path:
    """A throwaway copy of `argazui/` for one server to run from.

    WHY NOT JUST EDIT THE REAL TREE AND PUT IT BACK
    -----------------------------------------------
    Several tests here need genuine drift: an extra entry in models.json, an
    edited .py, a touched procedure. The earlier versions wrote that into the
    checkout and restored it in `finally` — which works right up until the
    process does not reach its `finally`. A SIGKILL, a runner timeout or a
    failing assertion inside the teardown itself all leave a modified working
    tree behind, and on CI that silently becomes part of whatever runs next.

    Copying first removes the failure mode rather than narrowing its window,
    and it also means no test needs a restore step at all.

    The copy is only the application: `ARGAZ_ROOT` still points at the real
    installation, so ArduPilot, env.sh and scripts/ are the genuine ones.
    """
    tree = tmp_path / "argazui"
    if not tree.exists():
        shutil.copytree(ARGAZUI, tree, ignore=_SANDBOX_IGNORE, symlinks=True)
    return tree


class Server:
    """One ArgazUI process, started the way a user starts it."""

    def __init__(self, port: int, process: subprocess.Popen, log: Path,
                 tree: Path) -> None:
        self.port = port
        self.process = process
        self.log = log
        # The application tree this server is actually running: a sandbox copy,
        # so tests edit files here and never in the checkout.
        self.tree = tree
        self.static_root = tree / "static"

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
                 tree: Optional[Path] = None,
                 env_extra: Optional[dict] = None) -> Server:
    """Launches `python -m argazui` from a sandbox tree and waits for it."""
    port = port or _free_port()
    tree = tree or sandbox_tree(tmp_path)
    log = tmp_path / f"server-{port}.log"

    env = os.environ.copy()
    env["ARGAZ_RUNS_ROOT"] = str(tmp_path / "runs")
    # The application is a copy; the installation around it is not. Without
    # this the sandbox's parent would be auto-detected as ARGAZ and the server
    # would look for ArduPilot in an empty temporary directory.
    env["ARGAZ_ROOT"] = str(ROOT)
    if (ROOT / "argaz.toml").is_file():
        env["ARGAZ_CONFIG"] = str(ROOT / "argaz.toml")
    env.update(env_extra or {})

    handle = log.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "argazui", "--port", str(port)],
        cwd=str(tree), stdout=handle, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True, env=env)

    server = Server(port, process, log, tree)
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


def drift(server: Server, relative: str, marker: str) -> Path:
    """Append a harmless line to a file the given server is serving.

    Genuine drift, created inside that server's sandbox tree. Nothing is
    restored afterwards because nothing shared was touched.
    """
    target = server.tree / relative
    target.write_bytes(target.read_bytes() + f"\n{marker}\n".encode())
    return target


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
