# 2026-06-08 STM32 编码器接入 + UART 迁移 + 右侧联调日志

整理时间：2026-06-08

记录范围：本次围绕"给四轮麦克纳姆底盘接入 4 路正交编码器"的固件改造、引脚迁移、刷写、以及实机联调与逐项硬件验证。包含 N10 雷达恢复后的状态、STM32 引脚重排、编码器读取、右侧电机+编码器实测，以及 TB6612-A 故障的确认与影响。本文是工程归档，不是逐字记录。

## 1. 背景与前序状态

- N10 激光雷达此前"固定后无串口数据"的阻塞已解决（物理重启/拔插恢复），`/scan` 10Hz 稳定、四向坐标验证通过、固定后遮挡清零。详见 `2026-06-07-rdk-n10-stm32-mecanum-execution-handoff.md` 与当日恢复。
- 目标推进到 M6：给四个 520 编码电机接入 A/B 相，做轮速里程计基础。

## 2. 关键约束：为什么要迁移引脚

STM32F411 能做硬件正交编码器的定时器只有 TIM1~TIM5。其中：

- TIM3 已用于 4 路 PWM（PA6/PA7/PB0/PB1），不可动。
- TIM1 的编码器通道必用 PA9（48 脚封装上 TIM1_CH2 无替代），而 PA9 原是 RDK 串口 USART1_TX。
- TIM5 编码器必用 PA0/PA1，原是 LF 方向脚。

因此要凑满 4 路硬件编码器，必须：把 RDK 串口从 USART1 迁到 **USART2(PA2/PA3)**（让出 PA9 给 TIM1），并把 LF/LR 方向脚移到空闲的 PB12-15（让出 PA0/PA1 给 TIM5、PA2/PA3 给 USART2）。

## 3. 迁移后的完整引脚映射（已刷入并验证）

| 功能 | 引脚 | 定时器/外设 | 备注 |
| --- | --- | --- | --- |
| LF PWM | PA6 | TIM3_CH1 | 不变 |
| LR PWM | PA7 | TIM3_CH2 | 不变 |
| RF PWM | PB0 | TIM3_CH3 | 不变 |
| RR PWM | PB1 | TIM3_CH4 | 不变 |
| RF DIR | PA4/PA5 | GPIO | 不变 |
| RR DIR | PB8/PB9 | GPIO | 不变 |
| LF DIR | **PB12/PB13** | GPIO | 由 PA0/PA1 迁移 |
| LR DIR | **PB14/PB15** | GPIO | 由 PA2/PA3 迁移 |
| RDK UART | **PA2(TX)/PA3(RX)** | USART2 AF7 | 由 USART1 PA9/PA10 迁移；RDK 侧仍 `/dev/ttyS1` 115200 |
| LF 编码器 A/B | PA0/PA1 | TIM5 | 新增 |
| RF 编码器 A/B | PA8/PA9 | TIM1 | 新增 |
| LR 编码器 A/B | PA15/PB3 | TIM2 | 新增（SWD 下 JTDI/JTDO 可用） |
| RR 编码器 A/B | PB6/PB7 | TIM4 | 新增 |

编码器供电 3.3V、GND 与 STM32 共地，编码器输入开内部上拉。

## 4. 固件改动

文件：
- `Core/Src/main.c`：USART1→USART2（句柄 `huart2`）；电机方向表 LF/LR 改 PB12-15；`MX_GPIO_Init`/`app_motor_output_start` 方向脚更新；新增 `MX_TIM1/2/4/5_Init`（编码器模式 TI12 四倍频 + 输入滤波）、`app_encoders_start()`、`send_odom()`；`app_tick` 周期内随 STATUS 发送 ODOM。
- `Core/Src/stm32f4xx_hal_msp.c`：USART1→USART2 + 引脚 PA2/PA3；新增 `HAL_TIM_Encoder_MspInit`（4 个定时器的 GPIO AF + 时钟）。
- `Core/Src/stm32f4xx_it.c` / `Core/Inc/stm32f4xx_it.h`：`USART1_IRQHandler`→`USART2_IRQHandler`，`huart1`→`huart2`。
- ODOM 帧（0x82, 4×int16，顺序 LF,RF,LR,RR）= 各轮 16-bit 计数原值。
- 测试：`tests/test_stm32_main_uart_integration.py` 更新断言（huart2 + 新增迁移测试）。

构建/刷写：
- STM32CubeIDE headless `-cleanBuild`：0 errors, 0 warnings。
- `STM32_Programmer_CLI -c port=SWD mode=UR -w <elf> -v -rst`：Download verified。
- host 测试 `python3 -m unittest discover -s tests`：66 passed。

⚠️ `.ioc` 未同步（改动是手改 .c/.h）。若日后用 CubeMX 重新生成代码会覆盖 USART2/编码器改动——需先把这些改动补回 .ioc 或继续走 headless build。

