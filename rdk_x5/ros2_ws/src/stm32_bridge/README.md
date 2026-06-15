# stm32_bridge

RDK X5 ↔ STM32F411 mecanum chassis bridge (ROS 2 Humble, ament_python).

## What it does

- Subscribes **`/cmd_vel`** (`geometry_msgs/Twist`) → clamps → sends `CMD_VEL`
  over the 40-pin UART using the shared RDK-STM32 protocol
  (`shared/protocol/rdk_stm32_uart.py`).
- Sends periodic `SET_MODE` (on start) and `HEARTBEAT` (the STM32 stops the
  chassis if heartbeats stop for >2 s).
- Reads STM32 `ODOM` (4× raw 16-bit wheel counters, order LF,RF,LR,RR) →
  integrates mecanum odometry → publishes **`/odom`** (`nav_msgs/Odometry`) and
  TF `odom → base_link`.
- Republishes STM32 `STATUS` as `std_msgs/String` on **`/stm32/status`**;
  logs `FAULT` / NACK.
- On shutdown sends `STOP`.

Odometry math is the exact inverse of the firmware's `MecanumDrive_Mix`
(`stm32_bridge/mecanum_odometry.py`, unit-tested in
`tests/test_mecanum_odometry.py`).

## Hardware context (2026-06-08)

- STM32 RDK link is **USART2 on PA2/PA3** (migrated from USART1); RDK side is
  still `/dev/ttyS1` @ 115200 8N1.
- 4 wheel encoders: LF=TIM5, RF=TIM1, LR=TIM2, RR=TIM4.
- **TB6612-A is currently faulty → LF/LR motors + encoders dead.** RF/RR verified
  working. Full-chassis odometry needs all four wheels.

## Calibrate before trusting /odom

1. **`ticks_per_rev`** (config) — placeholder `1320`. Roll one wheel exactly one
   revolution by hand, read that wheel's ODOM tick delta, set the value.
2. **`encoder_sign`** `[LF,RF,LR,RR]` — each wheel's count must be **positive when
   the wheel rolls the robot forward**. RF/RR measured `+1`; set LF/LR after the
   TB6612-A board is replaced.
3. **geometry** (`wheel_radius_m`, `half_length_m`, `half_width_m`) must match the
   firmware `app_chassis_init`.

## Build & run (on RDK)

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select stm32_bridge
source install/setup.bash
ros2 launch stm32_bridge stm32_bridge.launch.py
# then:  ros2 topic echo /odom   |   ros2 topic pub /cmd_vel geometry_msgs/Twist ...
```

Needs `pyserial` on the RDK.
