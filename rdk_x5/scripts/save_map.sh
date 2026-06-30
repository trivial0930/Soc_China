#!/bin/bash
# 存当前 slam 地图到 ~/maps/<name>.pgm|.yaml。参数:name(已由上游净化)。
export HOME=/root
# 注意:ROS 的 setup.bash 引用未定义变量,必须在 set -u 之前 source
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null
set -u
name="${1:-lab_map}"
mkdir -p /root/maps
ros2 run nav2_map_server map_saver_cli -f "/root/maps/${name}" --ros-args -p save_map_timeout:=20.0