## 5. 实机验证结果（2026-06-08）

### 5.1 UART 迁移（USART2）
RDK 经 `/dev/ttyS1` 收到 STM32 `STATUS`/`ACK`，`crc_errors=0 len_errors=0`，进入 `MANUAL`。证明 PA2/PA3 串口线 + 共地正确。

### 5.2 编码器（手转验证，无需电机上电）
手转四轮，ODOM 计数：

- **RF（TIM1, PA8/PA9）**：大幅变化 ✅
- **RR（TIM4, PB6/PB7）**：大幅变化 ✅
- **LF（TIM5, PA0/PA1）**：全程 0 ❌
- **LR（TIM2, PA15/PB3）**：全程 0 ❌

### 5.3 右侧电机驱动（四轮悬空，vx=80mm/s 前进，PWM≈53/999）
ODOM `delta_ticks=(LF,RF,LR,RR)`：RF 1734→1879、RR 2012→2133 持续递增，LF/LR 恒 0。说明 RF/RR 电机驱动正常、编码器前进方向计正值；端到端链路 RDK→USART2→STM32→麦轮解算→TB6612-B→RF/RR 电机→编码器→ODOM→RDK 全通。

## 6. 当前阻塞：TB6612-A 故障

左侧 LF+LR 两个编码器同时无信号、且右侧两个完全正常——指向共同原因：**TB6612-A 板故障**（左侧编码器供电/共地经该板，板坏→左编码器无电→无输出；其电机驱动同样不可用）。用户决定：确认 TB6612-A 坏，左侧只保留软件、跳过硬件测试，待换板。

影响：
- LF/LR 电机驱动 + 编码器在换板前不可用（固件已就绪）。
- 真正的整车 20cm 移动测试、里程计左右符号标定、四轮闭环 PID 暂缓（需四轮齐全）。

## 7. 后续里程碑（换 TB6612-A 后）

1. 复测 LF/LR 编码器（手转）+ LF/LR 电机驱动（验证迁移到 PB12-15 的方向脚）。
2. 标定四轮编码器方向符号，使"前进"四轮一致为正。
3. 四轮悬空运动学验证：前进/后退/横移/原地旋转的轮向组合。
4. 低速落地 + 20cm 移动测试。
5. 固件：ODOM 由原始计数改为里程计/轮速（物理单位），加四轮速度闭环 PID。
6. RDK：`stm32_bridge` 节点（`/cmd_vel`→CMD_VEL，STATUS/ODOM→`/odom`+TF）。
7. IMU 接 RDK + robot_localization EKF 融合。
8. `/scan`+`/odom`+TF → slam_toolbox 建图 → Nav2 航点。

## 7.5 纯软件产出：stm32_bridge ROS2 节点（不依赖完整硬件）

在硬件因 TB6612-A 受阻期间，推进了文档规划已久的 RDK 端桥接节点。

新增 ROS2 包 `rdk_x5/ros2_ws/src/stm32_bridge`（ament_python）：
- 节点 `stm32_bridge_node.py`：订阅 `/cmd_vel`(Twist) → clamp → 发 `CMD_VEL`；周期发 `SET_MODE`/`HEARTBEAT`；读 STM32 `ODOM`/`STATUS` → 发布 `/odom`(nav_msgs/Odometry) + TF `odom→base_link` + `/stm32/status`；退出发 `STOP`。复用 `shared/protocol/rdk_stm32_uart.py`。
- 纯里程计数学 `mecanum_odometry.py`：正运动学是固件 `MecanumDrive_Mix` 的**精确逆**；16-bit 计数环绕安全；中点航向积分位姿；逐轮 `encoder_sign` + `ticks_per_rev` 可标定。
- 配置/启动/README 齐全。

验证：
- host 单测 `tests/test_mecanum_odometry.py` 11 项（正逆运动学round-trip、前进/横移/旋转、环绕、基准、符号）全过；全量 `python3 -m unittest discover -s tests` **77 项全过**。
- RDK 实跑（`colcon build --packages-select stm32_bridge` 成功；注意该机 setuptools 不支持 `--symlink-install` 的 `--editable`，用普通安装）：节点起来后 `/odom` 稳定 **10.0 Hz**，消息 `frame_id=odom`/`child_frame_id=base_link`、位姿正确（电机停→原点），`/stm32/status` 正常。

待标定（需四轮齐全/换板后）：`ticks_per_rev`（占位 1320）、`encoder_sign`（RF/RR 实测 +1，LF/LR 待定）。

## 7.6 纯软件续：轮速 PID 模块 + 导航地基

