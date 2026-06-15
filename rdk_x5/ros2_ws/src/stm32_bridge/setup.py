from glob import glob
from setuptools import setup


package_name = "stm32_bridge"

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
    description="RDK X5 to STM32F411 chassis UART bridge (cmd_vel -> CMD_VEL, ODOM -> /odom + TF).",
    license="MIT",
    entry_points={
        "console_scripts": [
            "stm32_bridge_node = stm32_bridge.stm32_bridge_node:main",
        ],
    },
)
