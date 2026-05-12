# RDK-STM32 UART Frame Reference

This file mirrors the code in `shared/protocol/rdk_stm32_uart.py` and the STM32 C module in `stm32/firmware/stm32_motion_controller/Core/`.

## Fixed Choices

- Frame head: `AA 55`
- Version: `01`
- Maximum payload: 64 bytes
- Byte order: little-endian
- CRC: CRC16-CCITT-FALSE over `VER TYPE SEQ LEN PAYLOAD`
- CRC storage: low byte first
- `CMD_VEL`: `vx_mm_s int16`, `vy_mm_s int16`, `wz_mrad_s int16`
- `ODOM`: encoder deltas, not cumulative counts

## Quick Checks

```bash
python3 -m unittest discover -s tests
python3 rdk_x5/scripts/uart_protocol_test.py
python3 rdk_x5/scripts/uart_send_test.py --dry-run --mode manual --vx 50
```

Use the simulator when no STM32 board is available:

```bash
python3 sim/stm32_simulator/serial_simulator.py
# In another terminal, use the PTY printed by the simulator:
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttysXXX
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttysXXX --duration 5 --mode manual --vx 50
```
