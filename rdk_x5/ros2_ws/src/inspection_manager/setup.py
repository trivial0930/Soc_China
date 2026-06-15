from glob import glob
from setuptools import setup


package_name = "inspection_manager"

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
    description="Layer 2/3 of the three-layer hazard decision: local cognition + on-demand cloud report.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "cognition_node = inspection_manager.cognition_node:main",
            "report_service = inspection_manager.report_service:main",
            "voice_node = inspection_manager.voice_node:main",
            "recheck_node = inspection_manager.recheck_node:main",
            "sim_hazard_publisher = inspection_manager.sim_hazard_publisher:main",
            "workstation_record_node = inspection_manager.workstation_record_node:main",
        ],
    },
)
