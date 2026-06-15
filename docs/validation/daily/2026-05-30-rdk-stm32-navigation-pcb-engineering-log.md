# 2026-05-30 RDK-STM32 底盘接线、PCB 与自主导航工程日志

整理时间：2026-05-30

记录范围：本日志整理本段对话中围绕 RDK X5 控制 STM32 麦克纳姆底盘、电机驱动接线与 PCB 转接板、实车 UART 调试、左轮方向修正，以及后续“不贴线、不贴标识”的自主路线行驶方案、算力评估和硬件采购建议。本文不是逐字聊天记录，而是工程日志版归档。

## 当前系统状态

- RDK X5 已通过 40Pin UART 与 STM32F411CEU6 通信。
- RDK 侧实测有效串口为：

```text
/dev/ttyS1
```

- STM32 工程为：

```text
stm32/firmware/stm32_motion_controller
```

- STM32 已接收 RDK 的 UART 协议帧，并能返回 `ACK`、`STATUS`。
- STM32 已接入四轮麦克纳姆控制逻辑。
- 两块 TB6612 双路电机驱动板用于控制四个麦克纳姆轮。
- 当前实车已经能够由 RDK 通过 UART 下发速度命令并驱动小车移动。
- 实测发现左侧两个轮子的旋转方向与预期相反，已通过固件修正。

## UART 与底盘控制链路

当前控制链路为：

```text
RDK X5
  -> /dev/ttyS1
  -> UART 115200 8N1
  -> STM32 USART1
  -> rdk_stm32_uart 协议解析
  -> mecanum_drive 麦轮运动学
  -> TIM3 PWM + GPIO IN1/IN2
  -> 两块 TB6612
  -> 四个电机
```

RDK 到 STM32 的 UART 接线：

| 功能 | RDK X5 40Pin | STM32F411CEU6 | 说明 |
| --- | --- | --- | --- |
| RDK TX | Pin 8 / UART1_TX | PA10 / USART1_RX | RDK 发 `CMD_VEL`、`SET_MODE`、`STOP` |
| RDK RX | Pin 10 / UART1_RX | PA9 / USART1_TX | STM32 回 `ACK`、`STATUS` |
| GND | 任一 GND | STM32 GND | RDK、STM32、电机驱动、电机电源负极必须共地 |

UART 参数保持为：

```text
115200 8N1
3.3V TTL
```

## TB6612 驱动板丝印确认

根据实物图片，驱动板控制排针包含：

```text
1B
1A
2B
2A
G
1IN1
1IN2
1P
G
2IN1
2IN2
2P
G
```

工程判断：

- `1IN1`、`1IN2`、`1P` 用于电机 1 控制。
- `2IN1`、`2IN2`、`2P` 用于电机 2 控制。
- `1P`、`2P` 是 PWM 输入。
- `1IN1/1IN2`、`2IN1/2IN2` 是方向输入。
- `G` 是信号地，应与 STM32 GND、RDK GND、电机电源负极共地。
- `1A/1B`、`2A/2B` 不是当前开环驱动所需控制输入，应视为编码器 A/B 输出或编码器相关接口，后续闭环控制时再接入。
- 当前固件没有使用独立 `EN/STBY` 脚，不再占用 PB10/PB11。

驱动逻辑：

| 命令方向 | IN1 | IN2 | PWM | 说明 |
| --- | --- | --- | --- | --- |
| 正转 | 1 | 0 | `command->pwm` | `MECANUM_DIR_FORWARD` |
| 反转 | 0 | 1 | `command->pwm` | `MECANUM_DIR_REVERSE` |
| 停止 | 0 | 0 | 0 | 滑行停车 |

## 四轮电机与 STM32 引脚映射

当前代码中的四轮顺序保持为：

```text
LF, RF, LR, RR
```

轮位命名：

| 中文轮位 | 代码轮位 | 说明 |
| --- | --- | --- |
| 左上 | `MECANUM_WHEEL_LF` | 左前轮 |
| 右上 | `MECANUM_WHEEL_RF` | 右前轮 |
| 左下 | `MECANUM_WHEEL_LR` | 左后轮 |
| 右下 | `MECANUM_WHEEL_RR` | 右后轮 |

