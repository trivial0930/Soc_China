"""Online async SLAM (slam_toolbox) for live mapping.

Prereqs running first: N10 driver (/scan) and chassis_bringup bringup.launch.py
(odom->base_link via EKF, base_link->laser static). This adds map->odom.
Save the map with:
    ros2 run nav2_map_server map_saver_cli -f ~/lab_map
"""

from launch import LaunchDescription
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    slam_cfg = PathJoinSubstitution(
        [FindPackageShare("chassis_bringup"), "config", "slam_toolbox.yaml"])

    return LaunchDescription([
        Node(
            package="slam_toolbox",
            executable="async_slam_toolbox_node",
            name="slam_toolbox",
            output="screen",
            parameters=[slam_cfg],
        ),
    ])
