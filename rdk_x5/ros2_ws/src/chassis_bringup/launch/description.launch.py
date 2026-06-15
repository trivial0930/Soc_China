"""Publish the chassis URDF via robot_state_publisher.

Emits TF:
  base_link -> lf/rf/lr/rr_wheel_link   (from /joint_states, published by stm32_bridge)
  base_link -> laser, base_link -> imu_link   (static fixed joints)
This replaces tf_static.launch.py for the laser/imu transforms — do not run both
or you will get duplicate base_link->laser publishers.
"""

from launch import LaunchDescription
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    urdf = PathJoinSubstitution(
        [FindPackageShare("chassis_bringup"), "description", "chassis.urdf"])
    robot_description = ParameterValue(Command(["cat ", urdf]), value_type=str)

    return LaunchDescription([
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),
    ])
