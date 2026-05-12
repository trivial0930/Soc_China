# 2026-05-12 STM32 UART 与麦轮底盘集成日志

整理时间：2026-05-12

记录范围：本次对话中围绕 RDK X5 通过 UART 控制 STM32F411CEU6，并将 STM32 UART 协议逻辑与四轮麦克纳姆底盘控制逻辑合并的设计、实现、构建修复和实机串口确认过程。

## 修改范围

- 阅读并确认 `stm32/firmware` 下已有两类代码：
  - `stm32_motion_controller`：RDK X5 与 STM32 UART 通信工程。
  - `stm32/firmware/Core/Inc|Src/mecanum_drive.*`：麦克纳姆底盘运动学与四轮输出接口。
- 采用“方案一”：
  - 先完成 UART 协议到麦轮控制的软件链路合并。
  - 暂不假设 PWM/DIR 引脚与 TIM 通道。
  - 硬件输出保持为可替换回调，等待电机驱动、pinmap 和实物接线确认后再接实际 GPIO/PWM。
- 新增方案设计文档：
  - `docs/superpowers/specs/2026-05-12-rdk-stm32-mecanum-uart-integration-design.md`
- 新增实现计划文档：
  - `docs/superpowers/plans/2026-05-12-rdk-stm32-mecanum-uart-integration.md`
- 将 `mecanum_drive.c/h` 加入 STM32CubeIDE 工程目录：
  - `stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h`
  - `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c`
- 修改 `main.c`，使 `CMD_VEL` 不再只解析后丢弃，而是进入麦轮底盘控制：
  - `vx_mm_s` 转为 `vx_mps`
  - `vy_mm_s` 转为 `vy_mps`
  - `wz_mrad_s` 转为 `wz_radps`
  - 调用 `MecanumDrive_SetVelocity()`
- 在 `STOP`、`IDLE`、命令超时、心跳超时和急停状态下统一调用停车。
- 增加测试：
  - 工程内 `mecanum_drive` 模块的 host-side C 编译测试。
  - `main.c` 中 UART 到麦轮控制链路的文本集成检查。
- 修复 STM32CubeIDE 构建失败：
  - 发现 `stm32_motion_controller` 工程目录中存在大量未跟踪的 `* 2.c`、`* 2.h`、`* 2.s` 等副本。
  - CubeIDE 自动生成的 `Debug/subdir.mk` 同时编译正常文件和 ` 2` 副本，导致链接阶段 `multiple definition`。
  - 将这些副本移出工程目录并备份到 `.tmp`。
  - 清理旧 `Debug` 构建目录并重新构建。
- 确认 RDK X5 40pin 直连 STM32 时，当前有效串口为：
  - `/dev/ttyS1`

## 修改原因

- 让 RDK X5 能通过既有 UART 协议向 STM32 下发底盘速度命令。
- 让 STM32 在收到 `CMD_VEL` 后进入麦克纳姆四轮运动学控制链路，而不是只完成协议 ACK/STATUS。
- 在没有电机、电机驱动和最终 pinmap 的情况下，先验证软件链路：
  - RDK 发帧。
  - STM32 收帧。
  - STM32 解析命令。
  - STM32 更新模式与安全状态。
  - STM32 计算四轮控制输出。
- 避免在硬件未确认时写死 PWM/DIR 引脚，降低误接线或错误输出风险。
- 修复 CubeIDE 构建中的重复编译问题，使工程恢复为可 Build 状态。

## 涉及文件

设计与计划：

- `docs/superpowers/specs/2026-05-12-rdk-stm32-mecanum-uart-integration-design.md`
- `docs/superpowers/plans/2026-05-12-rdk-stm32-mecanum-uart-integration.md`

STM32 工程：

- `stm32/firmware/stm32_motion_controller/Core/Src/main.c`
- `stm32/firmware/stm32_motion_controller/Core/Inc/mecanum_drive.h`
- `stm32/firmware/stm32_motion_controller/Core/Src/mecanum_drive.c`

测试：

- `tests/test_stm32_c_modules.py`
- `tests/test_stm32_main_uart_integration.py`

构建修复相关：

- `stm32/firmware/stm32_motion_controller/Debug/`
- `.tmp/stm32_motion_controller_duplicate_2_files_20260512_215359/`

## 方案设计摘要

本次采用分层设计：

- UART 协议层：
  - `rdk_stm32_uart.c/h`
  - 只负责帧格式、CRC、payload 打包与解析。
  - 不直接操作电机或 GPIO。
- 应用调度层：
  - `main.c`
  - 负责 UART 中断接收、帧分发、模式状态、超时检查、ACK/STATUS 回传。
  - 将有效 `CMD_VEL` 转给底盘控制。
