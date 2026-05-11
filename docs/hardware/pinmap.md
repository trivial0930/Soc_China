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
| SPI/I2C | Thermal-44/90 | 热成像 | TBD | 待确认 | 按模块要求供电 |

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
