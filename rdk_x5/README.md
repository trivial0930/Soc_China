# RDK X5

RDK X5 侧代码和运行脚本。

建议结构：

```text
ros2_ws/
  src/
    inspection_manager/
    perception_camera/
    thermal_detector/
    lidar_navigation/
    stm32_bridge/
    gimbal_laser/
    voice_prompt/
  launch/
  config/
scripts/
```

RDK 侧提交必须写清楚运行命令和依赖版本。

## 固定监控摄像头接入

当前实现见 `ros2_ws/src/perception_camera/`。

常用命令：

```bash
# 检查 RDK 上的 USB/UVC 摄像头和网络状态
./rdk_x5/scripts/detect_cameras.sh

# 编译 RDK ROS2 摄像头接入包
./tools/setup_rdk.sh

# 启动固定监控 RTSP/HTTP/本地视频/图片/备用 UVC 输入
SOURCE_TYPE=opencv SOURCE_URI=/dev/video0 ./rdk_x5/scripts/run_fixed_camera.sh
```

RTSP 固定监控摄像头示例：

```bash
CAMERA_URL=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
./rdk_x5/scripts/check_wifi_camera.sh

SOURCE_TYPE=opencv \
SOURCE_URI=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
WIDTH=1280 HEIGHT=720 FPS=15 \
./rdk_x5/scripts/run_fixed_camera.sh
```

USB 摄像头走 RDK 官方 `hobot_usb_cam`：

```bash
SOURCE_TYPE=usb SOURCE_URI=/dev/video0 USB_PIXEL_FORMAT=mjpeg \
WIDTH=1280 HEIGHT=720 FPS=30 \
./rdk_x5/scripts/run_fixed_camera.sh
```
