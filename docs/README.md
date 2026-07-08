# Docs

本目录保存项目的技术文档。

- `architecture/`：总体架构、感知/决策/语音各子系统设计与部署说明。
- `hardware/`：供电、接线、接口编号、转接板布局。
- `ops/`：现场操作手册（建图、自主导航）。
- `protocols/`：RDK X5 与 STM32、模块间消息格式。

## 当前关键文档

- `architecture/three_layer_hazard_decision.md`：三级分层危险决策架构。
- `architecture/thermal_multimodal_hazard_detector.md`：RGB+热成像多模态危险检测。
- `architecture/voice_asr_setup.md`：端侧语音交互（KWS/ASR/TTS）部署。
- `hardware/pinmap.md`：RDK、STM32、摄像头和底盘相关接口编号。
- `ops/lab_mapping_procedure.md`：实验室建图操作手册。
- `ops/lab_nav_procedure.md`：Nav2 自主导航操作手册。
- `protocols/rdk_stm32_uart.md`：RDK 与 STM32 控制链路协议。
