#!/bin/sh
# Environment loaded inside the container's simulation terminal.
set -eu
if [ -f /opt/ros/jazzy/setup.sh ]; then
    . /opt/ros/jazzy/setup.sh
fi
export GZ_SIM_SYSTEM_PLUGIN_PATH="/opt/argaz/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="/opt/argaz/SITL_Models/Gazebo:${GZ_SIM_RESOURCE_PATH:-}"
