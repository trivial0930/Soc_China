# 实验室一键建图操作手册（B1）

适用:RDK X5（`root@192.168.128.10`）+ STM32 USB CDC 底盘 + 雷神 N10 雷达 + BMI088 IMU。
方式:**方式一（RDK 端一条 launch 起整套）**，App 只当遥控手柄用，不在 App 里做"建图按钮"。

> 一句话流程:**到实验室 → 一条 launch 起栈 → App 摇杆慢速绕一圈（回到起点闭环）→ 一条命令存图**。

---

## 0. 出发前 / 到场前检查
- 黑药丸 **独立稳压供电**（反复失联根因是它 USB 供电不稳；电源前端要防反接，本工程已两次因反接烧 TB6612）。
- 网络:Mac/手机与 RDK 同网，或走 Tailscale（Mac `100.114.38.16`）。SSH 抖动多半在 Mac↔RDK 网线 en7。
- 仓库路径:RDK 上是 `/root/Soc_China`；Mac 上**用 `~/projects/Soc_China`**（Desktop 那份被 macOS TCC 拦 EPERM）。

## 1. 起栈前先腾出 CPU（重要）
开机自启的 **语音/认知/VLM 那套（asr / cognition / llama-server / gimbal）会和建图栈抢 CPU**（实测 gimbal_controller ~53%、llama-server 常驻）。建图不需要它们，先停掉，减少 EKF 滞后与 slam 丢扫描:

```bash
ssh root@192.168.128.10
systemctl stop voice-asr.service        # 停语音/认知/VLM/云台自启那一组
pkill -f llama-server 2>/dev/null        # 兜底:VLM 若残留再杀
# 确认没有旧的 lslidar / 建图节点占着串口或话题:
pkill -f lslidar_driver_node 2>/dev/null; pkill -f slam_toolbox 2>/dev/null
```

> 建图结束后想恢复语音:`systemctl start voice-asr.service`。

## 2. 一键起建图栈
```bash
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
ros2 launch chassis_bringup mapping.launch.py \
    ingest_token:=$(cat ~/.app_ingest_token)
```
这一条会起:`lslidar_driver`(→/scan) + `bringup`(轮速里程计 + BMI088 IMU-EKF → odom→base_link + 静态 base_link→laser) + `slam_toolbox`(map→odom、/map) + `teleop_safety`(App 遥控 + 雷达反应式避障)。

可选参数(一般用默认):
- `backend_url:=http://192.168.128.100:8000`（后端地址，给 teleop 回传安全状态）
- `use_imu:=true`（默认开，建图强烈建议融合 IMU）
- `lslidar_params:=/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml`

## 3. 确认栈起来了（30 秒自检）
另开一个 ssh:
```bash
source /opt/ros/humble/setup.bash; source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
ros2 node list           # 期望 7 个:lslidar / stm32_bridge / bmi088_imu / ekf_filter_node / slam_toolbox / lidar_safety / teleop_receiver
ros2 run tf2_ros tf2_echo map odom        # 有输出=slam 在消费扫描(静止时 [0,0,0] 正常)
ros2 run tf2_ros tf2_echo base_link laser # 期望 [0.126, 0, 0.100]
ros2 topic info /map                       # Publisher count: 1
```
**别用 `ros2 topic hz /scan` / `echo /map` 当判据**:雷达是 best_effort、/map 是 transient_local，ssh 临时节点 DDS 发现慢、短 timeout 经常抓空，**不代表没数据**。以 **TF 在走 + node list 全 + `/map` Publisher=1** 为准。

启动头几秒 slam 打印 `Message Filter dropping message ... queue is full` 和一次 EKF `Failed to meet update rate` 是**启动尖峰，正常**;`LaserRangeScan contains 451 range readings, expected 449` 也无害（slam 容忍）。只要不是持续刷屏即可。

## 4. App 遥控绕图走法
- 用 App 遥控页摇杆开车（链路:App→后端→RDK teleop_receiver→lidar_safety 门控→/cmd_vel）。
- **慢**。建图最怕快、最怕原地猛转。匀速直行 + 大半径转弯。
- **贴墙绕一圈，最后回到起点**形成闭环（loop closure），地图才准、不漂。
- 走廊/大空间多给雷达看到墙面;空旷无特征处会漂，尽量贴结构走。
- 倒退:雷达正后方 30cm 内是车体/线，已被 `near_masks=[180,45,0.30]` 屏蔽（后方 <30cm 当车体丢弃、≥30cm 仍避障）。
- 安全:三重 deadman（松手发 0 / 后端 age / RDK staleness + stm32_bridge 0.5s），避障纯本地，网络断不影响刹停。

## 5. 存图
绕完、回到起点、车停稳后，新开 ssh:
```bash
source /opt/ros/humble/setup.bash; source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
ros2 run nav2_map_server map_saver_cli -f ~/lab_map
```
产出 `~/lab_map.pgm` + `~/lab_map.yaml`。建议 `scp` 回 Mac 备份:
```bash
scp root@192.168.128.10:'~/lab_map.*' ~/projects/Soc_China/rdk_x5/maps/
```
存完可以 Ctrl-C 停建图栈。

## 6. 常见问题
| 现象 | 原因 / 处理 |
|---|---|
| 第一个终端起 lslidar 报 "No file path provided" | 命令被终端折行了，用单行绝对路径 |
| lslidar 起不来 / 串口被占 | 上一次的 lslidar 没退，`pkill -f lslidar_driver_node` 后重起 |
| `topic hz /scan` 空 / `echo /map` 空 | DDS 发现/QoS 假象，不是没数据；看 TF + node list（见 §3）|
| 启动时 slam "queue is full" 丢几帧 / EKF "Failed to meet rate" | 启动尖峰，正常；持续刷屏才查 CPU（先停 voice-asr.service，§1）|
| 地图漂/重影 | 走太快或原地猛转；放慢、贴墙、闭环回起点重建 |
| 摇杆突然失效 | 多为前端停发（后端 age 变大），机器人端无恙；查 App，机器人会自动刹停 |
| 反复失联 | 黑药丸 USB 供电不稳（独立稳压）；或 Mac↔RDK 网线 en7 |

## 7. 下一步（B2 导航）
存好图后做 Nav2:AMCL 定位 + MPPI(Omni) 控制 + costmap，在 `~/lab_map` 上自主导航（已配未实测）。

---
关联:`rdk_x5/ros2_ws/src/chassis_bringup/launch/mapping.launch.py`、`docs/validation/daily/2026-06-27-pcb-bringup-teleop-lidar-safety.md`、teleop_safety 包 README。
