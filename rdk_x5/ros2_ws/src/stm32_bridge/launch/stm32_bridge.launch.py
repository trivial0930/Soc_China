from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    default_config = PathJoinSubstitution(
        [FindPackageShare("stm32_bridge"), "config", "stm32_bridge.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=default_config,
                description="YAML config for the RDK X5 <-> STM32 chassis bridge.",
            ),
            Node(
                package="stm32_bridge",
                executable="stm32_bridge_node",
                name="stm32_bridge",
                output="screen",
                parameters=[config_file],
            ),
        ]
    )
