# RDK-STM32 UART 协议草案

状态：草案，待三人确认。

## 链路职责

RDK X5 发送速度、模式和停止命令。STM32 回传编码器、里程计、急停、电池和故障状态。

## 基础要求

- 电平：3.3V TTL。
- 连接：RDK TX -> STM32 RX，RDK RX -> STM32 TX，GND 共地。
- 频率：控制帧建议 20 Hz，心跳超时 2 s 进入安全停止。
- 校验：建议使用 CRC8 或 CRC16，最终实现前固定。

## 帧格式

| 字段 | 长度 | 说明 |
| --- | --- | --- |
| SOF | 2 | 帧头，建议 `0xAA 0x55` |
| TYPE | 1 | 帧类型 |
| LEN | 1 | payload 长度 |
| PAYLOAD | N | 数据内容 |
| CRC | 1/2 | 校验 |

## RDK -> STM32

| TYPE | 名称 | 内容 | 说明 |
| --- | --- | --- | --- |
| 0x01 | HEARTBEAT | seq, timestamp | 心跳 |
| 0x10 | CMD_VEL | vx, vy, wz | 速度命令 |
| 0x11 | STOP | reason | 停止 |
| 0x12 | SET_MODE | mode | 模式切换 |

## STM32 -> RDK

| TYPE | 名称 | 内容 | 说明 |
| --- | --- | --- | --- |
| 0x81 | STATUS | mode, fault, estop, battery_mv | 状态 |
| 0x82 | ODOM | ticks_lf, ticks_rf, ticks_lr, ticks_rr | 编码器 |
| 0x83 | FAULT | code, detail | 故障 |

## 待确认问题

- CRC8 还是 CRC16。
- 速度单位使用 m/s、rad/s 还是缩放整数。
- 编码器计数是否用增量还是累计值。
- 急停是独立引脚上报，还是同时切断动力使能。
