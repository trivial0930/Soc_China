# perception_camera

RDK X5 固定监控摄像头接入包。

## 设计边界

- RDK X5 负责接入固定监控画面并发布 ROS2 图像话题。
- STM32 只负责底盘、电机、传感器底层控制，不参与图像采集。
- 固定监控输入先进入 `/fixed_camera/image_raw`，后续告警、桌面验收、复核任务从该话题订阅。

## 支持输入

| `source_type` | 输入 | 说明 |
| --- | --- | --- |
| `usb` | USB/UVC 摄像头 | 使用 RDK 官方 `hobot_usb_cam`，适合 `/dev/video*` |
| `mipi` | RDK MIPI 摄像头 | 使用 RDK 官方 `mipi_cam` |
| `opencv` | RTSP/HTTP/本地视频/图片/备用 UVC | 使用本包 `fixed_camera_node`，适合固定监控摄像头、录像回放和无硬件模拟 |

官方文档依据：

- RDK X5 支持 2.4GHz/5GHz WiFi，固定摄像头可以通过同一局域网传输 RTSP/HTTP 码流。
- RDK X5 支持 USB 摄像头，接入后会生成 `/dev/video*`。
- RDK X5 支持两路 MIPI CSI。
- TogetheROS.Bot 的 `hobot_usb_cam` 和 `mipi_cam` 发布 ROS2 标准图像消息。

## RDK 环境

RDK X5 使用 Ubuntu 22.04 / ROS2 Humble / tros.b。

```bash
source /opt/tros/humble/setup.bash
cd ~/Soc_China/rdk_x5/ros2_ws
colcon build --symlink-install --packages-select perception_camera
source install/setup.bash
```

如果使用本包 `opencv` 后端，需要系统有 OpenCV Python：

```bash
sudo apt update
sudo apt install -y python3-opencv v4l-utils
```

## 启动方式

### 1. 固定监控 RTSP 或 HTTP 流

WiFi 固定摄像头推荐使用 RTSP TCP：

```bash
ros2 launch perception_camera fixed_camera.launch.py \
  source_type:=opencv \
  source_uri:=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
  width:=1280 \
  height:=720 \
  fps:=15 \
  rtsp_transport:=tcp
```

使用脚本启动：

```bash
SOURCE_TYPE=opencv \
SOURCE_URI=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
WIDTH=1280 HEIGHT=720 FPS=15 \
./rdk_x5/scripts/run_fixed_camera.sh
```

发布话题：

- `/fixed_camera/image_raw`
- `/fixed_camera/camera_info`
- `/fixed_camera/status`

启动前可先检测 WiFi 摄像头链路：

```bash
CAMERA_URL=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
./rdk_x5/scripts/check_wifi_camera.sh
```

### 2. USB 摄像头，按 RDK 官方节点启动

```bash
ros2 launch perception_camera fixed_camera.launch.py \
  source_type:=usb \
  source_uri:=/dev/video0 \
  usb_pixel_format:=mjpeg \
  width:=1280 \
  height:=720 \
  fps:=30
```

如官方节点启动失败，先查设备支持格式：

```bash
v4l2-ctl --device=/dev/video0 --list-formats-ext
```

`hobot_usb_cam` 支持的格式包括 `mjpeg`、`mjpeg2rgb`、`yuyv`、`yuyv2rgb` 等。配置必须与摄像头硬件实际支持格式一致。

### 3. MIPI 摄像头，按 RDK 官方节点启动

```bash
ros2 launch perception_camera fixed_camera.launch.py source_type:=mipi
```

MIPI 摄像头严禁带电插拔。更换摄像头型号后，先按官方文档确认 I2C 地址和 `mipi_video_device` 参数。

### 4. 无硬件调试：本地视频或图片目录

```bash
ros2 launch perception_camera fixed_camera.launch.py \
  source_type:=opencv \
  source_uri:=/home/sunrise/datasets/lab_demo.mp4 \
  fps:=15
```

也可以把 `source_uri` 指向图片目录，本节点会按文件名排序循环发布。

## 验证命令

```bash
ros2 topic list
ros2 topic hz /fixed_camera/image_raw
ros2 topic echo /fixed_camera/status
```

Web 预览可使用 RDK 官方 websocket：

```bash
ros2 launch websocket websocket.launch.py \
  websocket_image_topic:=/fixed_camera/image_raw \
  websocket_only_show_image:=true
```

PC 浏览器访问 `http://RDK_IP:8000`。

## 现场记录

每次换摄像头或改网络地址，都需要更新：

- `docs/hardware/pinmap.md`
- `docs/validation/daily/` 当天记录
- 摄像头 IP、账号权限、码流地址、分辨率和帧率
