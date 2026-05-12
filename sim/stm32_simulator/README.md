# STM32 Simulator

用于远程开发 RDK 串口节点时替代真实 STM32。

目标：

- 接收 RDK 控制帧。
- 回传心跳、编码器、急停、电池和故障状态。
- 构造异常帧和超时场景。

## 运行

```bash
python3 sim/stm32_simulator/serial_simulator.py
```

启动后会打印一个伪串口路径，例如：

```text
[sim] connect RDK script to: /dev/ttys012
```

如果只启动模拟器，不启动 RDK 脚本，终端里会逐渐出现 `CMD_TIMEOUT` 和 `HEARTBEAT_TIMEOUT`。这是模拟 STM32 的安全状态机在提示“没有收到速度命令/心跳”，不是程序错误。

另开一个终端，把该路径传给 RDK 调试脚本：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttys012
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttys012 --duration 5 --mode manual --vx 50
```

常用故障注入：

```bash
python3 sim/stm32_simulator/serial_simulator.py --estop-after 3
python3 sim/stm32_simulator/serial_simulator.py --bad-crc-every 20
```
