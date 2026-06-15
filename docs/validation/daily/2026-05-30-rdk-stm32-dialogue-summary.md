# 2026-05-30 RDK-STM32 项目对话摘要

整理时间：2026-05-30

说明：本文是本段长对话的尽量完整摘要版，不是逐字转录。内容按对话推进顺序整理，保留问题背景、关键操作、结论、命令、文件和后续决策，便于新开对话或交接给队友继续推进。

## 1. 起始目标：合并 RDK X5 UART 与 STM32 麦轮控制

用户最初说明：

- 在 `/Users/sthefirst/Desktop/Soc_China/stm32/firmware` 目录下已有一个 RDK X5 与 STM32 UART 通信工程。
- 也已有部分 STM32 控制四轮麦克纳姆底盘的工程。
- 四个麦克纳姆轮由两个双路电机模块控制。
- 目标是在不破坏原有功能的前提下，将 UART 协议部分与控制部分合并，最终实现 RDK X5 控制 STM32 操控电机。

随后用户要求：

- 先按“方案一”写出简要 Markdown 流程设计方案。
- 阅读并执行：

```text
/Users/sthefirst/Desktop/Soc_China/docs/superpowers/specs/2026-05-12-rdk-stm32-mecanum-uart-integration-design.md
```

执行结果摘要：

- 采用先合并 UART 到麦轮控制软件链路、暂不绑定最终 PWM/DIR 硬件的策略。
- 新增或完善麦轮控制模块与测试。
- 将 RDK 的 `CMD_VEL` 链接到 STM32 的 `mecanum_drive` 控制逻辑。
- 在 `STOP`、`IDLE`、心跳超时、命令超时等情况下执行停车。
- 后续将该方案合并到本地 `main` 分支。

## 2. STM32 工程构建失败排查

用户反馈 STM32 项目 build 失败，截图中出现大量：

```text
multiple definition
collect2: error: ld returned 1 exit status
Build Failed. 240 errors
```

排查结论：

- STM32CubeIDE managed build 把项目目录里的重复副本也作为源码编译。
- 工程目录中存在大量 `xxx 2.c`、`xxx 2.h`、`xxx 2.s` 等未跟踪副本。
- 这些副本和原文件同时参与链接，导致 `multiple definition`。

处理方式：

- 将重复副本移出 STM32 工程树并备份到 `.tmp`。
- 清理旧 `Debug` 构建目录。
- 使用 STM32CubeIDE headless build 重建。

验证结果：

```text
Build Finished. 0 errors, 0 warnings.
```

## 3. 当前 main 函数文件确认

用户询问：

```text
现在 main 主函数 main 是 main.c 还是 main 2.c
```

结论：

- 有效主函数是：

```text
stm32/firmware/stm32_motion_controller/Core/Src/main.c
```

- `main 2.c` 是重复副本，不应参与编译。
- 后续所有 STM32 主程序修改均应基于 `main.c`。

## 4. 无电机、仅两块开发板时的测试方案

用户询问在没有电机和电机驱动、仅有 RDK X5 与 STM32 两块开发板的情况下如何测试。

建议的测试层级：

1. UART 物理链路测试：
   - RDK 能否打开串口。
   - STM32 是否能收到数据。
   - TX/RX 是否交叉接线。
   - 是否共地。

2. 协议层测试：
   - RDK 发送 `HEARTBEAT`、`SET_MODE`、`CMD_VEL`。
   - STM32 回 `ACK`、`STATUS`。
   - 检查 CRC、长度、版本错误计数。

3. 控制链路测试：
   - 不接电机，只看 STM32 是否根据命令更新四轮目标输出。
   - 通过代码测试或调试变量确认四轮方向/PWM 变化。

4. 安全逻辑测试：
   - 停止发送命令后，STM32 是否超时停车。
   - 进入 `IDLE` 或 `STOP` 后，四轮输出是否归零。

## 5. RDK 串口设备确认

用户在 RDK 上执行：

```bash
ls -l /dev/ttyUSB* /dev/ttyS* 2>/dev/null
```

截图显示存在多个：

```text
/dev/ttyS0
/dev/ttyS1
/dev/ttyS2
...
/dev/ttyS7
```

用户说明使用 40Pin 直连，希望帮助测试哪个串口是 STM32。

排查过程：

