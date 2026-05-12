# RDK X5 与 STM32F411CEU6 UART 移动控制执行计划

状态：v1 可执行计划  
日期：2026-05-11  
目标：让 RDK X5 通过 UART 稳定控制 STM32F411CEU6，STM32 再通过 PWM/DIR 控制电机驱动，实现底盘移动、停车、急停和状态回传。

## 1. 总体目标

本计划只解决 RDK X5 与 STM32F411CEU6 之间的底盘控制通信闭环。

RDK X5 负责：

- 运行 Linux/ROS2 或 Python 控制程序。
- 生成速度命令，例如前进、后退、横移、旋转。
- 通过 UART 周期性发送 `CMD_VEL` 和 `HEARTBEAT`。
- 接收 STM32 的 `STATUS`、`ACK`、`ODOM`、`FAULT`。
- 记录日志，供现场调试和答辩材料使用。

STM32F411CEU6 负责：

- 接收并解析 UART 帧。
- 校验 CRC16，拒绝错误帧。
- 将 `CMD_VEL` 转成四轮速度目标。
- 输出 PWM/DIR 到 MDDS20。
- 读取编码器、急停、故障输入。
- 在通信超时或急停时独立停车。
- 周期性回传状态。

不在本计划范围内：

- 视觉识别、热成像、导航算法。
- 完整 ROS2 工程实现。
- PCB 原理图设计。
- 云台、激光、语音模块控制。

## 2. 文件与目录约定

建议最终相关文件放在以下位置：

```text
docs/protocols/rdk_stm32_uart.md
docs/protocols/rdk_stm32_uart_execution_plan.md
docs/hardware/pinmap.md
docs/hardware/power-tree.md
docs/validation/daily/YYYY-MM-DD.md
rdk_x5/scripts/uart_send_test.py
rdk_x5/scripts/uart_protocol_test.py
shared/protocol/rdk_stm32_frame.md
sim/stm32_simulator/serial_simulator.py
stm32/firmware/
stm32/docs/uart_setup.md
stm32/docs/timer_pwm_encoder_setup.md
```

## 3. 硬件前置条件

### 3.1 必备硬件

| 类别 | 建议硬件 | 用途 |
| --- | --- | --- |
| 上位主控 | RDK X5 | 发送速度命令，运行日志和控制程序 |
| 底层 MCU | STM32F411CEU6 开发板 | 解析协议，输出 PWM/DIR，读取编码器和急停 |
| 调试电脑 | macOS/Windows/Linux 均可 | 烧录 STM32，查看串口日志 |
| USB 数据线 | Type-C/Micro-USB，按开发板接口 | 给 STM32 烧录/供电/调试 |
| USB-TTL 模块 | 3.3V 逻辑电平 | 初期串口调试，推荐保留 |
| 杜邦线 | 母对母/公对母 | TX/RX/GND 接线 |
| 万用表 | 任意可靠型号 | 测电压、共地、短路 |
| 电机驱动 | Cytron MDDS20 x2 | 驱动四个直流电机 |
| 急停开关 | 常闭或常开，按接线方案固定 | 安全停机 |
| 电源 | 12V 主电池、5V 降压、6V UBEC | 整机分路供电 |

### 3.2 推荐调试阶段

第一阶段不要直接上底盘和电机。按下面顺序逐级推进：

1. 电脑 USB-TTL 与 STM32 串口回显。
2. RDK USB-TTL 与 STM32 串口回显。
3. RDK 40PIN UART 与 STM32 串口回显。
4. RDK 发送协议帧，STM32 返回 `ACK`。
5. STM32 空载输出 PWM，用 LED、示波器或逻辑分析仪验证。
6. 单电机台架测试。
7. 四轮悬空测试。
8. 底盘低速落地测试。

## 4. 接线前置条件

### 4.1 UART 基本接线

UART 必须交叉连接：

```text
RDK UART_TX  -> STM32 UART_RX
RDK UART_RX  -> STM32 UART_TX
RDK GND      -> STM32 GND
```

必须确认：

