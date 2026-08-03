#!/bin/bash
# Start ArgazUI, then open the URL it prints in a browser.
#
# NOTE: this script does NOT source env.sh, and must not. env.sh is sourced
# *inside* the terminal sessions ArgazUI opens (exactly as you would by hand);
# the server itself runs in a clean environment.
#
# PICKING PYTHON: venv-ardupilot is activated only from ~/.profile, i.e. only in
# login shells. A terminal opened by VS Code is not a login shell, so there
# `python3` resolves to /usr/bin/python3 and uvicorn is missing. That is why we
# locate a suitable interpreter here instead of trusting PATH.
#
# EVERY COMMAND THIS SCRIPT PRINTS MUST RUN VERBATIM. No `<pid>`, no `<path>`,
# nothing that turns into a bash syntax error when pasted. A user pasted an
# earlier version's suggestion and got `syntax error near unexpected token
# 'newline'`; instructions that do not survive a paste are not instructions.
set -u
cd "$(dirname "$0")" || exit 1

HERE="$(pwd)"
ARGAZ_DIR="$(cd .. && pwd)"
REQUIRED="uvicorn fastapi pymavlink yaml"

# --replace is ours, not the Python CLI's; strip it before passing the rest on.
REPLACE=0
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--replace" ]; then REPLACE=1; else ARGS+=("$arg"); fi
done
set -- ${ARGS+"${ARGS[@]}"}

# `doctor` is its own command and needs no port handling.
DOCTOR_ONLY=0
[ "${1:-}" = "doctor" ] && DOCTOR_ONLY=1
[ "${1:-}" = "serve" ] && shift

# ----------------------------------------------------------------- which port
# Resolved WITHOUT Python, because the interpreter search below wants to know
# who holds the port and Python may not be usable yet.
PORT=8770
if [ -f "$ARGAZ_DIR/argaz.toml" ]; then
    toml_port="$(sed -n 's/^[[:space:]]*port[[:space:]]*=[[:space:]]*\([0-9]\+\).*/\1/p' \
                 "$ARGAZ_DIR/argaz.toml" | head -1)"
    [ -n "$toml_port" ] && PORT="$toml_port"
fi
[ -n "${ARGAZ_PORT:-}" ] && PORT="$ARGAZ_PORT"
prev=""
for arg in ${ARGS+"${ARGS[@]}"}; do
    [ "$prev" = "--port" ] && PORT="$arg"
    prev="$arg"
done

# Kernel-reported holder of the port. Never a name match — see USAGE.md §10.
holder_pid() {
    ss -ltnpH "sport = :$PORT" 2>/dev/null \
        | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1
}
HOLDER_PID="$(holder_pid)"
HOLDER_PY=""
if [ -n "$HOLDER_PID" ] && [ -r "/proc/$HOLDER_PID/cmdline" ]; then
    # The interpreter that process is running under. This is the single most
    # reliable hint available: a working ArgazUI is proof that interpreter has
    # every package. An earlier version printed this path in its own error
    # message and then failed to use it.
    HOLDER_PY="$(tr '\0' '\n' < "/proc/$HOLDER_PID/cmdline" | head -1)"
    case "$HOLDER_PY" in *python*) ;; *) HOLDER_PY="" ;; esac
fi

# ----------------------------------------------------------- interpreter hunt
has_packages() {
    "$1" - <<'PY' >/dev/null 2>&1
import importlib
for m in ("uvicorn", "fastapi", "pymavlink", "yaml"):
    importlib.import_module(m)
PY
}

