from glob import glob
from setuptools import setup


package_name = "gimbal_laser"

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
    description="Two-axis gimbal controller for RDK X5.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "gimbal_controller_node = gimbal_laser.gimbal_controller_node:main",
            "gimbal_aim_node = gimbal_laser.gimbal_aim_node:main",
        ],
    },
)
