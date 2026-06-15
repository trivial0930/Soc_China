"""Path B: bring up RGB hazard detection + thermal + fusion as ROS2 nodes.

  ros2 launch thermal_detector hazard_fusion.launch.py

Nodes:
  rgb_hazard_node       -> /perception/hazard_detections, /perception/image_color
  thermal_detector_node -> /thermal/temperature, /thermal/image_color
  hazard_fusion_node    -> /hazard/status, /hazard/events (thermal_risk)

Stop the standalone lab_thermal_fusion_web_detector.py first (camera+BPU are
single-owner). Set mock_thermal:=true to run the thermal node without the sensor.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory("thermal_detector")
    hazard_cfg = os.path.join(share, "config", "thermal_hazard.yaml")
    calib_cfg = os.path.join(share, "config", "thermal_rgb_calib.yaml")

    mock_thermal = LaunchConfiguration("mock_thermal")
    station_id = LaunchConfiguration("station_id")
    out_dir = "/root/lab_detector_deploy"

    return LaunchDescription([
        DeclareLaunchArgument("mock_thermal", default_value="false"),
        DeclareLaunchArgument("station_id", default_value="desk-01"),

        Node(
            package="thermal_detector", executable="rgb_hazard_node",
            name="rgb_hazard_node", output="screen",
        ),
        Node(
            package="thermal_detector", executable="thermal_detector_node",
            name="thermal_detector_node", output="screen",
            parameters=[{"mock_thermal": mock_thermal}],
        ),
        Node(
            package="thermal_detector", executable="hazard_fusion_node",
            name="hazard_fusion_node", output="screen",
            parameters=[{
                "hazard_config": hazard_cfg,
                "calib_config": calib_cfg,
                "station_id": station_id,
                "evidence_dir": os.path.join(out_dir, "evidence"),
                "events_dir": os.path.join(out_dir, "events"),
            }],
        ),
    ])
