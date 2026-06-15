from glob import glob
from setuptools import setup


package_name = "thermal_detector"

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
    description="Thermal capture and RGB+thermal hazard fusion for RDK X5.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "thermal_detector_node = thermal_detector.thermal_detector_node:main",
            "rgb_hazard_node = thermal_detector.rgb_hazard_node:main",
            "hazard_fusion_node = thermal_detector.hazard_fusion_node:main",
        ],
    },
)
