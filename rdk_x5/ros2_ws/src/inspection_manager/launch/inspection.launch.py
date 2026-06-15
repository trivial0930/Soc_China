from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = FindPackageShare("inspection_manager")
    cognition_cfg = PathJoinSubstitution([share, "config", "cognition.yaml"])
    stations_cfg = PathJoinSubstitution([share, "config", "stations.yaml"])
    report_cfg = PathJoinSubstitution([share, "config", "report.yaml"])

    return LaunchDescription(
        [
            DeclareLaunchArgument("cognition_config", default_value=cognition_cfg),
            DeclareLaunchArgument("stations_config", default_value=stations_cfg),
            DeclareLaunchArgument("report_config", default_value=report_cfg),
            Node(
                package="inspection_manager",
                executable="cognition_node",
                name="cognition_node",
                output="screen",
                parameters=[
                    {
                        "cognition_config": LaunchConfiguration("cognition_config"),
                        "stations_config": LaunchConfiguration("stations_config"),
                    }
                ],
            ),
            Node(
                package="inspection_manager",
                executable="report_service",
                name="report_service",
                output="screen",
                parameters=[{"report_config": LaunchConfiguration("report_config")}],
            ),
        ]
    )