- 结合 RDK X5 40Pin UART 文档与实际测试。
- 多次测试串口打开、发送、读取。
- 确认 `/dev/ttyS1` 是当前有效串口。

最终结论：

```text
RDK 40Pin UART 与 STM32 通信使用 /dev/ttyS1
```

## 6. 生成 2026-05-11 UART 代码日志

用户要求根据本次对话内容生成类似：

```text
docs/validation/daily/2026-05-11-stm32-uart-code-log.md
```

的 Markdown 日志，并放入相同 daily 目录。

处理结果：

- 生成了 UART 代码修改日志。
- 内容包括：
  - 协议实现。
  - RDK 侧脚本。
  - STM32 侧协议模块。
  - 测试情况。
  - RDK `/dev/ttyS1` 实测现象。
  - 后续烧录与 ACK/STATUS 验证计划。

## 7. 当前代码是否能直接控制电机

用户询问：

```text
当前代码是否可以直接用 RDK X5 控制 STM32 驱动电机进行移动？
```

阶段性结论：

- 在尚未确认实际 TB6612 丝印、接线和 STM32 PWM/GPIO 引脚前，不能直接保证能驱动电机。
- 软件链路已经接近完成，但硬件输出层需要按真实驱动板修改。
- 后续需要：
  - 确认 TB6612 控制脚。
  - 确认 STM32 引脚映射。
  - 修改 `main.c` 的实际 TIM3 PWM 和 GPIO 输出。
  - 构建、刷机、实测。

## 8. 根据 RDK 官方文档与驱动模块图片给出接线方式

用户提供：

- RDK X5 官方文档链接：

```text
https://developer.d-robotics.cc/rdk_doc/Quick_start/display_use/display_rdkx5
```

- 电机驱动模块图片。
- RDK X5 已用接口截图。
- 要求不能重复使用已占用接口。
- 要求说明电机连线时使用左上、左下、右上、右下。
- 若有疑问必须指出，不自行决定。

初步接线方案：

- RDK 不直接控制 TB6612。
- RDK 只通过 UART 控制 STM32。
- STM32 负责 PWM 和方向 GPIO。
- 两块 TB6612 分别控制左侧和右侧：
  - TB6612-A：左上、左下。
  - TB6612-B：右上、右下。

RDK 到 STM32：

| RDK | STM32 |
| --- | --- |
| Pin 8 / UART1_TX | PA10 / USART1_RX |
| Pin 10 / UART1_RX | PA9 / USART1_TX |
| GND | GND |

避免使用 RDK 已占用引脚：

```text
Pin 1, 3, 5, 11, 13, 17, 24, 27, 28, 29, 31, 32, 33, 37
```

因此电机控制新增信号不从 RDK 40Pin 直接引出，而全部从 STM32 引出。

## 9. 编写电机控制工程文档

用户要求：

- 暂不考虑具体丝印问题。
- 按设想的 STM32 引脚使用情况和电机分组情况，给出一份继续完善电机控制的 Markdown 工程文档。

处理结果：

- 编写/完善：

```text
stm32/docs/tb6612_motor_control_integration.md
```

文档内容包括：

- 系统边界。
- RDK 只走 UART。
- STM32 PWM/GPIO 规划。
- 两块 TB6612 与四轮分组。
- 左上、左下、右上、右下轮位定义。
- TIM3 四路 PWM 建议。
- 初版控制逻辑。
- 测试步骤和安全注意事项。

## 10. 根据工程文档完善 UART 代码，使 RDK 控制 STM32 驱动电机

用户要求根据工程文档修改当前 UART 代码，使 RDK X5 能利用 STM32 驱动电机。

实施内容：

- 在 STM32 `main.c` 中接入实际硬件输出。
- 使用 TIM3 四路 PWM：
  - PA6 / TIM3_CH1
  - PA7 / TIM3_CH2
  - PB0 / TIM3_CH3
  - PB1 / TIM3_CH4
- 使用 GPIO 控制方向：
  - PA0、PA1
  - PA2、PA3
  - PA4、PA5
  - PB8、PB9
- 删除对 PB10/PB11 作为使能脚的依赖。
- 更新 `.ioc`，避免 PB10/PB11 继续作为电机使能输出。
- 更新测试，检查 TIM3、GPIO、HAL TIM 驱动和 `main.c` 集成。

构建结果：

```text
STM32CubeIDE headless build: 0 errors, 0 warnings
```

