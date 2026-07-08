# Soc_China

面向电子实验室安全的智能巡检机器人与管理系统。

基于地瓜机器人 RDK X5(感知/决策/语音)+ STM32F411(麦轮底盘运动控制)的移动巡检机器人,配套 FastAPI 管理后端与 Flutter 手机 App,实现实验室危险检测、语音交互、远程遥控、SLAM 建图与自主导航的完整闭环。

## 核心功能

- **三级分层危险决策**:L1 端侧 YOLO11 + 热成像快速检测 → L1.5 端侧小 VLM 分级 → L2/L3 云端多模态大模型深度分析,兼顾响应速度与成本。
- **RGB + 热成像多模态融合**:Thermal-90 热成像与 MIPI 相机标定融合,检测过热设备等热学危险并联动语音播报。
- **端侧语音交互**:唤醒词 KWS + SenseVoice ASR + TTS 全离线运行,语音下发巡检指令、播报告警。
- **App 遥控 + 雷达安全层**:手机 App 虚拟摇杆低延迟遥控,激光雷达本地反应式避障门控,断网自动停车。
- **SLAM 建图与自主导航**:App 一键切换建图模式,slam_toolbox 建图;AMCL + Nav2(MPPI 全向控制)自主导航。
- **管理端系统**:FastAPI + SQLite 后端(SSE 实时推送、命令下行队列、断网补传)+ Flutter 四屏 App(告警/报告/操作/设置)。

## 目录结构

```text
app/        管理后端(FastAPI)、Flutter 手机 App、演示 PWA
docs/       架构设计、硬件接线、操作手册、通信协议
rdk_x5/     RDK X5 侧 ROS2 工作区(感知/决策/语音/导航各包)、脚本、地图
stm32/      STM32 固件(麦轮驱动、编码器、速度 PID、USB CDC 通信)
shared/     RDK 与 STM32 共用协议、事件结构定义
sim/        无硬件时的 STM32 模拟器和样例数据
tests/      host 侧单元测试
tools/      安装、测试、日志收集脚本
```

模型训练与部署产物:`yolo_lab_training_export_20260603/`(YOLO 训练脚本与配置)、`rdk_x5_lab_detector_deploy_20260603/`(RDK 端检测器运行时)。

## 快速开始

- 后端 + App:见 `app/README.md` 与 `app/API_SPEC.md`。
- RDK 侧 ROS2 工作区:见 `rdk_x5/README.md`。
- STM32 固件:见 `stm32/README.md`。
- 建图与导航操作:见 `docs/ops/lab_mapping_procedure.md`、`docs/ops/lab_nav_procedure.md`。

## 测试

```bash
python -m pytest tests/
```

涉及电机、主电池、底盘运动的真机测试,必须有人现场看护。
