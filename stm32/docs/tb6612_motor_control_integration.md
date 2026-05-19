# STM32 TB6612 电机控制完善工程文档

整理时间：2026-05-19

目标：在现有 RDK X5 通过 UART 控制 STM32 的软件链路基础上，补齐 STM32 到两个 TB6612 双路电机模块的真实硬件输出设计，使 RDK X5 最终可以通过 STM32 控制四个麦克纳姆轮移动。

## 当前结论

- RDK X5 不直接接电机驱动板的 PWM、方向或使能信号。
- RDK X5 只通过 UART 与 STM32 通信。
- 四个电机全部由 STM32 输出 PWM、方向和使能信号控制。
- 本文先按抽象信号名规划，不依赖 TB6612 模块具体丝印顺序。
- 后续接线时只需要把本文中的 `IN1/IN2/PWM/EN` 对应到实物模块丝印即可。

## 范围

本阶段包含：

- 规划 STM32F411CEU6 的 UART、PWM、GPIO 引脚使用。
- 规划两个 TB6612 双路电机模块与四个麦轮的分组。
- 规划 STM32CubeMX/CubeIDE 需要新增的 TIM3 PWM 与 GPIO 配置。
- 规划 `main.c` 中 `app_write_motor()` 的真实硬件输出实现。
- 规划无电机、有驱动板、有电机三个阶段的验证流程。

本阶段不包含：

- 编码器闭环控制。
- 电机 PID。
- 里程计融合。
- ROS2 控制节点。
- 根据实物丝印生成最终接线标签。

## RDK X5 接线约束

RDK X5 只负责给 STM32 发控制帧，不直接控制 TB6612。

| 功能 | RDK X5 40Pin | STM32F411CEU6 | 说明 |
| --- | --- | --- | --- |
| UART TX | Pin 8 / UART1_TX | PA10 / USART1_RX | RDK 发 `CMD_VEL`、`SET_MODE`、`STOP` |
| UART RX | Pin 10 / UART1_RX | PA9 / USART1_TX | STM32 回 `ACK`、`STATUS` |
| GND | 公共地 | STM32 GND | RDK、STM32、电机驱动、电机电源负极必须共地 |

不要使用已经被其他模块占用的 RDK 40Pin 信号脚，包括：

```text
Pin 1, 3, 5, 11, 13, 17, 24, 27, 28, 29, 31, 32, 33, 37
```

说明：

- 这些 RDK 引脚可以继续服务原有显示屏、PWM、I2C 或编码器模块。
- 电机控制新增信号全部放在 STM32 上，不与 RDK 已用接口冲突。
- GND 不是普通信号脚，所有模块仍必须接到同一个公共地。

## 轮位命名

本文统一使用下面四个轮位：

| 中文轮位 | 代码轮位 | 说明 |
| --- | --- | --- |
| 左上 | `MECANUM_WHEEL_LF` | 左前轮 |
| 右上 | `MECANUM_WHEEL_RF` | 右前轮 |
| 左下 | `MECANUM_WHEEL_LR` | 左后轮 |
| 右下 | `MECANUM_WHEEL_RR` | 右后轮 |

代码中的数组顺序必须保持为：

```text
LF, RF, LR, RR
```

注意：这不是物理电机模块的分组顺序。即使两块 TB6612 按左右分组，`mecanum_drive` 的数组顺序仍然要按 `LF, RF, LR, RR`。

## 两个 TB6612 模块分组

建议用两个双路 TB6612 模块分别控制左侧和右侧。

| 模块 | 通道 | 轮位 | 代码轮位 |
| --- | --- | --- | --- |
| TB6612-A | 电机1 / A 通道 | 左上 | `MECANUM_WHEEL_LF` |
| TB6612-A | 电机2 / B 通道 | 左下 | `MECANUM_WHEEL_LR` |
| TB6612-B | 电机1 / A 通道 | 右上 | `MECANUM_WHEEL_RF` |
| TB6612-B | 电机2 / B 通道 | 右下 | `MECANUM_WHEEL_RR` |

这样做的好处：

- 左侧两路电机线集中到同一块驱动板。
- 右侧两路电机线集中到另一块驱动板。
- 每块驱动板只需要一根公共 `EN/STBY` 使能线。
- 后续排查时可以按左板、右板快速定位问题。

## STM32 引脚规划

当前 STM32 工程已经使用：

