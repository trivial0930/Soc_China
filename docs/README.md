# Docs

本目录保存项目中需要长期协作和复盘的文档。

- `code_upload_log.md`：每次上传代码的日期、提交号、目录结构、内容和验证记录。
- `architecture/`：总体架构、演示闭环、分层处理方案。
- `hardware/`：BOM、供电、接线、接口编号、照片标注。
- `protocols/`：RDK X5 与 STM32、模块间消息格式。
- `validation/`：每日调试记录、周末联调记录、故障复盘。
- `reports/`：技术文档、PPT、视频脚本、答辩问答。
- `source/`：原始文档索引和转换说明。

## 当前关键文档

- `architecture/camera_ingest.md`：固定监控摄像头接入 RDK X5 的模块边界、ROS2 话题和验证标准。
- `hardware/wifi_camera.md`：固定摄像头通过 WiFi/RTSP 向 RDK X5 传输视频的网络方案和现场记录项。
- `hardware/pinmap.md`：RDK、STM32、摄像头和底盘相关接口编号。
- `protocols/rdk_stm32_uart.md`：RDK 与 STM32 控制链路草案。
