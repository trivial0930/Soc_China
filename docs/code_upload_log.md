# 代码上传记录

本文档记录每次上传到远端仓库的代码日期、提交号、目录结构和主要内容。后续每次上传代码后，都需要在本文件追加一条记录。

## 记录格式

| 字段 | 说明 |
| --- | --- |
| 日期 | 上传或提交日期，使用北京时间 |
| Commit | Git 提交短哈希 |
| 标题 | 提交信息 |
| 结构 | 涉及的主要目录和文件 |
| 内容 | 本次上传实现或修改的功能 |
| 验证 | 上传前执行过的检查 |

## 2026-05-11

### 1e5eaca - Add STM32 mecanum drive module

上传时间：2026-05-11 20:14:08 +08:00

结构：

```text
stm32/
  README.md
  docs/
    mecanum_drive.md
  firmware/
    README.md
    Core/
      Inc/
        mecanum_drive.h
      Src/
        mecanum_drive.c
```

内容：

- 新增 STM32 麦轮底盘驱动模块。
- 提供 `MecanumDriveConfig`、`MecanumDrive`、四轮枚举、PWM/DIR 输出命令结构。
- 实现麦轮运动学计算：`vx_mps`、`vy_mps`、`wz_radps` 到 `LF/RF/LR/RR` 四轮角速度。
- 支持四轮方向反转校准、PWM 最大值、PWM 死区、轮速比例缩放限幅。
- 支持控制帧超时停车，默认 2000 ms。
- 新增 CubeMX/HAL 集成示例和空载验证流程。

验证：

```bash
cc -std=c99 -Wall -Wextra -Werror -I stm32/firmware/Core/Inc \
  -c stm32/firmware/Core/Src/mecanum_drive.c
```

### 8efbbdc - Add RDK fixed camera ingest

上传时间：2026-05-11 20:34:17 +08:00

结构：

```text
docs/
  architecture/
    README.md
    camera_ingest.md
  hardware/
    pinmap.md
rdk_x5/
  README.md
  scripts/
    README.md
    detect_cameras.sh
    run_fixed_camera.sh
  ros2_ws/
    src/
      perception_camera/
        README.md
        package.xml
        setup.cfg
        setup.py
        config/
          fixed_camera.yaml
        launch/
          fixed_camera.launch.py
        perception_camera/
          __init__.py
          fixed_camera_node.py
        resource/
          perception_camera
tools/
  run_smoke_test.sh
  setup_rdk.sh
```

内容：

- 新增 RDK X5 固定监控摄像头 ROS2 接入包 `perception_camera`。
- 支持三类输入：
  - `opencv`：RTSP/HTTP、本地视频、图片目录、备用 `/dev/video*`。
  - `usb`：调用 RDK 官方 `hobot_usb_cam`。
  - `mipi`：调用 RDK 官方 `mipi_cam`。
- 统一发布话题：
  - `/fixed_camera/image_raw`
  - `/fixed_camera/camera_info`
  - `/fixed_camera/status`
- 新增摄像头检测脚本 `detect_cameras.sh`。
- 新增固定摄像头启动脚本 `run_fixed_camera.sh`。
- 更新 RDK 环境构建脚本 `tools/setup_rdk.sh`。
- 新增架构文档 `docs/architecture/camera_ingest.md`。

验证：

```bash
./tools/run_smoke_test.sh
```

结果：Python 语法检查和 shell 语法检查通过。

### 7d7eb4a - Add WiFi camera streaming support

上传时间：2026-05-11 20:48:42 +08:00

结构：

```text
README.md
docs/
  README.md
  architecture/
    camera_ingest.md
  hardware/
    README.md
    wifi_camera.md
rdk_x5/
  README.md
  scripts/
    README.md
    check_wifi_camera.sh
    run_fixed_camera.sh
  ros2_ws/
    src/
      perception_camera/
        README.md
        config/
          fixed_camera.yaml
          fixed_camera_wifi.yaml
        launch/
          fixed_camera.launch.py
        perception_camera/
          fixed_camera_node.py
tools/
  run_smoke_test.sh
```

内容：

