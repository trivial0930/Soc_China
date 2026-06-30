#!/bin/bash
# 退出建图模式:停建图栈(干净,含 setsid 孤儿)-> 重拉重负载层。
# 全部恢复 exit 0;有组件没起来 exit 2。
set -u
export HOME=/root
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null

# 1) 停建图栈(彻底清孤儿,释放 STM32 串口)
for pat in "mapping.launch" lslidar_driver_node async_slam_toolbox_node \
           ekf_node stm32_bridge_node bmi088_imu_node lidar_safety_node teleop_receiver_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 2

# 2) 重拉重负载层(各自 start 脚本;命令通道一直没动,不重起)
for s in start_llm start_tts_server start_voice start_report start_cognition start_gimbal start_asr; do
  bash /root/$s.sh >/tmp/${s}.relaunch.log 2>&1
  sleep 1
done

# 3) 粗校验:llama + 关键语音节点回来没
sleep 3
warn=0
pgrep -f llama-server >/dev/null || warn=1
pgrep -f voice_node >/dev/null || warn=1
pgrep -f asr_node >/dev/null || warn=1
[ "$warn" = "0" ] && { echo "[mode] normal stack restored"; exit 0; }
echo "[mode] some heavy components did not restart" >&2
exit 2
