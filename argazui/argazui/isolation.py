"""What a run owns, and how it is known to have given it back.

THE PROBLEM, STATED PRECISELY
------------------------------
Teardown has always been correct while the server lives: the pty's bash is its
own kernel session, `/proc` is walked for every process group in that session,
and signals escalate SIGINT → SIGTERM → SIGKILL by PGID. Nothing here changes
that, and `pkill -f` is still never used.

What it cannot survive is the server dying. The session id lived in the process
that died with it, so a crashed or SIGKILLed ArgazUI leaves `gz sim`,
`sim_vehicle.py`, SITL and MAVProxy running, holding 14550 and 5760. The next
START neither detected nor reported it — `MavlinkLink` binds `udpin:14550` and
may receive the PREVIOUS vehicle's telemetry, which is a run whose evidence
came from an aircraft nobody launched.

THE OWNERSHIP RULE
------------------
A run owns exactly what it started. Ownership is established by the kernel —
session id, process group id, and the socket inode a port is held by — and
never by a process name. This is the same rule the shutdown path has followed
since the `pkill -f` incident recorded in session.py, extended to the two
questions that path could not answer:

    who holds this port?          /proc/net/{tcp,udp} → inode → /proc/*/fd
    are these processes mine?     the SID they were started under

A holder that is not ours is REPORTED and never signalled. That restriction is
the whole point: a developer running their own SITL on 14550 in another
terminal must get a clear message, not a dead process.

WHY NOT `ss` AND `lsof`
-----------------------
`argazui/start.sh` shells out to `ss` because a shell script has to, and the
tier-1 image installs it for that. Inside Python the kernel's own tables are
already readable, they need no package, and they cannot be absent. The one
thing this cannot see is a socket held by another user's process, which is
reported as an unidentified holder rather than as nobody.
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = 1

PROC = Path("/proc")

# The three families a simulation run puts on the network, named so a conflict
# report can say what is probably in the way rather than only which number.
KIND_UDP = "udp"
KIND_TCP = "tcp"


# --------------------------------------------------------------- port holders
def _net_table(name: str) -> list[tuple[int, int]]:
    """[(local port, socket inode)] from one of the kernel's own tables."""
    out: list[tuple[int, int]] = []
    for suffix in ("", "6"):
        path = PROC / "net" / (name + suffix)
        try:
            lines = path.read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10:
                continue
            local = fields[1]
            if ":" not in local:
                continue
            try:
                port = int(local.rsplit(":", 1)[1], 16)
                inode = int(fields[9])
            except ValueError:
                continue
            out.append((port, inode))
    return out


def _pid_for_inode(inode: int) -> Optional[int]:
    """Which process holds a socket inode, when this user is allowed to see.

    A `PermissionError` on another user's `/proc/<pid>/fd` is not an error
    here: it means the holder exists and is not ours, which is exactly the
    answer a conflict report needs.
    """
    marker = f"socket:[{inode}]"
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        fds = entry / "fd"
        try:
            handles = list(fds.iterdir())
        except (OSError, PermissionError):
            continue
        for handle in handles:
            try:
                if os.readlink(handle) == marker:
                    return int(entry.name)
            except (OSError, PermissionError):
                continue
    return None


@dataclass
class Holder:
    """Something already on a port this run wants."""

    port: int
    kind: str
    pid: Optional[int]
    sid: Optional[int]
    command: str
    ours: bool

    def as_dict(self) -> dict:
        return {"port": self.port, "kind": self.kind, "pid": self.pid,
                "sid": self.sid, "command": self.command, "ours": self.ours}

    def describe(self) -> str:
        who = (f"pid {self.pid} ({self.command})" if self.pid
               else "a process this user cannot see")
        return (f"{self.kind}/{self.port} is held by {who}"
                + (" — started by this run" if self.ours
                   else " — NOT started by this run"))


def _command_of(pid: int) -> str:
    try:
        raw = (PROC / str(pid) / "cmdline").read_bytes()
    except (OSError, PermissionError):
        return "(unreadable)"
    parts = [p for p in raw.decode("utf-8", "replace").split("\0") if p]
    # Collapsed to one line: a command line may legitimately contain newlines
    # (`bash -c` with a script in it does), and a conflict report is read in a
    # console where a multi-line entry buries the entries after it.
    return " ".join(" ".join(parts).split())[:200] or "(no command line)"


def _sid_of(pid: int) -> Optional[int]:
    from .session import _proc_stat

    stat = _proc_stat(pid)
    return stat[1] if stat else None


