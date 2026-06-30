# App 遥控 + 雷达安全层(反应式避障 A 阶段)— 设计

日期:2026-06-27 · 阶段:A(反应式避障,模式 b = 遥控 + 雷达本地安全)。成功后再做 B(完整 Nav2)。

## Context(为什么)
底盘已验收(PCB 接线/PID/前进/旋转 OK)。下一步要让**雷达真正联动运动并避障**。先做轻量、自包含的 A 阶段:用户用控制 App 遥控小车,**雷达安全层在 RDK 本地实时运行**——网络遥控可有延迟,但前方有障碍时 RDK 自己减速/停,保证安全。这是 B(Nav2)的垫脚石。

现有可复用(已探索确认):
- `stm32_bridge` 订阅 `/cmd_vel`(Twist)→ STM32(USB CDC),带 0.5s cmd_vel 超时归零。
- 雷达 N10 经 `lslidar_driver` 发 `/scan`(frame `laser`,≤12m);`base_link→laser` 静态 TF 已测(URDF)。
- App(Flutter `app/mobile` + PWA)↔ 后端(FastAPI)↔ RDK:**下行是 2s 轮询命令队列**(`POST /api/commands` → RDK `command_receiver` 轮询)——**太慢,不能用于实时遥控**;故遥控速度走**新的低延迟端点**。
- RDK↔后端:HTTP,`backend_url=http://192.168.128.100:8000`,Bearer `ingest_token`;有现成 poster/轮询模式(uplink_node / command_receiver)。

## 数据流
```
App 摇杆(~10Hz) ─POST /api/robot/teleop {vx,vy,wz}→ 后端(存最新速度+ts,覆盖式)
RDK teleop_receiver ─GET /api/robot/teleop(10Hz)→ 取最新 → 发 /cmd_vel_teleop(Twist)
RDK lidar_safety: /scan + /cmd_vel_teleop → 门控 → /cmd_vel → stm32_bridge → STM32
RDK lidar_safety 发 /safety/status → teleop_receiver POST /api/robot/teleop/status → App 显示
```

## RDK 端(本仓库实现)—— 新 ROS2 包 `teleop_safety`
### lidar_safety_node(核心避障;纯 ROS、可 host 单测)
- 订阅 `/scan`(sensor_msgs/LaserScan)、`/cmd_vel_teleop`(geometry_msgs/Twist);发 `/cmd_vel`(Twist)、`/safety/status`(std_msgs/String JSON)。
- 门控逻辑(纯函数 `gate_twist(scan_ranges, angle_min, angle_inc, vx, vy, wz, params)`):
  - 平移方向 `heading=atan2(vy,vx)`(机体系,0=前,+=左);仅当平移速度 `|v|>v_eps` 才检测。
  - 取以 heading 为中心 ±`sector_half_angle`(默认 35°)扇区内有效点最近距离 `d`。
  - `d < stop_dist`(默认 0.30m):**砍掉朝障碍的平移分量**(vx,vy 投影到 heading 的部分清零;保留后退/横向远离;wz 不动)。
  - `stop_dist ≤ d < slow_dist`(默认 0.60m):平移整体按 `(d-stop)/(slow-stop)` 线性缩放。
  - `d ≥ slow_dist`:放行。
  - **wz(旋转)始终透传**(原地转不平移、不会撞)。
  - **deadman**:`/cmd_vel_teleop` 超 `cmd_timeout`(0.5s)未更新 → 输出全 0。
  - 状态:`clear`/`slow`/`blocked` + 前向最近距离 `front_dist_m`。
- 参数(config):sector_half_angle、stop_dist、slow_dist、v_eps、cmd_timeout、scan 角度裁剪、最小有效距离(滤 0/inf)。
- 控制频率:20Hz(或随 scan)。

### teleop_receiver_node(网络;复用现有 poster/轮询)
- 10Hz `GET /api/robot/teleop`(Bearer)→ 取 {vx,vy,wz,age_ms};age 过大(后端侧无新指令)→ 发 0。发 `/cmd_vel_teleop`。
- 订阅 `/safety/status` → 限频(~2Hz)`POST /api/robot/teleop/status`。
- 参数:backend_url、token、poll_hz、staleness 阈值。

### 其他
- launch:`teleop_safety.launch.py` 起两节点 + 参数;文档/README 写明与 bringup、lslidar 的启动顺序。
- host 单测:`gate_twist` 纯逻辑(障碍正前→砍 vx 保 wz;障碍侧前→减速;deadman→0;旋转透传)。沿用项目 host-test 模式。
- 不动 `stm32_bridge`(仍订 `/cmd_vel`);不引入 twist_mux(A 阶段单源)。

## 后端(交给后端 agent 的 prompt)
新增、与 2s 命令队列**分开**的低延迟端点(内存存最新值即可):
- `POST /api/robot/teleop`(Bearer):body `{vx,vy,wz}`(m/s, rad/s),存最新+server ts。
- `GET /api/robot/teleop`:返回 `{vx,vy,wz,age_ms}`。
- `POST /api/robot/teleop/status`(Bearer):body `{state,front_dist_m}`,存最新+ts。
- `GET /api/robot/teleop/status`:返回最新状态+age_ms。
- 更新 `API_SPEC.md`;写最小测试。安全上限可在后端再 clamp(vx/vy≤0.4, wz≤1.5)。

## 前端(交给前端 agent 的 prompt)
App 加"遥控"页:
- 虚拟摇杆:前后=vx、左右=wz;可选第二摇杆/横向=vy(默认弱或可关,因麦轮地面横移弱)。
- 按住时 ~10Hz `POST /api/robot/teleop`,**松手立即发 0**;断触/退页也发 0(deadman)。
- 显示 `/api/robot/teleop/status`:clear/slow/blocked + 距离(颜色提示)。
- 沿用设置页 backend URL + token。

## 安全
- 三重 deadman:前端松手发 0 → 后端 age_ms → RDK teleop_receiver staleness → stm32_bridge 0.5s 超时。
- 雷达安全层在 RDK 本地,网络延迟/断不影响避障。
- 阶段限速沿用 stm32_bridge clamp(vx/vy 0.4m/s、wz 1.5)。

## 验证
- host:`gate_twist` 单测全绿。
- 集成:bringup(odom/EKF/TF)+ lslidar(/scan)+ teleop_safety;App 遥控前进撞向墙 → 距离<0.6 减速、<0.3 停;松手停;转向不被挡。

## 范围之外(留给 B / 后续)
建图(slam_toolbox)、Nav2/AMCL/代价地图、自主路径、横移优化(需光滑地面)、twist_mux 多源仲裁。
