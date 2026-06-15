"""Chassis localization bring-up: wheel-odom bridge + EKF + static TF (URDF) [+ IMU].

TF tree produced here:
    odom -> base_link        (robot_localization EKF, fusing /odom [+ /imu])
    base_link -> laser/imu/wheels (URDF via robot_state_publisher)
stm32_bridge publishes the /odom TOPIC only (publish_tf:=false) so the EKF owns
odom->base_link. Run the N10 driver and (slam_toolbox | nav2) separately.

  use_imu:=true  -> also launch the BMI088 IMU node (/imu) and fuse it (ekf_imu.yaml).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = FindPackageShare("chassis_bringup")
    bridge_cfg = PathJoinSubstitution(
        [FindPackageShare("stm32_bridge"), "config", "stm32_bridge.yaml"])
    description = PathJoinSubstitution(
        [bringup_share, "launch", "description.launch.py"])

    use_imu = LaunchConfiguration("use_imu")
    # use_imu -> ekf_imu.yaml (fuses /imu); else ekf.yaml (wheel odom only)
    ekf_file = PythonExpression(
        ["'ekf_imu.yaml' if '", use_imu, "' == 'true' else 'ekf.yaml'"])
    ekf_cfg = PathJoinSubstitution([bringup_share, "config", ekf_file])

    return LaunchDescription([
        DeclareLaunchArgument(
            "use_imu", default_value="false",
            description="Launch the BMI088 IMU node and fuse /imu in the EKF."),

        # URDF -> robot_state_publisher: base_link->wheels (from /joint_states)
        # and base_link->laser/imu (static).
        IncludeLaunchDescription(PythonLaunchDescriptionSource([description])),

        # wheel-odom bridge — EKF owns the TF, so disable the bridge's own TF
        Node(
            package="stm32_bridge",
            executable="stm32_bridge_node",
            name="stm32_bridge",
            output="screen",
            parameters=[bridge_cfg, {"publish_tf": False}],
        ),

        # BMI088 IMU (only when use_imu:=true)
        Node(
            package="bmi088_imu",
            executable="bmi088_imu_node",
            name="bmi088_imu",
            output="screen",
            condition=IfCondition(use_imu),
            parameters=[{"i2c_bus": 5, "accel_addr": 0x18, "gyro_addr": 0x68,
                         "frame_id": "imu_link", "rate_hz": 100.0, "topic": "imu"}],
        ),

        # robot_localization EKF: /odom (+ /imu if use_imu) -> odom->base_link
        Node(
            package="robot_localization",
            executable="ekf_node",
            name="ekf_filter_node",
            output="screen",
            parameters=[ekf_cfg],
        ),
    ])
