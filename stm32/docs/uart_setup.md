# STM32F411CEU6 UART Setup

目标：让 STM32 以 `115200 8N1` 接收 RDK X5 协议帧，并用单字节中断方式驱动 `rdk_parser_feed`。

## CubeMX 建议

- MCU：STM32F411CEU6
- SYSCLK：84 MHz
- USART：优先选择开发板最容易引出的 USART1/USART2/USART6
- BaudRate：115200
- Word Length：8 bits
- Parity：None
- Stop Bits：1
- Hardware Flow Control：None
- Mode：TX/RX
- NVIC：开启对应 USART global interrupt

## 接收方式

第一版使用单字节中断：

```c
HAL_UART_Receive_IT(&huart1, &rx_byte, 1);
```

在 `HAL_UART_RxCpltCallback` 中：

```c
rdk_frame_t frame;
rdk_parse_result_t result = rdk_parser_feed(&parser, rx_byte, &frame);
if (result == RDK_PARSE_FRAME_READY) {
    dispatch_frame(&frame);
}
HAL_UART_Receive_IT(&huart1, &rx_byte, 1);
```

后续稳定后可以改成 DMA circular buffer + idle line interrupt，但第一版优先保证状态机和 CRC 一致。

## 调试顺序

1. 先做普通字符串回显。
2. 再接入 `rdk_stm32_uart.c`，验证 HEARTBEAT -> ACK。
3. 验证 CMD_VEL 0 速度 -> ACK，PWM 仍为 0。
4. 验证 CRC 错误帧不会 ACK 成功。
5. 再启用 PWM/DIR 输出。
