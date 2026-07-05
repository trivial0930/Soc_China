# B2 Nav2 自主导航 — 设计 spec

## 背景与目标

B1(建图)已完成:实地建好并存了 `lab_map`(~20.6×26.4m,5cm 分辨率)。B2 要基于这张静态图,让 RDK X5 麦轮底盘用 **Nav2** 做自主导航——发一个目标点,车自主规划路径、避障、开过去。

**本轮范围(已与用户确认):最小闭环 + 动态避障验证。**
- 起 Nav2 栈 + AMCL 在 `lab_map` 上定位;命令行/脚本发目标,车自主到达(xy≤10cm)。
- 额外验证:路上放个障碍,Nav2 能重规划绕过。
- **上板实测通过即完成。** App 发目标、地图渲染、导航为正式 App 模式——全部留后(YAGNI)。

## 现状(已有 vs 缺)

**已有**:
- `chassis_bringup/config/nav2_params.yaml` — 完整模板:**MPPI 控制器**(`motion_model: Omni`,麦轮)、**AMCL**(`OmniMotionModel`)、局部+全局 costmap(`/scan` 障碍层 + 静态层)、navfn 规划器、behaviors、velocity_smoother。`robot_radius: 0.16`、`vx_max: 0.25`。
- `~/maps/lab_map.{pgm,yaml}`(RDK 上;仓库 `rdk_x5/maps/` 有备份)。
- EKF(`odom→base_link`,融合轮式 odom + IMU 陀螺;IMU accel+gyro 现已全部修复,定位更稳)、lslidar `/scan`、`stm32_bridge`、static TF。
- `package.xml` 已声明 `nav2_bringup`、`nav2_simple_commander` 依赖。
- 里程标定已校准(`ticks_per_rev=1323`、`wheel_radius=0.038`,固件与 RDK odom 一致,命令 vx≈真实 vx)。

**缺**:
- `nav.launch.py`(一键起导航全栈)
- `send_goal.py`(发初始位姿 + 目标 + 监控的脚本)
- 操作手册 `docs/ops/lab_nav_procedure.md`
- 上板整定(footprint/速度/costmap 膨胀等模板值按实车核)

## 架构与数据流

**TF 树**(Nav2 要求):
```
map ──[AMCL]──> odom ──[EKF]──> base_link ──[static]──> laser
```
- `map→odom`:**AMCL**(在静态 `lab_map` 上粒子滤波定位,替代建图时的 slam_toolbox)。
- `odom→base_link`:**EKF**(现有,融合轮式 odom + IMU 陀螺 vyaw)。
- `base_link→laser`:static TF(现有)。

**节点栈**(一条 `nav.launch.py` 起全):
```
底盘基座(复用):lslidar(/scan) + EKF(/odom, odom→base_link) + stm32_bridge(/cmd_vel→电机) + static TF
定位:        nav2_bringup/localization_launch.py = map_server(载入 lab_map) + amcl(map→odom)
导航:        nav2_bringup/navigation_launch.py = planner(navfn) + controller(MPPI/Omni)
             + bt_navigator + behaviors + velocity_smoother + lifecycle_manager(autostart)
```
用官方 `nav2_bringup` 子 launch(而非手写节点),传我们的 `nav2_params.yaml` + `map:=~/maps/lab_map.yaml`,标准、少踩坑。

**cmd_vel 路径(独立模式,已确认)**:
```
Nav2 controller ─> velocity_smoother ─(remap)─> /cmd_vel ─> stm32_bridge ─> 电机
```
导航时 **teleop_safety 不跑**(与 Nav2 互斥,和建图模式一致);避障完全靠 Nav2 的 local costmap(`/scan` 障碍层)。velocity_smoother 输出 remap 到 `/cmd_vel`(bridge 订阅的话题),**不改 bridge**。

## 组件

**① `nav.launch.py`**:结构照搬 `mapping.launch.py`。起底盘基座(lidar/EKF/bridge/static TF)+ include `nav2_bringup` 的 `localization_launch.py` 与 `navigation_launch.py`,统一传 `nav2_params.yaml`,`navigation_launch` 里把 velocity_smoother 的 `cmd_vel` 输出 remap 到 `/cmd_vel`。参数:`map`(默认 `~/maps/lab_map.yaml`)、`params_file`(默认 nav2_params.yaml)、`use_sim_time:=false`。

**② `send_goal.py`(nav2_simple_commander,跑在 RDK)**:
- `BasicNavigator`:`waitUntilNav2Active()` → `setInitialPose(x,y,yaw)` → `goToPose(x,y,yaw)`;
- 循环打印反馈(剩余距离/预计时间),到达/失败/超时都明确报;
- CLI:`send_goal.py --init x y yaw --goal x y yaw`(初始位姿把车放地图已知点后传入)。

**③ 操作手册** `docs/ops/lab_nav_procedure.md`:开机 → 停 voice-asr → 放已知起点 → 起 `nav.launch` → 验栈 → `send_goal` → 观察 → 避障测试。

## 定位初始化

- 车放地图上**已知起点**(建图起点附近最稳),`send_goal.py` 用 `setInitialPose` 播 `/initialpose`。
- 发完初始位姿后**原地缓慢转一圈或前后挪一点**让 AMCL 粒子云收敛(omni 模型靠运动 + 扫描匹配)。
- 判据:`/amcl_pose` 稳定 ≈ 实际位姿、`tf map→odom` 不乱跳。

## 成功标准

1. `nav.launch` 起栈,lifecycle 全 `active`,`tf map→odom` 存在。
2. AMCL 定位收敛(`amcl_pose` ≈ 真实起点)。
3. 发近目标(~1–2m)→ 规划出路径 → 自主开过去 → 到达(xy≤10cm、yaw≤0.15,取自配置)。
4. **动态避障**:导航中路上放障碍 → local costmap 标记 → Nav2 重规划绕过(或安全停),最终到达。

## 验证方案(无头,SSH 驱动)

- 起栈:`ros2 node list`、各 lifecycle 节点 `active`、`ros2 run tf2_ros tf2_echo map odom` 非空、`/amcl_pose` 有值。
- 定位:发 initialpose + 挪车 → `amcl_pose` 收敛核对。
- 导航:`send_goal` 发近目标 → 打印反馈到到达 → 量终点位姿 vs 目标。
- 避障:发目标 + 中途放障碍 → 确认路径变化(重规划)+ 结果。
- **安全**:车落地留足空地、先发短目标(~1m)、vx_max 0.25 已限速;失控时 SSH 杀 nav 栈停车。

## 资源前置(坑)

Nav2(MPPI batch 2000)+ AMCL + 双 costmap 在 RDK 上**吃 CPU 比 slam 还重**。起 nav 前必须 **`systemctl stop voice-asr.service`** 腾资源(否则 controller/AMCL 跟不上),与建图模式同理。

## 不做(YAGNI)

App 发目标、App 地图渲染、导航作为正式 App 模式(命令通道/mode_switch 集成)、多点巡航(waypoints)、costmap/MPPI 精细整定超出"能跑通+避障"的部分——全部留后续迭代。

## 风险与待定

- **AMCL 收敛**:omni 麦轮需运动才收敛;首次可能要多挪几下。
- **MPPI/costmap 为模板值**:`robot_radius 0.16`、`inflation_radius 0.35`、速度上限等上板第一次要按实车核/微调。
- **CPU**:若停 voice 后仍跟不上,考虑降 MPPI `batch_size`/`time_steps` 或 costmap 频率。
- **黑药丸挂死**:驱动电机时的老风险仍在(功率地未根治),导航跑动中若 /odom 断需复位 STM32。