**(1) STM32 轮速闭环 PID 模块**（框架，未接入live控制，零回归）：
- `Core/Inc/wheel_pid.h` + `Core/Src/wheel_pid.c`：前馈 + Kp/Ki/Kd、积分限幅、抗饱和、输出限幅。`ff=pwm_max/max_radps` 且增益为 0 时与现有开环映射完全一致，可逐步加增益开启闭环（增益需硬件整定）。
- 主机 C 测试 `tests/test_wheel_pid.py` 5 项全过；工程内 headless 编译 0 错 0 警。
- 未改动现有可用的 `mecanum_drive` 开环路径，故未重刷固件。

**(2) RDK 导航地基包 `rdk_x5/ros2_ws/src/chassis_bringup`**（仅 launch+config，无新节点代码）：
- TF 树：`map→odom`(slam/amcl) → `odom→base_link`(EKF) → `base_link→laser/imu_link`(静态)。stm32_bridge 设 `publish_tf:=false`，TF 交给 EKF。
- `config/ekf.yaml`(robot_localization，融合 /odom，IMU 块就绪待启用)、`config/slam_toolbox.yaml`、`config/nav2_params.yaml`(全向/holonomic 模板，待整定)。
- `launch/tf_static.launch.py`(base_link→laser/imu，偏移占位待实测；yaw≈0 由 6-07 方向验证支持)、`bringup.launch.py`(bridge+EKF+静态TF)、`slam.launch.py`。
- 验证：3 个 YAML 合法、`colcon build` 成功、静态 TF 实跑 `base_link→laser=[0,0,0.15]` 正常。
- **nav 栈已装 + EKF 已验证（2026-06-08）**：经 Mac NAT(en0 转发 + pfctl) 给 RDK 联网，`apt install ros-humble-{robot-localization,slam-toolbox,navigation2,nav2-bringup}` 成功；`ros2 launch chassis_bringup bringup.launch.py` 起来后 `/ekf_filter_node`+`/stm32_bridge` 运行，话题 `/odom`、`/odometry/filtered`、`/tf` 正常，**EKF 实时发布 `odom→base_link` TF**（车静止=原点，符合预期）。联网后 RDK 系统时钟也校准。
- ⚠️ 仍待：`/odom` 数值标定（`ticks_per_rev`+左侧 `encoder_sign`，需换 TB6612-A 四轮齐全）、静态 TF 安装偏移实测、`nav2_params` 整定后才能真正建图/导航。Mac NAT 重启后需重开。

## 7.7 纯软件批次（不需换板）：joint_states / URDF / MPPI / 航点

- **F bridge 增强**：stm32_bridge 增发 `/joint_states`（四轮关节角+角速度，从编码器累计，应用 encoder_sign），加 `sensor_msgs` 依赖与配置项。
- **D URDF + robot_state_publisher**：`chassis_bringup/description/chassis.urdf`（base_link+四轮+laser+imu，几何取自固件）；`launch/description.launch.py` 跑 robot_state_publisher；`bringup.launch.py` 改用 URDF 提供 laser/imu/轮 TF（替代 tf_static，避免重复）。
- **C Nav2 控制器换 MPPI 全向**：`nav2_params.yaml` 的 FollowPath 由 DWB 改为 `nav2_mppi_controller::MPPIController`，`motion_model: Omni` + 一套 critic。
- **E 航点巡航**：`chassis_bringup/chassis_bringup/waypoint_patrol.py`（nav2_simple_commander，读航点可循环）+ `config/waypoints.example.yaml` + 入口点；纯函数单测。

验证：host 测试 **88 项全过**（+6：航点解析/yaw→quat）；RDK `colcon build` 两包成功（注意重装需先 `rm -rf build/install/<pkg>`，该机 setuptools 不支持 colcon 的 `--uninstall`/`--editable`）；bring-up 实跑——`/joint_states` 正常、TF `base_link→laser=[0,0,0.15]`、`base_link→rf_wheel_link=[0.12,-0.10,0]`、`odom→base_link`(EKF) 全部正确。完整 TF 树成形（差 map→odom）。

## 7.8 标定 `ticks_per_rev`（A，无需换板）

手滚 RF 右前轮 6 整圈：RF 原始计数 1883 → −13796，差 15679，÷6 = **2613 ticks/rev**（手滚估计 ±2~3%，≈ 11PPR×4×1:60=2640，在误差内）。已写入 `stm32_bridge.yaml` 与 `mecanum_odometry.py` 默认值并部署。四电机同型号故常数通用。
- 方向说明：手滚"朝前"时 RF 计数减，而电机 forward 时 RF 计数增——以电机实测为准，`encoder_sign[RF]=+1`（前进=正）不变。
- 注：`/odom` 端到端数值仍需四轮齐全才能验证（麦轮正运动学要 4 轮），常数本身已标定可用。
- 后续可用"驱动已知地面距离"精修（待换板四轮齐全）。

## 7.9 雷达安装偏移(B) + IMU 软件就绪(G)

