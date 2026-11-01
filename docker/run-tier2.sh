#!/usr/bin/env bash
# Run the complete ArgazUI stack from the current checkout.
#
# The image supplies the pinned ROS 2 / Gazebo / ArduPilot environment.  The
# source, documentation, preview assets, and run output remain on the host so
# an image never hides the code a developer is reviewing and runs survive a
# container replacement.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${ARGAZ_CONTAINER_RUNTIME:-}" ]]; then
    runtime="$ARGAZ_CONTAINER_RUNTIME"
elif command -v podman >/dev/null 2>&1; then
    runtime=podman
elif command -v docker >/dev/null 2>&1; then
    runtime=docker
else
    echo "ArgazUI: install Podman or Docker, or set ARGAZ_CONTAINER_RUNTIME." >&2
    exit 127
fi

image="${ARGAZ_TIER2_IMAGE:-argazui:tier2}"
name="${ARGAZ_CONTAINER_NAME:-argazui-tier2}"
partition="${ARGAZ_GZ_PARTITION:-argazui-${USER:-local}}"

mkdir -p "$root/runs" "$root/argazui/run" "$root/argazui/static/models"

if "$runtime" container inspect "$name" >/dev/null 2>&1; then
    if [[ "${ARGAZ_REPLACE:-0}" == "1" ]]; then
        "$runtime" rm -f "$name" >/dev/null
    else
        echo "ArgazUI: container '$name' already exists." >&2
        echo "Stop it first, or re-run with ARGAZ_REPLACE=1." >&2
        exit 1
    fi
fi

exec "$runtime" run --rm --name "$name" --network host \
    -v "$root/argazui:/opt/argaz/argazui:ro" \
    -v "$root/argazui/run:/opt/argaz/argazui/run" \
    -v "$root/argaz.toml:/opt/argaz/argaz.toml:ro" \
    -v "$root/runs:/opt/argaz/runs" \
    -v "$root/docs:/opt/argaz/docs:ro" \
    -v "$root/README.md:/opt/argaz/README.md:ro" \
    -v "$root/CHANGELOG.md:/opt/argaz/CHANGELOG.md:ro" \
    -v "$root/TROUBLESHOOTING.md:/opt/argaz/TROUBLESHOOTING.md:ro" \
    -e GZ_IP="${ARGAZ_GZ_IP:-127.0.0.1}" \
    -e GZ_PARTITION="$partition" \
    "$image" serve
