"""`start.sh` in the shell a user actually has.

Not a browser test, but the same category: the failure it guards against was
found by a person running a command, not by anything that imports Python. The
script chose `/bin/python3` — because `"${VIRTUAL_ENV:-}/bin/python3"` expands
to exactly that when the variable is unset — and then tried to pip-install
into a PEP 668 interpreter.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ARGAZUI, ROOT, _free_port, start_server

pytestmark = [pytest.mark.e2e, pytest.mark.tier1]

START = ARGAZUI / "start.sh"

# The shell a VS Code terminal gives you: no login profile, so no venv.
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp"),
             "TERM": "dumb"}


def run_start(args: list[str], env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run([str(START), *args], capture_output=True, text=True,
                          timeout=timeout, env=env, cwd=str(ROOT))


def test_finds_a_working_interpreter_in_a_clean_shell(tmp_path):
    """No VIRTUAL_ENV, nothing but /usr/bin on PATH — and it must still work.

    The port is deliberately occupied by a server this test starts, because
    that is also the case where the script has the strongest hint available:
    the interpreter the running ArgazUI is using. It printed that path in its
    own error message and then ignored it.
    """
    running = start_server(tmp_path)
    try:
        result = run_start(["--port", str(running.port)], CLEAN_ENV)
        assert "using interpreter" in result.stderr, (
            "start.sh does not say which interpreter it chose:\n" + result.stderr)

        chosen = [line for line in result.stderr.splitlines()
                  if "using interpreter" in line][0].split("using interpreter", 1)[1].strip()
        assert chosen not in ("/bin/python3", "/usr/bin/python3"), (
            f"start.sh fell back to the system interpreter: {chosen}")

        # Whatever it chose must genuinely be able to run ArgazUI.
        check = subprocess.run(
            [chosen, "-c", "import fastapi, uvicorn, pymavlink, yaml"],
            capture_output=True, text=True)
        assert check.returncode == 0, (
            f"start.sh chose {chosen}, which cannot import the requirements:\n"
            + check.stderr)
    finally:
        running.stop()


@pytest.mark.container_only
def test_never_tries_to_install_into_a_managed_interpreter(tmp_path):
    """PEP 668 must be detected before an install is attempted, not after.

    The user's console showed `error: externally-managed-environment` — the
    script had already tried. With no usable interpreter anywhere, the output
    must explain and offer a runnable fix instead.

    WHERE THIS ACTUALLY RUNS
    ------------------------
    It needs a machine whose bare `PATH` interpreter cannot import the
    requirements — otherwise `start.sh` rightly succeeds and there is no
    rejection to inspect. A developer machine set up to run ArgazUI usually
    fails that condition, so this is verified in the tier-1 image, where the
    system Python is PEP 668-managed and the requirements live in a venv.

    Marked `container_only`: when it skips, the run summary and
    `docs/status.md` say so. A skip here is never counted as a pass.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {"PATH": "/usr/bin:/bin", "HOME": str(fake_home), "TERM": "dumb"}

    # A venv the script might otherwise find must not exist for this scenario.
    if (ROOT / "venv-argazui").exists():
        pytest.skip("a venv-argazui already exists in the checkout; the "
                    "no-interpreter path cannot be exercised here")

    result = run_start(["--port", str(_free_port(8960))], env)
    if "using interpreter" in result.stderr:
        pytest.skip("this machine has a usable interpreter on the bare PATH; "
                    "the no-interpreter path cannot be exercised here")

    assert "externally-managed" not in (result.stdout + result.stderr).lower(), (
        "pip was invoked against a managed interpreter:\n" + result.stderr)
    assert "break-system-packages" not in (result.stdout + result.stderr), (
        "start.sh used --break-system-packages")
    assert "distribution-managed" in result.stderr, (
        "the rejection reason was not explained:\n" + result.stderr)


def test_every_command_start_sh_prints_parses_in_bash(tmp_path):
    """Its own suggestions must survive a paste, like everything else.

    Lines are picked out by shape — indented, containing no angle brackets —
    and fed to `bash -n`. This is the check the banner's `<pid>` failed.
    """
    running = start_server(tmp_path)
    try:
        result = run_start(["--port", str(running.port)], CLEAN_ENV)
        text = result.stderr
        assert "already in use" in text, text

        suggestions = [line.strip() for line in text.splitlines()
                       if line.startswith("    ") and line.strip()
                       and not line.strip().startswith(("pid", "started", "command",
                                                        "identity", "-", "This", "It",
                                                        "an ", "OLDER", "the "))]
        assert suggestions, "start.sh offered no commands at all:\n" + text
        for command in suggestions:
            assert "<" not in command and ">" not in command, (
                f"start.sh printed a placeholder: {command!r}")
            check = subprocess.run(["bash", "-n"], input=command, text=True,
                                   capture_output=True)
            assert check.returncode == 0, (
                f"start.sh printed unparseable bash: {command!r}\n{check.stderr}")
    finally:
        running.stop()


def test_replace_actually_takes_over_the_port(tmp_path):
    """--replace stops an identified ArgazUI and a NEW server ends up serving.

    Asserted by identity, not by log text: the port must end up held by a
    different pid that answers /api/version. Two bugs hid behind weaker
    versions of this check — the process exiting is not the same as the socket
    being freed (the doctor preflight then failed with EADDRINUSE), and
    `kill -0` succeeds on a zombie, so a server that was a child of the
    calling shell looked alive forever.
    """
    old = start_server(tmp_path)
    port = old.port
    old_pid = old.process.pid
    log = tmp_path / "replace.log"

    handle = log.open("wb")
    taking_over = subprocess.Popen(
        [str(START), "--port", str(port), "--replace"],
        cwd=str(ROOT), env=CLEAN_ENV, stdout=handle, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.time() + 180
        new_pid = None
        while time.time() < deadline:
            holder = subprocess.run(
                ["bash", "-c",
                 f"ss -ltnpH 'sport = :{port}' | sed -n 's/.*pid=\\([0-9]*\\).*/\\1/p' | head -1"],
                capture_output=True, text=True).stdout.strip()
            if holder and holder != str(old_pid):
                new_pid = holder
                break
            time.sleep(1)

        text = log.read_text(errors="replace")
        assert "sending SIGTERM" in text, text
        assert "released; taking over" in text, (
            "--replace never reached the takeover step:\n" + text)
        assert "STILL HELD" not in text, ("the port was not released in time:\n" + text)
        assert new_pid, (
            f"nothing new is serving {port} after --replace:\n{text}")

        # And the replacement is a working ArgazUI, not just something bound.
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version",
                                    timeout=10) as response:
            assert json.loads(response.read().decode())["version"]
    finally:
        for pid in filter(None, [taking_over.pid]):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        old.stop()