两块 TB6612 分组：

| 驱动板 | 通道 | 轮位 | 代码轮位 |
| --- | --- | --- | --- |
| TB6612-A | 电机1 | 左上 | `MECANUM_WHEEL_LF` |
| TB6612-A | 电机2 | 左下 | `MECANUM_WHEEL_LR` |
| TB6612-B | 电机1 | 右上 | `MECANUM_WHEEL_RF` |
| TB6612-B | 电机2 | 右下 | `MECANUM_WHEEL_RR` |

STM32 到 TB6612 的当前固件映射：

| 轮位 | PWM | TIM 通道 | IN1 | IN2 | TB6612 丝印 |
| --- | --- | --- | --- | --- | --- |
| 左上 LF | PA6 | TIM3_CH1 | PA0 | PA1 | `1P / 1IN1 / 1IN2` |
| 右上 RF | PB0 | TIM3_CH3 | PA4 | PA5 | `1P / 1IN1 / 1IN2` |
| 左下 LR | PA7 | TIM3_CH2 | PA2 | PA3 | `2P / 2IN1 / 2IN2` |
| 右下 RR | PB1 | TIM3_CH4 | PB8 | PB9 | `2P / 2IN1 / 2IN2` |

对应 `main.c` 当前硬件表：

```c
static AppMotorHw app_motor_hw[MECANUM_WHEEL_COUNT] = {
  [MECANUM_WHEEL_LF] = {&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_0, GPIOA, GPIO_PIN_1},
  [MECANUM_WHEEL_RF] = {&htim3, TIM_CHANNEL_3, GPIOA, GPIO_PIN_4, GPIOA, GPIO_PIN_5},
  [MECANUM_WHEEL_LR] = {&htim3, TIM_CHANNEL_2, GPIOA, GPIO_PIN_2, GPIOA, GPIO_PIN_3},
  [MECANUM_WHEEL_RR] = {&htim3, TIM_CHANNEL_4, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9},
};
```

## 左轮方向修正

实车测试后发现：

- 左上轮方向反了。
- 左下轮方向反了。
- 右侧两个轮子方向不需要同时反向。

处理方式：

- 不改接线。
- 不交换电机 `M+ / M-`。
- 在底盘配置中反向左侧两个轮子。

当前 `app_chassis_init()` 中已经加入：

```c
cfg.invert[MECANUM_WHEEL_LF] = -1;
cfg.invert[MECANUM_WHEEL_LR] = -1;
```

新增回归测试：

```text
tests/test_stm32_main_uart_integration.py
```

测试检查 `main.c` 中必须保留：

```c
cfg.invert[MECANUM_WHEEL_LF] = -1;
cfg.invert[MECANUM_WHEEL_LR] = -1;
```

已执行验证：

```bash
python3 -m unittest discover -s tests
```

结果：

```text
Ran 12 tests
OK
```

STM32CubeIDE headless build 结果：

```text
Build Finished. 0 errors, 0 warnings.
```

固件通过 STM32CubeProgrammer 刷入并校验：

```text
Download verified successfully
```

## 实车 UART 调试记录

早期现象：

- RDK 能打开 `/dev/ttyS1`。
- RDK 能持续发送 `SET_MODE`、`HEARTBEAT`、`CMD_VEL`。
- 初期没有收到 ACK。
- 后续确认 STM32 供电、刷入当前固件并重新接线后，RDK 能收到 `ACK` 和 `STATUS`。

曾出现状态：

```text
RX STATUS mode=IDLE estop=0 fault=0x0002 battery=12000mV last_cmd_seq=0 comm=HEARTBEAT_TIMEOUT
```

解释：

- 该状态说明 STM32 已经在回传 `STATUS`。
- `fault=0x0002` 对应心跳超时，不是 UART 收不到。
- 后续使用带心跳的 `uart_send_test.py` 命令可以进入 `MANUAL` 并收到 `ACK CMD_VEL`。

可用测试命令示例：

