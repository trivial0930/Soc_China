# B2 Nav2 上板 bring-up 验证 — 2026-07-06

实验室现场,SSH 驱动 RDK。执行 plan `docs/superpowers/plans/2026-07-06-b2-nav2-navigation.md` 的 Task 5。

## ✅ 已验证

**底盘 / 供电(重大)**
- **黑药丸供电挂死已根治**:从给 RDK 供电的 5V 稳压模块**直连一路 5V/GND 到黑药丸的 5V 脚**(绕开 RDK USB VBUS 供电路径)。实测:改前空闲 1-2 分钟必挂;改后**连续 240s 0 挂死**,且 **Nav2 驱动电机(原地旋转)全程 /odom 不断 = 带载也不挂**。详见 [[runaway-fix-and-blackpill-hang]]。
- `nav.launch` 起自己的 stm32_bridge;起栈时多节点抢 CPU 偶发 bridge 开串口拿不到 /odom → 重起一次 bridge/栈即好(STM32 未挂时)。

**Nav2 软件栈**
- 部署 + `colcon build` OK;`nav.launch` 起全 10+ 节点(amcl/planner/controller/bt_navigator/map_server/velocity_smoother/behavior_server/ekf/lslidar/bridge)。
- **上板修 3 个 nav2_params 缺陷才起得来**(已改并提交):
  1. **缺 `map_server` 段** → map_server 报 `yaml_filename is not initialized`、定位栈 abort。补 `map_server: {yaml_filename: ""}`(launch 的 `map:=` 改写它)。
  2. **amcl 不自动定位** → 裸 `ros2 topic pub /initialpose` 因 QoS/时间戳投递不到 amcl。改用 `set_initial_pose: true` + `initial_pose` 参数启动即定位。
  3. **costmap TF 容差太小** → global_costmap 报 `extrapolation into the past` (base_link→map)。amcl + 两 costmap 加 `transform_tolerance: 1.0`。
- 修完:map_server/amcl/controller/planner/bt_navigator 全 `active`,map→odom 出现,`/map` 载入(412×528,占据 2954 cell),TF 链 map→odom→base_link→laser 全通。
- **Nav2 自主驱动电机验证通过**:发原地旋转目标 `send_goal --goal 0 0 1.57` → 车**实际旋转 ~90°**(用户目视确认 + odom qz→0.704)、result SUCCEEDED。

## ⛔ 未完成:平移导航(定位问题,非栈缺陷)

- 前进目标 `send_goal --goal 0.3 0 0` 全部 **1s 内 SUCCEEDED、odom 0 位移、/plan 0 点**——planner 出空路径、Nav2 误判到达。
- **根因**:用户**不记得建图起点**,而 amcl 被播成 (0,0,0)=建图起点,车物理上不在那 → 扫描与地图对不上 → 定位是乱的 → planner 起点/终点在乱定位空间 → 空路径。
- 非栈 bug:地图/TF/costmap/planner 配置都对了,纯粹缺**正确的初始定位**。headless(无 RViz)+ 不知起点 + 线长限制,今天给不了正确初始位姿、也没法做全局定位(要开车跑才收敛)。

## 下一步

1. **正确定位**:用 RViz「2D Pose Estimate」在地图上点出车真实位置(需笔记本+网络到 RDK 的 ROS 图),或把车放到地图上一个**认得出的地标/建图起点**,amcl 收敛后 map 目标即可用(栈已验证功能正常)。
2. **odom 转向标定**:纯旋转时 odom 漂 ~28cm(mecanum 逆运动学 half_length/half_width 是模板值未标定)→ 影响转弯定位精度,待标定。
3. 供电改的直连 5V 已根治挂死;可继续把它做成永久接法。
4. 最终 whole-branch review 待平移导航验完一并做。
