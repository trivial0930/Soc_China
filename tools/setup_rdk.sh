#!/usr/bin/env bash
set -euo pipefail

if [[ -f /opt/tros/humble/setup.bash ]]; then
  source /opt/tros/humble/setup.bash
elif [[ -f /opt/tros/setup.bash ]]; then
  source /opt/tros/setup.bash
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

cd "$(dirname "$0")/../rdk_x5/ros2_ws"
colcon build --symlink-install --packages-select perception_camera

echo "[setup] RDK camera workspace built"
