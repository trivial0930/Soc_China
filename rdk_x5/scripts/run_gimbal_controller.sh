#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(cd "${SCRIPT_DIR}/../ros2_ws" && pwd)"

CONFIG_FILE="${CONFIG_FILE:-}"

if [[ -f /opt/tros/humble/setup.bash ]]; then
  set +u
  source /opt/tros/humble/setup.bash
  set -u
elif [[ -f /opt/tros/setup.bash ]]; then
  set +u
  source /opt/tros/setup.bash
  set -u
else
  echo "[gimbal] Cannot find tros.b setup.bash under /opt/tros" >&2
  exit 1
fi

if [[ -f "${WS_DIR}/install/setup.bash" ]]; then
  set +u
  source "${WS_DIR}/install/setup.bash"
  set -u
else
  echo "[gimbal] Workspace is not built yet. Run:" >&2
  echo "  cd ${WS_DIR}" >&2
  echo "  colcon build --symlink-install --packages-select gimbal_laser" >&2
  exit 1
fi

if ! python3 -c "import smbus2" >/dev/null 2>&1; then
  echo "[gimbal] python3-smbus2 is missing. Install on RDK with:" >&2
  echo "  sudo apt update && sudo apt install -y python3-smbus2 i2c-tools" >&2
  exit 1
fi

if pgrep -x gimbal_controll >/dev/null 2>&1; then
  echo "[gimbal] controller is already running; refusing to start a duplicate." >&2
  echo "[gimbal] Stop the existing controller first, or run:" >&2
  echo "  pgrep -x gimbal_controll | xargs -r kill" >&2
  exit 0
fi

echo "[gimbal] starting controller"

if [[ -n "${CONFIG_FILE}" ]]; then
  ros2 launch gimbal_laser gimbal_controller.launch.py config_file:="${CONFIG_FILE}"
else
  ros2 launch gimbal_laser gimbal_controller.launch.py
fi
