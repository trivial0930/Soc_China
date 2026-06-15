# 2026-06-07 RDK X5 + N10 + STM32 麦轮底盘工程接手执行文档

整理时间：2026-06-07

适用范围：本文整理当前 RDK X5、镭神 N10 2D 激光雷达、STM32F411、TB6612 双路电机驱动、四轮麦克纳姆底盘的调试状态、已验证结论、当前阻塞、后续执行步骤和安全注意事项。本文是后续施工手册，不是聊天逐字记录。

## 1. 当前工程目标

最终目标是做一台基于 RDK X5 的电子实验室巡检小车：

- RDK X5 作为上位机，运行 ROS 2、感知、建图、导航与任务逻辑。
- 镭神 N10 提供 2D 激光扫描 `/scan`。
- STM32F411 作为底盘实时控制器，接收 RDK 的速度命令，控制四个麦克纳姆轮。
- 两块 TB6612 双路电机驱动板分别控制四个编码电机。
- 后续 IMU 与编码器用于里程计、姿态估计和闭环控制。

推荐控制链路：

```text
RDK X5
  -> ROS 2 / Nav2 / SLAM
  -> cmd_vel
  -> RDK-STM32 UART 协议
  -> STM32F411
  -> 麦克纳姆运动学
  -> PWM + DIR
  -> TB6612 x2
  -> 四个编码电机
```

感知链路：

```text
镭神 N10
  -> USB 串口
  -> RDK X5 /dev/ttyACM0
  -> lslidar_driver
  -> ROS 2 /scan
  -> RViz / SLAM / Nav2 costmap
```

## 2. 硬件与接口现状

### 2.1 RDK X5

已知 RDK 管理地址：

```text
192.168.128.10
root / root
```

Mac 侧 USB 网络地址曾配置为：

```text
192.168.128.100
```

RDK 外网 NAT 曾通过 Mac 转发解决。Mac 重启后可能需要重新执行：

```bash
sudo sysctl -w net.inet.ip.forwarding=1
printf "nat on en0 from 192.168.128.0/24 to any -> (en0)\n" | sudo pfctl -a com.apple/rdk_nat -f -
sudo pfctl -E
```

RDK 侧 netplan 已配置过 USB 网络默认路由，文件位置：

```text
/etc/netplan/01-hobot-net.yaml
```

### 2.2 镭神 N10 激光雷达

已确认型号：

```text
镭神 N10
```

推荐连接方式：

- N10 既有 USB 又有网口时，当前阶段推荐 USB。
- 原因：接线简单、RDK 上识别为串口、官方 ROS 2 驱动已按串口方式跑通。
- 网口后续可作为替代方案，但需要重新处理 IP、UDP/网络配置和驱动参数。

RDK 上曾识别为：

```text
/dev/ttyACM0
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E669875-if00
```

实测正确波特率：

```text
230400
```

曾在 230400 下读到 N10 原始帧头：

```text
a5 5a
```

### 2.3 STM32F411

STM32 用作底盘实时控制器。历史上 RDK 通过 40Pin UART 与 STM32 通信的有效串口为：

```text
RDK: /dev/ttyS1
UART: 115200 8N1
TTL: 3.3V
```

RDK 到 STM32 的 40Pin UART 接线：

| 功能 | RDK X5 40Pin | STM32F411 | 说明 |
| --- | --- | --- | --- |
| RDK TX | Pin 8 / UART1_TX | PA10 / USART1_RX | RDK 发命令 |
| RDK RX | Pin 10 / UART1_RX | PA9 / USART1_TX | STM32 回状态 |
| GND | 任一 GND | GND | 必须共地 |

如果当前改成 USB 接 STM32，则 RDK 上可能出现：

```text
/dev/ttyACM1
/dev/ttyUSB0
```

需要用 `dmesg`、`ls -l /dev/ttyACM* /dev/ttyUSB*` 确认。

### 2.4 TB6612 与四轮麦克纳姆底盘

两块 TB6612 双路驱动板控制四个电机：

| 驱动板 | 通道 | 轮位 | 代码轮位 |
| --- | --- | --- | --- |
| TB6612-A | 电机1 | 左上 | `LF` |
| TB6612-A | 电机2 | 左下 | `LR` |
| TB6612-B | 电机1 | 右上 | `RF` |
| TB6612-B | 电机2 | 右下 | `RR` |

