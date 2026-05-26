# RDK X5 二自由度云台控制工程流程

状态：规划草案  
日期：2026-05-26  
适用对象：RDK X5 直接控制双自由度云台驱动板、两路 AS5600 编码器和后续 ROS2 控制节点。

## 1. 目标

在 RDK X5 上实现一个可测试、可限幅、可记录状态的二自由度云台控制模块。第一阶段先完成硬件连通性、PWM 输出、I2C 编码器读取和手动角度控制；第二阶段再接入视觉检测、激光提醒或任务链路。

本模块优先保证：

- 上电默认不使能电机。
- 未完成 I2C 编码器读取前不进入闭环控制。
- PWM 输出有频率、占空比、角度和速度限幅。
- 所有实物测试都有日志和验证记录。

## 2. 范围

### 2.1 本阶段包含

- RDK X5 40Pin PWM/GPIO/I2C 控制。
- 两路云台电机驱动板使能控制。
- 两个 AS5600 编码器角度读取。
- ROS2 Python 包 `gimbal_laser` 的工程结构规划。
- 手动目标角度命令、状态发布和安全停机。
- 空载、限幅、单轴、双轴联调流程。

### 2.2 本阶段不包含

- 视觉目标自动跟踪算法。
- 激光器实际开关控制。
- 云台动力学精调和高性能控制器。
- 与 STM32 底盘控制协议耦合。
- 比赛管理端 UI。

## 3. 硬件接线假设

所有引脚编号均按 RDK X5 40Pin 物理针脚编号记录。代码实现时不能只依赖物理针脚号，必须在 `rdk_x5_pwm.py` 中把物理针脚映射到 RDK 系统实际暴露的 pwmchip/channel。实际接线变更后必须同步更新 `docs/hardware/pinmap.md` 和现场接线记录。

| 功能 | RDK X5 引脚 | 云台侧接口 | 说明 |
| --- | --- | --- | --- |
| 公共地 | 任一 GND，如 Pin 6 | 驱动板 GND、编码器 GND | 必须共地 |
| 电机 1 PWM A | Pin 29 | 电机 1 IN1/PWM1 | 三相 PWM 控制线 |
| 电机 1 PWM B | Pin 31 | 电机 1 IN2/PWM2 | 三相 PWM 控制线 |
| 电机 1 PWM C | Pin 37 | 电机 1 IN3/PWM3 | 三相 PWM 控制线 |
| 电机 1 EN | Pin 11 | 电机 1 EN | 默认低电平关闭 |
| 电机 2 PWM A | Pin 24 | 电机 2 IN1/PWM1 | 三相 PWM 控制线 |
| 电机 2 PWM B | Pin 32 | 电机 2 IN2/PWM2 | 三相 PWM 控制线 |
| 电机 2 PWM C | Pin 33 | 电机 2 IN3/PWM3 | 三相 PWM 控制线 |
| 电机 2 EN | Pin 13 | 电机 2 EN | 默认低电平关闭 |
| 电机 1 编码器 SDA | Pin 3 | AS5600 SDA | I2C5 |
| 电机 1 编码器 SCL | Pin 5 | AS5600 SCL | I2C5 |
| 电机 2 编码器 SDA | Pin 27 | AS5600 SDA | I2C0 |
| 电机 2 编码器 SCL | Pin 28 | AS5600 SCL | I2C0 |
| 编码器 VCC | Pin 1 或 Pin 17 | AS5600 VCC | 3.3V |
| 编码器 GND | 任一 GND | AS5600 GND | 与驱动板共地 |

电机驱动板电源不从 RDK X5 获取，应按电机规格接外部直流电源。RDK X5 的 40Pin 只承载 3.3V 逻辑控制信号。

Pin 27/28 用作第二路编码器 I2C0 时，不应再启用与其冲突的 PWM2 复用功能。PWM 规划优先使用 PWM0、PWM1 和 PWM3。

## 4. 软件模块位置

云台控制代码放在 RDK 侧 ROS2 工作区，作为独立包实现：

```text
rdk_x5/ros2_ws/src/gimbal_laser/
  README.md
  package.xml
  setup.cfg
  setup.py
  resource/
    gimbal_laser
  gimbal_laser/
    __init__.py
    as5600.py
    rdk_x5_gpio.py
    rdk_x5_pwm.py
    gimbal_controller.py
    gimbal_controller_node.py
  config/
    gimbal.yaml
  launch/
    gimbal_controller.launch.py
```

职责划分：

