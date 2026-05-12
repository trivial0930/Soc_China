# 2026-05-11 STM32 UART 代码修改日志

整理时间：2026-05-12

记录范围：本次对话中围绕 RDK X5 与 STM32F411CEU6 UART 通信协议进行的代码编写、修复、合并和验证。

## 修改范围

- 新增 RDK X5 与 STM32F411CEU6 UART 通信协议实现。
- 新增 Python 参考协议栈，用于 RDK 侧发帧、收帧、CRC 校验和离线自测。
- 新增 STM32 侧 C 语言协议模块，用于帧编码、帧解析、CRC16-CCITT-FALSE 校验和常用 payload 打包。
- 新增 STM32 运动安全控制模块，用于命令超时停车、心跳超时停车、急停状态处理和 PWM 输出接口预留。
- 新增 STM32 串口模拟器，便于无硬件时在电脑上模拟 STM32 回传 `ACK`、`STATUS`、`ODOM`。
- 修复模拟器在没有 RDK 读端时可能出现的 `BlockingIOError: [Errno 35] Resource temporarily unavailable`。
- 修复一次误操作导致的 STM32 工程 `Core/` 目录缺失问题，恢复并补回 UART 协议 C 模块。
- 合并 STM32CubeMX 新生成工程 `stm32_motion_controller_CubeMX`，并将协议模块同步进 CubeMX 工程。
- 更新 CubeMX/CubeIDE 工程文件，使 `rdk_stm32_uart.c`、`motion_controller.c` 能被工程识别。

## 修改原因

- 支持 RDK X5 通过 40pin UART 与 STM32F411CEU6 通信，后续用于控制移动底盘。
- 建立 RDK 与 STM32 的统一通信契约，避免两端对帧格式、字节序、CRC、帧类型理解不一致。
- 在真实硬件联调前提供 Python 自测和 STM32 模拟器，降低串口接线、波特率、CRC 错误的排查难度。
- 为 STM32 侧后续接入电机控制预留清晰接口：先完成 UART 协议收发，再接 PWM、编码器和急停。
- 修复 CubeMX 重新生成代码后手写协议文件被遗漏的问题，保证工程目录可继续编译和维护。

## 涉及文件

协议文档：

- `docs/protocols/rdk_stm32_uart.md`
- `shared/protocol/rdk_stm32_frame.md`

RDK/Python 侧：

- `shared/protocol/rdk_stm32_uart.py`
- `shared/__init__.py`
- `shared/protocol/__init__.py`
- `rdk_x5/scripts/uart_protocol_test.py`
- `rdk_x5/scripts/uart_send_test.py`
- `rdk_x5/scripts/README.md`

STM32 侧：

- `stm32/firmware/stm32_motion_controller/Core/Inc/rdk_stm32_uart.h`
- `stm32/firmware/stm32_motion_controller/Core/Src/rdk_stm32_uart.c`
- `stm32/firmware/stm32_motion_controller/Core/Inc/motion_controller.h`
- `stm32/firmware/stm32_motion_controller/Core/Src/motion_controller.c`
- `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
- `stm32/firmware/stm32_motion_controller/stm32_motion_controller.ioc`
- `stm32/firmware/stm32_motion_controller_CubeMX/Core/Inc/rdk_stm32_uart.h`
- `stm32/firmware/stm32_motion_controller_CubeMX/Core/Src/rdk_stm32_uart.c`
- `stm32/firmware/stm32_motion_controller_CubeMX/Core/Inc/motion_controller.h`
- `stm32/firmware/stm32_motion_controller_CubeMX/Core/Src/motion_controller.c`
- `stm32/firmware/stm32_motion_controller_CubeMX/STM32CubeIDE/.project`
- `stm32/firmware/stm32_motion_controller_CubeMX/.mxproject`

STM32 文档与模拟器：

- `stm32/docs/uart_setup.md`
- `sim/stm32_simulator/serial_simulator.py`
- `sim/stm32_simulator/README.md`

测试与工具：

- `tests/test_rdk_stm32_uart.py`
- `tests/test_stm32_c_modules.py`
- `tests/test_stm32_simulator.py`
- `tools/run_smoke_test.sh`

## 协议内容摘要

- UART 参数：`115200 8N1`。
- 电平：`3.3V TTL`。
- 帧头：`0xAA 0x55`。
- 帧格式：`SOF + VER + TYPE + SEQ + LEN + PAYLOAD + CRC16`。
- 协议版本：`0x01`。
- 最大 payload：64 字节。
- CRC：`CRC16-CCITT-FALSE`，计算范围为 `VER + TYPE + SEQ + LEN + PAYLOAD`，低字节在前。
- RDK 到 STM32：
  - `HEARTBEAT`
  - `CMD_VEL`
  - `STOP`
  - `SET_MODE`
- STM32 到 RDK：
  - `STATUS`
  - `ODOM`
  - `FAULT`
  - `ACK`
- 安全策略：
  - 500 ms 未收到有效速度命令则停车。
  - 2 s 未收到心跳则进入安全停止状态。

## 测试情况

电脑本地测试：

- 已执行：

```bash
./tools/run_smoke_test.sh
```

- 最近一次结果：

```text
Ran 8 tests in 1.241s
OK
```

- 覆盖内容：
  - Python 协议帧编码/解码。
  - CRC16 参考向量校验。
  - 流式解析器错误恢复。
  - STM32 C 协议模块通过 `gcc -Wall -Wextra -Werror` 编译测试。
  - STM32 运动控制模块命令超时、急停逻辑测试。
  - STM32 模拟器基础行为测试。

CubeMX/CubeIDE 状态：

- 已完成 STM32CubeMX 工程生成。
- 已配置 USART1：
  - `PA9` 为 `USART1_TX`
  - `PA10` 为 `USART1_RX`
  - 波特率 `115200`
  - 8 data bits、无校验、1 stop bit、无硬件流控
  - 已开启 USART1 中断
- 已配置系统时钟：
  - HSE：25 MHz
  - SYSCLK：84 MHz
  - AHB：84 MHz
  - APB1：42 MHz
  - APB2：84 MHz
- 尚未在本记录中确认 STM32CubeIDE 图形界面完整 Build 通过。

RDK 实机测试：

- 已将代码同步到 RDK X5：`/root/Soc_China`。
- 已在 RDK 上运行 smoke test，结果通过。
- 已在 RDK 上运行 UART 发送测试：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --duration 10 --mode manual --vx 0
```