历史固件中的 STM32 到 TB6612 映射：

| 轮位 | PWM | TIM 通道 | IN1 | IN2 |
| --- | --- | --- | --- | --- |
| 左上 LF | PA6 | TIM3_CH1 | PA0 | PA1 |
| 右上 RF | PB0 | TIM3_CH3 | PA4 | PA5 |
| 左下 LR | PA7 | TIM3_CH2 | PA2 | PA3 |
| 右下 RR | PB1 | TIM3_CH4 | PB8 | PB9 |

历史实测左侧两个轮子方向反过，固件中通过反向配置修正：

```c
cfg.invert[MECANUM_WHEEL_LF] = -1;
cfg.invert[MECANUM_WHEEL_LR] = -1;
```

## 3. 软件与文件位置

### 3.1 RDK ROS 2 工作区

RDK 上 ROS 2 工作区：

```text
/root/Soc_China/rdk_x5/ros2_ws
```

已安装 N10 驱动包：

```text
/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver
/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_msgs
```

使用的是官方 `Lslidar_ROS2_driver` 的 `N10_V1.0` 分支。

N10 配置文件：

```text
/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml
```

关键参数：

```yaml
lidar_name: N10
interface_selection: serial
serial_port_: /dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E669875-if00
frame_id: laser
scan_topic: /scan
max_range: 12.0
```

构建命令：

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select lslidar_msgs lslidar_driver
```

启动命令：

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run lslidar_driver lslidar_driver_node --ros-args \
  --params-file /root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml
```

后台启动建议：

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
setsid ros2 run lslidar_driver lslidar_driver_node --ros-args \
  --params-file /root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml \
  >/tmp/n10_driver.log 2>&1 </dev/null &
```

### 3.2 本机辅助快照脚本

本轮调试中创建过本机辅助脚本：

```text
/Users/sthefirst/Desktop/Soc_China/.tmp/n10_grab_snapshot.py
```

用途：

- 在 RDK 上订阅 `/scan` 一帧。
- 输出 JSON 统计。
- 生成等价 RViz 的 SVG 极坐标图。
- 紫色点代表 `0.30-1.20 m` 目标带。
- 橙色/红色点代表 `0.30 m` 内近距离遮挡风险。

运行方式：

```bash
scp /Users/sthefirst/Desktop/Soc_China/.tmp/n10_grab_snapshot.py \
  root@192.168.128.10:/tmp/n10_grab_snapshot.py

ssh root@192.168.128.10 \
  'source /opt/ros/humble/setup.bash; source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; python3 /tmp/n10_grab_snapshot.py /tmp/n10_scan_fixed'
```

拉回图像：

```bash
scp root@192.168.128.10:/tmp/n10_scan_fixed.svg \
  /Users/sthefirst/Desktop/Soc_China/.tmp/n10_scan_fixed.svg
scp root@192.168.128.10:/tmp/n10_scan_fixed.json \
  /Users/sthefirst/Desktop/Soc_China/.tmp/n10_scan_fixed.json
```

本机渲染 PNG：

```bash
qlmanage -t -s 1200 -o /Users/sthefirst/Desktop/Soc_China/.tmp \
  /Users/sthefirst/Desktop/Soc_China/.tmp/n10_scan_fixed.svg
