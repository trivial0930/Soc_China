#!/usr/bin/env python3
"""BMI088 IMU ROS 2 node -> sensor_msgs/Imu on /imu (RDK X5, i2c-5).

No magnetometer, so no absolute orientation: orientation_covariance[0] = -1
(REP-145), and the EKF (ekf_imu.yaml) fuses only gyro yaw-rate + accel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

try:
    from bmi088_imu.bmi088 import Bmi088, ACC_RANGE_G, GYR_RANGE_DPS
except ImportError:  # pragma: no cover - source-tree fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from bmi088_imu.bmi088 import Bmi088, ACC_RANGE_G, GYR_RANGE_DPS

_ACC_REG_BY_G = {v: k for k, v in ACC_RANGE_G.items()}
_GYR_REG_BY_DPS = {v: k for k, v in GYR_RANGE_DPS.items()}


class Bmi088Node(Node):
    def __init__(self):
        super().__init__("bmi088_imu")
        self.declare_parameter("i2c_bus", 5)
        self.declare_parameter("accel_addr", 0x18)
        self.declare_parameter("gyro_addr", 0x68)
        self.declare_parameter("frame_id", "imu_link")
        self.declare_parameter("rate_hz", 100.0)
        self.declare_parameter("accel_range_g", 6.0)
        self.declare_parameter("gyro_range_dps", 2000.0)
        self.declare_parameter("topic", "imu")
        # measurement noise (variance) — rough defaults; tune if needed
        self.declare_parameter("gyro_variance", 0.0009)     # (rad/s)^2
        self.declare_parameter("accel_variance", 0.04)      # (m/s^2)^2
        # startup gyro zero-bias calibration (robot must be still); 0 disables
        self.declare_parameter("calibrate_gyro_samples", 200)

        gp = self.get_parameter
        bus_no = int(gp("i2c_bus").value)
        self.frame_id = str(gp("frame_id").value)
        self.gyro_var = float(gp("gyro_variance").value)
        self.accel_var = float(gp("accel_variance").value)
        acc_reg = _ACC_REG_BY_G.get(float(gp("accel_range_g").value), 0x01)
        gyr_reg = _GYR_REG_BY_DPS.get(float(gp("gyro_range_dps").value), 0x00)

        import smbus2
        self.bus = smbus2.SMBus(bus_no)
        self.imu = Bmi088(self.bus,
                          acc_addr=int(gp("accel_addr").value),
                          gyr_addr=int(gp("gyro_addr").value),
                          acc_range_reg=acc_reg, gyr_range_reg=gyr_reg)

        aid = self.imu.accel_chip_id()
        gid = self.imu.gyro_chip_id()
        if aid != 0x1E:
            self.get_logger().warn(f"accel CHIP_ID=0x{aid:02X} (expected 0x1E)")
        if gid != 0x0F:
            self.get_logger().warn(f"gyro CHIP_ID=0x{gid:02X} (expected 0x0F)")
        self.imu.setup()
        nsamp = int(gp("calibrate_gyro_samples").value)
        if nsamp > 0:
            bx, by, bz = self.imu.calibrate_gyro_bias(nsamp)
            self.get_logger().info(
                f"gyro bias (rad/s) = ({bx:+.4f}, {by:+.4f}, {bz:+.4f}) "
                f"from {nsamp} samples — keep robot still at startup")
        self.get_logger().info(
            f"BMI088 up: accel 0x{aid:02X}/gyro 0x{gid:02X} on i2c-{bus_no}, "
            f"+/-{self.imu.acc_range_g}g +/-{self.imu.gyr_range_dps}dps")

        self.pub = self.create_publisher(Imu, str(gp("topic").value), 50)
        self.create_timer(1.0 / float(gp("rate_hz").value), self._tick)

    def _tick(self):
        try:
            ax, ay, az = self.imu.read_accel()
            gx, gy, gz = self.imu.read_gyro()
        except Exception as exc:  # noqa: BLE001 - transient I2C, skip this sample
            self.get_logger().warn(f"IMU read failed: {exc}", throttle_duration_sec=2.0)
            return

        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        # no absolute orientation (no magnetometer)
        msg.orientation_covariance[0] = -1.0
        msg.angular_velocity.x = gx
        msg.angular_velocity.y = gy
        msg.angular_velocity.z = gz
        msg.linear_acceleration.x = ax
        msg.linear_acceleration.y = ay
        msg.linear_acceleration.z = az
        for i in (0, 4, 8):
            msg.angular_velocity_covariance[i] = self.gyro_var
            msg.linear_acceleration_covariance[i] = self.accel_var
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = Bmi088Node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