## 11. 根据驱动板实际丝印重新思考接线与代码

用户提供了驱动板丝印照片，指出有：

```text
1A
1B
1P
2A
2B
2P
1IN1
1IN2
2IN1
2IN2
G
```

重新判断：

- `1P`、`2P` 是 PWM 输入。
- `1IN1/1IN2`、`2IN1/2IN2` 是方向输入。
- `1A/1B`、`2A/2B` 更可能是编码器 A/B 输出，不应当作为电机控制输入。
- 控制电机不需要接 `1A/1B/2A/2B`。
- 后续闭环控制需要编码器时，再将它们接入 STM32。

代码是否需要修改：

- 当前代码已经采用 `1P/2P + IN1/IN2` 控制方式。
- 不需要因为 `1A/1B/2A/2B` 改控制代码。
- 但文档需要明确这些脚暂不接入控制。

## 12. 为什么暂时不接编码器

用户询问：

```text
为什么不需要接编码器
```

解释：

- 当前阶段目标是验证 RDK -> STM32 -> TB6612 -> 电机 的开环控制链路。
- 编码器用于闭环速度控制和里程计，不是让电机转起来的必要条件。
- 不接编码器时：
  - 可以遥控电机。
  - 可以验证方向和 PWM。
  - 但速度不准，长期行驶会漂。
- 后续做自主导航时必须接编码器。

结论：

- 当前开环调试可以不接编码器。
- 后续 Nav2/里程计/闭环速度控制阶段必须接入编码器。

## 13. 驱动板上多个 G 如何接

用户询问：

```text
驱动板上有三个 G，应当如何接
```

结论：

- 驱动板上多个 `G` 都应视为同一系统地。
- 它们应与：
  - STM32 GND
  - RDK GND
  - 电机电源负极
  - TB6612 信号地
  共地。

建议：

- PCB 上统一接到 `GND_SYS`。
- 信号排针附近的 `G` 必接。
- 编码器接口中的 `G` 后续使用编码器时也接。
- 电源入口负极也接同一地。

## 14. 接线完成后检查和修改代码

用户说明所有线已接好，要求按照接线检查或修改代码。

处理：

- 检查 `main.c` 中当前 STM32 引脚映射是否与实际接线一致。
- 检查 TB6612 文档与代码映射。
- 确认不使用 PB10/PB11 作为 EN。
- 确认四轮映射为：

```text
LF: PA6 PWM, PA0 IN1, PA1 IN2
LR: PA7 PWM, PA2 IN1, PA3 IN2
RF: PB0 PWM, PA4 IN1, PA5 IN2
RR: PB1 PWM, PB8 IN1, PB9 IN2
```

- 构建并刷入 STM32。

## 15. RDK 与 STM32 实机联调

用户提供：

```text
RDK IP: 192.168.128.10
user: root
password: root
```

目标：

- 通过 SSH 登录 RDK。
- 运行 UART 测试脚本。
- 验证 RDK 与 STM32 通信和控制。

期间出现问题：

- 刚开始 STM32 忘记接电。
- 后续重新接电。
- 早期测试没有 ACK。
- `STATUS` 中有 `HEARTBEAT_TIMEOUT`。
- 通过重新刷入当前固件与检查接线后，RDK 可收到 ACK/STATUS。

示例命令：

```bash
cd /root/Soc_China && python3 rdk_x5/scripts/uart_protocol_test.py \
  --port /dev/ttyS1 --baud 115200 --duration 3
```

以及持续发送测试：

```bash
cd /root/Soc_China && python3 rdk_x5/scripts/uart_send_test.py \
  --port /dev/ttyS1 --baud 115200 \
  --duration 0.5 --mode manual \
  --vx -150 --vy 0 --wz 0 \
  --cmd-hz 10 --heartbeat-hz 1 \
  --log-root /root/Soc_China/logs
```

## 16. 串口短接与 ttyS 设备排查

用户曾进行 RDK 端串口短接测试。

现象：

- `/dev/ttyS1` 短接读取返回 `b''`。
- 部分 `/dev/ttyS2`、`ttyS3`、`ttyS4` 打开时报 I/O error。
- `/dev/ttyS5` 出现 write timeout。

判断：