- 麦轮驱动层：
  - `mecanum_drive.c/h`
  - 负责 `vx/vy/wz` 到四轮速度的麦轮运动学转换。
  - 负责限幅、方向反转、PWM 比例计算和超时停车。
- 硬件输出层：
  - 当前阶段为 `app_write_motor()` 回调。
  - 只记录 `app_last_motor_command`，不输出真实 PWM/DIR。
  - 后续确认引脚后再改为实际 TIM/GPIO 输出。

## STM32 主循环集成摘要

`main.c` 当前关键逻辑：

- 初始化阶段：
  - `app_chassis_init()`
  - `app_uart_start()`
- 主循环：
  - `app_tick()`
  - 调用 `MecanumDrive_UpdateTimeout(&app_chassis, now)`
  - 周期性发送 `STATUS`
- `CMD_VEL`：
  - 长度正确、非急停、非 `IDLE` 时执行。
  - 调用 `app_cmd_to_chassis(&cmd)`。
  - 更新 `app_last_cmd_ms` 和 `app_last_cmd_seq`。
- `SET_MODE`：
  - 切到 `IDLE` 时调用 `app_chassis_stop()`。
- `STOP`：
  - 切回 `IDLE`。
  - 调用 `app_chassis_stop()`。
- 超时与急停：
  - 命令超时、心跳超时、急停均调用 `app_chassis_stop()`。

## 当前硬件状态

- 当前只有 RDK X5 与 STM32 两块开发板。
- 暂无电机。
- 暂无电机驱动模块。
- 暂未确认 PWM/DIR 实际引脚。
- 因此当前可测内容是软件与 UART 链路，不是实际轮子动作。

当前已确认接线方向应为：

```text
RDK TX  -> STM32 PA10 / USART1_RX
RDK RX  -> STM32 PA9  / USART1_TX
RDK GND -> STM32 GND
```

当前已确认 RDK 40pin 直连 STM32 的串口设备为：

```text
/dev/ttyS1
```

## 测试情况

### 本地 Python/host-side 测试

合并实现前基线：

```bash
python3 -m unittest discover -s tests
```

结果：

```text
Ran 9 tests in 1.483s
OK
```

新增测试后先进入 TDD RED 阶段：

- `test_mecanum_drive_project_module_velocity_stop_and_timeout` 失败，原因是工程内尚不存在 `mecanum_drive.c`。
- `test_main_starts_uart_rx_and_can_reply_to_rdk` 失败，原因是 `main.c` 尚未包含麦轮集成点。

实现后测试：

```bash
python3 -m unittest tests.test_stm32_c_modules
```

结果：

```text
Ran 3 tests in 1.579s
OK
```

全量测试：

```bash
python3 -m unittest discover -s tests
```

结果：

```text
Ran 10 tests in 1.400s
OK
```

合并到 `main` 后再次测试：

```bash
python3 -m unittest discover -s tests
```

结果：

```text
Ran 10 tests in 1.825s
OK
```

### STM32CubeIDE 构建测试

最初用户在 STM32CubeIDE 中看到：

```text
Build Failed. 240 errors, 0 warnings
multiple definition
```

排查结果：

- `Debug/Core/Src/subdir.mk` 同时包含：
  - `../Core/Src/main.c`
  - `../Core/Src/main 2.c`
  - `../Core/Src/rdk_stm32_uart.c`
  - `../Core/Src/rdk_stm32_uart 2.c`
  - 其他多个重复源文件
- `Debug/Drivers/STM32F4xx_HAL_Driver/Src/subdir.mk` 同时包含：
  - `../Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c`
  - `../Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart 2.c`
  - 其他多个重复 HAL 源文件

根因：

- 工程目录内存在大量未跟踪的 ` 2` 副本。
- CubeIDE managed build 会扫描项目源目录，把这些副本也当作有效源文件编译。
- 链接器因此看到同名函数的多份定义。

处理：

- 将副本移出 `stm32_motion_controller` 工程树。
- 备份目录：

```text
.tmp/stm32_motion_controller_duplicate_2_files_20260512_215359/
```

- 删除旧 `Debug` 构建目录。
- 使用 STM32CubeIDE headless build 重新构建：

```bash
/Applications/STM32CubeIDE.app/Contents/MacOS/STM32CubeIDE \
  --launcher.suppressErrors \
  -nosplash \
  -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data /Users/sthefirst/Desktop/Soc_China/.tmp/stm32cubeide_headless_workspace \
  -import /Users/sthefirst/Desktop/Soc_China/stm32/firmware/stm32_motion_controller \
  -cleanBuild stm32_motion_controller/Debug
```