| 引脚 | 用途 | 是否保留 |
| --- | --- | --- |
| PA9 | USART1_TX | 保留 |
| PA10 | USART1_RX | 保留 |
| PA13 | SWDIO | 保留 |
| PA14 | SWCLK | 保留 |
| PH0 / PH1 | HSE 外部晶振 | 保留 |
| PC13 | 板载 LED / GPIO | 保留 |

建议新增 TIM3 四路 PWM：

| 轮位 | 模块通道 | PWM 引脚 | TIM 通道 | 方向 IN1 | 方向 IN2 | 使能 |
| --- | --- | --- | --- | --- | --- | --- |
| 左上 LF | TB6612-A 电机1 | PA6 | TIM3_CH1 | PA0 | PA1 | PB10 |
| 右上 RF | TB6612-B 电机1 | PB0 | TIM3_CH3 | PA4 | PA5 | PB11 |
| 左下 LR | TB6612-A 电机2 | PA7 | TIM3_CH2 | PA2 | PA3 | PB10 |
| 右下 RR | TB6612-B 电机2 | PB1 | TIM3_CH4 | PB8 | PB9 | PB11 |

选择理由：

- TIM3 的 4 个通道可以统一 PWM 频率和周期。
- PA6、PA7、PB0、PB1 不占用 USART1 的 PA9/PA10。
- PA13/PA14 仍保留给 SWD 下载和调试。
- 方向脚使用普通 GPIO，方便后续替换。
- 每块 TB6612 一个 `EN/STBY`，安全停车时可统一关闭整块驱动。

## TB6612 控制逻辑

每个电机通道按三根控制线处理：

```text
PWM: 控制速度
IN1: 方向输入 1
IN2: 方向输入 2
```

初版建议使用下面逻辑：

| `MecanumMotorCommand.dir` | IN1 | IN2 | PWM | 说明 |
| --- | --- | --- | --- | --- |
| `MECANUM_DIR_FORWARD` | 1 | 0 | `command->pwm` | 正转 |
| `MECANUM_DIR_REVERSE` | 0 | 1 | `command->pwm` | 反转 |
| `MECANUM_DIR_STOP` | 0 | 0 | 0 | 滑行停车 |

暂不使用 `IN1=1, IN2=1` 的刹车模式。原因是第一阶段优先降低风险，先验证方向、PWM 和通信链路；确认电机和驱动板表现后，再决定是否引入主动刹车。

## CubeMX 配置建议

### TIM3

新增 `TIM3`：

| 配置项 | 建议值 |
| --- | --- |
| Mode | PWM Generation CH1, CH2, CH3, CH4 |
| Prescaler | 3 |
| Counter Period | 999 |
| PWM Frequency | 约 21 kHz |
| Pulse 初始值 | 0 |
| Polarity | High |

当前工程 `APP_CHASSIS_PWM_MAX` 是 `999u`，所以 `Counter Period` 也建议设为 `999`，避免代码和定时器周期不一致。

### GPIO

新增普通 GPIO 输出：

```text
PA0, PA1, PA2, PA3, PA4, PA5, PB8, PB9, PB10, PB11
```

建议配置：

| 配置项 | 建议值 |
| --- | --- |
| Mode | GPIO_Output |
| Output type | Push Pull |
| Pull-up/Pull-down | No pull |
| Speed | Low 或 Medium |
| 初始电平 | Reset |

上电默认电平必须为低，避免 STM32 启动过程中电机误动。

## STM32 代码改造方案

现有代码已经完成：

- UART 收帧。
- `CMD_VEL` 解析。
- `CMD_VEL` 调用 `MecanumDrive_SetVelocity()`。
- 麦轮运动学计算。
- 超时、急停、STOP、IDLE 停车。

当前缺口在：

```c
static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user)
{
  app_last_motor_command[wheel] = *command;
}
```

需要把它改成真实硬件输出。

### 建议新增硬件映射结构

在 `main.c` 的 `USER CODE BEGIN PV` 区域增加：

```c
typedef struct
{
  TIM_HandleTypeDef *htim;
  uint32_t channel;
  GPIO_TypeDef *in1_port;
  uint16_t in1_pin;
  GPIO_TypeDef *in2_port;
  uint16_t in2_pin;
  GPIO_TypeDef *en_port;
  uint16_t en_pin;
} AppMotorHw;
```

映射数组必须按 `LF, RF, LR, RR` 排列：