- 不同 `/dev/ttyS*` 对应的硬件 UART 并非都可用或已配置。
- 当前项目实际使用仍以 `/dev/ttyS1` 为准。
- UART 能收到 STM32 `STATUS` 后，说明 RDK 到 STM32 的线路与设备名已基本确认。

## 17. 实车移动测试

用户要求：

- 让小车前进一点距离。
- 给出左上轮顺时针转动 1 秒的命令。
- 让小车后退一点。

过程中曾出现：

- 远程 expect 命令写法被 shell 解析问题卡住。
- 后续改为给用户可直接执行的命令。
- 用户执行后小车最初不动。
- 后续刷入正确固件并重新测试后，小车可以动。

用户反馈：

```text
好的现在动了，但是刚才的操作似乎是使他掉头
```

随后经过测试确定：

```text
两个左轮的旋转方向都反了
```

## 18. 左轮反向修正实施

用户要求：

```text
经过测试发现，两个左轮的旋转方向都反了，帮助我修改代码以更正
```

实施过程：

1. 使用 TDD 思路先添加测试：

```text
tests/test_stm32_main_uart_integration.py
```

新增测试检查 `main.c` 中必须包含：

```c
cfg.invert[MECANUM_WHEEL_LF] = -1;
cfg.invert[MECANUM_WHEEL_LR] = -1;
```

2. 初始运行测试失败，符合预期。

3. 修改 `main.c` 的 `app_chassis_init()`：

```c
cfg.invert[MECANUM_WHEEL_LF] = -1;
cfg.invert[MECANUM_WHEEL_LR] = -1;
```

4. 重新运行测试通过。

5. 运行全量测试：

```bash
python3 -m unittest discover -s tests
```

结果：

```text
Ran 12 tests
OK
```

6. STM32CubeIDE headless build：

```text
Build Finished. 0 errors, 0 warnings.
```

7. 刷入 STM32：

```text
Download verified successfully
```

期间曾出现 ST-Link 短暂断联：

```text
ST-LINK error (DEV_USB_COMM_ERR)
```

用户修复连接后，重新使用低速 SWD、under reset 成功刷机。

## 19. PCB 转接板需求

用户提出：

- 需要详细接线图，用于画 PCB。
- 后续说明是插接现有 STM32 开发板，不是画 STM32 裸芯片。
- PCB 目标是让接线更美观，尽量减少线缆交叉。
- 用户提供 WeAct STM32F4x1Cx v2.0+ 引脚图。
- 希望生成一张插接 STM32 的 PCB 示意图，便于直观确认。

接线规划：

- STM32 插在 PCB 中间。
- USB-C 朝上，方便烧录与调试。
- 左侧放 TB6612-A，控制左上、左下。
- 右侧放 TB6612-B，控制右上、右下。
- 四个电机接口放在 PCB 四角。
- RDK UART 接口放靠近 STM32 PA9/PA10 的区域。
- 电机电源入口放底部中间。

生成文件：

```text
docs/hardware/stm32_tb6612_adapter_layout.svg
```

该图为 SVG 示意图，不是 Gerber。

## 20. 后续自主路线行驶方案讨论

用户提出新目标：

- 小车能够按照预设路线行驶。
- 不在地上贴标识。
- 不做普通循迹。

建议方案：

```text
2D 激光雷达
+ 编码器里程计
+ IMU
+ ROS2 Nav2
+ 静态地图定位
+ STM32 底盘闭环
```

解释：

- 不建议用固定时间和固定 PWM 开环行驶。
- 麦克纳姆轮容易打滑，开环累计误差很大。
- 小车需要知道自己在地图中的位置。

系统分工：

```text
RDK X5：
  2D 雷达数据接收
  SLAM/地图加载
  定位
  路径规划
  避障
  预设航点执行
  视觉检测与任务逻辑

STM32：
  接收速度指令
  四轮麦轮解算
  PWM/方向输出
  编码器读取
  轮速闭环
  回传状态/里程计
```

## 21. 2D 建图在 RDK 还是 STM32 上进行

用户询问：

```text
2D建图主要是在stm32上进行还是rdk上进行
```

结论：

- 2D 建图在 RDK X5 上进行。
- STM32F411 不适合跑 SLAM、Nav2、地图和路径规划。
- STM32 只做实时底盘控制。

推荐链路：

```text
2D LiDAR
  -> RDK X5 SLAM/Nav2
  -> UART cmd_vel
  -> STM32
  -> 电机

STM32
  -> 编码器/状态/里程计
  -> RDK X5
```

