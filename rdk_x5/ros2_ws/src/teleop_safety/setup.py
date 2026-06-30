from glob import glob
from setuptools import setup


package_name = "teleop_safety"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Soc China Team",
    maintainer_email="rongzechen@example.com",
    description="App teleop receiver + lidar safety layer (reactive obstacle avoidance, stage A).",
    license="MIT",
    entry_points={
        "console_scripts": [
            "lidar_safety_node = teleop_safety.lidar_safety_node:main",
            "teleop_receiver_node = teleop_safety.teleop_receiver_node:main",
        ],
    },
)
