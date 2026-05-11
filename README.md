# Soc_China

面向电子实验室安全的智能巡检与管理系统。

本仓库采用 monorepo 结构，统一管理 RDK X5 侧软件、STM32 底层程序、跨端协议、硬件文档、现场验证记录和比赛材料。

## 协作分工

- 戎择辰：RDK X5、ROS2、视觉、串口节点、日志系统。
- 戴鹏林：硬件保管、烧录、接线、上电、真实硬件验证、日志和截图回传。
- 曹鸿治：BOM、接线记录、照片标注、硬件说明、答辩材料。

硬件集中在戴鹏林处。涉及电机、主电池、MDDS20、底盘运动的测试，必须有人现场看护。

## 目录

```text
docs/       架构、硬件、协议、验证记录、报告和原始材料索引
rdk_x5/     RDK X5 侧 ROS2 工作区、脚本和配置
stm32/      STM32 固件、CubeMX 工程和底层说明
shared/     RDK 与 STM32 共用协议、事件结构和配置格式
sim/        无硬件时的模拟器和样例数据
tools/      安装、测试、日志收集等项目脚本
```

## 日常流程

1. 远程成员从 `main` 拉新分支开发代码或文档。
2. 提交 PR 前写清楚运行命令、交付物和验证方式。
3. 戴鹏林在真实硬件上拉取代码测试。
4. 每次测试都记录到 `docs/validation/`，包含 commit id、命令、现象、截图或串口输出。

## 当前优先级

1. 在 RDK X5 上实测 WiFi 固定摄像头 RTSP 输入，记录 IP、码流、分辨率、帧率和截图。
2. 在 RDK X5 上编译并启动 `perception_camera`，确认 `/fixed_camera/image_raw` 稳定发布。
3. 在 STM32 CubeMX 工程中接入麦轮驱动回调，实测 MDDS20 四轮方向。
4. 完成 RDK-STM32 UART 协议实现和实板互测。
5. 每次真实硬件测试都补充 `docs/validation/` 记录。

## 当前已实现

- STM32 麦轮底盘驱动：`stm32/firmware/Core/Inc/mecanum_drive.h`、`stm32/firmware/Core/Src/mecanum_drive.c`。
- 固定监控摄像头接入：`rdk_x5/ros2_ws/src/perception_camera/`。
- WiFi/RTSP 固定摄像头方案：`docs/hardware/wifi_camera.md`。
- 摄像头链路检测脚本：`rdk_x5/scripts/check_wifi_camera.sh`。
- RDK 固定摄像头启动脚本：`rdk_x5/scripts/run_fixed_camera.sh`。

RDK 上的 WiFi 摄像头启动示例：

```bash
./tools/setup_rdk.sh
CAMERA_URL=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 ./rdk_x5/scripts/check_wifi_camera.sh
SOURCE_TYPE=opencv SOURCE_URI=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 ./rdk_x5/scripts/run_fixed_camera.sh
```
