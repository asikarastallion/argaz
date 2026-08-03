#!/bin/bash
# Environment loaded inside the container's simulation terminal.
# Source it, do not execute it:  source env.sh
#
# Deliberately NOT `set -eu`. This file is sourced into the interactive shell
# ArgazUI opens, so `set -e` would belong to that shell afterwards: the next
# command with a non-zero exit — a grep that matches nothing, a Ctrl-C — would
# close the terminal out from under the user. An environment script must not
# change the caller's error handling.

# ARGAZ_ROOT is set by the image; fall back to this file's own directory so the
# script still works if it is copied somewhere else.
if [ -n "${ARGAZ_ROOT:-}" ]; then
    export ARGAZ="$ARGAZ_ROOT"
elif [ -n "${BASH_SOURCE[0]:-}" ]; then
    export ARGAZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    export ARGAZ="$(pwd)"
fi

# ROS 2 is present only in the tier-2 image; tier 1 has SITL and nothing else.
if [ -f /opt/ros/jazzy/setup.bash ]; then
    . /opt/ros/jazzy/setup.bash
fi

# sim_vehicle.py is how every launch method starts a vehicle, so it has to be
# on PATH in the terminal ArgazUI opens — not only in the image's own ENV.
# Without this the SIMULATION terminal reports "sim_vehicle.py: command not
# found" and the model simply never appears, which reads as a broken button.
export PATH="$PATH:$ARGAZ/ardupilot/Tools/autotest"

export GZ_VERSION=harmonic

# This one file stands in for BOTH env.sh and quadplane_env.sh in the image, so
# it has to provide what each of them provides in a checkout. SITL_MODELS in
# particular is not optional: models.json refers to parameter files as
# "$SITL_MODELS/Gazebo/config/<model>.param", and an unset variable expands to
# nothing — `--add-param-file=/Gazebo/config/x.param`, which SITL rejects, so
# the model boots with default parameters and flies like something else
# entirely, or does not boot at all.
export SITL_MODELS="$ARGAZ/SITL_Models"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARGAZ/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
# models/ and worlds/ are separate search roots, not children of one: Gazebo
# resolves `<uri>model://x</uri>` under models/ and `gz sim <world>.sdf` under
# worlds/, and pointing only at Gazebo/ finds neither.
#
# ardupilot_gazebo's own models belong here too. Every SITL_Models world starts
# with `<include><uri>model://runway</uri></include>`, and `runway` ships in
# ardupilot_gazebo, not in SITL_Models. Without it Gazebo loads the world,
# fails with "Unable to find uri[model://runway]" and exits — after which SITL
# sits waiting on a physics backend that will never answer, and the model
# simply never appears. In a checkout the ROS 2 workspace happens to put these
# on the path; nothing does that here.
export GZ_SIM_RESOURCE_PATH="$SITL_MODELS/Gazebo:$SITL_MODELS/Gazebo/models:$SITL_MODELS/Gazebo/worlds:$ARGAZ/ardupilot_gazebo/models:$ARGAZ/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH:-}"
