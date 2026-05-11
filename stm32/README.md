# STM32

STM32F411CEU6 底层控制工程。

职责：

- UART 命令解析与状态回传。
- PWM/DIR 控制 MDDS20。
- 编码器采集。
- 急停、微动开关、ToF 可选。
- 电池电压和故障状态回传。

底层代码优先保证安全和可验证，不放复杂视觉或报告逻辑。

## 当前固件模块

- `firmware/Core/Inc/mecanum_drive.h`
- `firmware/Core/Src/mecanum_drive.c`

麦轮底盘驱动说明见 `docs/mecanum_drive.md`。