```c
static AppMotorHw app_motor_hw[MECANUM_WHEEL_COUNT] = {
  [MECANUM_WHEEL_LF] = {&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_0, GPIOA, GPIO_PIN_1, GPIOB, GPIO_PIN_10},
  [MECANUM_WHEEL_RF] = {&htim3, TIM_CHANNEL_3, GPIOA, GPIO_PIN_4, GPIOA, GPIO_PIN_5, GPIOB, GPIO_PIN_11},
  [MECANUM_WHEEL_LR] = {&htim3, TIM_CHANNEL_2, GPIOA, GPIO_PIN_2, GPIOA, GPIO_PIN_3, GPIOB, GPIO_PIN_10},
  [MECANUM_WHEEL_RR] = {&htim3, TIM_CHANNEL_4, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, GPIOB, GPIO_PIN_11},
};
```

### 建议新增 PWM 启动函数

在 `app_chassis_init()` 前调用：

```c
static void app_motor_output_start(void)
{
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11, GPIO_PIN_SET);

  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_3);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_4);

  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_3, 0);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_4, 0);
}
```

`main()` 初始化顺序建议变为：

```c
MX_GPIO_Init();
MX_USART1_UART_Init();
MX_TIM3_Init();

app_motor_output_start();
app_chassis_init();
app_uart_start();
```

### 建议实现真实 `app_write_motor()`

```c
static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user)
{
  AppMotorHw *hw;

  (void)user;

  if ((wheel >= MECANUM_WHEEL_COUNT) || (command == 0))
  {
    return;
  }

  hw = &app_motor_hw[wheel];
  app_last_motor_command[wheel] = *command;

  if ((command->dir == MECANUM_DIR_STOP) || (command->pwm == 0u))
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_RESET);
    __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, 0u);
    return;
  }

  if (command->dir == MECANUM_DIR_FORWARD)
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_RESET);
  }
  else
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_SET);
  }

  __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, command->pwm);
}
```

后续如果要在急停时直接关闭驱动板，可以增加：

```c
static void app_motor_output_enable(uint8_t enabled)
{
  GPIO_PinState state = (enabled != 0u) ? GPIO_PIN_SET : GPIO_PIN_RESET;

  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, state);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11, state);
}
```

初版可以先保持 `EN/STBY` 上电后拉高，通过 `PWM=0` 和 `IN1=IN2=0` 停车。

## 代码文件影响范围

预计需要改动：

| 文件 | 改动 |
| --- | --- |
| `stm32/firmware/stm32_motion_controller/stm32_motion_controller.ioc` | 增加 TIM3 PWM 和 GPIO |
| `stm32/firmware/stm32_motion_controller/Core/Src/main.c` | 增加 TIM3 初始化调用、电机硬件映射、真实 `app_write_motor()` |
| `stm32/firmware/stm32_motion_controller/Core/Inc/main.h` | CubeMX 生成 GPIO 宏后会更新 |
| `stm32/firmware/stm32_motion_controller/Core/Src/stm32f4xx_hal_msp.c` | CubeMX 生成 TIM3 MSP 初始化后会更新 |
| `tests/test_stm32_main_uart_integration.py` | 增加文本检查，防止硬件输出回退成只记录内存 |

预计不需要改动：

| 文件 | 原因 |
| --- | --- |
| `rdk_x5/scripts/uart_send_test.py` | RDK 发送协议不变 |
| `shared/protocol/rdk_stm32_uart.py` | UART 帧格式不变 |
| `stm32/firmware/stm32_motion_controller/Core/Src/rdk_stm32_uart.c` | 协议层不直接控制电机 |
| `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c` | 已经输出 `dir + pwm` 抽象命令 |

## 推荐实施步骤

### 步骤 1：更新测试

在 `tests/test_stm32_main_uart_integration.py` 增加检查：

- `main.c` 包含 `HAL_TIM_PWM_Start`
- `main.c` 包含 `__HAL_TIM_SET_COMPARE`
- `main.c` 包含 `HAL_GPIO_WritePin`
- `app_write_motor()` 不再只写 `app_last_motor_command`

运行：

```bash
python3 -m unittest tests.test_stm32_main_uart_integration
```

预期：先失败，证明当前工程还没有真实硬件输出。

### 步骤 2：在 CubeMX 配置 TIM3 和 GPIO

打开：

```text
stm32/firmware/stm32_motion_controller/stm32_motion_controller.ioc
```

新增：

- TIM3_CH1：PA6
- TIM3_CH2：PA7
- TIM3_CH3：PB0
- TIM3_CH4：PB1
- GPIO Output：PA0、PA1、PA2、PA3、PA4、PA5、PB8、PB9、PB10、PB11

生成代码后检查：

- `MX_TIM3_Init()` 已生成。
- `TIM_HandleTypeDef htim3` 已生成。
- GPIO 初始输出为低。

