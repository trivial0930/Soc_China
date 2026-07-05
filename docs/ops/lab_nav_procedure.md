# 实验室自主导航(B2 / Nav2)操作手册

前提:B1 已建好并存了 `~/maps/lab_map.{pgm,yaml}`;里程/固件已标定;IMU 正常。

## 1. 腾 CPU(必做)
Nav2(MPPI + AMCL + 双 costmap)吃 CPU 比 slam 还重:
```
systemctl stop voice-asr.service
```

## 2. 放车到已知起点
把车放在地图上一个**记得住的起点**(建图起点附近最稳),记下它在地图坐标里的大致 (x, y, yaw)。

## 3. 一键起导航栈
```
ros2 launch chassis_bringup nav.launch.py
```
起底盘基座 + AMCL(载入 lab_map)+ Nav2。

## 4. 验栈(另一个终端)
```
ros2 node list | grep -E "amcl|controller_server|planner_server|bt_navigator|map_server"
for n in /amcl /controller_server /planner_server /bt_navigator /map_server; do echo -n "$n: "; ros2 lifecycle get $n; done   # 各应 active
ros2 run tf2_ros tf2_echo map odom      # 非空 = map->odom 有了
ros2 topic echo --once /amcl_pose       # 有位姿
```

## 5. 定位收敛
```
ros2 run chassis_bringup send_goal --init <x> <y> <yaw> --goal <x> <y> <yaw>
```
`--init` 播初始位姿。若粒子云不收敛,原地缓慢转一圈或前后挪一点让 AMCL 咬住扫描。

## 6. 发目标 + 观察
先发**近目标(~1–2m)**:
```
ros2 run chassis_bringup send_goal --goal <x> <y> <yaw>
```
脚本打印剩余距离,到达/失败/超时都会报;车到达容差 xy≤10cm、yaw≤0.15。

## 7. 动态避障测试
导航中在路上放个障碍 → local costmap 标记 → Nav2 重规划绕过(或安全停)。

## 坑
- 起 nav 前没停 voice-asr → controller/AMCL 跟不上,路径抖/丢定位。
- 车放地上留足空地;先发短目标;失控就 Ctrl-C 掉 nav.launch(会停发 /cmd_vel,bridge 500ms cmd 超时自动停车)。
- 黑药丸驱动电机时仍有挂死风险(功率地未根治);跑动中 /odom 断 → 复位 STM32(见 [[runaway-fix-and-blackpill-hang]])。
- `robot_radius/inflation/速度上限` 为模板值,首次按实车观察微调 nav2_params.yaml。
