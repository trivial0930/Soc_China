# 接口编号表

所有接口编号必须与实物标签一致。改线后必须更新本文件和对应照片。

## RDK X5

| 接口 | 连接对象 | 用途 | 线号 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| USB-A | STM32 Type-C | 底盘命令+状态(USB CDC) | — | ✅ 实测通过 | `/dev/ttyACM*`,by-id 固定名;取代旧 40-pin UART |
| USB-A | 雷神 N10 雷达 | 激光雷达 | — | ✅ | `/dev/ttyACM0`(1a86 CH343)|
| MIPI CSI | RDK Camera | 主视觉 | TBD | 待确认 | 注意排线方向 |
| USB | RPLIDAR A2 | 雷达 | TBD | 待确认 | 如保留 |
| USB/ETH/Wi-Fi | Fixed Monitor Camera | 固定监控输入 | TBD | 待确认 | USB 用 `/dev/video*`，网络摄像头记录 RTSP/HTTP 地址 |
| I2C | PCA9685 | 云台舵机控制 | TBD | 待确认 | 推荐方案 |
| SPI/I2C | Thermal-90 (SenXor MI48) | 热成像 | 见下表 | 已接线 | `/dev/spidev5.0` + `/dev/i2c-5`，详见下表 |

## 微雪 Thermal-90 模组接线（已实测）

模组：微雪 Thermal-90（Meridian MI0801 + MI48x3 SenXor），80×62 辐射测温。
I2C 配置寄存器（默认 0x40，可改 0x41）；SPI 读全帧（mode 0、MSB、16-bit）；RESET、READY/DATA_READY 为 GPIO。
SPI 节点 `/dev/spidev5.0`，I2C 总线 `/dev/i2c-5`。

| 模组引脚 | 功能 | RDK X5 40-pin（物理脚） | 状态 | 备注 |
| --- | --- | --- | --- | --- |
| VCC | 电源 | 1（3.3V） | 已接 | 用 3.3V 避免信号上拉到 5V 风险；若模组供电不足再评估 5V |
| GND | 共地 | 6（GND） | 已接 | 也可用其他 GND |
| SDA | I2C 数据 | 3（I2C SDA） | 已接 | 地址 0x40，与云台 AS5600(0x36) 不冲突，可共用 |
| SCL | I2C 时钟 | 5（I2C SCL） | 已接 | `/dev/i2c-5` |
| MOSI | SPI 主发 | 19（SPI MOSI） | 已接 | 读帧时发 0x0000 产生时钟 |
| MISO | SPI 主收 | 21（SPI MISO） | 已接 | 16-bit 帧数据 |
| CLK | SPI 时钟 | 23（SPI SCLK） | 已接 | mode 0 |
| SS  | SPI 片选 | **7（GPIO 软件片选）** | 已接 | 原接 24(CSN1) 但 spidev 不驱动 CS，改用 BOARD 7 软件片选 |
| RESET | 复位 | 16（GPIO） | 已接（软复位为主） | Hobot.GPIO 导不出 16，驱动已容错；MI48 构造时软上电 |
| READY | 数据就绪 | 13（GPIO） | 已接（未用） | 驱动改用轮询 STATUS.DATA_READY，不依赖此脚 |

> ✅ **SPI 已打通（2026-06-07）**：用 `spidev1.1`(SPI1, `34010000.spi`)，自定义 overlay
> `dtoverlay_spi1_spidev1_x5_rdk` 在云台 overlay 之后 re-enable SPI1；`SS` 改接 **BOARD 7** 做软件片选
> （spidev 在本 SoC 不驱动 CS），SPI 速率降到 4MHz，开启 MI48 片上滤波 → 读到正常热成像。
> 工作参数：`--spi-bus 1 --spi-device 1 --i2c-bus 5 --cs-gpio-pin 7`。MOSI/MISO/SCLK 仍在 19/21/23。

## STM32F411CEU6（事实源:固件 main.c app_motor_hw + hal_msp.c,2026-06-14 实测核对）

底盘链路已从 40-pin UART 改为**黑药丸原生 USB CDC(Type-C)**(RDK serial3↔i2c5 引脚硬冲突,见 [[stm32-usb-cdc-migration]])。
四轮电机/编码器经**转接板**分组引出(左 LF+LR、右 RF+RR),完整连接器引脚表见
`docs/hardware/pcb_breakout_pinout.md`,速查卡见 `docs/hardware/wiring_quick_ref.md`。

| 链路 | 连接对象 | STM32 脚 | 状态 | 备注 |
| --- | --- | --- | --- | --- |
| USB CDC | RDK USB-A | PA11/PA12(Type-C) | ✅ 实测通过 | 底盘通信,枚举为 `/dev/ttyACM*`(by-id 固定名)|
| SWD | ST-Link | PA13(DIO)/PA14(CLK) | ✅ | 烧录调试 |
| USART2 | (冗余,未用) | PA2/PA3 | 闲置 | 通信已迁 USB;RX 未 arm |

**四轮电机控制 + 编码器(权威引脚表)**

| 轮 | PWM | IN1 | IN2 | 编码器A | 编码器B | 编码器定时器 | 连接器 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LF 左前 | PA6 | PB12 | PB13 | PA15 | PB3 | TIM2 | J_L_CTRL / J_L_ENC |
| LR 左后 | PA7 | PB14 | PB15 | PA0 | PA1 | TIM5 | J_L_CTRL / J_L_ENC |
| RF 右前 | PB1 | PB8 | PB9 | PA8 | PA9 | TIM1 | J_R_CTRL / J_R_ENC |
| RR 右后 | PB0 | PA4 | PA5 | PB6 | PB7 | TIM4 | J_R_CTRL / J_R_ENC |

> 编码器以固件 `send_odom` 为准(LF←TIM2、LR←TIM5,含 06-11 左侧交叉补偿);
> MSP 注释里 TIM2="LR"/TIM5="LF" 是旧标签,勿信。
> 编码器供电 **3V3**(霍尔上限 3.6V,勿接 5V)。每条 PWM/IN 线加 10k 下拉。
> PC13 = 板载 LED;空闲脚 PB10/PB11/PA10/PA2/PA3。