| 文件 | 职责 |
| --- | --- |
| `as5600.py` | 读取 AS5600 原始角度、角度换算和 I2C 错误处理 |
| `rdk_x5_gpio.py` | 控制 EN 引脚，保证默认关闭 |
| `rdk_x5_pwm.py` | 封装 RDK PWM 导出、频率、占空比和关闭流程 |
| `gimbal_controller.py` | 双轴状态机、限幅、闭环控制和安全策略 |
| `gimbal_controller_node.py` | ROS2 参数、订阅目标角、发布状态、服务接口 |
| `gimbal.yaml` | 引脚、I2C 总线、角度零点、限幅、控制周期 |
| `gimbal_controller.launch.py` | 启动节点并加载配置 |

## 5. ROS2 接口规划

### 5.1 订阅话题

| 话题 | 类型 | 说明 |
| --- | --- | --- |
| `/gimbal/target_angle` | `geometry_msgs/msg/Vector3` | `x=pan_deg`，`y=tilt_deg`，`z` 保留 |
| `/gimbal/enable` | `std_msgs/msg/Bool` | `true` 允许使能，`false` 立即关闭输出 |

### 5.2 发布话题

| 话题 | 类型 | 说明 |
| --- | --- | --- |
| `/gimbal/status` | `std_msgs/msg/String` | JSON 状态，包含角度、目标、是否使能、故障码 |
| `/gimbal/angle` | `geometry_msgs/msg/Vector3` | 当前角度，`x=pan_deg`，`y=tilt_deg` |

### 5.3 服务接口

| 服务 | 类型 | 说明 |
| --- | --- | --- |
| `/gimbal/home` | `std_srvs/srv/Trigger` | 读取当前位置作为临时零点 |
| `/gimbal/stop` | `std_srvs/srv/Trigger` | 停止 PWM 并拉低 EN |

第一版只使用 ROS2 标准消息，避免新增自定义消息包。

## 6. 控制状态机

```text
BOOT
  -> GPIO_SAFE
  -> I2C_CHECK
  -> PWM_CHECK
  -> IDLE
  -> ENABLED_OPEN_LOOP
  -> ENABLED_CLOSED_LOOP
  -> FAULT
```

| 状态 | 行为 | 退出条件 |
| --- | --- | --- |
| `BOOT` | 节点启动，读取参数 | 参数合法 |
| `GPIO_SAFE` | 拉低两路 EN，关闭 PWM | 安全输出确认 |
| `I2C_CHECK` | 扫描 I2C0/I2C5，读取 AS5600 地址 `0x36` | 两路角度可读 |
| `PWM_CHECK` | 初始化 PWM，但占空比保持 0 | PWM 初始化成功 |
| `IDLE` | 发布角度，不驱动电机 | 收到 enable |
| `ENABLED_OPEN_LOOP` | 低占空比手动测试 | 空载测试阶段使用 |
| `ENABLED_CLOSED_LOOP` | 根据目标角和当前角计算输出 | 正常控制 |
| `FAULT` | 立即关闭 PWM 和 EN | 人工复位或重启 |

任何状态出现 I2C 连续读取失败、角度跳变异常、目标角越界或用户停止命令，都应进入安全停机流程。

## 7. 启动流程

### 7.1 RDK 前置检查

```bash
sudo srpi-config
ls /sys/class/pwm
ls /dev/i2c-*
sudo i2cdetect -y 5
sudo i2cdetect -y 0
```

预期结果：

- 已启用 I2C0、I2C5 和云台所需 PWM 复用。
- `/dev/i2c-5` 能看到电机 1 编码器 `0x36`。
- `/dev/i2c-0` 能看到电机 2 编码器 `0x36`。
- PWM 设备路径存在。
- 未启动控制节点时，驱动板 EN 不应使能。

### 7.2 ROS2 启动

```bash
source /opt/tros/humble/setup.bash
cd ~/Soc_China/rdk_x5/ros2_ws
colcon build --symlink-install --packages-select gimbal_laser
source install/setup.bash
ros2 launch gimbal_laser gimbal_controller.launch.py
```

### 7.3 手动命令

```bash
ros2 topic pub --once /gimbal/enable std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /gimbal/target_angle geometry_msgs/msg/Vector3 "{x: 0.0, y: 0.0, z: 0.0}"
ros2 topic echo /gimbal/status
ros2 service call /gimbal/stop std_srvs/srv/Trigger "{}"
```

## 8. 配置文件规划

`gimbal.yaml` 建议包含：