## 22. RDK 算力是否足够

用户担心：

- RDK 上同时会有视觉任务和其他任务。
- 目录下工程文档中已有固定摄像头、云台、视觉检测等规划。
- 如果再做 2D 导航，算力是否不足。

读取本地文档后确认已有模块：

- 固定摄像头接入：

```text
docs/architecture/camera_ingest.md
rdk_x5/ros2_ws/src/perception_camera/
```

- 云台控制：

```text
docs/architecture/gimbal_control_flow.md
rdk_x5/ros2_ws/src/gimbal_laser/
```

判断：

- 2D 雷达定位和 Nav2 本身不算特别重。
- 真正占资源的是：
  - 摄像头解码。
  - 高分辨率 ROS 图像发布。
  - AI 视觉推理。
  - Web 预览。
  - 在线 SLAM。
  - 大模型/多模态常驻。

建议：

- 建图阶段关闭或降低视觉任务。
- 巡航阶段使用静态地图 + AMCL，不持续在线建图。
- 视觉 720p、10-15 FPS。
- 推理走 BPU，不要用 CPU 跑重模型。
- Web 预览只调试时开。

压测建议：

```bash
htop
free -h
sudo hrut_somstatus
ros2 topic hz /fixed_camera/image_raw
ros2 topic bw /fixed_camera/image_raw
hrut_bpuprofile -b 0
```

## 23. 是否可以提前建图

用户询问：

- 能否提前建图，然后交给 RDK。
- 这样建图任务就不交给 RDK。
- 用户给出队友担忧截图：
  - “用激光雷达做得完吗”
  - “不太懂”
  - “感觉不好搞”
  - “要把房间扫描还要训练，这个要怎么训呢”
  - “自动驾驶技术吗，那要上强化学习吧”

解释结论：

- 可以提前建图。
- 但运行时仍然要在 RDK 上做实时定位和导航。
- 建图不是训练。
- 不需要强化学习。
- 不需要自动驾驶模型训练。

区分：

| 内容 | 含义 | 是否必须实时运行 |
| --- | --- | --- |
| 建图 Mapping | 扫描环境生成地图 | 可以提前完成 |
| 定位 Localization | 运行时知道小车在地图哪里 | 必须实时运行 |
| 导航 Navigation | 规划路径和避障 | 必须实时运行 |

推荐模式：

```text
建图阶段：
  手动遥控小车扫房间
  生成 lab_map.yaml + lab_map.pgm

巡航阶段：
  RDK 加载地图
  AMCL 定位
  Nav2 航点巡航
```

对队友的解释建议：

```text
激光雷达不是拿来训练自动驾驶模型的。
我们先手动扫一遍房间生成地图。
比赛/演示时 RDK 只加载地图做定位和路径规划。
真正实时跑的是 AMCL/Nav2，不是强化学习。
难点不在训练，而在编码器里程计、TF 坐标、雷达安装和 Nav2 参数调试。
```

## 24. 完成该方案需要购买哪些模块

用户询问如果按上述方案，需要购买哪些模块。

推荐必须购买：

| 模块 | 用途 |
| --- | --- |
| 2D 激光雷达 | 建图、定位、避障 |
| 四个带 AB 相编码器的电机，或给现有电机加编码器 | 轮速闭环、里程计 |
| IMU | yaw 角辅助、转向稳定 |
| 稳定电源模块 | RDK、STM32、电机分路供电 |
| 急停开关 | 实车安全 |
| USB-TTL | 串口调试 |
| 逻辑分析仪 | UART/PWM/编码器波形调试 |

2D 雷达建议：

- RPLIDAR A1/A2
- LDROBOT LD06/LD19
- YDLIDAR X2/X4/G4

更推荐：

```text
RPLIDAR A1/A2 或 LD19
```

IMU 建议：

- JY901/JY61
- BNO055
- ICM-20948
- MPU6050/MPU9250

更推荐：

```text
JY901/JY61 或 BNO055
```

整体推荐组合：

```text
RDK X5
+ STM32F411
+ 2D 雷达
+ 四个带 AB 编码器的减速电机
+ IMU
+ 5V 5A/8A 降压模块
+ 急停开关
+ 逻辑分析仪
```

## 25. 是否新开对话

用户询问：