```bash
cd /root/Soc_China && python3 rdk_x5/scripts/uart_send_test.py \
  --port /dev/ttyS1 --baud 115200 \
  --duration 1 --mode manual \
  --vx -150 --vy 0 --wz 0 \
  --cmd-hz 10 --heartbeat-hz 2 \
  --log-root /root/Soc_China/logs
```

注意：

- 该命令会让车移动，测试时应先架空底盘。
- 若整体前后方向与预期相反，优先判断是 `vx` 正负约定问题。
- 若出现原地旋转或掉头，优先检查左右轮方向、轮位映射和麦轮安装方向。

## PCB 转接板规划

用户计划画 PCB 的目标：

- 不是重新做 STM32 核心板。
- 不是把 STM32F411 芯片本体画入 PCB。
- 而是插接现有 WeAct STM32F4x1Cx v2.0+ 开发板。
- PCB 作为转接板，使 RDK、STM32、两块 TB6612 和四个电机的线束更整洁，减少外部线缆交叉。

已生成 PCB 布局示意图：

```text
docs/hardware/stm32_tb6612_adapter_layout.svg
```

布局原则：

- STM32 开发板插在 PCB 中间，USB-C 朝上，方便烧录和调试。
- TB6612-A 放在 PCB 左侧，控制左上、左下轮。
- TB6612-B 放在 PCB 右侧，控制右上、右下轮。
- 四个电机接口放在 PCB 四角，便于电机线直接出板。
- RDK UART 接口放在靠近 STM32 PA9/PA10 的区域。
- 电机电源入口放在底部中间，再分配到两块 TB6612。
- STM32 到左侧 TB6612 的部分控制线可通过双层 PCB 内部过孔走线处理。

PCB 设计建议：

- 建议使用双层板。
- 底层尽量铺完整 GND。
- RDK UART TX/RX 可串 33Ω-100Ω 电阻。
- 每根 PWM/IN 控制线建议预留 10k 下拉，保证 STM32 复位时电机不乱动。
- PWM、IN、UART 均预留测试点。
- 保留 STM32 SWD：3V3、DIO、SCLK、GND。
- 电机电源入口建议加保险丝、反接保护、TVS 和大电解电容。

## 自主路线行驶需求

用户提出下一阶段需求：

- 小车能够按照预设路线行驶。
- 不在地上贴线。
- 不在地上贴标识。
- 不做普通循迹。

工程判断：

- 不能只靠“固定 PWM + 固定时间”实现可靠路线行驶。
- 开环路线会受到电池电压、地面摩擦、电机差异、麦轮打滑和累计误差影响。
- 需要让小车实时知道自己在地图中的位置，并能根据误差修正运动。

推荐方案：

```text
提前建图
+ RDK X5 加载静态地图
+ 2D 激光雷达定位
+ 编码器里程计
+ IMU 辅助 yaw
+ ROS2 Nav2 航点巡航
+ STM32 底盘闭环控制
```

推荐系统分工：

```text
RDK X5：
  2D 雷达数据接收
  地图加载
  AMCL / 定位
  Nav2 路径规划
  局部避障
  航点任务
  视觉检测与告警
  UART bridge

STM32：
  接收 vx/vy/wz
  麦克纳姆运动学
  四轮速度闭环
  编码器计数
  急停与超时停车
  回传状态/里程计
```

## 关于“提前建图”的结论

可以提前建图，然后把地图交给 RDK X5。

需要区分：

| 名称 | 说明 | 是否必须实时运行 |
| --- | --- | --- |
| 建图 Mapping | 扫描房间生成地图 | 可以提前离线完成 |
| 定位 Localization | 小车运行时知道自己在地图哪里 | 必须实时运行 |
| 导航 Navigation | 规划路径、避障、输出速度 | 必须实时运行 |

推荐流程：

1. 建图阶段：
   - 手动遥控小车扫完整环境。
   - 使用 2D 雷达、编码器里程计、IMU。
   - 可以在 RDK 上跑 SLAM，也可以让 PC 远程跑 SLAM。
   - 保存地图文件。
2. 巡航阶段：
   - RDK 不再持续建图。
   - RDK 加载静态地图。
   - 运行 AMCL/Nav2。
   - 按预设航点巡航。

