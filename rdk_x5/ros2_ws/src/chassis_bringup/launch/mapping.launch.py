"""一键建图(B1):雷达 + 底盘里程计/IMU-EKF/TF + slam_toolbox + App遥控安全层。

到实验室一条命令起整套,然后用 App 摇杆开车绕一圈建图,最后:
    ros2 run nav2_map_server map_saver_cli -f ~/lab_map

启动示例(token 给 teleop 回传安全状态用,可留空):
    ros2 launch chassis_bringup mapping.launch.py ingest_token:=$(cat ~/.app_ingest_token)

TF 链:map -(slam_toolbox)-> odom -(EKF)-> base_link -(URDF)-> laser/imu/wheels。
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    bringup_share = FindPackageShare("chassis_bringup")
    teleop_share = FindPackageShare("teleop_safety")

    backend_url = LaunchConfiguration("backend_url")
    ingest_token = LaunchConfiguration("ingest_token")
    use_imu = LaunchConfiguration("use_imu")
    lslidar_params = LaunchConfiguration("lslidar_params")

    bringup = PathJoinSubstitution([bringup_share, "launch", "bringup.launch.py"])
    slam = PathJoinSubstitution([bringup_share, "launch", "slam.launch.py"])
    teleop = PathJoinSubstitution([teleop_share, "launch", "teleop_safety.launch.py"])

    return LaunchDescription([
        DeclareLaunchArgument("backend_url", default_value="http://192.168.128.100:8000"),
        DeclareLaunchArgument("ingest_token", default_value=""),
        DeclareLaunchArgument("use_imu", default_value="true",
                              description="fuse BMI088 /imu in EKF (recommended for mapping)"),
        DeclareLaunchArgument(
            "lslidar_params",
            default_value="/root/Soc_China/rdk_x5/ros2_ws/src/lslidar_driver/params/lsx10.yaml"),

        # 1) N10 lidar -> /scan
        Node(package="lslidar_driver", executable="lslidar_driver_node",
             name="lslidar_driver_node", output="screen",
             parameters=[lslidar_params]),

        # 2) wheel odom + IMU-fused EKF (odom->base_link) + static TF (base_link->laser)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([bringup]),
            launch_arguments={"use_imu": use_imu}.items()),

        # 3) slam_toolbox (map->odom, /map)
        IncludeLaunchDescription(PythonLaunchDescriptionSource([slam])),

        # 4) teleop receiver + lidar safety (drive via App during mapping)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([teleop]),
            launch_arguments={"backend_url": backend_url, "ingest_token": ingest_token}.items()),
    ])
