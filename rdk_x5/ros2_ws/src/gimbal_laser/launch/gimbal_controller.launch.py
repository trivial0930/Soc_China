from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    default_config = PathJoinSubstitution(
        [FindPackageShare("gimbal_laser"), "config", "gimbal.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=default_config,
                description="YAML config for the RDK X5 gimbal controller.",
            ),
            Node(
                package="gimbal_laser",
                executable="gimbal_controller_node",
                name="gimbal_controller_node",
                output="screen",
                parameters=[config_file],
            ),
        ]
    )