- 当时现象：
  - RDK 能打开 `/dev/ttyS1` 并持续发送帧。
  - `tx`、`heartbeat_tx`、`cmd_vel_tx` 计数正常增加。
  - `ack=0`
  - `status=0`
  - `odom=0`
  - `fault=0`
  - parser 错误计数为 0。
- 判断：
  - RDK 发送侧基本可用。
  - STM32 当时尚未烧录响应协议的固件，或 USART1 接线/共地/固件接收逻辑尚未完成。

烧录情况：

- 当前记录中尚未确认已将协议固件烧录到 STM32。
- 当前 `main.c` 仍主要是 CubeMX 初始化与空循环，尚未完整接入 `HAL_UART_RxCpltCallback`、协议分发、`ACK/STATUS` 回传逻辑。

## 仓库同步记录

本次代码整理与上传采用独立功能分支：

```text
feature/stm32-uart-protocol
```

- 已将 UART 协议、RDK 侧脚本、STM32 侧协议模块、模拟器、测试与文档整理为一次独立提交。
- 已先拉取并基于最新 `origin/main` 整理分支，保留队友已经上传的 STM32 电机控制代码。
- 合并过程中仅处理了 `tools/run_smoke_test.sh` 的内容冲突，将队友已有的摄像头/环境检查与本次 UART 协议检查合并到同一个 smoke test 中。
- 已更新 `.gitignore`，排除 STM32CubeIDE/CubeMX 生成的构建目录与临时备份目录，例如 `Debug/`、`Release/`、`build/`、`Core_Before_Modified/`。
- 已清理本地未跟踪的重复副本文件，例如 `xxx 2.py`、`xxx 2.h`、`xxx 2.md`，这些副本未进入提交，也未上传到 GitHub。
- 已将功能分支推送到 GitHub：

```text
git@github.com:trivial0930/Soc_China.git
```

- 当前对应提交：

```text
ab3d098 feat(stm32): add uart protocol controller
```

- 当前功能分支可用于发起 Pull Request：

```text
https://github.com/trivial0930/Soc_China/pull/new/feature/stm32-uart-protocol
```

## 目前存在的问题

- STM32 侧协议模块已经存在，但还没有完整接入 `main.c` 的中断接收和主循环。
- CubeIDE 图形界面 Build 结果尚未记录。
- STM32 尚未实测回传 `ACK`、`STATUS`。
- 电机 PWM、编码器、急停输入尚未与 UART 命令联调。
- RDK 与 STM32 实际接线后仍需确认：
  - RDK Pin 8 TX 接 STM32 PA10 RX。
  - RDK Pin 10 RX 接 STM32 PA9 TX。
  - RDK GND 与 STM32 GND 共地。
  - 两端均为 3.3V TTL，不接 5V 信号。

## 后续计划

- 在 STM32CubeIDE 中打开：

```text
stm32/firmware/stm32_motion_controller
```

- 先执行一次 Build，记录是否生成 `Debug/stm32_motion_controller.elf`。
- 在 `Core/Src/main.c` 中接入：
  - `rdk_parser_t`
  - `HAL_UART_Receive_IT`
  - `HAL_UART_RxCpltCallback`
  - `CMD_VEL`、`HEARTBEAT`、`SET_MODE`、`STOP` 分发逻辑
  - `ACK` 回传
  - 周期性 `STATUS` 回传
- 烧录到 STM32 后，用 RDK 执行：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --duration 10 --mode manual --vx 0
```

- 验收目标：
  - RDK 侧 `ack` 计数大于 0。
  - RDK 侧 `status` 计数大于 0。
  - `crc_errors=0`。
  - `len_errors=0`。
- 再与电机控制模块联调：
  - `CMD_VEL=0` 时 PWM 保持 0。
  - 小速度命令时四路 PWM 方向和大小符合预期。
  - 命令超时后 500 ms 内停车。
  - 心跳超时后进入安全停止。
  - 急停触发后拒绝继续执行速度命令。
