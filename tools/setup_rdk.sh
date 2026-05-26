#!/usr/bin/env bash
set -euo pipefail

if [[ -f /opt/tros/humble/setup.bash ]]; then
  set +u
  source /opt/tros/humble/setup.bash
  set -u
elif [[ -f /opt/tros/setup.bash ]]; then
  set +u
  source /opt/tros/setup.bash
  set -u
else
  echo "[setup] Cannot find tros.b setup.bash under /opt/tros" >&2
  echo "[setup] Install RDK Ubuntu 22.04 + tros.b before running project nodes." >&2
  exit 1
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "[setup] ros2 command not found after sourcing tros.b" >&2
  exit 1
fi

if ! python3 -c "import cv2" >/dev/null 2>&1; then
  echo "[setup] python3-opencv is missing. Install on RDK with:" >&2
  echo "  sudo apt update && sudo apt install -y python3-opencv v4l-utils" >&2
  exit 1
fi

if ! python3 -c "import smbus2" >/dev/null 2>&1; then
  echo "[setup] python3-smbus2 is missing. Install on RDK with:" >&2
  echo "  sudo apt update && sudo apt install -y python3-smbus2 i2c-tools" >&2
  exit 1
fi

cd "$(dirname "$0")/../rdk_x5/ros2_ws"

packages=()
[[ -f src/perception_camera/package.xml ]] && packages+=("perception_camera")
[[ -f src/gimbal_laser/package.xml ]] && packages+=("gimbal_laser")

if [[ "${#packages[@]}" -eq 0 ]]; then
  echo "[setup] No RDK ROS2 packages found under rdk_x5/ros2_ws/src" >&2
  exit 1
fi

colcon build --packages-select "${packages[@]}"

echo "[setup] RDK workspace built"