- RDK UART 是 3.3V 逻辑电平。
- STM32F411CEU6 UART 是 3.3V 逻辑电平。
- 不要把 5V TTL 串口直接接到 RDK 或 STM32 的 3.3V IO。
- 不要只接 TX/RX 而不接 GND。
- TX/RX 接反不会烧坏通常只是没数据，但供电接错会有风险。

### 4.2 初期推荐接法

为了减少 RDK 40PIN pinmux 和设备名不确定带来的干扰，第一天建议先用 USB-TTL：

```text
RDK USB-A  -> USB-TTL 模块
USB-TTL TX -> STM32 RX
USB-TTL RX -> STM32 TX
USB-TTL GND -> STM32 GND
```

RDK 端设备通常会显示为：

```text
/dev/ttyUSB0
```

如果使用 RDK 40PIN UART，设备可能是：

```text
/dev/ttyS*
```

实际设备名以 RDK 上的 `ls /dev/ttyS* /dev/ttyUSB*` 输出为准，并记录到 `docs/hardware/pinmap.md`。

### 4.3 供电规则

调试早期：

- RDK X5 使用自己的 5V 供电。
- STM32 开发板可以先通过 USB 供电。
- 两者 UART 通信必须共地。
- 电机驱动和主电池不要接入，直到串口协议稳定。

上电联调阶段：

```text
12V 主电池
├── MDDS20 x2 -> 四个底盘电机
├── 5V 8A 降压 -> RDK X5
└── 6V 5A UBEC -> PCA9685/舵机，若本阶段不用可不接
```

安全要求：

- 电机支路、RDK 支路、舵机支路分开供电。
- 所有 GND 最终共地。
- 电机动力线和编码器线分开走线。
- 第一次电机测试必须悬空或台架固定。
- 涉及电机运动时，必须有人现场看护急停。

## 5. RDK X5 前置配置

### 5.1 系统要求

建议 RDK X5 使用官方支持的 Ubuntu 系统环境。计划中默认：

```text
OS: Ubuntu 22.04 或 RDK 官方镜像
Shell: bash/zsh 均可
UART: 115200 8N1
Python: 3.10+
```

### 5.2 RDK 基础检查命令

在 RDK 上执行：

```bash
uname -a
lsb_release -a
whoami
pwd
```

检查串口设备：

```bash
ls -l /dev/ttyS* /dev/ttyUSB* 2>/dev/null
dmesg | tail -n 50
```

如果使用 USB-TTL，插入前后各运行一次：

```bash
ls -l /dev/ttyUSB*
```

新增的那个通常就是串口设备。

### 5.3 串口权限配置

如果打开串口时报 `Permission denied`，把当前用户加入串口权限组：

```bash
sudo usermod -aG dialout $USER
```

然后退出 SSH 重新登录，或重启 RDK：

```bash
sudo reboot
```

确认用户组：

```bash
groups
```

应包含：

```text
dialout
```

### 5.4 RDK Python 依赖