**B**：实测 N10 相对底盘几何中心 x=0.126m(前)、y=0、离地 0.15m → `base_link` 在轴高(~0.05)，故 z=0.10。写入 URDF `base_to_laser` 与 tf_static。实跑验证 `base_link→laser=[0.126,0,0.10]`。（排查到早前 tf_static 冒烟遗留的 static_transform_publisher 在抢发旧值 0.15，已清理。）

**G（IMU BMI088）—— 完整集成并验证 ✅**：
- 排查过程：先经 RDK_IMU_CONNECTOR Ver.2.0 接 i2c-5，**加速度计正常但陀螺 0x69 只 ACK 地址、读写全 NACK**，断电/重插/整机重启均无效；拨 SPI 测（无法测，SPI 与热成像冲突）。**最终绕开 connector 直连裸模块**（CSA/CSG/SEL 拉高、SDO1/SDO2 接地）→ **陀螺立刻 100% 可读** → **判定 connector Ver.2.0 缺陷（未把 CSG 拉好），BMI088 模块本身完好**。
- 直连后地址 **0x18 加速度 / 0x68 陀螺**，i2c-5（与热成像 0x40 共存，不冲突）。**关键坑：本 BMI088/控制器不支持重复起始位，必须"写寄存器-STOP-读"分离事务**（smbus2 `i2c_msg` 分两次）。
- 新增驱动包 **`bmi088_imu`**：`bmi088.py`(分离事务读、缩放、**启动陀螺零偏标定**) + 节点发 `sensor_msgs/Imu` 到 `/imu` @100Hz（无姿态→`orientation_covariance[0]=-1`）。缩放单测 9 项。
- **EKF 集成**：`bringup.launch.py use_imu:=true` 一键拉起 IMU + 用 `ekf_imu.yaml`。**只融合陀螺 vyaw**（不融合 ax/ay——无姿态时重力会漏进水平加速度致漂移）。
- 实测验证：accel 0x1E/gyro 0x0F、`/imu`@100Hz（陀螺静止≈0、加速度幅值≈9.6=重力）、`/odometry/filtered`@30Hz、**静止 `odom→base_link` 无位置漂移、yaw 8s 内 qz≈0.001**（零偏标定 + 仅融合 vyaw 后漂移消除）。
- 注意：本机 setuptools 重装包需先 `rm -rf build/install/<pkg>`；批量 kill 进程会偶发掐断 SSH（kill 仍生效）。
- 已备软件：`config/ekf_imu.yaml`（融合 /imu：陀螺 vyaw + 加速度，无磁力计故不融合绝对 yaw）；`bringup.launch.py` 加 `ekf_config_file` 参数，接好后 `ros2 launch chassis_bringup bringup.launch.py ekf_config_file:=ekf_imu.yaml` 一键启用。
- 待硬件：BMI088 跳到 **I2C**、接空闲 `i2c-1`(或共用 i2c-5)、`i2cdetect` 见 0x18/0x68，再写驱动节点发 `/imu`（板上无现成包，需像热成像 senxor_driver 那样写）。40-pin 已被云台 PWM+I2C1、热成像 SPI1+i2c-5、STM32 UART 占用，接线需规划。详见包 README。

## 8. 关键文件

- `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
- `stm32/firmware/stm32_motion_controller/Core/Src/stm32f4xx_hal_msp.c`
- `stm32/firmware/stm32_motion_controller/Core/Src/stm32f4xx_it.c`
- `rdk_x5/scripts/encoder_monitor.py`（新增：手转编码器实时监视）
- `rdk_x5/scripts/n10_serial_diag.py`（新增：N10 串口一次性诊断）
- `rdk_x5/scripts/uart_send_test.py`（复用：发 CMD_VEL + 打印 ODOM）
- `tests/test_stm32_main_uart_integration.py`
- `rdk_x5/ros2_ws/src/stm32_bridge/`（新增 ROS2 桥接包：节点 + 里程计数学 + 配置/启动）
- `tests/test_mecanum_odometry.py`（新增：里程计数学 11 项单测）
- `stm32/firmware/.../Core/{Inc/wheel_pid.h,Src/wheel_pid.c}`（新增：轮速 PID 模块）
- `tests/test_wheel_pid.py`（新增：PID 5 项主机 C 测试）
- `rdk_x5/ros2_ws/src/chassis_bringup/`（EKF/SLAM/Nav2(MPPI) 配置 + URDF + bring-up(含 use_imu)/description/slam 启动 + 航点巡航 + ekf_imu.yaml）
- `tests/test_waypoint_patrol.py`（航点解析/yaw→quat 单测）
- `rdk_x5/ros2_ws/src/bmi088_imu/`（新增：BMI088 I2C 驱动包 → /imu）
- `tests/test_bmi088_scaling.py`（BMI088 缩放 9 项单测）
