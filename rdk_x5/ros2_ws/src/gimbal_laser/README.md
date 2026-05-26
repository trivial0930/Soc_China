# gimbal_laser

RDK X5 二自由度云台控制 ROS2 包。

## 功能

- 读取两路 AS5600 编码器角度。
- 控制两路云台电机驱动板 EN 和三相 PWM。
- 订阅目标角度和使能命令。
- 发布云台角度和 JSON 状态。
- 提供 home 和 stop 服务。

## 构建

运行云台节点前需要 I2C Python 依赖：

```bash
sudo apt update
sudo apt install -y python3-smbus2 i2c-tools
```

```bash
source /opt/tros/humble/setup.bash
cd ~/Soc_China/rdk_x5/ros2_ws
colcon build --symlink-install --packages-select gimbal_laser
source install/setup.bash
```

## 启动

```bash
ros2 launch gimbal_laser gimbal_controller.launch.py
```

默认配置见 `config/gimbal.yaml`。第一次实测前先确认：

```bash
ls /dev/i2c-*
sudo i2cdetect -y 5
sudo i2cdetect -y 0
ls /sys/class/pwm
```

## 手动测试

```bash
ros2 topic pub --once /gimbal/enable std_msgs/msg/Bool "{data: true}"
ros2 topic pub --once /gimbal/target_angle geometry_msgs/msg/Vector3 "{x: 5.0, y: 0.0, z: 0.0}"
ros2 topic echo /gimbal/status
ros2 service call /gimbal/stop std_srvs/srv/Trigger "{}"
```