- 明确固定摄像头可以通过 WiFi 与 RDK X5 传输视频数据。
- 新增 WiFi/RTSP 固定摄像头方案文档 `docs/hardware/wifi_camera.md`。
- 新增 WiFi 摄像头配置 `fixed_camera_wifi.yaml`。
- `fixed_camera_node.py` 增加 RTSP TCP 传输、打开超时、读取超时参数。
- `run_fixed_camera.sh` 增加 `RTSP_TRANSPORT`、`OPEN_TIMEOUT_MS`、`READ_TIMEOUT_MS` 环境变量。
- 新增 `check_wifi_camera.sh`，用于检测 RDK 网络、摄像头 IP、RTSP 端口和视频帧解码。
- 更新总 README、docs 总索引、RDK README 和摄像头接入文档。

验证：

```bash
./tools/run_smoke_test.sh
```

结果：Python 语法检查和 shell 语法检查通过。

## 2026-05-12

### ab3d098 - feat(stm32): add uart protocol controller

上传时间：2026-05-12 09:10:56 +08:00

结构：

```text
docs/
  protocols/
    rdk_stm32_uart.md
    rdk_stm32_uart_execution_plan.md
rdk_x5/
  scripts/
    uart_protocol_test.py
    uart_send_test.py
shared/
  protocol/
    rdk_stm32_frame.md
    rdk_stm32_uart.py
sim/
  stm32_simulator/
    README.md
    serial_simulator.py
stm32/
  docs/
    uart_setup.md
  firmware/
    stm32_motion_controller/
tests/
  test_rdk_stm32_uart.py
  test_stm32_c_modules.py
  test_stm32_simulator.py
tools/
  run_smoke_test.sh
```

内容：

- 新增 RDK X5 与 STM32F411CEU6 的 UART 通信协议实现。
- 新增 Python 参考协议栈，支持组帧、解析、CRC16 校验和 dry-run 发送测试。
- 新增 STM32 侧协议模块和 STM32CubeMX/CubeIDE 工程目录。
- 新增 STM32 串口模拟器，用于无硬件时验证 RDK 侧发送与解析逻辑。
- 更新 smoke test，将 UART 协议自测、发送脚本 dry-run 和 STM32 C 模块编译测试纳入检查。
- 基于最新 `origin/main` 整理功能分支，保留队友已上传的 STM32 麦轮驱动模块。

验证：

```bash
./tools/run_smoke_test.sh
```

结果：8 个单元测试通过，UART 协议自测通过，dry-run 发送测试通过。

### e37f06d - docs: add stm32 uart daily log

上传时间：2026-05-12 09:31:04 +08:00

结构：

```text
docs/
  validation/
    daily/
      2026-05-11-stm32-uart-code-log.md
```

内容：

- 新增 STM32 UART 代码修改日志。
- 记录 RDK X5 与 STM32F411CEU6 UART 协议代码、CubeMX/CubeIDE 状态、RDK 实机测试现象和后续联调计划。
- 补充仓库同步记录，包括功能分支、冲突处理、`.gitignore` 更新、重复副本清理和 PR 链接。
- 详细日志见：`docs/validation/daily/2026-05-11-stm32-uart-code-log.md`

验证：

```bash
git diff --cached --check
git status --short --branch
```

结果：Markdown 格式检查通过，提交后本地分支与远端功能分支一致。

### c212e37 - feat(stm32): integrate uart protocol in main

上传时间：2026-05-12 20:46:37 +08:00

结构：

```text
stm32/
  firmware/
    stm32_motion_controller/
      Core/
        Src/
          main.c
      stm32_motion_controller.launch
tests/
  test_stm32_main_uart_integration.py
```

内容：

- 在 STM32 `main.c` 中接入 RDK-STM32 UART 协议头文件和解析器。
- 初始化 USART1 中断接收，使用 `HAL_UART_Receive_IT` 按字节接收 RDK 指令帧。
- 新增 `HAL_UART_RxCpltCallback`，在收到完整协议帧后分发 `HEARTBEAT`、`CMD_VEL`、`SET_MODE`、`STOP`。
- 新增 `ACK` 和周期性 `STATUS` 回传，便于 RDK 侧确认 STM32 已响应。
- 新增通信状态更新逻辑，覆盖命令超时、心跳超时、急停和 CRC 错误状态。
- 更新 STM32CubeIDE launch 配置。
- 新增主循环 UART 集成检查测试，避免后续 CubeMX 重生成时遗漏 UART 回调和回传逻辑。

验证：

```bash
./tools/run_smoke_test.sh
```

