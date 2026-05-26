#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[smoke] current directory: $(pwd)"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/soc_china_pycache"

echo "[smoke] python syntax"
python3 -m py_compile \
  rdk_x5/ros2_ws/src/perception_camera/perception_camera/fixed_camera_node.py \
  rdk_x5/ros2_ws/src/perception_camera/launch/fixed_camera.launch.py \
  rdk_x5/ros2_ws/src/gimbal_laser/gimbal_laser/as5600.py \
  rdk_x5/ros2_ws/src/gimbal_laser/gimbal_laser/gimbal_controller.py \
  rdk_x5/ros2_ws/src/gimbal_laser/gimbal_laser/gimbal_controller_node.py \
  rdk_x5/ros2_ws/src/gimbal_laser/gimbal_laser/rdk_x5_gpio.py \
  rdk_x5/ros2_ws/src/gimbal_laser/gimbal_laser/rdk_x5_pwm.py \
  rdk_x5/ros2_ws/src/gimbal_laser/launch/gimbal_controller.launch.py \
  rdk_x5/scripts/uart_protocol_test.py \
  rdk_x5/scripts/uart_send_test.py \
  sim/stm32_simulator/serial_simulator.py \
  shared/protocol/rdk_stm32_uart.py

echo "[smoke] shell syntax"
bash -n rdk_x5/scripts/detect_cameras.sh
bash -n rdk_x5/scripts/check_wifi_camera.sh
bash -n rdk_x5/scripts/run_fixed_camera.sh
bash -n rdk_x5/scripts/run_gimbal_controller.sh
bash -n tools/setup_rdk.sh

echo "[smoke] unit tests"
python3 -m unittest discover -s tests

echo "[smoke] uart protocol self-test"
python3 rdk_x5/scripts/uart_protocol_test.py
python3 rdk_x5/scripts/uart_send_test.py --dry-run --mode manual --vx 50

echo "[smoke] ok"
