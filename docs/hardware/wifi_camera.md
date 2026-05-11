# 固定摄像头 WiFi 接入方案

## 结论

固定监控摄像头可以通过 WiFi 把视频数据传给 RDK X5。推荐链路是：

```text
固定摄像头 --WiFi/路由器--> RDK X5 --ROS2--> /fixed_camera/image_raw
```

RDK X5 官方硬件文档说明开发板具备 Wi-Fi 天线接口，支持 2.4GHz/5GHz WiFi 传输；HDMI 也支持实时显示网络流画面。因此固定摄像头只要能输出 RTSP/HTTP 码流，RDK X5 就可以在同一局域网内拉流。

## 推荐网络拓扑

### 方案 A：摄像头和 RDK 接入同一个路由器

```text
WiFi Router/AP
  ├── Fixed Camera: 192.168.1.64
  └── RDK X5:       192.168.1.20
```

优点是稳定、便于 PC 同时调试。比赛和联调优先用这个方案。

### 方案 B：摄像头自带热点，RDK 连接摄像头热点

```text
Fixed Camera AP
  └── RDK X5
```

适合临时测试，但不利于 RDK 同时访问互联网、PC SSH 和云端服务。只建议备用。

## 摄像头参数记录

| 项 | 值 |
| --- | --- |
| 摄像头型号 | TBD |
| WiFi SSID | TBD |
| 摄像头 IP | TBD |
| RDK X5 IP | TBD |
| RTSP/HTTP URL | TBD |
| 用户名/权限 | TBD，不提交真实密码 |
| 分辨率 | 推荐 1280x720 |
| 帧率 | 推荐 10-15 fps |
| 码率 | 推荐 2-4 Mbps |

不要把真实摄像头密码提交到仓库。运行时用环境变量传入 `SOURCE_URI` 或 `CAMERA_URL`。

## RDK 侧验证

1. 确认 RDK 已连接到摄像头所在 WiFi。

```bash
ip -brief addr
ping -c 3 CAMERA_IP
```

2. 检查 RTSP 端口和解码。

```bash
CAMERA_URL=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
./rdk_x5/scripts/check_wifi_camera.sh
```

3. 启动 ROS2 接入。

```bash
SOURCE_TYPE=opencv \
SOURCE_URI=rtsp://USER:PASSWORD@CAMERA_IP:554/stream1 \
WIDTH=1280 HEIGHT=720 FPS=15 \
./rdk_x5/scripts/run_fixed_camera.sh
```

4. 查看话题。

```bash
ros2 topic hz /fixed_camera/image_raw
ros2 topic echo /fixed_camera/status
```

## 稳定性建议

- 优先使用 5GHz WiFi，摄像头和 RDK 距离路由器不要过远。
- 固定摄像头码流建议从 1080p/30fps 降到 720p/10-15fps，减少延迟和丢帧。
- RTSP 在 WiFi 下默认使用 TCP，避免 UDP 丢包造成花屏。
- 比赛现场提前固定路由器、摄像头 IP、RDK IP，避免 DHCP 地址变化。
- RDK 如果放在金属外壳里，按官方说明接外置天线增强信号。