# PEP 668: a distribution-managed interpreter must not be installed into.
# Detected BEFORE any install is attempted, and --break-system-packages is
# deliberately never used — breaking the user's system Python is not ours to do.
externally_managed() {
    "$1" - <<'PY' >/dev/null 2>&1
import os, sys, sysconfig
sys.exit(0 if os.path.exists(
    os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")) else 1)
PY
}

# Candidates in descending order of confidence. Note the guards: an unset
# VIRTUAL_ENV must NOT expand to "/bin/python3", which is what the previous
# version did — it then tried to pip-install into the system interpreter.
CANDIDATES=()
[ -n "${ARGAZUI_PYTHON:-}" ] && CANDIDATES+=("$ARGAZUI_PYTHON")
[ -n "${VIRTUAL_ENV:-}" ] && CANDIDATES+=("$VIRTUAL_ENV/bin/python3")
[ -n "$HOLDER_PY" ] && CANDIDATES+=("$HOLDER_PY")
for venv in "$ARGAZ_DIR"/venv* "$ARGAZ_DIR"/.venv* "$HOME"/venv* "$HOME"/.venv*; do
    [ -x "$venv/bin/python3" ] && CANDIDATES+=("$venv/bin/python3")
done
path_python="$(command -v python3 2>/dev/null)"
[ -n "$path_python" ] && CANDIDATES+=("$path_python")
[ -x /usr/bin/python3 ] && CANDIDATES+=("/usr/bin/python3")

# Scan every candidate first. Only if none works is installing even considered.
PY=""
REJECTED=()
seen=""
for candidate in ${CANDIDATES+"${CANDIDATES[@]}"}; do
    case "$seen" in *"|$candidate|"*) continue ;; esac
    seen="$seen|$candidate|"
    if [ ! -x "$candidate" ]; then
        REJECTED+=("$candidate — not executable")
        continue
    fi
    if has_packages "$candidate"; then PY="$candidate"; break; fi
    if externally_managed "$candidate"; then
        REJECTED+=("$candidate — missing packages, and it is a distribution-managed interpreter (PEP 668); ArgazUI will not install into it")
    else
        REJECTED+=("$candidate — missing one of: $REQUIRED")
    fi
done

if [ -z "$PY" ]; then
    # Only now, and only into a virtual environment we create ourselves.
    VENV="$ARGAZ_DIR/venv-argazui"
    if [ -x "$VENV/bin/python3" ] && has_packages "$VENV/bin/python3"; then
        PY="$VENV/bin/python3"
    else
        echo "ArgazUI: no Python interpreter on this machine has all of: $REQUIRED" >&2
        echo "" >&2
        echo "  Candidates tried, and why each was rejected:" >&2
        for r in ${REJECTED+"${REJECTED[@]}"}; do echo "    - $r" >&2; done
        echo "" >&2
        echo "  Create a virtual environment for ArgazUI and install them (copy this" >&2
        echo "  whole line; it is complete and needs no editing):" >&2
        echo "" >&2
        echo "    python3 -m venv $VENV && $VENV/bin/python3 -m pip install -q -r $HERE/requirements.txt && $HERE/start.sh" >&2
        echo "" >&2
        echo "  Or point ArgazUI at an interpreter you already have, for example:" >&2
        echo "" >&2
        echo "    ARGAZUI_PYTHON=$VENV/bin/python3 $HERE/start.sh" >&2
        echo "" >&2
        exit 1
    fi
fi

echo "ArgazUI: using interpreter $PY" >&2

if [ "$DOCTOR_ONLY" = "1" ]; then
    exec "$PY" -m argazui "$@"
fi

# ---------------------------------------------------------------- port in use
# A user lost a debugging session to this: an ArgazUI left running from the
# previous day still held the port, start.sh refused to launch a replacement,
# and the browser kept loading today's interface files from disk while talking
# to that old server's API. Refusing was right; refusing without saying who
# holds the port, since when, and what to do about it was not.
if [ -n "$HOLDER_PID" ]; then
    STARTED="$(ps -o lstart= -p "$HOLDER_PID" 2>/dev/null | sed 's/^ *//')"
    IDENT="$(curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/version" 2>/dev/null || true)"
    CMDLINE=""
    if [ -r "/proc/$HOLDER_PID/cmdline" ]; then
        CMDLINE="$(tr '\0' ' ' < "/proc/$HOLDER_PID/cmdline")"
    fi
    # Second, weaker identification for servers older than /api/version — which
    # is exactly the case that motivated all of this. This reads the kernel's
    # record for ONE pid already resolved from the port; it is not a name search
    # across every process, and so is not the `pkill -f` mistake. That command
    # matches patterns against every command line on the machine, including the
    # shell running it.
    LOOKS_LIKE_ARGAZUI=0
    case "$CMDLINE" in *"argazui"*) LOOKS_LIKE_ARGAZUI=1 ;; esac

    echo "ArgazUI: 127.0.0.1:$PORT is already in use." >&2
    echo "  pid     : $HOLDER_PID" >&2
    echo "  started : ${STARTED:-unknown}" >&2
    echo "  command : ${CMDLINE:-unreadable}" >&2
    if [ -n "$IDENT" ]; then
        echo "  identity: $IDENT" >&2
        echo "  This IS an ArgazUI server. Your browser would load the current" >&2
        echo "  interface files from disk but talk to that server's API." >&2
    elif [ "$LOOKS_LIKE_ARGAZUI" = "1" ]; then
        echo "  identity: it does not answer /api/version, but its command line is" >&2
        echo "            an ArgazUI. That endpoint arrived in v1.1, so this is an" >&2
        echo "            OLDER ArgazUI — the interface it serves you is newer than" >&2
        echo "            the API it answers with." >&2
    else
        echo "  identity: not recognisable as an ArgazUI server." >&2
    fi

    if [ "$REPLACE" = "1" ]; then
        if [ -z "$IDENT" ] && [ "$LOOKS_LIKE_ARGAZUI" = "0" ]; then
            echo "ArgazUI: refusing --replace: the process on $PORT did not identify" >&2
            echo "         itself as an ArgazUI server, and this script will not kill" >&2
            echo "         a process it cannot recognise. Stop it yourself, or run:" >&2
            echo "" >&2
            echo "    $HERE/start.sh --port $((PORT + 1))" >&2
            echo "" >&2
            exit 1
        fi
        echo "ArgazUI: --replace given; sending SIGTERM to pid $HOLDER_PID..." >&2
        kill -TERM "$HOLDER_PID" 2>/dev/null || true
        # Wait for the PORT to be released, not for the pid to disappear.
        # Two reasons, both found by testing rather than reasoning:
        #   * `kill -0` succeeds on a zombie, so when the old server is a child
        #     of the shell running this script it can look alive long after it
        #     has exited — the loop then never breaks.
        #   * The process exiting is not the same as the socket being freed;
        #     without waiting for that, the doctor preflight a second later
        #     fails with EADDRINUSE and --replace reports a fake failure.
        # The port is what we actually need, so the port is what we wait on.
        # 30 s: a clean shutdown closes two pty sessions with a 3 s grace each
        # and may be stopping a simulation, measured at ~6 s idle.
        freed=0
        for _ in $(seq 1 60); do
            if [ -z "$(ss -ltnH "sport = :$PORT" 2>/dev/null)" ]; then freed=1; break; fi
            sleep 0.5
        done
        if [ "$freed" = "0" ]; then
            echo "" >&2
            echo "ArgazUI: 127.0.0.1:$PORT is STILL HELD 30 s after SIGTERM to pid" >&2
            echo "         $HOLDER_PID." >&2
            echo "  It is not escalated to SIGKILL automatically: an ArgazUI that is" >&2
            echo "  shutting a simulation down needs that time, and killing it there" >&2
            echo "  would leave Gazebo and SITL orphaned and the run half-recorded." >&2
            echo "" >&2
            echo "  Wait a few more seconds and run the same command again:" >&2
            echo "" >&2
            echo "    $HERE/start.sh --replace" >&2
            echo "" >&2
            echo "  If it is genuinely stuck, force it and then start again:" >&2
            echo "" >&2
            echo "    kill -KILL $HOLDER_PID && $HERE/start.sh" >&2
            echo "" >&2
            exit 1
        fi
        echo "ArgazUI: port $PORT released; taking over." >&2
    else
        echo "" >&2
        echo "  Take it over (stops that server with SIGTERM, then starts this one):" >&2
        echo "" >&2
        echo "    $HERE/start.sh --replace" >&2
        echo "" >&2
        echo "  Or leave it running and use another port:" >&2
        echo "" >&2
        echo "    $HERE/start.sh --port $((PORT + 1))" >&2
        echo "" >&2
        exit 1
    fi
fi

# Fail before the web server and terminal sessions start. This checks the
# configured installation; it does not assume env.sh is beside this script.
#
# The tier-1 profile, not the full one, for the same reason `argazui serve`
# uses it: Gazebo and ROS 2 decide which MODELS can fly, not whether ArgazUI
# can run. Checking the full set here refused to start the server on any
# machine without a simulator — including the tier-1 container image, where
# it made `--replace` fail with no explanation a reader could act on. The
# server prints the Gazebo/ROS findings as warnings on its way up, and
# `argazui doctor` remains the complete report.
if ! "$PY" -m argazui doctor --tier tier1 "$@"; then
    echo "ArgazUI: prerequisites are incomplete; fix the items above and retry." >&2
    exit 1
fi

exec "$PY" -m argazui "$@"