```text
本段对话有点长，你建议是新开启一段对话还是继续在本对话继续，新开的话是否会节省一些token
```

建议：

- 如果继续做代码修改或基于当前仓库文件的任务，可以继续本对话。
- 如果讨论采购、导航方案、系统架构，建议新开对话。
- 新开对话会更省 token，也不容易被旧的 UART/接线调试上下文干扰。

建议新对话开场摘要：

```text
我在做一个 RDK X5 + STM32F411 + 四轮麦克纳姆小车项目。
当前状态：
1. RDK X5 已能通过 UART 控制 STM32。
2. STM32 已能控制四个 TB6612 电机驱动。
3. 小车已经能动，左轮方向已通过固件修正。
4. 现在想实现不贴线、不贴标识的预设路线巡航。
5. 计划采用：提前建图 + RDK 加载静态地图 + 2D 激光雷达定位 + Nav2 航点巡航。
6. RDK 上还要跑固定摄像头接入、视觉检测、云台控制等任务。
请继续帮我规划导航硬件采购、ROS2/Nav2 架构和实施步骤。
```

## 26. 导出与日志生成

用户询问是否能直接将整段对话完整导出。

回答：

- 不能保证逐字完整导出原始对话。
- 当前上下文中包含完整可见内容和压缩摘要，但不能像客户端 transcript 一样导出每个原始消息。
- 可替代生成两种文档：
  - 工程日志版 Markdown。
  - 尽量完整的对话摘要版 Markdown。

随后用户要求生成工程日志版 Markdown。

已生成：

```text
docs/validation/daily/2026-05-30-rdk-stm32-navigation-pcb-engineering-log.md
```

内容覆盖：

- UART/电机控制状态。
- TB6612 接线。
- 左轮方向修正。
- PCB 转接板规划。
- 自主导航方案。
- 提前建图。
- RDK 算力评估。
- 采购建议。
- 后续实施计划。

本文件为第二份：

```text
docs/validation/daily/2026-05-30-rdk-stm32-dialogue-summary.md
```

用于按对话时间线尽量完整还原本段讨论。

## 27. 当前关键文件清单

本段对话中重要文件包括：

```text
stm32/firmware/stm32_motion_controller/Core/Src/main.c
stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h
stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c
stm32/firmware/stm32_motion_controller/stm32_motion_controller.ioc
tests/test_stm32_main_uart_integration.py
stm32/docs/tb6612_motor_control_integration.md
docs/hardware/stm32_tb6612_adapter_layout.svg
docs/validation/daily/2026-05-30-rdk-stm32-navigation-pcb-engineering-log.md
docs/validation/daily/2026-05-30-rdk-stm32-dialogue-summary.md
docs/architecture/camera_ingest.md
docs/architecture/gimbal_control_flow.md
rdk_x5/ros2_ws/src/perception_camera/
rdk_x5/ros2_ws/src/gimbal_laser/
rdk_x5/scripts/uart_send_test.py
rdk_x5/scripts/uart_protocol_test.py
```

## 28. 当前最终结论

本段对话最终形成以下工程结论：

1. RDK X5 到 STM32 的 UART 控制链路已经可用，当前有效串口为 `/dev/ttyS1`。
2. STM32 已接入四轮麦克纳姆底盘控制，当前通过 TIM3 PWM 和 GPIO 控制两块 TB6612。
3. 两个左轮方向已通过固件 `invert` 修正，不建议再通过交换电机线反向。
4. TB6612 板上的 `1A/1B/2A/2B` 暂不参与开环控制，后续作为编码器信号考虑。
5. PCB 转接板应采用插接现有 STM32 开发板的方案，不是重画 STM32 裸芯片。
6. 自主路线行驶不应走地面循迹，也不建议走强化学习自动驾驶。
7. 推荐路线为：

```text
提前建图
+ 静态地图加载
+ 2D 激光雷达定位
+ 编码器里程计
+ IMU
+ Nav2 航点巡航
+ STM32 底盘闭环
```

8. RDK X5 运行静态地图定位和 Nav2 大概率够用，但必须控制视觉任务负载。
9. 下一步重点不是继续开环遥控，而是补齐：
   - 编码器。
   - IMU。
   - 2D 激光雷达。
   - STM32 轮速闭环。
   - RDK ROS2 `stm32_bridge`。
   - `/odom`、`/scan`、TF 和 Nav2 配置。

