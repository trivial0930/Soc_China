# RDK Scripts

RDK X5 侧运行脚本。

## 摄像头

- `detect_cameras.sh`：列出 `/dev/video*`、V4L2 支持格式和当前网络地址。
- `check_wifi_camera.sh`：检测 WiFi/RTSP 固定摄像头 IP、端口和视频帧解码。
- `run_fixed_camera.sh`：启动固定监控摄像头接入。

示例：

```bash
./rdk_x5/scripts/detect_cameras.sh
CAMERA_URL=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 ./rdk_x5/scripts/check_wifi_camera.sh

SOURCE_TYPE=opencv SOURCE_URI=/dev/video0 ./rdk_x5/scripts/run_fixed_camera.sh
SOURCE_TYPE=opencv SOURCE_URI=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 ./rdk_x5/scripts/run_fixed_camera.sh
SOURCE_TYPE=usb SOURCE_URI=/dev/video0 ./rdk_x5/scripts/run_fixed_camera.sh
SOURCE_TYPE=mipi ./rdk_x5/scripts/run_fixed_camera.sh
```

放 RDK X5 上直接运行的辅助脚本，例如相机采集、日志打包、环境检查。

## UART 调试

无硬件协议自检：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py
python3 rdk_x5/scripts/uart_send_test.py --dry-run --mode manual --vx 50
```

真实串口或模拟器联调：

```bash
python3 rdk_x5/scripts/uart_protocol_test.py --port /dev/ttyUSB0
python3 rdk_x5/scripts/uart_send_test.py --port /dev/ttyUSB0 --duration 10 --mode manual --vx 50
```

依赖：

```bash
python3 -m pip install pyserial
```
