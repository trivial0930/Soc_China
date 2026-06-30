"""Launch the app-teleop + lidar-safety stage-A stack.

Prereqs (start first): lslidar driver (/scan) and chassis_bringup (stm32_bridge
subscribes /cmd_vel; odom/EKF/TF). Override backend/token at launch, e.g.:
  ros2 launch teleop_safety teleop_safety.launch.py \
      backend_url:=http://192.168.128.100:8000 ingest_token:=<token>
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    cfg = PathJoinSubstitution(
        [FindPackageShare("teleop_safety"), "config", "teleop_safety.yaml"])

    backend_url = LaunchConfiguration("backend_url")
    ingest_token = LaunchConfiguration("ingest_token")

    return LaunchDescription([
        DeclareLaunchArgument("backend_url", default_value="http://192.168.128.100:8000"),
        DeclareLaunchArgument("ingest_token", default_value=""),
        Node(
            package="teleop_safety", executable="lidar_safety_node",
            name="lidar_safety", parameters=[cfg], output="screen",
        ),
        Node(
            package="teleop_safety", executable="teleop_receiver_node",
            name="teleop_receiver",
            parameters=[cfg, {"backend_url": backend_url, "ingest_token": ingest_token}],
            output="screen",
        ),
    ])
