# 接口编号表

所有接口编号必须与实物标签一致。改线后必须更新本文件和对应照片。

## RDK X5

| 接口 | 连接对象 | 用途 | 线号 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| UART_TX | STM32 UART_RX | 速度命令/控制帧 | TBD | 待确认 | 3.3V TTL |
| UART_RX | STM32 UART_TX | 状态回传 | TBD | 待确认 | 3.3V TTL |
| GND | STM32 GND | 共地 | TBD | 待确认 | 必须共地 |
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
> 工作参数：`--spi-bus 1 --spi-device 1 --i2c-bus 5 --cs-gpio-pin 7`。详见
> `docs/validation/daily/2026-06-07-thermal-90-bringup.md`。MOSI/MISO/SCLK 仍在 19/21/23。

## STM32F411CEU6

| 接口 | 连接对象 | 用途 | 线号 | 状态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| UART_RX | RDK UART_TX | 接收控制帧 | TBD | 待确认 | 3.3V TTL |
| UART_TX | RDK UART_RX | 回传状态 | TBD | 待确认 | 3.3V TTL |
| PWM1/DIR1 | MDDS20-1 A | 左前轮 | LF | 待确认 | 方向需实测 |
| PWM2/DIR2 | MDDS20-1 B | 右前轮 | RF | 待确认 | 方向需实测 |
| PWM3/DIR3 | MDDS20-2 A | 左后轮 | LR | 待确认 | 方向需实测 |
| PWM4/DIR4 | MDDS20-2 B | 右后轮 | RR | 待确认 | 方向需实测 |
| GPIO | 急停 | 安全停机 | TBD | 待确认 | 必须实测 |
