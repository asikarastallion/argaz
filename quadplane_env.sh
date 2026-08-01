#!/bin/bash
# QuadPlane (Alti Transition) uçuşları için ortam.
# env.sh'ı DEĞİŞTİRMİYOR, üzerine ekleme yapıyor. Copter uçuşları için hâlâ
# sadece `source env.sh` kullan; QuadPlane için bunu kullan.

source /home/asikarastallion/Documents/argaz/env.sh

export SITL_MODELS=/home/asikarastallion/Documents/argaz/SITL_Models
export GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH:$SITL_MODELS/Gazebo/models:$SITL_MODELS/Gazebo/worlds"

alias argaz-quadplane-gz='gz sim -v4 -r alti_transition_runway.sdf'
alias argaz-quadplane-sitl='cd /home/asikarastallion/Documents/argaz/ardupilot/ArduPlane && sim_vehicle.py -v ArduPlane --model JSON --add-param-file=$SITL_MODELS/Gazebo/config/alti_transition_quad.param --console --map'
