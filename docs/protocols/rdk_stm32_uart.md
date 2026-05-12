# RDK-STM32 UART 协议

状态：v1，可按本仓库代码调试。

## 链路职责

RDK X5 发送速度、模式和停止命令。STM32 回传编码器、里程计、急停、电池和故障状态。

## 基础要求

- 电平：3.3V TTL。
- 连接：RDK TX -> STM32 RX，RDK RX -> STM32 TX，GND 共地。
- 波特率：115200 8N1。
- 频率：`CMD_VEL` 建议 20 Hz，`HEARTBEAT` 和 `STATUS` 建议 10 Hz。
- 安全：500 ms 未收到有效速度命令置零，2 s 心跳超时进入安全停止。
- 校验：CRC16-CCITT-FALSE，低字节在前。
- 字节序：全部多字节整数使用 little-endian。

## 帧格式

| 字段 | 长度 | 说明 |
| --- | --- | --- |
| SOF | 2 | 帧头，固定 `0xAA 0x55` |
| VER | 1 | 协议版本，当前 `0x01` |
| TYPE | 1 | 帧类型 |
| SEQ | 1 | 序号，0-255 循环 |
| LEN | 1 | payload 长度 |
| PAYLOAD | N | 数据内容 |
| CRC16 | 2 | CRC16-CCITT-FALSE |

`LEN` 最大 64。CRC16 计算范围为：

```text
VER + TYPE + SEQ + LEN + PAYLOAD
```

CRC16 参数：

```text
poly=0x1021 init=0xFFFF refin=false refout=false xorout=0x0000
```

## RDK -> STM32

| TYPE | 名称 | 内容 | 说明 |
| --- | --- | --- | --- |
| `0x01` | HEARTBEAT | `uptime_ms uint32` | 心跳 |
| `0x10` | CMD_VEL | `vx_mm_s int16`, `vy_mm_s int16`, `wz_mrad_s int16` | 速度命令 |
| `0x11` | STOP | `reason uint8` | 停止 |
| `0x12` | SET_MODE | `mode uint8` | 模式切换 |

## STM32 -> RDK

| TYPE | 名称 | 内容 | 说明 |
| --- | --- | --- | --- |
| `0x81` | STATUS | `mode uint8`, `estop uint8`, `fault_code uint16`, `battery_mv uint16`, `last_cmd_seq uint8`, `comm_state uint8` | 状态 |
| `0x82` | ODOM | `delta_lf int16`, `delta_rf int16`, `delta_lr int16`, `delta_rr int16` | 编码器增量 |
| `0x83` | FAULT | `fault_code uint16`, `detail uint16` | 故障 |
| `0x84` | ACK | `ack_type uint8`, `ack_seq uint8`, `result uint8` | 命令确认 |

## 枚举

`mode`：

| 值 | 名称 |
| --- | --- |
| `0x00` | IDLE |
| `0x01` | MANUAL |
| `0x02` | AUTO |
| `0x03` | TEST |

`comm_state`：

| 值 | 名称 |
| --- | --- |
| `0x00` | OK |
| `0x01` | CMD_TIMEOUT |
| `0x02` | HEARTBEAT_TIMEOUT |
| `0x03` | CRC_ERROR_LIMIT |

`ACK.result`：

| 值 | 名称 |
| --- | --- |
| `0x00` | OK |
| `0x01` | CRC_ERROR |
| `0x02` | LEN_ERROR |
| `0x03` | UNSUPPORTED_TYPE |
| `0x04` | MODE_NOT_ALLOWED |
| `0x05` | ESTOP_ACTIVE |
| `0x06` | CLAMPED |

## 代码位置

- Python 参考实现：`shared/protocol/rdk_stm32_uart.py`
- RDK 无硬件协议自检：`python3 rdk_x5/scripts/uart_protocol_test.py`
- RDK 串口联调：`python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyUSB0 --mode manual --vx 50`
- STM32 模拟器：`python3 sim/stm32_simulator/serial_simulator.py`
- STM32 C 模块：`stm32/firmware/stm32_motion_controller/Core/`
