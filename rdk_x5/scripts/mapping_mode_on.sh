#!/bin/bash
# 进建图模式:停重负载子集(保留命令通道三件)-> 起建图栈 -> 校验(<=30s)。
# 成功 exit 0;失败自清建图栈并 exit 1。
set -u
export HOME=/root
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null

# 1) 停重负载子集(绝不动 uplink/command_receiver/acceptance)
for pat in llama-server tts_server.py voice_node report_service \
           cognition_node gimbal_controller_node laser_node asr_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 2

# 2) 起建图栈(后台,孤儿化,日志独立)
TOK=$(cat /root/.app_ingest_token 2>/dev/null)
setsid ros2 launch chassis_bringup mapping.launch.py ingest_token:="$TOK" \
  >/tmp/mapping.log 2>&1 < /dev/null &

# 3) 校验:关键节点是否都起来(用 node list,不信 topic hz)
need="lslidar_driver_node async_slam_toolbox_node stm32_bridge_node ekf_node"
for i in $(seq 1 30); do
  sleep 1
  nodes=$(ros2 node list 2>/dev/null)
  ok=1
  for n in $need; do echo "$nodes" | grep -q "$n" || ok=0; done
  [ "$ok" = "1" ] && { echo "[mode] mapping stack up after ${i}s"; exit 0; }
done

echo "[mode] mapping stack FAILED to come up in 30s; tearing down" >&2
for pat in "mapping.launch" lslidar_driver_node async_slam_toolbox_node \
           ekf_node stm32_bridge_node bmi088_imu_node lidar_safety_node teleop_receiver_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
exit 1