地图文件通常包括：

```text
lab_map.yaml
lab_map.pgm
```

或者使用 slam_toolbox 的序列化地图格式。

对队友疑问的解释：

- 激光雷达导航不是强化学习。
- 不需要训练自动驾驶模型。
- 建图是扫描环境生成地图，不是训练神经网络。
- 真正难点是：
  - 编码器里程计是否稳定。
  - TF 坐标是否正确。
  - 雷达安装是否稳固。
  - 底盘速度闭环是否可靠。
  - Nav2 参数是否调通。

## 建议分阶段验收

### 第 1 阶段：遥控与里程计

目标：

- STM32 回传轮速/里程计。
- RDK 能发布 `/odom`。
- RViz 中能看到底盘移动趋势。

验收：

- 前进、后退、横移、原地旋转时，`/odom` 方向大致正确。
- 停车时 odom 不应继续明显漂移。

### 第 2 阶段：离线建图

目标：

- 用雷达和里程计手动扫房间。
- 保存地图。

验收：

- 地图中墙体、桌椅、固定障碍物形状合理。
- 回环后地图不明显重影。

### 第 3 阶段：静态地图定位

目标：

- RDK 加载已有地图。
- 小车在地图中完成定位。

验收：

- RViz 中 `map -> odom -> base_link -> laser` 坐标关系正确。
- 手动推动小车，定位能跟随变化。
- 小范围移动后不会快速丢定位。

### 第 4 阶段：Nav2 航点巡航

目标：

- 在地图中设置预设点。
- 小车按顺序行驶。

验收：

- 能从起点到达指定航点。
- 能避开局部障碍。
- 到达后能停车。
- 航点序列可重复运行。

## RDK X5 算力评估

用户担心：

- RDK X5 上还要运行固定摄像头接入、视觉检测、云台控制和其他任务。
- 如果再加入 2D 建图/导航，算力是否不足。

工程判断：

- 2D 雷达定位和 Nav2 本身算力压力不算高。
- 持续在线 SLAM 比静态地图定位更重。
- 真正容易吃满 RDK 的是：
  - RTSP/OpenCV 视频解码。
  - 高分辨率 raw image ROS2 发布。
  - AI 视觉模型推理。
  - Websocket 实时预览。
  - 大模型或多模态任务常驻。

推荐运行模式：

```text
建图/调试模式：
  2D 雷达 + 编码器 + IMU + SLAM
  视觉关闭或降频

巡航/演示模式：
  静态地图 + AMCL + Nav2
  视觉检测低频或事件触发
  关闭不必要 Web 预览
```

建议控制视觉负载：

- 摄像头优先 720p。
- 固定摄像头默认 10-15 FPS。
- 检测模型输入可降到 640x480。
- AI 推理尽量走 RDK BPU，不要用 CPU 跑重模型。
- Web 预览只在调试时开启。

RDK 上建议压测命令：

```bash
htop
free -h
sudo hrut_somstatus
ros2 topic hz /fixed_camera/image_raw
ros2 topic bw /fixed_camera/image_raw
```

BPU 使用率可尝试：

```bash
hrut_bpuprofile -b 0
```

或：

```bash
cat /sys/devices/system/bpu/bpu0/ratio
```

温度检查可尝试：

```bash
cat /sys/class/hwmon/hwmon0/temp1_input
cat /sys/class/hwmon/hwmon0/temp2_input
cat /sys/class/hwmon/hwmon0/temp3_input
```

结论：

- 如果采用静态地图定位，而不是持续在线建图，RDK X5 大概率够用。
- 如果同时运行高分辨率多路视觉、CPU 推理、在线 SLAM 和 Web 预览，则存在资源不足和温度降频风险。

## 推荐采购模块

为完成“不贴线、不贴标识”的预设路线巡航，推荐购买：

