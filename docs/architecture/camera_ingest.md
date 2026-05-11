# 固定监控摄像头接入

## 目标

把固定监控摄像头画面接入 RDK X5，统一转换为 ROS2 图像话题，供后续实验室异常检测、告警事件生成、机器人复核任务使用。

## 模块边界

| 模块 | 职责 |
| --- | --- |
| 固定监控摄像头 | 提供 RTSP/HTTP 码流、USB/UVC 画面或 MIPI 图像 |
| RDK X5 | 采集图像、发布 ROS2 话题、运行视觉检测和告警逻辑 |
| STM32 | 只处理底盘、电机、编码器、急停等底层控制 |
| 管理端/演示端 | 查看图像、告警记录和巡检结果 |

## ROS2 话题

| 话题 | 类型 | 说明 |
| --- | --- | --- |
| `/fixed_camera/image_raw` | `sensor_msgs/msg/Image` | 固定监控原始图像 |
| `/fixed_camera/camera_info` | `sensor_msgs/msg/CameraInfo` | 相机基础信息，未标定时只包含宽高 |
| `/fixed_camera/status` | `std_msgs/msg/String` | JSON 状态，包含源地址、帧数、是否正常 |

## 推荐链路

1. 真实固定监控或网络摄像头优先使用 WiFi/以太网 + `source_type=opencv` + RTSP 地址。
2. 临时 USB 摄像头可以使用 RDK 官方 `hobot_usb_cam`，即 `source_type=usb`。
3. RDK MIPI 摄像头用于机器人本体视觉或桌面验收时使用 `source_type=mipi`。
4. 无硬件时用本地视频或图片目录模拟固定监控输入。

## WiFi 视频链路

固定摄像头和 RDK X5 可以接入同一个 2.4GHz/5GHz WiFi 网络，摄像头提供 RTSP/HTTP 码流，RDK X5 拉流后统一发布 `/fixed_camera/image_raw`。WiFi 下 RTSP 默认使用 TCP，减少丢包导致的花屏。

```text
Fixed Camera -> WiFi Router/AP -> RDK X5 -> perception_camera -> ROS2 topics
```

现场需要记录摄像头 IP、RDK IP、码流 URL、分辨率、帧率和码率。真实密码不提交到仓库。

## 验证标准

- `ros2 topic hz /fixed_camera/image_raw` 能稳定输出目标帧率。
- `/fixed_camera/status` 中 `ok=true`，`state=streaming`。
- Websocket 预览可以在 PC 浏览器看到实时画面。
- 断开 RTSP 或拔掉 USB 摄像头后，状态话题能报告失败并自动重连。
