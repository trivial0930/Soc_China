# 实验室一键建图操作手册（B1）

适用:RDK X5（`root@192.168.128.10`）+ STM32 USB CDC 底盘 + 雷神 N10 雷达 + BMI088 IMU。
方式:**App「建图模式」开关一键就绪**(主流程);RDK 端手动 launch 作为高级/备用。

> 一句话流程:**到实验室 → App 打开「建图模式」开关(自动腾资源+起栈)→ App 摇杆慢速绕一圈（回到起点闭环）→ App「存图」按钮 → 关开关恢复语音**。

---

## 0. 出发前 / 到场前检查
- 黑药丸 **独立稳压供电**（反复失联根因是它 USB 供电不稳；电源前端要防反接，本工程已两次因反接烧 TB6612）。
- 网络:Mac/手机与 RDK 同网，或走 Tailscale（用 Mac 的 Tailscale IP）。SSH 抖动多半在 Mac↔RDK 网线 en7。
- 仓库路径:RDK 上是 `/root/Soc_China`；Mac 上**用 `~/projects/Soc_China`**（Desktop 那份被 macOS TCC 拦 EPERM）。

## 1. 主流程:App 一键建图模式
打开 App「建图模式」开关即可,RDK 自动:停语音/认知/VLM 那套(它们会和建图栈抢 CPU/内存,实测 gimbal ~53%、llama-server 占 ~3GB)→ 起整套建图栈。

- 开关状态以 RDK 回报的真实 mode 为准:`normal`(正常)/`switching`(切换中,十几秒,禁开关)/`mapping`(建图中)/`mapping_error`(进建图失败,已停在安全态,可重试/退出)。
- 进建图失败会**停在安全态、不自动回滚**:App 显示红色错误,点【退出】恢复语音或【重试】。
- 实现:命令经现有命令队列(`set_mode`/`save_map`)→ RDK `command_receiver` 调 `mapping_mode_on.sh`/`off.sh`/`save_map.sh`;状态文件 `/root/.robot_mode`,经 uplink/command_receiver 上报。

> 关开关 = 拆建图栈 + 重拉语音栈。命令通道(uplink+command_receiver+acceptance)全程不停,所以建图中也始终能从 App 发"退出"。
> 注意:建图模式中若 RDK 重启,开机自启会拉回正常语音栈,但状态文件 `/root/.robot_mode` 仍记 `mapping`(App 会短暂显示建图中);点一次 OFF 即自愈回 normal。建图是临时态,别让它跨重启。

## 2.（备用/手动）RDK 端命令行起栈
App 不可用时,SSH 上 RDK 手动起:
```bash
ssh root@192.168.128.10
systemctl stop voice-asr.service        # 停语音/认知/VLM/云台自启那一组(腾 CPU/内存)
pkill -f llama-server 2>/dev/null        # 兜底:VLM 若残留再杀
pkill -f lslidar_driver_node 2>/dev/null; pkill -f slam_toolbox 2>/dev/null   # 清旧建图节点
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
ros2 launch chassis_bringup mapping.launch.py ingest_token:=$(cat ~/.app_ingest_token)
```
> 注意:`voice-asr.service` 是 KillMode=process + setsid,`systemctl stop` 杀不掉已起的节点,故上面要 `pkill`。建图结束恢复语音:`systemctl start voice-asr.service`(或直接用 App 关开关,走 `mapping_mode_off.sh` 更干净)。

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
关联:`rdk_x5/ros2_ws/src/chassis_bringup/launch/mapping.launch.py`、teleop_safety 包 README。
