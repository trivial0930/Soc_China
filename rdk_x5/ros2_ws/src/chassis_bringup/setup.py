from glob import glob
from setuptools import setup


package_name = "chassis_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/description", glob("description/*.urdf")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Soc China Team",
    maintainer_email="rongzechen@example.com",
    description="Bring-up launches and configs (EKF, SLAM, Nav2, static TF) for the RDK X5 mecanum chassis.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "waypoint_patrol = chassis_bringup.waypoint_patrol:main",
            "send_goal = chassis_bringup.send_goal:main",
        ],
    },
)
