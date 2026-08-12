"""Starting a real ArgazUI and driving it: the machinery, not the fixtures.

Separate from `conftest.py` for a concrete reason. Two `conftest.py` files are
reachable as top-level modules here — `tests/` and `tests/e2e/` — and which one
`import conftest` resolves to depends on collection order. On a developer
machine the tier-1 modules won; inside the tier-1 image the e2e one did, and
the whole suite failed to collect with

    ImportError: cannot import name 'boot' from 'conftest'

Helpers belong in named modules. conftest.py keeps fixtures and hooks, which
pytest loads by path rather than by import, so no name can collide.
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
                 tree: Path, runs_root: Optional[Path] = None) -> None:
        self.port = port
        self.process = process
        self.log = log
        # The application tree this server is actually running: a sandbox copy,
        # so tests edit files here and never in the checkout.
        self.tree = tree
        self.static_root = tree / "static"
        # Where this server writes its runs. Exposed so a test can seed one:
        # several panels only have anything to show once a run exists, and
        # flying one to test a table would be an hour for a rendering check.
        self.runs_root = runs_root or (tmp_path_of(log) / "runs")

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


def tmp_path_of(log: Path) -> Path:
    """The sandbox a server's log sits in — its runs root is beside it."""
    return log.parent


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

    server = Server(port, process, log, tree,
                    runs_root=Path(env["ARGAZ_RUNS_ROOT"]))
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


def drift(server: Server, relative: str, marker: str) -> Path:
    """Append a harmless line to a file the given server is serving.

    Genuine drift, created inside that server's sandbox tree. Nothing is
    restored afterwards because nothing shared was touched.
    """
    target = server.tree / relative
    target.write_bytes(target.read_bytes() + f"\n{marker}\n".encode())
    return target


def open_page(page, server: Server, wait_ms: int = 2500):
    page.goto(server.url, wait_until="networkidle")
    page.wait_for_timeout(wait_ms)
    return page


def open_section(page, name: str, wait_ms: int = 400):
    """Bring one module page on screen, the way a person does.

    The interface is an application shell: the landing screen is the operator's
    workstation — vehicles, quick commands, terminals — and everything else is
    a section reached from the navigation rail (see `static/ui.js`). A test that
    asserts on a module's panel has to be looking at that module, which is what
    this does. Only one section is ever not `[hidden]`, so waiting on the view
    is enough; there is no animation to race.
    """
    page.locator(f'.rail-item[data-nav="{name}"]').first.click()
    page.wait_for_selector(f'[data-view="{name}"]:not([hidden])', timeout=10000)
    page.wait_for_timeout(wait_ms)
    return page


def assert_no_console_errors(page, context: str = "") -> None:
    errors = getattr(page, "console_errors", [])
    assert not errors, (
        f"the browser console reported {len(errors)} error(s){' ' + context if context else ''}:\n"
        + "\n".join(f"  - {e}" for e in errors))