### 步骤 3：接入真实 `app_write_motor()`

修改：

```text
stm32/firmware/stm32_motion_controller/Core/Src/main.c
```

完成：

- 添加 `AppMotorHw`。
- 添加 `app_motor_hw[]`。
- 添加 `app_motor_output_start()`。
- 在 `main()` 初始化流程中启动 TIM3 PWM。
- 将 `app_write_motor()` 改为控制 `IN1/IN2/PWM`。

### 步骤 4：本地验证

运行：

```bash
python3 -m unittest discover -s tests
```

预期：

```text
OK
```

再运行 STM32CubeIDE headless build：

```bash
/Applications/STM32CubeIDE.app/Contents/MacOS/STM32CubeIDE \
  --launcher.suppressErrors \
  -nosplash \
  -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data /Users/sthefirst/Desktop/Soc_China/.tmp/stm32cubeide_headless_workspace \
  -import /Users/sthefirst/Desktop/Soc_China/stm32/firmware/stm32_motion_controller \
  -cleanBuild stm32_motion_controller/Debug
```

预期：

```text
Build Finished. 0 errors, 0 warnings.
```

### 步骤 5：无电机验证

只接 RDK、STM32，不接电机驱动板。

RDK 上运行：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttyS1 --baud 115200 --duration 3
```

再运行低速命令：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --baud 115200 --duration 5 --mode manual --vx 50 --vy 0 --wz 0
```

用示波器、逻辑分析仪或万用表检查：

- PA6、PA7、PB0、PB1 是否输出 PWM。
- PA0/PA1、PA2/PA3、PA4/PA5、PB8/PB9 是否随方向变化。
- STOP 后 PWM 是否为 0。
- 超时后 PWM 是否为 0。

### 步骤 6：只接驱动板验证

接 TB6612，但先不接电机。

检查：

- TB6612 电源电压正确。
- STM32 与 TB6612 共地。
- `EN/STBY` 高电平后驱动板进入使能状态。
- 下发命令后电机输出端电压随 PWM 改变。
- STOP 后输出回到 0。

### 步骤 7：单电机验证

只接一个电机，建议从左上开始。

命令：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --baud 115200 --duration 3 --mode manual --vx 30 --vy 0 --wz 0
```

检查：

- 左上轮是否转动。
- 转向是否符合前进方向。
- 如果方向反了，先不要改接线，优先改 `MecanumDriveConfig.invert[MECANUM_WHEEL_LF]`。

然后依次测试：

- 左下
- 右上
- 右下

### 步骤 8：四轮悬空验证

底盘架空后测试：

| 命令 | 预期 |
| --- | --- |
| `vx > 0, vy = 0, wz = 0` | 四轮前进 |
| `vx < 0, vy = 0, wz = 0` | 四轮后退 |
| `vx = 0, vy > 0, wz = 0` | 车体向左平移 |
| `vx = 0, vy < 0, wz = 0` | 车体向右平移 |
| `vx = 0, vy = 0, wz > 0` | 逆时针旋转 |
| `STOP` | 四轮停止 |

方向不一致时，只调整对应 `invert[]`。

## 安全要求

- 电机第一次上电必须架空。
- RDK、STM32、TB6612、电机电源负极必须共地。
- 电机电源不要从 RDK 40Pin 取。
- STM32 控制信号必须确认是 3.3V 逻辑可接受。
- TB6612 模块如果有独立逻辑电源口，优先确认说明书后再接。
- 上电前确认 `EN/STBY` 默认低电平。
- 调试初期限制速度，例如 RDK 只发 `vx=30` 或 `vx=50`。
- 未验证方向前不要落地高速运行。

## 当前疑问

这些疑问不影响先写代码结构，但会影响最终接线和实车测试：

- TB6612 模块控制排针的真实丝印顺序。
- 模块 `EN/STBY` 是否每个电机独立，还是整板共用。
- 模块逻辑输入是否明确支持 STM32 3.3V 高电平。
- 普通电机接口与编码器电机接口是否共用同一路 TB6612 输出。
- 如果使用编码器电机接口，编码器输出线后续接 RDK 还是 STM32。

## 建议提交顺序

1. `test(stm32): require tb6612 hardware motor outputs`
2. `feat(stm32): add tim3 pwm gpio motor output mapping`
3. `docs(stm32): document tb6612 motor control wiring`

每个提交后都运行：

```bash
python3 -m unittest discover -s tests
```

完成硬件输出后，再运行 STM32CubeIDE 构建确认固件可编译。