建议先使用 Python 写协议测试脚本。安装依赖：

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
python3 -m pip install pyserial
```

验证：

```bash
python3 -c "import serial; print(serial.__version__)"
```

### 5.5 RDK 串口最小测试

先做普通串口收发测试，不上协议。

RDK 发送测试目标：

```text
RDK 每 1 秒发送 hello stm32
STM32 原样回传 hello stm32
RDK 能打印收到的内容
```

推荐串口参数：

```text
baudrate: 115200
bytesize: 8
parity: none
stopbits: 1
timeout: 0.1s
```

### 5.6 RDK 端日志要求

每次运行必须记录：

```text
日期
commit id
串口设备名
波特率
发送帧数量
收到 ACK 数量
CRC 错误数量
超时次数
最后一次 STATUS
```

建议日志路径：

```text
logs/YYYYMMDD_HHMMSS_uart_test/
```

## 6. STM32F411CEU6 前置配置

### 6.1 软件工具

推荐工具链：

| 工具 | 用途 |
| --- | --- |
| STM32CubeIDE | 创建、编译、烧录 STM32 工程 |
| STM32CubeMX | 配置时钟、USART、TIM、GPIO |
| ST-Link 驱动 | 连接调试器 |
| 串口助手 | 初期查看串口回显 |
| 逻辑分析仪/示波器 | 验证 PWM 和 UART 波形，可选但很有用 |

### 6.2 STM32 工程建议

建议使用 HAL 起步，后续稳定后再考虑 LL 优化。

工程名称建议：

```text
stm32_motion_controller
```

目录建议：

```text
stm32/firmware/stm32_motion_controller/
├── Core/
├── Drivers/
├── MDK-ARM/ 或 STM32CubeIDE 工程文件
└── README.md
```

### 6.3 时钟配置

建议第一版使用稳定、容易复现的配置：

```text
SYSCLK: 84 MHz
HCLK: 84 MHz
APB1: 42 MHz
APB2: 84 MHz
```

如果开发板晶振不确定，可以先使用内部 HSI 跑通串口，再切换 HSE。

要求：

- UART 实际波特率误差不能过大。
- PWM 频率计算必须基于最终时钟。
- 时钟配置截图或 `.ioc` 文件必须提交。

### 6.4 USART 配置

推荐使用一个 USART 专门连接 RDK。

常见可选组合：

```text
USART1: PA9  TX, PA10 RX
USART2: PA2  TX, PA3  RX
USART6: PC6  TX, PC7  RX
```

实际使用哪个取决于开发板引脚是否方便引出。选定后必须写入：

```text
docs/hardware/pinmap.md
stm32/docs/uart_setup.md
```

USART 参数固定为：

```text
BaudRate: 115200
WordLength: 8 bits
Parity: None
StopBits: 1
Mode: TX/RX
Hardware Flow Control: None
Oversampling: 16
```

接收方式建议：

第一版：

```text
UART interrupt receive one byte
```

后续优化：

```text
DMA circular buffer + idle line interrupt
```

第一版不要直接上 DMA，先确保协议状态机正确。

### 6.5 PWM/DIR 配置

STM32 至少需要 4 路 PWM 和 4 路方向 GPIO：

```text
LF: PWM1 + DIR1
RF: PWM2 + DIR2
LR: PWM3 + DIR3
RR: PWM4 + DIR4
```

建议 PWM 参数：

```text
PWM frequency: 10 kHz 到 20 kHz
Duty range: 0 到 1000
Initial duty: 0
Boot default: disabled 或 duty=0
```

方向 GPIO：

```text
GPIO output push-pull
default low
```

安全要求：

- 上电后 PWM 必须为 0。
- 未收到有效命令前 PWM 必须为 0。
- 急停触发后 PWM 必须立即为 0。
- 通信超时后 PWM 必须为 0。

### 6.6 编码器配置

如果四个电机编码器已经可用，建议使用定时器 Encoder Mode。

第一版可以先做两级目标：

1. `encoder_stub`：没有真实编码器时，回传 0。
2. `encoder_real`：接入真实编码器后，回传四轮增量。

ODOM 第一版建议回传增量：

```text
delta_lf int16
delta_rf int16
delta_lr int16
delta_rr int16
```

### 6.7 急停输入配置

急停必须接入 STM32。

GPIO 建议：

```text
Mode: GPIO input
Pull: 根据实际电路选择 Pull-up 或 Pull-down
Interrupt: 可选，推荐后续开启 EXTI
```

逻辑要求：

- 触发急停时，STM32 立即停止 PWM。
- STM32 回传 `STATUS.estop = 1`。
- RDK 收到后停止继续发运动命令，并记录日志。

## 7. 协议正式定义

### 7.1 字节序

全部多字节整数使用小端：

```text
little-endian
```

原因：

- STM32 ARM Cortex-M 默认小端。
- RDK Linux 也是小端。
- 解析简单。

### 7.2 帧格式

统一帧格式：

```text
+------+-----+------+-----+-----+---------+-------+
| SOF  | VER | TYPE | SEQ | LEN | PAYLOAD | CRC16 |
+------+-----+------+-----+-----+---------+-------+
| 2B   | 1B  | 1B   | 1B  | 1B  | 0-64B   | 2B    |
+------+-----+------+-----+-----+---------+-------+
```

字段：

| 字段 | 长度 | 值/范围 | 说明 |
| --- | --- | --- | --- |
| SOF | 2 | `0xAA 0x55` | 帧头 |
| VER | 1 | `0x01` | 协议版本 |
| TYPE | 1 | 见帧类型表 | 帧类型 |
| SEQ | 1 | 0-255 | 命令序号，循环递增 |
| LEN | 1 | 0-64 | payload 长度 |
| PAYLOAD | N | 0-64 字节 | 数据 |
| CRC16 | 2 | CRC16-CCITT-FALSE | 校验 |

CRC16 计算范围：

```text
VER + TYPE + SEQ + LEN + PAYLOAD
```

不包含：

```text
SOF
CRC16 自身
```

CRC16 参数：

```text
Name: CRC-16/CCITT-FALSE
Polynomial: 0x1021
Initial: 0xFFFF
RefIn: false
RefOut: false
XorOut: 0x0000
```

CRC16 存储方式：

```text
low byte first, high byte second
```

### 7.3 RDK 到 STM32 帧类型

| TYPE | 名称 | 方向 | 频率 | 作用 |
| --- | --- | --- | --- | --- |
| `0x01` | `HEARTBEAT` | RDK -> STM32 | 10 Hz | 保活 |
| `0x10` | `CMD_VEL` | RDK -> STM32 | 20 Hz | 底盘速度控制 |
| `0x11` | `STOP` | RDK -> STM32 | 按需 | 主动停车 |
| `0x12` | `SET_MODE` | RDK -> STM32 | 按需 | 模式切换 |

### 7.4 STM32 到 RDK 帧类型

| TYPE | 名称 | 方向 | 频率 | 作用 |
| --- | --- | --- | --- | --- |
| `0x81` | `STATUS` | STM32 -> RDK | 10 Hz | 基础状态 |
| `0x82` | `ODOM` | STM32 -> RDK | 20 Hz 或 10 Hz | 编码器增量 |
| `0x83` | `FAULT` | STM32 -> RDK | 事件触发 | 故障上报 |
| `0x84` | `ACK` | STM32 -> RDK | 收到命令后 | 命令确认 |

## 8. Payload 定义

### 8.1 HEARTBEAT `0x01`

RDK 周期发送，STM32 用于判断通信是否在线。

Payload：

| 字段 | 类型 | 长度 | 单位 | 说明 |
| --- | --- | --- | --- | --- |
| `uptime_ms` | `uint32` | 4 | ms | RDK 程序运行时间 |

LEN：

```text
4
```

### 8.2 CMD_VEL `0x10`

RDK 发送底盘速度目标。

Payload：

| 字段 | 类型 | 长度 | 单位 | 范围 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `vx_mm_s` | `int16` | 2 | mm/s | -500 到 500 | 前后速度，前进为正 |
| `vy_mm_s` | `int16` | 2 | mm/s | -500 到 500 | 左右速度，左移为正 |
| `wz_mrad_s` | `int16` | 2 | mrad/s | -1500 到 1500 | 旋转速度，逆时针为正 |

LEN：

```text
6
```

初期实车限速建议：

```text
vx_mm_s: -100 到 100
vy_mm_s: -100 到 100
wz_mrad_s: -300 到 300
```

等底盘方向、急停、制动都验证后，再逐步放开。

### 8.3 STOP `0x11`

RDK 主动要求停车。

Payload：

| 字段 | 类型 | 长度 | 值 | 说明 |
| --- | --- | --- | --- | --- |
| `reason` | `uint8` | 1 | 见下表 | 停车原因 |

`reason`：

| 值 | 含义 |
| --- | --- |
| `0x00` | 普通停止 |
| `0x01` | 用户急停 |
| `0x02` | 任务结束 |
| `0x03` | 上层故障 |
| `0x04` | 调试停止 |

LEN：

```text
1
```

### 8.4 SET_MODE `0x12`

RDK 设置 STM32 工作模式。

Payload：

| 字段 | 类型 | 长度 | 值 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | `uint8` | 1 | 见下表 | 目标模式 |

`mode`：

| 值 | 名称 | 说明 |
| --- | --- | --- |
| `0x00` | `IDLE` | 空闲，PWM 为 0 |
| `0x01` | `MANUAL` | 手动/键盘控制 |
| `0x02` | `AUTO` | 自动任务控制 |
| `0x03` | `TEST` | 台架测试 |

LEN：

```text
1
```

### 8.5 STATUS `0x81`

STM32 周期回传基础状态。

Payload：

| 字段 | 类型 | 长度 | 单位 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | `uint8` | 1 | - | 当前模式 |
| `estop` | `uint8` | 1 | - | 0 正常，1 急停触发 |
| `fault_code` | `uint16` | 2 | - | 故障码 |
| `battery_mv` | `uint16` | 2 | mV | 电池电压，未知填 0 |
| `last_cmd_seq` | `uint8` | 1 | - | 最近成功执行的 RDK 命令 SEQ |
| `comm_state` | `uint8` | 1 | - | 通信状态 |

LEN：

```text
8
```

`comm_state`：

| 值 | 含义 |
| --- | --- |
| `0x00` | 正常 |
| `0x01` | 500ms 未收到有效速度命令 |
| `0x02` | 2000ms 心跳超时 |
| `0x03` | CRC 错误计数过多 |

### 8.6 ODOM `0x82`

STM32 回传四轮编码器增量。

Payload：

| 字段 | 类型 | 长度 | 单位 | 说明 |
| --- | --- | --- | --- | --- |
| `delta_lf` | `int16` | 2 | tick | 左前轮增量 |
| `delta_rf` | `int16` | 2 | tick | 右前轮增量 |
| `delta_lr` | `int16` | 2 | tick | 左后轮增量 |
| `delta_rr` | `int16` | 2 | tick | 右后轮增量 |

LEN：

```text
8
```

如果编码器暂未接入：

```text
delta_lf = 0
delta_rf = 0
delta_lr = 0
delta_rr = 0
```

### 8.7 FAULT `0x83`

STM32 出现故障时主动上报。

Payload：

| 字段 | 类型 | 长度 | 说明 |
| --- | --- | --- | --- |
| `fault_code` | `uint16` | 2 | 故障码 |
| `detail` | `uint16` | 2 | 附加信息 |

LEN：

```text
4
```

故障码：

| 值 | 名称 | 说明 |
| --- | --- | --- |
| `0x0000` | `NO_FAULT` | 无故障 |
| `0x0001` | `ESTOP_TRIGGERED` | 急停触发 |
| `0x0002` | `HEARTBEAT_TIMEOUT` | 心跳超时 |
| `0x0003` | `CMD_TIMEOUT` | 速度命令超时 |
| `0x0004` | `CRC_ERROR_LIMIT` | CRC 错误过多 |
| `0x0005` | `MOTOR_DRIVER_FAULT` | 电机驱动故障 |
| `0x0006` | `BATTERY_LOW` | 电池电压低 |

### 8.8 ACK `0x84`

STM32 对关键命令做确认。

Payload：

| 字段 | 类型 | 长度 | 说明 |
| --- | --- | --- | --- |
| `ack_type` | `uint8` | 1 | 被确认的命令 TYPE |
| `ack_seq` | `uint8` | 1 | 被确认的命令 SEQ |
| `result` | `uint8` | 1 | 0 成功，非 0 失败 |

LEN：

```text
3
```

`result`：

| 值 | 含义 |
| --- | --- |
| `0x00` | 成功 |
| `0x01` | CRC 错误 |
| `0x02` | LEN 错误 |
| `0x03` | TYPE 不支持 |
| `0x04` | 当前模式不允许 |
| `0x05` | 急停中拒绝执行 |
| `0x06` | 速度超限，已限幅 |

## 9. STM32 安全状态机

STM32 必须独立保证底盘安全。

状态：

```text
BOOT
IDLE
ACTIVE
CMD_TIMEOUT
HEARTBEAT_TIMEOUT
ESTOP
FAULT
```

状态说明：

| 状态 | PWM | 进入条件 | 退出条件 |
| --- | --- | --- | --- |
| `BOOT` | 0 | 上电复位 | 初始化完成 |
| `IDLE` | 0 | 未进入运动模式 | 收到 `SET_MODE MANUAL/AUTO` |
| `ACTIVE` | 按命令输出 | 收到有效 `CMD_VEL` | 超时、急停、STOP、故障 |
| `CMD_TIMEOUT` | 0 | 500ms 未收到有效 `CMD_VEL` | 收到有效 `CMD_VEL` |
| `HEARTBEAT_TIMEOUT` | 0 | 2000ms 未收到 `HEARTBEAT` | 重新收到心跳并人工确认 |
| `ESTOP` | 0 | 急停输入触发 | 急停释放并重新使能 |
| `FAULT` | 0 | 驱动/电池/CRC 等严重故障 | 人工复位或清故障 |

硬性规则：

- 上电默认 PWM 为 0。
- CRC 错误帧不得执行。
- `LEN > 64` 的帧必须丢弃。
- 500ms 未收到有效 `CMD_VEL`，速度置零。
- 2000ms 未收到 `HEARTBEAT`，进入超时故障。
- 急停触发立即停 PWM，不等待 RDK 命令。
- 所有速度命令必须限幅。

## 10. RDK 端执行流程

### 10.1 第 1 步：确认串口设备

执行：

```bash
ls -l /dev/ttyS* /dev/ttyUSB* 2>/dev/null
```

记录：

```text
设备名：
接线方式：USB-TTL / RDK 40PIN
波特率：115200
```

### 10.2 第 2 步：普通字符串回显

目标：

```text
RDK 发送 hello
STM32 回传 hello
RDK 打印 hello
```

通过标准：

- 10 次发送至少 10 次收到。
- 无乱码。
- 拔掉 TX/RX 后能明确看到超时。

### 10.3 第 3 步：发送 HEARTBEAT

目标：

```text
RDK 每 100ms 发送 HEARTBEAT
STM32 返回 ACK
```

通过标准：

- 连续 60 秒无崩溃。
- ACK 数量接近发送数量。
- STM32 `comm_state = 0x00`。

### 10.4 第 4 步：发送 CMD_VEL 零速度

目标：

```text
vx=0, vy=0, wz=0
```

通过标准：

- STM32 ACK 成功。
- PWM 输出保持 0。
- STATUS 正常。

### 10.5 第 5 步：发送低速 CMD_VEL

初期只允许：

```text
vx_mm_s = 50
vy_mm_s = 0
wz_mrad_s = 0
```

通过标准：

- STM32 解析正确。
- 四轮目标方向符合预期。
- 空载 PWM 输出符合预期。
- 不允许直接落地高速测试。

## 11. STM32 端执行流程

### 11.1 第 1 步：创建基础工程

配置：

```text
SYSCLK 84 MHz
USART 115200 8N1
LED GPIO output
UART RX interrupt one byte
```

交付物：

```text
STM32 可以烧录
LED 心跳闪烁
串口可以发送 hello stm32
```

### 11.2 第 2 步：串口回显

逻辑：

```text
收到一个字节，原样发回
```

交付物：

```text
RDK 或电脑串口助手可看到回显
```

### 11.3 第 3 步：协议状态机

解析状态：

```text
WAIT_SOF1
WAIT_SOF2
READ_VER
READ_TYPE
READ_SEQ
READ_LEN
READ_PAYLOAD
READ_CRC_LOW
READ_CRC_HIGH
VERIFY
DISPATCH
```

错误处理：

- 帧头不匹配，继续寻找 `0xAA`。
- LEN 超过 64，丢弃。
- CRC 错误，丢弃并计数。
- TYPE 不支持，回 ACK 失败。

### 11.4 第 4 步：ACK 与 STATUS

先不接电机，只实现：

```text
收到 HEARTBEAT -> ACK
收到 CMD_VEL -> ACK
周期发送 STATUS
```

通过标准：

- RDK 能统计 ACK。
- RDK 能打印 STATUS。
- CRC 故意改错时，STM32 不 ACK 成功。

### 11.5 第 5 步：PWM 空载

不接电机，先用 LED、万用表、示波器或逻辑分析仪验证：

```text
CMD_VEL vx=0 -> PWM duty=0
CMD_VEL vx=50 -> PWM duty 有小幅输出
STOP -> PWM duty=0
通信超时 -> PWM duty=0
急停触发 -> PWM duty=0
```

### 11.6 第 6 步：接 MDDS20 单电机

接线前：

- 电机必须固定。
- 低压/限流优先。
- 急停可用。
- PWM duty 初始上限不超过 10%。

测试顺序：

1. STOP 命令，确认电机不动。
2. 低速正转 1 秒。
3. 停止。
4. 低速反转 1 秒。
5. 停止。
6. 急停触发。

## 12. 四轮速度映射策略

第一阶段 STM32 可以先不做复杂运动学，只验证单轴前进。

最小版本：

```text
vx > 0: 四轮同向前进
vx < 0: 四轮同向后退
vy = 0
wz = 0
```

第二阶段再实现麦克纳姆轮运动学。

建议公式，待实车方向校正：

```text
wheel_lf = vx - vy - k * wz
wheel_rf = vx + vy + k * wz
wheel_lr = vx + vy - k * wz
wheel_rr = vx - vy + k * wz
```

其中：

```text
k = (wheel_base + track_width) / 2
```

注意：

- 公式符号必须通过实车校正。
- 每个电机都要有 `reverse` 参数。
- 初期可以把 `vy` 和 `wz` 禁用，只测 `vx`。

## 13. 测试计划

### 13.1 阶段 A：无电机通信测试

| 测试项 | 操作 | 通过标准 |
| --- | --- | --- |
| 串口设备识别 | RDK 查看 `/dev/ttyUSB0` 或 `/dev/ttyS*` | 设备存在 |
| 字符串回显 | RDK 发 hello | STM32 原样回传 |
| HEARTBEAT | RDK 10Hz 发送 | STM32 ACK |
| STATUS | STM32 10Hz 回传 | RDK 正确解析 |
| CRC 错误 | RDK 故意发错 CRC | STM32 丢弃 |
| 超时停车 | 停止 RDK 程序 | STM32 进入超时状态 |

### 13.2 阶段 B：PWM 空载测试

| 测试项 | 操作 | 通过标准 |
| --- | --- | --- |
| 上电默认 | STM32 上电 | PWM=0 |
| 零速度 | 发送 `CMD_VEL 0,0,0` | PWM=0 |
| 小速度 | 发送 `vx=50` | PWM 小占空比 |
| STOP | 发送 STOP | PWM=0 |
| 急停 | 触发急停输入 | PWM=0 |
| 超时 | 拔掉 RDK 串口或停止程序 | PWM=0 |

### 13.3 阶段 C：单电机台架测试

| 测试项 | 操作 | 通过标准 |
| --- | --- | --- |
| 正转 | duty 5%-10% | 电机低速正转 |
| 反转 | DIR 反向 | 电机低速反转 |
| 停车 | STOP | 电机停止 |
| 急停 | 按急停 | 电机立即停止 |
| 方向记录 | 拍摄视频 | 更新 pinmap 和方向参数 |

### 13.4 阶段 D：四轮悬空测试

| 测试项 | 操作 | 通过标准 |
| --- | --- | --- |
| LF | 单独驱动左前轮 | 方向符合编号 |
| RF | 单独驱动右前轮 | 方向符合编号 |
| LR | 单独驱动左后轮 | 方向符合编号 |
| RR | 单独驱动右后轮 | 方向符合编号 |
| vx 前进 | 四轮联动 | 方向一致 |
| STOP | 停车 | 四轮停止 |

### 13.5 阶段 E：底盘低速落地测试

初始限制：

```text
vx_mm_s <= 100
vy_mm_s = 0
wz_mrad_s = 0
测试距离 <= 0.5m
```

通过标准：

- 可低速前进。
- 可停止。
- 急停有效。
- 日志记录完整。
- 视频素材可用于复盘。

## 14. 每日记录要求

每次测试复制：

```text
docs/validation/daily-log-template.md
```

保存为：

```text
docs/validation/daily/YYYY-MM-DD.md
```

必须填写：

```text
日期
测试人
commit id
RDK 串口设备名
STM32 固件版本或 commit id
接线方式
测试命令
测试结果
串口输出
照片/视频路径
是否通过
下一步
```

## 15. 分工

### 戎择辰

- 编写 RDK Python 串口测试脚本。
- 实现打包/解析帧函数。
- 实现 ACK/STATUS 日志打印。
- 编写 STM32 模拟器，便于无硬件开发。
- 维护 `docs/protocols/rdk_stm32_uart.md`。

### 戴鹏林

- 配置 STM32 工程。
- 完成串口回显、状态机、ACK、STATUS。
- 完成 PWM 空载、单电机、四轮测试。
- 每天上传验证记录。
- 所有电机相关测试必须现场看护。

### 曹鸿治

- 维护接线记录、接口编号、照片标注。
- 整理测试视频和硬件说明。
- 记录采购、到货、风险项。
- 帮助把测试结果整理成答辩材料。

## 16. 当天可执行清单

2026-05-11 起，建议按以下顺序推进：

1. 确认 STM32 使用哪个 USART：USART1/USART2/USART6 选一个。
2. 在 `docs/hardware/pinmap.md` 写入 TX/RX/GND 真实引脚。
3. 在 STM32CubeMX 中配置 USART 115200 8N1。
4. 烧录 STM32 串口回显程序。
5. RDK 通过 USB-TTL 连接 STM32。
6. RDK 安装 `pyserial`。
7. RDK 运行字符串回显测试。
8. 实现 `HEARTBEAT` 和 `ACK`。
9. 实现 `CMD_VEL` 零速度解析。
10. 实现 STM32 超时停车逻辑。
11. 编写当天验证记录。

## 17. 常见问题排查

### 17.1 没有任何数据

检查：

- TX/RX 是否交叉。
- GND 是否共地。
- 波特率是否都是 115200。
- RDK 串口设备名是否正确。
- STM32 是否真的烧录成功。
- 串口是否被其他程序占用。

### 17.2 收到乱码

检查：

- 波特率不一致。
- 时钟配置错误导致 UART 波特率偏差。
- USB-TTL 电平不对。
- GND 没接好。

### 17.3 偶发 CRC 错误

检查：

- 线太长或靠近电机动力线。
- GND 不稳定。
- 串口线没有固定。
- RDK 和 STM32 的 CRC 计算范围不一致。
- CRC 高低字节顺序不一致。

### 17.4 电机方向反了

处理：

- 先停止测试。
- 记录 LF/RF/LR/RR 哪个方向反。
- 优先在软件中添加 `reverse` 参数。
- 必要时再交换电机线。
- 更新 `docs/hardware/pinmap.md` 和接线照片。

### 17.5 急停无效

立即停止所有电机测试。

检查：

- 急停是否实际切断动力使能。
- STM32 GPIO 是否能读到急停状态。
- 急停触发后 PWM 是否立即为 0。
- `STATUS.estop` 是否回传 1。

急停未验证通过前，不允许底盘落地运行。

## 18. 完成标准

本计划完成时，应满足：

- RDK 能找到串口设备并打开。
- STM32 能通过 UART 与 RDK 收发数据。
- `HEARTBEAT`、`CMD_VEL`、`STATUS`、`ACK` 四种帧稳定运行。
- CRC 错误帧不会执行。
- STM32 通信超时会自动停车。
- 急停触发会立即停车。
- PWM 空载测试通过。
- 单电机台架测试通过。
- 四轮悬空方向测试通过。
- 每次测试都有 `docs/validation/daily/` 记录。

## 19. 参考资料

- D-Robotics RDK X5 官方硬件说明：`https://developer.d-robotics.cc/rdk_doc/en/Quick_start/hardware_introduction/rdk_x5/`
- D-Robotics RDK GPIO/UART 使用文档：`https://developer.d-robotics.cc/rdk_doc/Basic_Application/40pin_user_guide/`
- STMicroelectronics STM32F411 产品资料：`https://www.st.com/en/microcontrollers-microprocessors/stm32f411ce.html`
- STMicroelectronics STM32CubeIDE：`https://www.st.com/en/development-tools/stm32cubeide.html`