```yaml
gimbal_controller_node:
  ros__parameters:
    pan:
      name: "motor1"
      i2c_bus: 5
      encoder_address: 0x36
      pwm_pins: [29, 31, 37]
      enable_pin: 11
      zero_deg: 0.0
      min_deg: -60.0
      max_deg: 60.0
      invert: false
    tilt:
      name: "motor2"
      i2c_bus: 0
      encoder_address: 0x36
      pwm_pins: [24, 32, 33]
      enable_pin: 13
      zero_deg: 0.0
      min_deg: -30.0
      max_deg: 45.0
      invert: false
    control:
      loop_hz: 100.0
      pwm_frequency_hz: 20000
      max_duty: 0.15
      startup_duty: 0.03
      angle_deadband_deg: 1.0
      i2c_error_limit: 5
      command_timeout_sec: 1.0
```

初次实测时 `max_duty` 必须保守，建议从 `0.03` 到 `0.05` 开始，再逐步提高。

## 9. 开发阶段

### 阶段 A：无电机安全检查

1. 编写 GPIO 和 PWM 封装，但默认不输出占空比。
2. 运行节点，确认 EN 引脚保持关闭。
3. 发布 `/gimbal/status`，确认状态进入 `IDLE` 或 `I2C_CHECK`。
4. 记录到 `docs/validation/daily/`。

### 阶段 B：编码器读取

1. 安装并使用 `i2c-tools` 确认两个 AS5600 都在 `0x36`。
2. 编写 `as5600.py`，读取原始角度寄存器。
3. 手动转动云台，确认角度连续变化。
4. 判断两个轴的正方向，记录 `invert` 配置。

### 阶段 C：PWM 空载输出

1. 断开电机动力电源，仅测量 PWM 信号。
2. 用示波器、逻辑分析仪或驱动板状态确认 PWM 频率。
3. 确认 `/gimbal/stop` 后 PWM 占空比为 0，EN 为低。

### 阶段 D：单轴低占空比测试

1. 只接电机 1 动力电源。
2. 进入 `ENABLED_OPEN_LOOP`，占空比限制在 `0.03`。
3. 观察转动方向、抖动、发热和编码器变化。
4. 通过配置修正方向，不在代码中写死方向。

### 阶段 E：双轴闭环测试

1. 两轴分别完成单轴测试后再接双轴。
2. 目标角从 `0` 开始，每次只增加 `5` 度。
3. 控制周期先用 50 Hz 到 100 Hz。
4. 出现抖动、发热、角度跳变时立即停机，记录故障。

### 阶段 F：接入任务链路

1. 视觉或任务节点只发布 `/gimbal/target_angle`。
2. 云台节点负责限幅和安全，不信任外部目标。
3. 告警、激光或语音提醒只订阅云台状态，不直接控制 PWM。

## 10. 验证标准

| 项目 | 命令/操作 | 通过标准 |
| --- | --- | --- |
| I2C 扫描 | `sudo i2cdetect -y 5`，`sudo i2cdetect -y 0` | 两路均出现 `0x36` |
| 节点启动 | `ros2 launch gimbal_laser gimbal_controller.launch.py` | 默认不使能电机 |
| 状态发布 | `ros2 topic echo /gimbal/status` | JSON 中角度和状态持续更新 |
| 停止命令 | `ros2 service call /gimbal/stop std_srvs/srv/Trigger "{}"` | PWM 为 0，EN 为低 |
| 目标限幅 | 发布超过范围的目标角 | 状态报告 clamped，不超过配置范围 |
| I2C 故障 | 临时断开一路编码器 | 进入 FAULT 并停机 |
| 命令超时 | 使能后停止发布目标角 | 超时后停机或保持安全状态 |

## 11. 风险和约束

- RDK X5 是 Linux 系统，PWM 输出和闭环周期存在调度抖动，不适合一开始追求高带宽控制。
- 两个 AS5600 地址相同，必须接在不同 I2C 总线，或使用 I2C 多路复用器。
- 编码器供电和 I2C 上拉必须是 3.3V，不能上拉到 5V。
- 电机动力电源与 RDK 供电分开，但 GND 必须共地。
- 任何调试阶段都不能默认上电使能电机。
- 若驱动板需要特定三相 PWM 波形，第一版代码必须先做低占空比空载验证。

## 12. 后续实现计划入口

完成本文档确认后，再拆成实现任务：

1. 新建 `gimbal_laser` ROS2 Python 包。
2. 编写并测试 AS5600 读取模块。
3. 编写并测试 GPIO/PWM 安全封装。
4. 编写云台控制状态机。
5. 增加 ROS2 节点、配置和 launch。
6. 增加 RDK 启动脚本和 smoke test。
7. 完成硬件验证记录和 pinmap 更新。

后续实现时，每个阶段都应先跑无动力或低风险测试，再进入真实电机测试。
