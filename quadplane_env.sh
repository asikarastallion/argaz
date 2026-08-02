#!/bin/bash
# QuadPlane (Alti Transition) ve diğer SITL_Models uçuşları için ortam.
# env.sh'ı DEĞİŞTİRMİYOR, üzerine ekleme yapıyor. Copter uçuşları için hâlâ
# sadece `source env.sh` kullan; SITL_Models modelleri için bunu kullan.
#
# Source it, do not execute it:  source quadplane_env.sh

# Same rule as env.sh: the root is this file's own directory, never a home
# directory baked in at authoring time. ARGAZ_ROOT overrides it.
if [ -n "${ARGAZ_ROOT:-}" ]; then
    _argaz_root="$ARGAZ_ROOT"
elif [ -n "${BASH_SOURCE[0]:-}" ]; then
    _argaz_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    _argaz_root="$(pwd)"
    echo "quadplane_env.sh: BASH_SOURCE is unset, assuming ARGAZ=$_argaz_root" >&2
fi

source "$_argaz_root/env.sh"
unset _argaz_root

export SITL_MODELS="$ARGAZ/SITL_Models"
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$SITL_MODELS/Gazebo/models:$SITL_MODELS/Gazebo/worlds"

alias argaz-quadplane-gz='gz sim -v4 -r alti_transition_runway.sdf'
alias argaz-quadplane-sitl='cd $ARGAZ/ardupilot/ArduPlane && sim_vehicle.py -v ArduPlane --model JSON --add-param-file=$SITL_MODELS/Gazebo/config/alti_transition_quad.param --console --map'