结果：9 个单元测试通过，UART 协议自测通过，dry-run 发送测试通过。

### 4815b59 - docs: add stm32 uart mecanum integration design

上传时间：2026-05-12 21:12:10 +08:00

结构：

```text
docs/
  superpowers/
    specs/
      2026-05-12-rdk-stm32-mecanum-uart-integration-design.md
```

内容：

- 新增 RDK X5 通过 UART 控制 STM32 麦克纳姆底盘的软件链路设计。
- 明确采用“先打通软件链路，暂不写死 PWM/DIR 引脚”的方案。
- 划分 UART 协议层、应用调度层、麦轮驱动层和硬件输出层。
- 说明当前阶段 `app_write_motor()` 只记录四轮命令，后续确认电机驱动和 pinmap 后再接真实 TIM/GPIO 输出。

验证：

```bash
python3 -m unittest discover -s tests
```

结果：设计前基线测试通过。

### 2e38398 - chore: ignore local worktrees

上传时间：2026-05-12 21:17:24 +08:00

结构：

```text
.gitignore
```

内容：

- 更新 `.gitignore`，忽略本地 `.worktrees/` 隔离工作树目录。
- 避免后续使用 Git worktree 开发时把本地临时工作目录误加入仓库。

验证：

```bash
git status --short --branch
```

结果：本地隔离 worktree 未进入提交范围。

### d49d5da - feat(stm32): connect uart commands to mecanum drive

上传时间：2026-05-12 21:29:22 +08:00

结构：

```text
docs/
  superpowers/
    plans/
      2026-05-12-rdk-stm32-mecanum-uart-integration.md
stm32/
  firmware/
    stm32_motion_controller/
      Core/
        Inc/
          mecanum_drive.h
        Src/
          main.c
          mecanum_drive.c
tests/
  test_stm32_c_modules.py
  test_stm32_main_uart_integration.py
```

内容：

- 将 `mecanum_drive.c/h` 加入 STM32CubeIDE 工程目录。
- 修改 STM32 `main.c`，使 `CMD_VEL` 进入麦克纳姆底盘控制链路。
- 将 `vx_mm_s`、`vy_mm_s`、`wz_mrad_s` 转换为麦轮模块使用的 `m/s` 和 `rad/s`。
- 在 `STOP`、`IDLE`、命令超时、心跳超时和急停状态下统一触发停车。
- 当前阶段不输出真实 PWM/DIR，只通过 `app_write_motor()` 记录四轮控制命令。
- 新增 host-side C 编译测试和 `main.c` 文本集成检查，防止后续 CubeMX 重生成时丢失关键集成点。

验证：

```bash
python3 -m unittest discover -s tests
/Applications/STM32CubeIDE.app/Contents/MacOS/STM32CubeIDE \
  --launcher.suppressErrors \
  -nosplash \
  -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
  -data /Users/sthefirst/Desktop/Soc_China/.tmp/stm32cubeide_headless_workspace \
  -import /Users/sthefirst/Desktop/Soc_China/stm32/firmware/stm32_motion_controller \
  -cleanBuild stm32_motion_controller/Debug
```

结果：10 个单元测试通过；STM32CubeIDE headless build 结果为 `0 errors, 0 warnings`。

### 24d9716 - docs: add stm32 uart mecanum daily log

上传时间：2026-05-12 22:22:36 +08:00

结构：

```text
docs/
  validation/
    daily/
      2026-05-12-stm32-uart-mecanum-integration-log.md
```

内容：

- 新增 2026-05-12 STM32 UART 与麦轮底盘集成详细日志。
- 记录方案选择、涉及文件、STM32 主循环集成摘要、RDK 串口 `/dev/ttyS1` 确认、CubeIDE 构建修复和后续计划。
- 记录 `* 2.c`、`* 2.h` 等重复副本导致 CubeIDE `multiple definition` 的原因和处理方式。
- 详细日志见：`docs/validation/daily/2026-05-12-stm32-uart-mecanum-integration-log.md`

验证：

```bash
git diff --cached --check
```

结果：Markdown 格式检查通过。

## 后续记录模板

### COMMIT_HASH - COMMIT_TITLE

上传时间：YYYY-MM-DD HH:MM:SS +08:00

结构：

```text
path/
  file
```

内容：

- TODO

验证：

```bash
TODO
```