| 模块 | 必要性 | 用途 |
| --- | --- | --- |
| 2D 激光雷达 | 必须 | 建图、定位、避障 |
| 带 AB 相编码器的四个电机，或给现有电机加编码器 | 必须 | 轮速闭环、里程计 |
| IMU 模块 | 强烈建议 | 辅助 yaw、改善转向稳定性 |
| 稳定 5V 大电流降压模块 | 必须 | 给 RDK X5 供电 |
| 电机电源/电池 | 必须 | 给两块 TB6612 和电机供电 |
| 急停开关 | 必须 | 实车安全 |
| USB-TTL 串口模块 | 强烈建议 | 调试 RDK/STM32 串口 |
| 逻辑分析仪 | 强烈建议 | 查看 UART、PWM、编码器 A/B 相 |

2D 雷达建议方向：

| 类型 | 说明 |
| --- | --- |
| RPLIDAR A1/A2 | 入门友好，资料多 |
| LDROBOT LD06/LD19 | 小车常用，体积小 |
| YDLIDAR X2/X4/G4 | 便宜，资料较多 |

建议优先：

```text
RPLIDAR A1/A2 或 LD19
```

IMU 建议方向：

| 型号方向 | 说明 |
| --- | --- |
| JY901/JY61 | 模块化，调试方便 |
| BNO055 | 内置姿态融合，上手简单 |
| ICM-20948 | 常见，资料多，但融合工作更多 |
| MPU6050/MPU9250 | 便宜，但漂移和调试成本较高 |

当前更推荐：

```text
JY901/JY61 或 BNO055
```

## 不建议采用的路线

当前阶段不建议：

- 直接做强化学习自动驾驶。
- 直接做视觉 SLAM 作为主导航。
- 依赖纯摄像头完成定位和避障。
- 用固定时间/PWM 的开环路线控制。
- 在 RDK 上长期同时跑在线 SLAM、高分辨率视觉、CPU 推理和 Web 预览。

原因：

- 工期和调试成本不可控。
- 对算力、数据集、算法经验要求更高。
- 室内巡航任务使用 2D 雷达 + 静态地图 + AMCL/Nav2 更成熟可靠。

## 后续工程计划

建议下一步按以下顺序推进：

1. 确认并采购 2D 雷达、编码器电机或编码器模块、IMU、电源与调试工具。
2. 完成编码器接入 STM32。
3. STM32 实现四轮速度闭环。
4. 扩展 UART 协议，回传轮速或里程计。
5. RDK 新增 `stm32_bridge` ROS2 节点：
   - 订阅 `/cmd_vel`
   - 通过 UART 发送 `CMD_VEL`
   - 接收 STM32 状态/里程计
   - 发布 `/odom`
6. 接入 2D 雷达，发布 `/scan`。
7. 配置 TF：
   - `map`
   - `odom`
   - `base_link`
   - `laser`
8. 手动遥控建图并保存地图。
9. 使用静态地图 + AMCL 验证定位。
10. 接 Nav2，先点到点导航，再做 waypoint follower。
11. 最后把视觉检测、云台和告警任务按低频或事件触发方式合入。

## 重要文件索引

当前对话涉及或生成的重要文件：

- `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
- `stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h`
- `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c`
- `tests/test_stm32_main_uart_integration.py`
- `stm32/docs/tb6612_motor_control_integration.md`
- `docs/hardware/stm32_tb6612_adapter_layout.svg`
- `docs/architecture/camera_ingest.md`
- `rdk_x5/ros2_ws/src/perception_camera/README.md`
- `docs/architecture/gimbal_control_flow.md`
- `docs/protocols/rdk_stm32_uart.md`

## 当前结论

当前底盘控制链路已经从“UART 能通信”推进到“RDK 可通过 STM32 驱动四轮电机移动”。下一阶段不应继续停留在开环速度测试，而应补齐编码器、IMU、2D 雷达和 ROS2 导航链路。

推荐最终方向：

```text
STM32：底盘实时闭环与安全
RDK X5：静态地图定位、Nav2 航点巡航、视觉检测和任务调度
2D 雷达：地图/定位/避障
编码器 + IMU：里程计与姿态约束
```

该路线不需要地面贴线，不需要贴二维码或标识，也不需要强化学习训练；它是更适合当前项目工期和硬件条件的传统移动机器人导航方案。
