"""Static transforms for the chassis sensor mounting.

base_link -> laser:  N10 lidar mount. The 2026-06-07 direction check showed the
                     N10 0 deg aligns with the robot +x (front), so yaw ~ 0.
                     >>> MEASURE x/y/z (mounting offset) on the real robot. <<<
base_link -> imu_link: placeholder for the future IMU.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="base_to_laser",
            arguments=[
                "--x", "0.126", "--y", "0.0", "--z", "0.10",  # measured 2026-06-08
                "--yaw", "0.0", "--pitch", "0.0", "--roll", "0.0",
                "--frame-id", "base_link", "--child-frame-id", "laser",
            ],
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="base_to_imu",
            arguments=[
                "--x", "0.0", "--y", "0.0", "--z", "0.0",     # TODO: measure
                "--yaw", "0.0", "--pitch", "0.0", "--roll", "0.0",
                "--frame-id", "base_link", "--child-frame-id", "imu_link",
            ],
        ),
    ])