```

## 4. 已完成验证

### 4.1 RDK 网络

已完成过：

- RDK 通过 USB 网络接入 Mac。
- Mac 侧 NAT 让 RDK 暂时访问外网。
- RDK 上能安装 ROS 依赖和下载源码。

注意：Mac/RDK 重启后外网转发可能需要重新启用。

### 4.2 N10 波特率与驱动

已完成过：

- RDK 识别 N10 USB 串口。
- 波特率检测确认 `230400` 正确。
- 官方 ROS 2 驱动安装并构建通过。
- `/scan` 曾稳定输出。

10 分钟稳定性测试结果摘要：

```text
/scan frequency: about 10.017-10.018 Hz
min interval: about 0.094 s
max interval: about 0.108 s
std dev: about 0.002 s
```

这说明在固定雷达之前，N10 与 ROS 2 驱动链路是可用的。

### 4.3 扫描方向验证

由于 RDK SSH 环境没有 `DISPLAY`，且未确认有可直接打开的 `rviz2`，实际使用 `/scan` 生成极坐标图替代 RViz 做方向检查。

坐标约定：

```text
front 0 deg: 红色 x 正方向
left 90 deg: 蓝色 y 正方向
back 180 deg: 灰色
right 270 deg: 绿色
```

已验证：

- 将目标放在车头正前方约 `40-80 cm`，`340-20 deg` 前方扇区出现明显目标点。
- 将目标放在左侧，`70-110 deg` 左侧扇区出现明显目标点。

结论：

```text
雷达 front / left 方向基本符合 ROS 坐标约定。
```

右侧和后方仍建议重新验证，尤其是在雷达固定后。

### 4.4 遮挡初判

固定前曾出现大量近距离点：

```text
有效点 371
0.30 m 内近点 249
0.15 m 内近点 106
```

这说明未固定或临时摆放状态下，雷达扫描平面内有车体、线束、桌面或支撑结构进入视野。

固定后必须重新做遮挡检查。

## 5. 当前阻塞：固定雷达后 N10 暂无串口数据

用户已固定雷达后，继续检查发现：

- `/dev/ttyACM0` 仍存在。
- `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E669875-if00` 仍存在。
- USB 设备仍正常枚举：

```text
1a86:55d4 QinHeng Electronics USB Single Serial
```

- ROS 驱动能启动并显示初始化成功。
- `/scan` topic 有发布者。
- 但 `ros2 topic echo /scan --once` 收不到实际消息。
- 停止驱动后直接读 `/dev/ttyACM0`，无原始字节。
- 轮询 `115200 / 230400 / 256000 / 460800`，均无字节。
- 用 pyserial 切换 DTR/RTS 后仍 `n=0`。
- 做过一次 USB 重新枚举，串口恢复，但仍无字节。

当前判断：

```text
问题不在 ROS 订阅层，优先怀疑雷达本体供电、雷达数据线、固定后插头受力、线束被压、雷达未真正上电输出。
```

必须先恢复 N10 原始数据，再继续 SLAM / Nav2。

## 6. 立即执行步骤

### Step 0：安全准备

在任何电机上电前：

- 小车放在稳定支架上，四轮悬空。
- 电机动力电源开关可随时断开。
- RDK、STM32、TB6612、电机电源负极必须共地。
- 不要在轮子落地时第一次运行电机测试。
- 不要直接发高速 `cmd_vel`。

### Step 1：恢复 N10 原始串口数据

人工检查：

1. 看 N10 是否有指示灯、旋转声或轻微工作声。
2. 检查固定后雷达端插头是否半插、被拉歪、被铜柱或扎带顶住。
3. 检查 USB 线是否松动。
4. 检查雷达供电线是否松动或压线。
5. 给雷达断电再上电，或拔插雷达到 RDK 的 USB。

RDK 上验证串口是否有原始数据：

```bash
stty -F /dev/ttyACM0 230400 raw -echo -crtscts
timeout 3 dd if=/dev/ttyACM0 bs=1 count=128 2>/tmp/n10_dd.err | od -An -tx1 -v
cat /tmp/n10_dd.err
```

期望看到类似：

```text
a5 5a ...
```

如果仍无任何字节：

- 不要继续 ROS 调试。
- 优先检查硬件连接、电源、雷达端口和线束应力。

### Step 2：重启 N10 ROS 2 驱动

只有在 Step 1 看到原始串口数据后，才重启驱动：

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
setsid ros2 run lslidar_driver lslidar_driver_node --ros-args \
  --params-file /root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml \
  >/tmp/n10_driver.log 2>&1 </dev/null &
```

验证：

```bash
source /opt/ros/humble/setup.bash
ros2 topic list
timeout 8 ros2 topic hz /scan
timeout 5 ros2 topic echo /scan --once
```

通过标准：

```text
/scan 存在
ros2 topic hz /scan 约 10 Hz
echo --once 能看到 sensor_msgs/msg/LaserScan
```

### Step 3：固定后重新做扫描图检查

抓固定后静态快照：

```bash
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
python3 /tmp/n10_grab_snapshot.py /tmp/n10_scan_fixed
```

判断标准：

- `near_lt_0_30m_count` 越少越好。
- 若大量点小于 `0.15 m` 或 `0.30 m`，说明扫描平面被车体、铜柱、线束或桌面遮挡。
- 单个铜柱如果非常靠近雷达且进入扫描平面，会形成固定方向的近距离点和局部盲区。
- 雷达四周应尽量无遮挡，至少让主要前方、左右两侧不要被支撑结构挡住。

