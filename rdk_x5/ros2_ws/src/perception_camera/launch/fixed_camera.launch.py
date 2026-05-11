from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node, SetRemap
from launch_ros.substitutions import FindPackageShare


def source_is(source_type, expected):
    return IfCondition(PythonExpression(["'", source_type, "' == '", expected, "'"]))


def generate_launch_description():
    source_type = LaunchConfiguration("source_type")
    config_file = LaunchConfiguration("config_file")
    source_uri = LaunchConfiguration("source_uri")
    frame_id = LaunchConfiguration("frame_id")
    width = LaunchConfiguration("width")
    height = LaunchConfiguration("height")
    fps = LaunchConfiguration("fps")
    image_topic = LaunchConfiguration("image_topic")
    camera_info_topic = LaunchConfiguration("camera_info_topic")
    usb_pixel_format = LaunchConfiguration("usb_pixel_format")
    mipi_video_device = LaunchConfiguration("mipi_video_device")

    default_config = PathJoinSubstitution(
        [FindPackageShare("perception_camera"), "config", "fixed_camera.yaml"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "source_type",
                default_value="opencv",
                description="Camera backend: opencv, usb, or mipi.",
            ),
            DeclareLaunchArgument(
                "config_file",
                default_value=default_config,
                description="YAML config for the local OpenCV ingest node.",
            ),
            DeclareLaunchArgument(
                "source_uri",
                default_value="/dev/video0",
                description="OpenCV source: /dev/video*, RTSP/HTTP URL, video file, image file, or image directory.",
            ),
            DeclareLaunchArgument("frame_id", default_value="fixed_monitor_cam"),
            DeclareLaunchArgument("width", default_value="1280"),
            DeclareLaunchArgument("height", default_value="720"),
            DeclareLaunchArgument("fps", default_value="15.0"),
            DeclareLaunchArgument("image_topic", default_value="/fixed_camera/image_raw"),
            DeclareLaunchArgument("camera_info_topic", default_value="/fixed_camera/camera_info"),
            DeclareLaunchArgument("usb_pixel_format", default_value="mjpeg"),
            DeclareLaunchArgument("mipi_video_device", default_value=""),
            Node(
                condition=source_is(source_type, "opencv"),
                package="perception_camera",
                executable="fixed_camera_node",
                name="fixed_camera_node",
                output="screen",
                parameters=[
                    config_file,
                    {
                        "source_uri": source_uri,
                        "frame_id": frame_id,
                        "image_topic": image_topic,
                        "camera_info_topic": camera_info_topic,
                        "width": width,
                        "height": height,
                        "fps": fps,
                    },
                ],
            ),
            GroupAction(
                condition=source_is(source_type, "usb"),
                actions=[
                    SetRemap(src="/image", dst=image_topic),
                    SetRemap(src="/camera_info", dst=camera_info_topic),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            [
                                PathJoinSubstitution(
                                    [
                                        FindPackageShare("hobot_usb_cam"),
                                        "launch",
                                        "hobot_usb_cam.launch.py",
                                    ]
                                )
                            ]
                        ),
                        launch_arguments={
                            "usb_video_device": source_uri,
                            "usb_pixel_format": usb_pixel_format,
                            "usb_image_width": width,
                            "usb_image_height": height,
                        }.items(),
                    ),
                ],
            ),
            GroupAction(
                condition=source_is(source_type, "mipi"),
                actions=[
                    SetRemap(src="/image_raw", dst=image_topic),
                    SetRemap(src="/camera_info", dst=camera_info_topic),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            [
                                PathJoinSubstitution(
                                    [FindPackageShare("mipi_cam"), "launch", "mipi_cam.launch.py"]
                                )
                            ]
                        ),
                        launch_arguments={
                            "mipi_video_device": mipi_video_device,
                        }.items(),
                    ),
                ],
            ),
        ]
    )
