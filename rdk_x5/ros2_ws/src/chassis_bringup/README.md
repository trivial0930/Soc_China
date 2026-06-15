# chassis_bringup

Localization / mapping / navigation bring-up for the RDK X5 mecanum chassis + N10
lidar. Launch files + tuned-template configs. **No new node code** — it wires
together `stm32_bridge`, `robot_localization`, `slam_toolbox`, `nav2` and the N10
driver.

## TF tree

```
map ──(slam_toolbox | amcl)──> odom ──(robot_localization EKF)──> base_link
                                                                    ├─(static)─> laser   (N10)
                                                                    └─(static)─> imu_link (future IMU)
```

`stm32_bridge` publishes the **/odom topic only** (`publish_tf:=false`); the EKF
owns `odom -> base_link`. The bringup launch sets this automatically.

## Files

- `launch/tf_static.launch.py` — `base_link->laser`, `base_link->imu_link`
  (⚠️ placeholder offsets — **measure on the real robot**; yaw≈0 confirmed by the
  2026-06-07 N10 direction check).
- `launch/bringup.launch.py` — stm32_bridge (no TF) + EKF + static TF.
- `launch/slam.launch.py` — slam_toolbox online async mapping.
- `config/ekf.yaml` — robot_localization (fuses /odom; IMU block ready to enable).
- `config/slam_toolbox.yaml` — mapping params for N10.
- `config/nav2_params.yaml` — Nav2 template (holonomic/omni; **tune on hardware**).

## Bring-up order

```bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash

# 1. N10 lidar  ->  /scan
ros2 run lslidar_driver lslidar_driver_node --ros-args \
  --params-file src/lslidar_driver/params/lsx10.yaml

# 2. odom + EKF + static TF
ros2 launch chassis_bringup bringup.launch.py

# 3a. live mapping
ros2 launch chassis_bringup slam.launch.py
#     drive slowly, then save:
ros2 run nav2_map_server map_saver_cli -f ~/lab_map

# 3b. OR navigation on a saved map
ros2 launch nav2_bringup bringup_launch.py \
  map:=$HOME/lab_map.yaml \
  params_file:=$(ros2 pkg prefix chassis_bringup)/share/chassis_bringup/config/nav2_params.yaml
```

## ⚠️ Must calibrate before trusting this stack

1. `stm32_bridge` `ticks_per_rev` + `encoder_sign` (see that package). **/odom is
   meaningless until this is done.** Needs all 4 wheels → **replace TB6612-A first**.
2. `tf_static.launch.py` laser/imu mounting offsets (measure).
3. `nav2_params.yaml` footprint (`robot_radius`), velocity/accel limits, costmap
   inflation, controller critics — tune on the real robot.
4. Build needs `robot_localization`, `slam_toolbox`, `nav2_bringup` installed
   (`apt install ros-humble-robot-localization ros-humble-slam-toolbox ros-humble-navigation2 ros-humble-nav2-bringup`).

## IMU (BMI088) — software ready, needs the module connected

The EKF is prepped: `config/ekf_imu.yaml` fuses an IMU on `/imu` (gyro yaw-rate +
accel; **no absolute yaw** — BMI088 has no magnetometer). Enable with:

```bash
ros2 launch chassis_bringup bringup.launch.py ekf_config_file:=ekf_imu.yaml
```

Still TODO (hardware): the BMI088 module is **not connected yet** (i2cdetect on
2026-06-08 shows no 0x18/0x68 on any bus). The 40-pin is crowded (gimbal PWM+I2C1,
thermal SPI1+i2c-5@0x40, STM32 UART). Recommended:
1. Jumper the module to **I2C** (not SPI) — simplest, fewest pins.
2. Tap SDA/SCL/3V3/GND onto a free I2C bus. `i2c-1` is empty; or share `i2c-5`
   (BMI088 accel 0x18 / gyro 0x68 don't clash with the thermal's 0x40).
3. Confirm `i2cdetect -y -r <bus>` shows 0x18 and 0x68.
4. Run an IMU driver node publishing `sensor_msgs/Imu` on `/imu` (no ready-made
   package on the board — to be written like the thermal `senxor_driver`, with
   accel→m/s², gyro→rad/s scaling and the BMI088 axis frame = `imu_link`).
5. Launch with `ekf_config_file:=ekf_imu.yaml`; verify `/odometry/filtered` yaw
   tracks rotation better than wheels alone.