建议：

- 雷达安装高度略高于车体上表面。
- 不要让铜柱、线束、外壳边缘穿过雷达扫描平面。
- 如果必须有支撑柱，尽量放在不影响导航的后方或远离雷达的位置。

### Step 4：重新确认前、左、右、后方向

每次固定位置变化后都要重新确认方向。

正前方：

```text
把纸板/书本放在车头正前方 40-80 cm。
期望目标点出现在 340-20 deg，靠近红色 front 0 deg。
```

左侧：

```text
把目标放在左侧 40-80 cm。
期望目标点出现在 70-110 deg，靠近蓝色 left 90 deg。
```

右侧：

```text
把目标放在右侧 40-80 cm。
期望目标点出现在 250-290 deg，靠近绿色 right 270 deg。
```

后方：

```text
把目标放在后方 40-80 cm。
期望目标点出现在 160-200 deg，靠近 back 180 deg。
```

如果方向反了：

- 优先检查雷达物理安装朝向。
- 其次再考虑 ROS frame 或 TF 修正。
- 不建议在方向未确认时开始 SLAM。

### Step 5：接入 STM32 到 RDK

当前建议：

```text
可以先接 STM32 到 RDK。
电机动力电源暂时不要上，或四轮必须悬空。
```

如果走 USB：

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
dmesg | tail -n 80
udevadm info -q property -n /dev/ttyACM1 2>/dev/null | grep -E "ID_MODEL|ID_VENDOR|ID_SERIAL"
```

如果走 40Pin UART：

```text
使用 /dev/ttyS1
参数 115200 8N1
TX/RX 交叉
RDK、STM32、驱动、电机电源共地
```

先做通信测试：

- RDK 打开串口。
- 发送 `HEARTBEAT`。
- 发送 `SET_MODE`。
- 发送小幅 `CMD_VEL`。
- 观察 STM32 是否回 `ACK` / `STATUS`。

不要在没有 ACK/STATUS 的情况下给电机落地测试。

### Step 6：电机低风险上电测试

前提：

- 雷达 `/scan` 已恢复。
- STM32 通信已确认。
- 四轮悬空。
- 电机电源可快速断开。
- RDK 到 STM32 的停止命令可用。

测试顺序：

1. 只上 STM32 和 RDK，不上电机动力电源。
2. 确认 UART 通信和状态回传。
3. 上电机动力电源，但四轮悬空。
4. 单轮低 PWM 测试。
5. 四轮单独确认方向。
6. 测试整车运动学：
   - 前进。
   - 后退。
   - 左平移。
   - 右平移。
   - 原地左转。
   - 原地右转。
7. 最后才低速落地测试。

落地测试速度建议从很小值开始：

```text
linear.x: 0.03-0.05 m/s
linear.y: 0.03-0.05 m/s
angular.z: 0.10-0.20 rad/s
```

## 7. IMU 的作用与接入时机

IMU 当前没用到是正常的，因为当前阶段是雷达静态接入和底盘基础通信。

IMU 后续作用：

- 提供角速度，尤其是 yaw 转动速度。
- 提供 pitch/roll，用于判断车体和雷达是否倾斜。
- 与轮速编码器融合，形成更稳定的 `/odom`。
- 在麦克纳姆轮打滑时提供短时运动参考。
- 支持异常运动检测，例如碰撞、卡住、打滑。

接入时机：

```text
雷达 /scan 稳定
-> STM32 通信稳定
-> 电机可控
-> 编码器接入
-> IMU 接入
-> 轮速 + IMU 融合 /odom
-> SLAM / Nav2
```

## 8. 编码电机 A/B 相的作用与当前限制

当前编码电机的 A/B 相如果没有接出，就暂时只能当普通直流减速电机用。

A/B 相接出后的作用：

- 测每个轮子的转速。
- 做四轮闭环速度控制。
- 估计底盘运动里程计。
- 配合 IMU 融合生成 `/odom`。
- 让 Nav2 知道实际运动和命令之间的差异。

不接 A/B 相的后果：

- 只能开环 PWM 控制。
- 麦克纳姆轮容易因摩擦差异跑偏。
- 横移和原地旋转精度较差。
- 不能得到可信轮速里程计。
- 后续自主导航可靠性会明显下降。

建议：

- 短期可以先不接 A/B 相，用于电机方向和运动学验证。
- 正式进入导航前，尽量四个电机的 A/B 相全部接到 STM32 定时器编码器输入。
- 编码器电源电压必须按电机规格确认，常见为 3.3V 或 5V。
- 编码器 GND 必须与 STM32 GND 共地。

## 9. RViz 与可视化说明

当前 RDK SSH 环境没有 `DISPLAY`，因此不能直接在 SSH 中打开 RViz 窗口。

可选方案：

1. 继续使用 `/scan` 快照 SVG 图做检查。
2. 在本机或另一台有显示的 ROS 2 电脑上通过 ROS_DOMAIN_ID/网络发现订阅 RDK `/scan`。
3. 给 RDK 外接显示器和桌面环境后再运行 `rviz2`。

当前阶段推荐继续使用快照图，因为它足够完成方向和遮挡检查。

## 10. 风险与注意事项

### 10.1 电机安全

- 不要让四轮落地时第一次上电。
- 不要一次性给四个电机大 PWM。
- 不要在 STM32 通信未确认时上动力电。
- 必须准备物理断电手段。

### 10.2 雷达安装

- N10 扫描平面不能被铜柱、线束、外壳边缘挡住。
- 雷达最好高于车体上表面。
- 固定后必须重新做方向和遮挡检查。
- 如果 `/dev/ttyACM0` 存在但无原始字节，优先看雷达供电和插头受力。

### 10.3 接地

以下必须共地：

```text
RDK GND
STM32 GND
TB6612 GND
电机电源负极
编码器 GND
IMU GND
```

否则 UART、电机控制和编码器读数都可能异常。

### 10.4 不要误判 `/scan`

`ros2 topic list` 看到 `/scan` 不代表有数据。

必须同时验证：

```bash
ros2 topic hz /scan
ros2 topic echo /scan --once
```

如果 topic 有发布者但 echo 没消息，要回到串口原始字节检查。

## 11. 后续里程碑

### M1：恢复固定后 N10 数据

通过标准：

- `/dev/ttyACM0` 能读到原始字节。
- 230400 下出现 N10 帧数据。
- `/scan` 恢复约 10 Hz。
- 固定后快照图生成成功。

### M2：固定后方向与遮挡合格

通过标准：

- 前、左、右、后方向均符合 ROS 坐标。
- 主要导航方向无大面积近距离遮挡。
- `0.30 m` 内点数量明显少于未固定时。

### M3：STM32 通信恢复

通过标准：

- RDK 能识别 STM32 串口。
- RDK 能收到 STM32 `ACK` / `STATUS`。
- 心跳超时、STOP、IDLE 安全逻辑可验证。

### M4：电机悬空测试

通过标准：

- 四个轮子能独立低速转动。
- 四轮方向与 `LF/RF/LR/RR` 定义一致。
- 前进、后退、横移、旋转的轮向组合正确。
- STOP 能立即停轮。

### M5：低速落地测试

通过标准：

- 小车能低速前进、后退、横移、旋转。
- 无突然冲车。
- 通信中断后能停车。
- 电源没有掉压重启。

### M6：编码器与 IMU

通过标准：

- 四轮编码器 A/B 相接入 STM32。
- 每轮转速方向正确。
- IMU 发布角速度/姿态。
- 轮速 + IMU 形成 `/odom`。

### M7：SLAM / Nav2

通过标准：

- `/scan`、`/odom`、`tf` 齐全。
- RViz 中 LaserScan、TF、Odometry 显示正常。
- 可进行低速建图。
- 可执行简单导航目标。

## 12. 当前下一步建议

最优先：

```text
恢复 N10 固定后的原始串口数据。
```

不要跳过这个问题直接给电机落地跑。N10 是后续 SLAM / 避障 / Nav2 的基础，当前已经证明 ROS 层不是主因，下一步应检查雷达本体供电和固定后的线束受力。

在 N10 恢复前，可以并行但保持安全地做：

```text
STM32 接入 RDK，仅验证串口识别和 ACK/STATUS。
电机动力电源暂不上，或四轮悬空。
```

不建议现在做：

```text
四轮落地直接上动力电。
未确认 STOP 和通信状态前发运动命令。
未恢复 /scan 前开始 SLAM 或导航。
```
