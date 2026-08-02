#!/bin/bash
# Environment for ArduPilot SITL + Gazebo + ROS 2 work in this checkout.
# Source it, do not execute it:  source env.sh
#
# VS Code'un 'code' snap paketinden miras kalan GTK/locale değişkenleri, GUI
# uygulamalarının (rviz2, gz sim -g) snap'in kendi core20 tabanındaki uyumsuz
# libpthread'i yüklemesine ve "undefined symbol: __libc_pthread_init" ile
# çökmesine neden oluyor. Bu yüzden burada temizleniyor.
unset GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GDK_PIXBUF_MODULE_FILE \
      GDK_PIXBUF_MODULEDIR LOCPATH GIO_MODULE_DIR GSETTINGS_SCHEMA_DIR

# ARGAZ is this file's own directory. Hard-coding a home directory here made
# the checkout unusable on any other machine, and this script IS part of the
# installation surface: ArgazUI sources it inside every simulation terminal.
# ARGAZ_ROOT (the same variable ArgazUI's configuration layer reads) still wins,
# so a relocated tree can override it without editing this file.
if [ -n "${ARGAZ_ROOT:-}" ]; then
    export ARGAZ="$ARGAZ_ROOT"
elif [ -n "${BASH_SOURCE[0]:-}" ]; then
    export ARGAZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    # zsh and `sh env.sh` do not set BASH_SOURCE; fall back to the caller's cwd
    # rather than silently pointing at somebody else's home directory.
    export ARGAZ="$(pwd)"
    echo "env.sh: BASH_SOURCE is unset, assuming ARGAZ=$ARGAZ" >&2
fi

source /opt/ros/jazzy/setup.bash
export GZ_VERSION=harmonic
if [ -f "$ARGAZ/ardu_ws/install/setup.bash" ]; then
    source "$ARGAZ/ardu_ws/install/setup.bash"
fi
export PATH="$PATH:$ARGAZ/ardupilot/Tools/autotest"
export PATH="$PATH:$ARGAZ/Micro-XRCE-DDS-Gen/scripts"
if [ -d /usr/lib/ccache ]; then
    export PATH="/usr/lib/ccache:$PATH"
fi
alias argaz-cd='cd $ARGAZ'
alias argaz-build='cd $ARGAZ/ardu_ws && colcon build --packages-up-to ardupilot_gz_bringup'
alias argaz-sitl='cd $ARGAZ/ardupilot/ArduCopter && sim_vehicle.py -w --console --map'
alias argaz-sim='ros2 launch ardupilot_gz_bringup iris_runway.launch.py'
