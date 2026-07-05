"""一键自主导航(B2):雷达 + 里程计/IMU-EKF/TF + AMCL 定位(静态 lab_map)+ Nav2 栈。

导航为独立模式:teleop_safety 不跑,Nav2 直接控 /cmd_vel。起之前先腾 CPU:
    systemctl stop voice-asr.service

启动:
    ros2 launch chassis_bringup nav.launch.py
    ros2 launch chassis_bringup nav.launch.py map:=/root/maps/lab_map.yaml

TF 链:map -(amcl)-> odom -(EKF)-> base_link -(static)-> laser。
发目标(另开一个终端):
    ros2 run chassis_bringup send_goal --init 0 0 0 --goal 1.5 0 0
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = FindPackageShare("chassis_bringup")
    nav2_share = FindPackageShare("nav2_bringup")

    use_imu = LaunchConfiguration("use_imu")
    lslidar_params = LaunchConfiguration("lslidar_params")
    params_file = LaunchConfiguration("params_file")
    map_yaml = LaunchConfiguration("map")

    bringup = PathJoinSubstitution([bringup_share, "launch", "bringup.launch.py"])
    localization = PathJoinSubstitution(
        [nav2_share, "launch", "localization_launch.py"])
    navigation = PathJoinSubstitution(
        [nav2_share, "launch", "navigation_launch.py"])
    default_params = PathJoinSubstitution(
        [bringup_share, "config", "nav2_params.yaml"])

    return LaunchDescription([
        DeclareLaunchArgument("use_imu", default_value="true",
                              description="fuse BMI088 /imu in EKF"),
        DeclareLaunchArgument(
            "lslidar_params",
            default_value="/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml"),
        DeclareLaunchArgument("params_file", default_value=default_params),
        DeclareLaunchArgument("map", default_value="/root/maps/lab_map.yaml"),

        # 1) N10 lidar -> /scan
        Node(package="lslidar_driver", executable="lslidar_driver_node",
             name="lslidar_driver_node", output="screen",
             parameters=[lslidar_params]),

        # 2) wheel odom + IMU-fused EKF (odom->base_link) + static TF (base_link->laser)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([bringup]),
            launch_arguments={"use_imu": use_imu}.items()),

        # 3) AMCL localization on the saved map (map->odom, map_server serves lab_map)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([localization]),
            launch_arguments={"map": map_yaml, "params_file": params_file,
                              "use_sim_time": "false"}.items()),

        # 4) Nav2 core (planner/controller/bt/behaviors/smoother/lifecycle).
        #    Remap the smoother's output to /cmd_vel (what stm32_bridge subscribes).
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([navigation]),
            launch_arguments={"params_file": params_file,
                              "use_sim_time": "false"}.items()),
    ])
