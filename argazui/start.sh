#!/bin/bash
# Start ArgazUI, then open http://127.0.0.1:8770 in a browser.
#
# NOTE: this script does NOT source env.sh, and must not. env.sh is sourced
# *inside* the terminal sessions ArgazUI opens (exactly as you would by hand);
# the server itself runs in a clean environment.
#
# PICKING PYTHON: venv-ardupilot is activated only from ~/.profile, i.e. only in
# login shells. A terminal opened by VS Code is not a login shell, so there
# `python3` resolves to /usr/bin/python3 and uvicorn is missing. That is why we
# locate a suitable interpreter here instead of trusting PATH.
set -u
cd "$(dirname "$0")" || exit 1

REQUIRED="uvicorn fastapi pymavlink yaml"

# Does this interpreter have every package we need?
has_packages() {
    "$1" - <<'PY' >/dev/null 2>&1
import importlib
for m in ("uvicorn", "fastapi", "pymavlink", "yaml"):
    importlib.import_module(m)
PY
}

CANDIDATES=(
    "${ARGAZUI_PYTHON:-}"                       # explicit override
    "${VIRTUAL_ENV:-}/bin/python3"              # currently active venv
    "$HOME/venv-ardupilot/bin/python3"          # the argaz setup's venv
    "$(command -v python3 2>/dev/null)"         # whatever is on PATH
    /usr/bin/python3
)

PY=""
for candidate in "${CANDIDATES[@]}"; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if has_packages "$candidate"; then PY="$candidate"; break; fi
done

# Nothing ready? Install the missing packages into the first usable venv.
if [ -z "$PY" ]; then
    for candidate in "${VIRTUAL_ENV:-}/bin/python3" "$HOME/venv-ardupilot/bin/python3"; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        echo "ArgazUI: installing missing Python packages ($REQUIRED) -> $candidate"
        if "$candidate" -m pip install --quiet fastapi uvicorn wsproto pyyaml \
           && has_packages "$candidate"; then
            PY="$candidate"; break
        fi
    done
fi

if [ -z "$PY" ]; then
    cat >&2 <<EOF
ERROR: none of the candidate Python interpreters has the packages ArgazUI needs.
Required: $REQUIRED

Install them with:
    ~/venv-ardupilot/bin/pip install fastapi uvicorn wsproto pyyaml

Or point ArgazUI at the interpreter you want:
    ARGAZUI_PYTHON=/path/to/python3 ./start.sh
EOF
    exit 1
fi

exec "$PY" -m argazui "$@"
