from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="bmi088_imu",
            executable="bmi088_imu_node",
            name="bmi088_imu",
            output="screen",
            parameters=[{
                "i2c_bus": 5,
                "accel_addr": 0x18,
                "gyro_addr": 0x68,
                "frame_id": "imu_link",
                "rate_hz": 100.0,
                "topic": "imu",
            }],
        ),
    ])
