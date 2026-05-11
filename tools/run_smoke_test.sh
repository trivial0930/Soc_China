#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] current directory: $(pwd)"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/soc_china_pycache"

echo "[smoke] python syntax"
python3 -m py_compile \
  rdk_x5/ros2_ws/src/perception_camera/perception_camera/fixed_camera_node.py \
  rdk_x5/ros2_ws/src/perception_camera/launch/fixed_camera.launch.py

echo "[smoke] shell syntax"
bash -n rdk_x5/scripts/detect_cameras.sh
bash -n rdk_x5/scripts/check_wifi_camera.sh
bash -n rdk_x5/scripts/run_fixed_camera.sh
bash -n tools/setup_rdk.sh

echo "[smoke] ok"