# A ZOMBIE IS NOT A SURVIVOR
# --------------------------
# `/proc/<pid>/stat` reports `Z` for a process that has exited and whose parent
# has not yet called `wait()`. It holds no memory, no file descriptors and no
# ports — it is a row in the process table and nothing else.
#
# This was found by the check itself. Two of the ten tier-2 runs in the v1.7
# verification reported `released: false` with one survivor apiece, each with an
# empty command line — which is what `/proc/<pid>/cmdline` gives for a zombie.
# The processes had died correctly; the sweep was racing `bash` reaping them.
#
# Counting them would make `released: false` appear on healthy runs, and a field
# that cries wolf is a field people learn to ignore — which would cost exactly
# the orphan detection this module exists to provide.
_ZOMBIE = "Z"


def _process_state(pid: int) -> Optional[str]:
    """The single-letter state from `/proc/<pid>/stat`, or None.

    Parsed after the LAST `)` for the same reason `session._proc_stat` is: the
    `comm` field can contain parentheses and spaces. The fields after it are
    state, ppid, pgrp, session — so the state is the first of them.
    """
    try:
        with open(f"{PROC}/{pid}/stat", "rb") as fh:
            data = fh.read().decode("utf-8", "replace")
    except (OSError, PermissionError):
        return None
    close = data.rfind(")")
    if close == -1:
        return None
    fields = data[close + 2:].split()
    return fields[0] if fields else None


def holders_of(port: int, kind: str = KIND_UDP,
               owned_sid: Optional[int] = None) -> list[Holder]:
    """Everything currently holding `port`, and whether this run started it."""
    found: list[Holder] = []
    for held_port, inode in _net_table(kind):
        if held_port != port:
            continue
        pid = _pid_for_inode(inode)
        sid = _sid_of(pid) if pid else None
        found.append(Holder(port=port, kind=kind, pid=pid, sid=sid,
                            command=_command_of(pid) if pid else "",
                            ours=bool(owned_sid and sid == owned_sid)))
    return found


def port_free(port: int, kind: str = KIND_UDP) -> bool:
    """Can this process bind the port right now?

    Binding is the honest test, because binding is what the server is about to
    do. The kernel table alone would report a socket in TIME_WAIT that a bind
    with SO_REUSEADDR would happily take.
    """
    family = socket.SOCK_DGRAM if kind == KIND_UDP else socket.SOCK_STREAM
    with socket.socket(socket.AF_INET, family) as probe:
        if family == socket.SOCK_STREAM:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


# ---------------------------------------------------------------- processes
@dataclass
class OwnedProcess:
    pid: int
    pgid: int
    sid: int
    command: str

    def as_dict(self) -> dict:
        return {"pid": self.pid, "pgid": self.pgid, "sid": self.sid,
                "command": self.command}


def processes_in_session(sid: int, exclude_pid: Optional[int] = None,
                         include_zombies: bool = False
                         ) -> list[OwnedProcess]:
    """Every process the kernel says is in this session and is still running.

    `session.pgids_in_session` answers the question teardown asks — which
    groups to signal. This answers the question a run record asks: what was
    running, by pid and command line, so "no orphan was left" is a statement
    with evidence under it rather than an absence of complaint.

    Zombies are excluded, because a zombie has already exited — see `_ZOMBIE`.
    `include_zombies=True` is for a caller that wants the raw picture; nothing
    in the cleanup check does.
    """
    from .session import _proc_stat

    out: list[OwnedProcess] = []
    try:
        entries = os.listdir(PROC)
    except OSError:
        return out
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if exclude_pid is not None and pid == exclude_pid:
            continue
        stat = _proc_stat(pid)
        if stat is None:
            continue
        pgid, psid = stat
        if psid != sid:
            continue
        if not include_zombies and _process_state(pid) == _ZOMBIE:
            continue
        out.append(OwnedProcess(pid=pid, pgid=pgid, sid=psid,
                                command=_command_of(pid)))
    return sorted(out, key=lambda p: p.pid)