结果：

```text
21:55:24 Build Finished. 0 errors, 0 warnings. (took 472ms)
```

固件大小：

```text
text    data    bss    dec    hex    filename
15068   12      1828   16908  420c   stm32_motion_controller.elf
```

### RDK X5 串口测试建议

由于使用 40pin 直连，先扫描 `/dev/ttyS1` 到 `/dev/ttyS7`，不要优先使用 `/dev/ttyS0`，因为 `/dev/ttyS0` 可能是系统 console。

扫描命令：

```bash
for p in /dev/ttyS1 /dev/ttyS2 /dev/ttyS3 /dev/ttyS4 /dev/ttyS5 /dev/ttyS6 /dev/ttyS7; do
  echo "===== testing $p ====="
  timeout 5 python3 rdk_x5/scripts/uart_protocol_test.py --port "$p" --baud 115200 --duration 2
  echo "exit=$?"
done
```

用户随后确认：

```text
有效串口是 /dev/ttyS1
```

后续稳定测试命令：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttyS1 --baud 115200 --duration 3
```

10 秒零速度通信闭环：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --baud 115200 --duration 10 --mode manual --vx 0 --vy 0 --wz 0
```

小速度软件链路测试：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --baud 115200 --duration 5 --mode manual --vx 50 --vy 0 --wz 0
```

当前无电机驱动时，预期观察项是：

- RDK 能收到 STM32 的 `ACK`。
- RDK 能收到周期性 `STATUS`。
- `crc_errors=0`。
- `len_errors=0`。
- `STOP` 能被 ACK。
- 停止命令后 STM32 能进入命令超时或安全停车状态。

## 仓库合并记录

设计文档提交：

```text
4815b59 docs: add stm32 uart mecanum integration design
```

工作树隔离设置提交：

```text
2e38398 chore: ignore local worktrees
```

实现提交：

```text
d49d5da feat(stm32): connect uart commands to mecanum drive
```

实现最初在隔离 worktree 中完成：

```text
/Users/sthefirst/Desktop/Soc_China/.worktrees/stm32-uart-mecanum-integration
```

分支：

```text
codex/stm32-uart-mecanum-integration
```

随后已本地 fast-forward 合并到 `main`：

```text
main -> d49d5da
```

合并后已清理：

- 删除 worktree：`.worktrees/stm32-uart-mecanum-integration`
- 删除本地 feature 分支：`codex/stm32-uart-mecanum-integration`

## 当前结论

- 当前有效主函数文件是：

```text
stm32/firmware/stm32_motion_controller/Core/Src/main.c
```

- `main 2.c` 是未跟踪副本，不是正式主函数。
- STM32 工程已恢复可构建状态。
- UART 协议到麦轮控制的软件链路已经接通。
- 当前阶段不输出真实 PWM/DIR，只在 `app_write_motor()` 中记录四轮命令。
- RDK 40pin 直连 STM32 的串口已确认为 `/dev/ttyS1`。

## 目前存在的问题

- 尚未接入真实电机驱动。
- 尚未确认四路 PWM/DIR 引脚和 TIM 通道。
- 尚未测量 PWM/DIR 波形。
- 尚未测试四轮实际方向、反转配置和限速参数。
- 当前 `app_write_motor()` 仍是软件记录回调，不会驱动 GPIO 或 TIM。
- 实机通信虽已定位到 `/dev/ttyS1`，但仍需记录一次完整 `ACK/STATUS` 稳定测试输出。

## 后续计划

短期：

- 在 RDK 上用 `/dev/ttyS1` 运行：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttyS1 --baud 115200 --duration 3
```

- 再运行：

```bash
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyS1 --baud 115200 --duration 10 --mode manual --vx 0 --vy 0 --wz 0
```

- 将 `ACK`、`STATUS`、`crc_errors`、`len_errors` 结果补充到日志。

中期：

- 确认最终四路 PWM/DIR 接线：
  - LF
  - RF
  - LR
  - RR
- 在 CubeMX 中配置对应 TIM PWM 和 DIR GPIO。
- 将 `app_write_motor()` 从记录回调改为真实硬件输出。
- 在没有电机时先用逻辑分析仪、示波器或 LED 验证 PWM/DIR。

后期：

- 接入电机驱动后按顺序测试：
  - 单电机空载。
  - 四轮悬空。
  - 低速落地。
  - `vx > 0` 前进。
  - `vy > 0` 左移。
  - `wz > 0` 逆时针旋转。
  - `STOP` 停车。
  - 命令超时停车。
  - 心跳超时停车。
  - 急停拒绝速度命令。
