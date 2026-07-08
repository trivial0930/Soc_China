# teleop_safety

App 遥控接收 + 雷达本地安全层(反应式避障 A 阶段)。

## 节点
- **lidar_safety_node**:`/scan` + `/cmd_vel_teleop` → 门控 → `/cmd_vel` + `/safety/status`。
  纯本地实时,网络延迟/断不影响避障。逻辑在 `teleop_safety/gate.py`(host 单测 `tests/test_teleop_gate.py`)。
  - `<stop_dist`(0.30m)砍平移、保旋转;`<slow_dist`(0.60m)按距离缩放;旋转 wz 恒透传;
    `/cmd_vel_teleop` 超 0.5s 无更新 → 停(deadman)。
- **teleop_receiver_node**:10Hz `GET /api/robot/teleop` → `/cmd_vel_teleop`;
  `/safety/status` → `POST /api/robot/teleop/status`。后端 setpoint 超 `staleness_ms` → 0。

## 启动(先起雷达 + bringup)
```bash
# 1) 雷达 /scan
ros2 run lslidar_driver lslidar_driver_node --ros-args --params-file src/lslidar_driver/params/lsx10.yaml
# 2) 底盘 odom/EKF/TF + stm32_bridge(订 /cmd_vel)
ros2 launch chassis_bringup bringup.launch.py
# 3) 遥控 + 安全层
ros2 launch teleop_safety teleop_safety.launch.py \
    backend_url:=http://192.168.128.100:8000 ingest_token:=<token>
```

## 依赖后端/前端
- 后端:`POST/GET /api/robot/teleop`(最新速度,覆盖式)、`POST/GET /api/robot/teleop/status`。契约见 `app/API_SPEC.md` §4.7。
- 前端:遥控页虚拟摇杆 + 安全状态显示。

## 参数
见 `config/teleop_safety.yaml`(扇区角、stop/slow 阈值、轮询率、backend_url/token 等)。

## 测试
`python3 -m unittest tests.test_teleop_gate`(纯门控逻辑)。