# ------------------------------------------------------------------ the lease
@dataclass
class RunResources:
    """The boundary of one run: what it started, and what it took.

    Held by `Manager` for the browser path and by the tier-2 harness for the
    test path, so both answer "was anything left behind" the same way. It owns
    no processes itself — `TerminalSession` does — and it signals nothing.
    Its job is to know what ownership means so cleanup can be CHECKED rather
    than assumed.
    """

    label: str = ""
    ports: dict[str, int] = field(default_factory=dict)
    sid: Optional[int] = None
    shell_pid: Optional[int] = None
    conflicts: list[Holder] = field(default_factory=list)
    survivors: list[OwnedProcess] = field(default_factory=list)
    released: Optional[bool] = None

    # -- before launch ----------------------------------------------------
    def check_ports(self, wanted: dict[str, tuple[int, str]]) -> list[Holder]:
        """Who is already on the ports this run needs, before anything starts.

        `wanted` is {name: (port, kind)}. Conflicts are recorded and returned;
        NOTHING is signalled. A holder that this run did not start is somebody
        else's, and terminating it would be the `pkill -f` incident with better
        manners.
        """
        self.ports = {name: port for name, (port, _) in wanted.items()}
        found: list[Holder] = []
        for name, (port, kind) in sorted(wanted.items()):
            if port_free(port, kind):
                continue
            held = holders_of(port, kind, owned_sid=self.sid)
            found.extend(held or [Holder(port=port, kind=kind, pid=None,
                                         sid=None, command="", ours=False)])
        self.conflicts = found
        return found

    def blocking_conflicts(self) -> list[Holder]:
        """Conflicts that are not this run's own doing.

        A port held by our own previous session is cleared by the ordinary stop
        path before the next START; a port held by anything else is a reason to
        refuse to launch, because a link that silently attaches to a stranger's
        vehicle produces evidence about an aircraft nobody in this run started.
        """
        return [h for h in self.conflicts if not h.ours]

    # -- after teardown ---------------------------------------------------
    def verify_released(self) -> dict:
        """Did everything this run owned actually go?

        Called after the stop path has run. Two independent questions, because
        they fail independently: are the processes gone, and are the ports
        free. A process that ignored SIGKILL and a socket in TIME_WAIT look
        identical to a caller that only asked one of them.
        """
        self.survivors = ([] if self.sid is None
                          else processes_in_session(self.sid,
                                                    exclude_pid=self.shell_pid))
        still_held = {name: port for name, port in self.ports.items()
                      if not port_free(port, _kind_for(name))}
        self.released = not self.survivors and not still_held
        return {
            "released": self.released,
            "survivors": [p.as_dict() for p in self.survivors],
            "ports_still_held": still_held,
        }

    def as_dict(self) -> dict:
        return {
            "schema": SCHEMA,
            "label": self.label,
            "session_id": self.sid,
            "ports": dict(self.ports),
            "conflicts_at_start": [h.as_dict() for h in self.conflicts],
            "released": self.released,
            "survivors": [p.as_dict() for p in self.survivors],
        }


# The MAVLink ports are UDP; SITL's serial0 is TCP. Kept as a table rather than
# a guess from the number, because the two tables are different kernel files
# and asking the wrong one reports a busy port as free.
PORT_KINDS = {"mavlink": KIND_UDP, "script_mavlink": KIND_UDP,
              "plotjuggler": KIND_UDP, "http": KIND_TCP, "sitl": KIND_TCP}


def _kind_for(name: str) -> str:
    return PORT_KINDS.get(name, KIND_UDP)


def wanted_ports(include_http: bool = False) -> dict[str, tuple[int, str]]:
    """The ports a simulation run BINDS, read from the configuration.

    Not a constant: `paths` resolves them through the CLI/environment/TOML
    chain, and a check against hard-coded 14550 would pass on a machine
    configured to use something else.

    WHY THE PLOTJUGGLER PORT IS NOT HERE
    -------------------------------------
    14552 is a DESTINATION, not a port this process binds. ArgazUI `sendto()`s
    the live telemetry mirror and PlotJuggler's UDP Server binds it — the
    producer sends, the consumer binds, which is the same discipline 14550 and
    14551 follow from the other end.

    So it is *supposed* to be held, by the very tool the feature exists for.
    Listing it would make ArgazUI refuse to start whenever PlotJuggler was
    running, which is exactly backwards. `telemetry_mirror.py` records this trap
    at its own doctor check, in the same words, and this is the second place
    that would have fallen into it.
    """
    from . import paths

    wanted: dict[str, tuple[int, str]] = {
        "mavlink": (paths.UI_MAVLINK_PORT, KIND_UDP),
        "script_mavlink": (paths.SCRIPT_MAVLINK_PORT, KIND_UDP),
    }
    if include_http:
        wanted["http"] = (paths.HTTP_PORT, KIND_TCP)
    return wanted


def describe(conflicts: Iterable[Holder]) -> str:
    """One line per conflict, for a console a person is watching."""
    return "\n".join(holder.describe() for holder in conflicts)
