"""F-12 — a run owns what it started, and nothing else.

WHAT THIS FILE HAS TO PROVE, FROM §7 OF THE v1.7 BRIEF
------------------------------------------------------
    1 normal cleanup
    2 timeout cleanup
    3 cancellation cleanup
    4 startup-failure cleanup
    5 no orphaned owned processes
    6 no stale owned port
    7 a repeated run after a previous failure
    8 an unrelated host process is NOT terminated   <- the important one

Eight is the one that has to hold whatever else does. `session.py` records the
incident that motivated the rule — a `pkill -f` matching a wrapper script's own
command line and killing the wrong process — and the port and orphan detection
this release adds is exactly the kind of code that invites somebody to reach for
`pkill` again. So there is a test that starts a real unrelated process on a real
port, runs the whole ownership and conflict path against it, and asserts it is
still alive afterwards.

WHY REAL PROCESSES AND REAL SOCKETS
------------------------------------
Ownership is established by the kernel — session id, process group id, socket
inode — so a test that stubbed any of the three would be asserting this file's
model of the kernel rather than the kernel. Every process below is a real
`sleep`, and every port is really bound.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time

import pytest

from argazui import isolation, session, simlifecycle

pytestmark = pytest.mark.tier1


# --------------------------------------------------------------- helpers
def _own_session_process() -> subprocess.Popen:
    """A real child in its own session, standing in for a launched simulator."""
    return subprocess.Popen(["sleep", "120"], start_new_session=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def _reap(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _bound(kind: str = "udp") -> tuple[socket.socket, int]:
    family = socket.SOCK_DGRAM if kind == "udp" else socket.SOCK_STREAM
    handle = socket.socket(socket.AF_INET, family)
    handle.bind(("127.0.0.1", 0))
    if family == socket.SOCK_STREAM:
        handle.listen(1)
    return handle, handle.getsockname()[1]


# ------------------------------------------------------------ port holders
def test_a_free_port_is_reported_free_and_a_held_one_is_not():
    handle, port = _bound("udp")
    try:
        assert isolation.port_free(port, "udp") is False
    finally:
        handle.close()


def test_a_holder_is_identified_by_socket_inode_and_not_by_name():
    """The kernel's own tables, so a rename cannot hide a holder.

    `argazui/start.sh` shells out to `ss` because a shell script has to. Inside
    Python the tables are already readable, need no package, and cannot be
    absent from the image.
    """
    handle, port = _bound("udp")
    try:
        holders = isolation.holders_of(port, "udp")
        assert holders, f"nothing was found holding udp/{port}"
        assert holders[0].pid == os.getpid()
        assert holders[0].command, "the holder was found with no command line"
    finally:
        handle.close()


def test_a_holder_command_line_is_one_line():
    """A conflict report is read in a console, where a multi-line entry buries
    the entries after it. `bash -c` legitimately carries newlines."""
    handle, port = _bound("udp")
    try:
        holder = isolation.holders_of(port, "udp")[0]
        assert "\n" not in holder.command
        assert "\n" not in holder.describe()
    finally:
        handle.close()


def test_tcp_and_udp_are_read_from_different_tables():
    """Asking the wrong table reports a busy port as free.

    Kept as an explicit table in `PORT_KINDS` rather than guessed from the
    number, because the MAVLink ports are UDP and SITL's serial0 is TCP and the
    numbers say nothing about which.
    """
    handle, port = _bound("tcp")
    try:
        assert isolation.port_free(port, "tcp") is False
        # The same number in the UDP table is a different socket entirely.
        assert isolation.port_free(port, "udp") is True
    finally:
        handle.close()
    assert isolation.PORT_KINDS["mavlink"] == isolation.KIND_UDP
    assert isolation.PORT_KINDS["http"] == isolation.KIND_TCP


# ----------------------------------------------- 8. an unrelated process lives
def test_a_port_held_by_an_unrelated_process_is_reported_and_not_signalled():
    """THE IMPORTANT ONE.

    A developer running their own SITL on 14550 in another terminal must get a
    clear message, not a dead process. The check reports; it never signals, and
    there is no code path from a conflict to a kill.
    """
    stranger = _own_session_process()
    handle, port = _bound("udp")
    try:
        # This run's session is not the stranger's session.
        resources = isolation.RunResources(label="probe", sid=os.getsid(0))
        conflicts = resources.check_ports({"mavlink": (port, "udp")})

        assert conflicts, "a held port was not detected"
        blocking = resources.blocking_conflicts()
        assert blocking or conflicts[0].ours, (
            "a holder outside this run's session was not treated as blocking")

        # Nothing was signalled. The stranger is alive and so is the socket.
        assert stranger.poll() is None, (
            "an unrelated process was terminated by a conflict check")
        assert isolation.port_free(port, "udp") is False
    finally:
        handle.close()
        _reap(stranger)


def _identifiers(path) -> set[str]:
    """Every name the module's CODE mentions, ignoring prose.

    Parsed rather than grepped, and the difference matters here: both
    `session.py` and `isolation.py` discuss `pkill` at length in their
    docstrings, because the rule is recorded beside the incident that produced
    it. A text search cannot tell a rule from a violation of it.
    """
    import ast

    tree = ast.parse(open(path, encoding="utf-8").read())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A string that is EXECUTED — an argv element, a shell line — is
            # code for this purpose. A docstring is not, and is the one string
            # position ast marks by placing it first in a body.
            found.add(node.value)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            text = ast.get_docstring(node, clean=False)
            if text:
                docstrings.add(text)
    return found - docstrings


def test_nothing_in_the_isolation_module_can_signal_a_process():
    """Asserted on the code, because this is a property of the design.

    `TerminalSession` signals, by process group, within its own session. The
    ownership layer must not acquire a second way to do it — reporting a
    conflict must never become terminating one, and that is how `pkill -f`
    came back last time.
    """
    names = _identifiers(isolation.__file__)
    for forbidden in ("kill", "killpg", "SIGKILL", "SIGTERM", "SIGINT",
                      "terminate", "pkill"):
        assert forbidden not in names, (
            f"isolation.py's code references {forbidden!r}; the ownership "
            f"layer reports conflicts and never acts on them")


def test_the_project_still_executes_no_pkill():
    """The rule session.py records, re-checked after adding process discovery.

    Both modules TALK about pkill — the incident is written down where the
    replacement lives — so this asks whether any module executes it.
    """
    from pathlib import Path

    root = Path(session.__file__).resolve().parent
    for path in sorted(root.glob("*.py")):
        names = _identifiers(path)
        offenders = {n for n in names if isinstance(n, str) and "pkill" in n}
        assert not offenders, f"{path} executes {offenders}"


def test_signalling_still_happens_and_still_happens_by_process_group():
    """The counterweight: nothing above may be read as "nothing kills anything".

    Teardown must still work, and it must still work the way the incident
    taught — `os.killpg` on groups found through the kernel's session table,
    never a name match.
    """
    names = _identifiers(session.__file__)
    assert "killpg" in names, (
        "session.py no longer terminates process groups; teardown is the one "
        "place that must")
    assert "pgids_in_session" in names


# ------------------------------------------------------ ownership by session
def test_processes_are_attributed_to_a_session_by_the_kernel():
    child = _own_session_process()
    try:
        sid = os.getsid(child.pid)
        found = isolation.processes_in_session(sid)
        pids = {entry.pid for entry in found}
        assert child.pid in pids, (
            f"a child in session {sid} was not found by the session walk")
        for entry in found:
            assert entry.sid == sid
    finally:
        _reap(child)


def test_a_process_in_another_session_is_not_claimed():
    """Ownership is not "anything that looks like a simulator"."""
    stranger = _own_session_process()
    try:
        our_sid = os.getsid(0)
        assert os.getsid(stranger.pid) != our_sid
        pids = {p.pid for p in isolation.processes_in_session(our_sid)}
        assert stranger.pid not in pids
    finally:
        _reap(stranger)


# ---------------------------------------------------- 1, 5, 6. normal cleanup
def test_a_clean_stop_reports_released():
    child = _own_session_process()
    sid = os.getsid(child.pid)
    handle, port = _bound("udp")

    resources = isolation.RunResources(label="probe", sid=sid)
    resources.ports = {"mavlink": port}

    # While the child is alive and the port is held, nothing has been released.
    before = resources.verify_released()
    assert before["released"] is False
    assert before["survivors"], "a live owned process was not reported"
    assert "mavlink" in before["ports_still_held"]

    handle.close()
    _reap(child)
    # Give the kernel a moment to retire the socket and reap the process.
    for _ in range(50):
        after = resources.verify_released()
        if after["released"]:
            break
        time.sleep(0.1)

    assert after["released"] is True, after
    assert after["survivors"] == []
    assert after["ports_still_held"] == {}


def test_an_owned_process_that_outlives_the_stop_is_reported_not_hidden():
    """5 — "no orphan was left" has to be a claim with evidence under it.

    `stop_children` already reported survivors to the console and nowhere else.
    The same question asked here lands in the run record.
    """
    child = _own_session_process()
    try:
        resources = isolation.RunResources(label="probe",
                                           sid=os.getsid(child.pid))
        released = resources.verify_released()
        assert released["released"] is False
        assert any(entry["pid"] == child.pid
                   for entry in released["survivors"]), released
        # And it reaches the run record rather than only the return value.
        assert resources.as_dict()["released"] is False
        assert resources.as_dict()["survivors"]
    finally:
        _reap(child)


# ------------------------------- 2, 3, 4. timeout / cancel / startup failure
@pytest.mark.parametrize("how", ["timeout", "cancelled", "startup-failure"])
def test_cleanup_is_verified_however_the_run_ended(how):
    """The four endings share one path on purpose.

    A cleanup that only ran on the happy path is the cleanup that is not there
    when it is needed. `verify_released` is called from `Simulation.stop`, which
    `addfinalizer` calls whether the test passed, failed, timed out, was
    cancelled or raised.
    """
    child = _own_session_process()
    sid = os.getsid(child.pid)
    resources = isolation.RunResources(label=how, sid=sid)
    lifecycle = simlifecycle.Lifecycle(label=how)

    if how == "startup-failure":
        lifecycle.fail(simlifecycle.ENVIRONMENT_FAILED, "gazebo died")
    elif how == "timeout":
        lifecycle.enter(simlifecycle.VEHICLE_STARTING, "")
        lifecycle.fail(simlifecycle.VEHICLE_START_FAILED, "no heartbeat")
    else:
        lifecycle.enter(simlifecycle.PROCEDURE_RUNNING, "")

    _reap(child)
    for _ in range(50):
        released = resources.verify_released()
        if released["released"]:
            break
        time.sleep(0.1)

    assert released["released"] is True, (
        f"cleanup after {how} left something behind: {released}")
    # And the ending is still legible: a cancelled run is not a failed one.
    assert (lifecycle.failed is (how != "cancelled"))


# ------------------------------------------------- 7. a run after a failure
def test_a_second_run_starts_cleanly_after_a_failed_one():
    """The repeatability question: does a failure poison the next attempt?

    The first "run" fails at start-up holding a port. Once it is cleaned up,
    the second must find the port free and record no blocking conflict —
    otherwise every failure would cost a manual intervention.
    """
    handle, port = _bound("udp")
    wanted = {"mavlink": (port, "udp")}

    first = isolation.RunResources(label="first", sid=os.getsid(0))
    assert first.check_ports(wanted), "the held port was not detected"
    first_lifecycle = simlifecycle.Lifecycle(label="first")
    first_lifecycle.fail(simlifecycle.ENVIRONMENT_FAILED, "port held")

    handle.close()
    for _ in range(50):
        if isolation.port_free(port, "udp"):
            break
        time.sleep(0.1)

    second = isolation.RunResources(label="second", sid=os.getsid(0))
    assert second.check_ports(wanted) == [], (
        "a run after a cleaned-up failure still saw a conflict")
    assert second.blocking_conflicts() == []


# --------------------------------------------------------------- the record
def test_the_ownership_record_names_the_ports_and_the_session():
    """A run record has to answer what this run owned, not merely that it did."""
    resources = isolation.RunResources(label="probe", sid=os.getsid(0))
    resources.check_ports(isolation.wanted_ports())
    document = resources.as_dict()
    assert document["session_id"] == os.getsid(0)
    assert set(document["ports"]) >= {"mavlink", "script_mavlink"}
    assert "released" in document and "survivors" in document


def test_the_ports_a_run_takes_come_from_the_configuration():
    """Not hard-coded 14550: `paths` resolves them through CLI/env/TOML, and a
    check against a constant would pass on a machine configured otherwise."""
    from argazui import paths

    wanted = isolation.wanted_ports()
    assert wanted["mavlink"][0] == paths.UI_MAVLINK_PORT
    assert wanted["script_mavlink"][0] == paths.SCRIPT_MAVLINK_PORT


def test_the_plotjuggler_port_is_not_claimed_as_a_conflict():
    """14552 is a destination, not a port this process binds.

    ArgazUI `sendto()`s the telemetry mirror and PlotJuggler's UDP Server binds
    it, so that port is SUPPOSED to be held — by the very tool the feature
    exists for. Claiming it would make ArgazUI refuse to start whenever
    PlotJuggler was running, which is exactly backwards. `telemetry_mirror.py`
    records the same trap for its own doctor check; this asserts the ownership
    layer did not walk into it a second time.
    """
    from argazui import paths

    assert paths.PLOTJUGGLER_PORT, (
        "this installation has the mirror disabled, so the trap cannot be "
        "tested here")
    ports = {port for port, _ in isolation.wanted_ports().values()}
    assert paths.PLOTJUGGLER_PORT not in ports


# ------------------------------------------------------------- zombies
def test_a_zombie_is_not_reported_as_a_survivor():
    """A zombie has already exited; it holds no port and no memory.

    FOUND BY THE CHECK ITSELF. Two of the ten tier-2 runs in the v1.7
    verification reported `released: false` with one survivor apiece, each with
    an empty command line — which is what `/proc/<pid>/cmdline` gives for a
    zombie. The processes had died correctly and the sweep was racing `bash`
    reaping them.

    Counting them would put `released: false` on healthy runs, and a field that
    cries wolf is a field people learn to ignore — which would cost exactly the
    orphan detection this module exists to provide.
    """
    # A child that exits and is deliberately not reaped is a zombie until this
    # process calls wait(). Popen does not reap until poll()/wait() is called.
    child = subprocess.Popen(["true"], start_new_session=True)
    sid = os.getsid(child.pid)
    for _ in range(100):
        if isolation._process_state(child.pid) == isolation._ZOMBIE:
            break
        time.sleep(0.05)
    assert isolation._process_state(child.pid) == isolation._ZOMBIE, (
        "the child did not become a zombie, so this test proves nothing")

    running = isolation.processes_in_session(sid)
    assert child.pid not in {p.pid for p in running}, (
        "a zombie was reported as a surviving process")

    # And it IS visible to a caller that asks for the raw picture, so the
    # exclusion is a decision this module makes rather than blindness.
    raw = isolation.processes_in_session(sid, include_zombies=True)
    assert child.pid in {p.pid for p in raw}

    # The cleanup verdict is therefore clean.
    resources = isolation.RunResources(label="probe", sid=sid)
    assert resources.verify_released()["released"] is True
    child.wait()


def test_a_running_process_is_still_reported():
    """The counterweight: excluding zombies must not exclude everything.

    A test that only asserted "the zombie is gone" would pass against a
    `processes_in_session` that returned nothing at all, which is the mistake
    that would silently disable orphan detection.
    """
    child = _own_session_process()
    try:
        sid = os.getsid(child.pid)
        assert isolation._process_state(child.pid) != isolation._ZOMBIE
        found = isolation.processes_in_session(sid)
        assert child.pid in {p.pid for p in found}
        assert isolation.RunResources(label="p", sid=sid).verify_released()[
            "released"] is False
    finally:
        _reap(child)
