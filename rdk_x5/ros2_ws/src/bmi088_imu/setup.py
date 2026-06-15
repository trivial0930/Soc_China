from glob import glob
from setuptools import setup


package_name = "bmi088_imu"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Soc China Team",
    maintainer_email="rongzechen@example.com",
    description="BMI088 IMU I2C driver for RDK X5 (sensor_msgs/Imu on /imu).",
    license="MIT",
    entry_points={
        "console_scripts": [
            "bmi088_imu_node = bmi088_imu.bmi088_imu_node:main",
        ],
    },
)
