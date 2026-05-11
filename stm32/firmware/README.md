# STM32 Firmware

当前目录放置 STM32F411CEU6 固件源代码。

## 已有模块

- `Core/Inc/mecanum_drive.h`
- `Core/Src/mecanum_drive.c`

麦轮底盘驱动提供四轮运动学、PWM/DIR 命令输出、方向反转校准和 2 s 控制帧超时停车。硬件接线和 CubeMX 集成说明见 `../docs/mecanum_drive.md`。
