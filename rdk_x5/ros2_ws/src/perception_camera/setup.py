from glob import glob
from setuptools import setup

package_name = "perception_camera"

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
    description="Fixed monitoring camera ingress for RDK X5 ROS2 pipelines.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "fixed_camera_node = perception_camera.fixed_camera_node:main",
        ],
    },
)
