#!/usr/bin/env python3
"""Send one Nav2 goal (with optional AMCL initial pose) via nav2_simple_commander.

Drives a single goToPose and prints feedback until arrival/failure/timeout. Pure
helpers (arg parsing) are unit-tested in tests/test_send_goal.py without ROS.

Run on the RDK once the Nav2 stack is up (nav.launch.py):
  ros2 run chassis_bringup send_goal --init 0 0 0 --goal 1.5 0 0
  ros2 run chassis_bringup send_goal --goal 1.5 0 0     # skip initialpose (already localized)
"""
from __future__ import annotations

import argparse
from typing import List, Optional, Tuple

# Reuse the planar yaw->quaternion helper (DRY; imports ROS-free).
from chassis_bringup.waypoint_patrol import yaw_to_quat  # noqa: F401

Pose = Tuple[float, float, float]


def parse_pose(values: Optional[List[float]]) -> Optional[Pose]:
    """[x, y, yaw] -> (x, y, yaw); None -> None. Raises ValueError on bad length."""
    if values is None:
        return None
    if len(values) != 3:
        raise ValueError("pose must be exactly 3 numbers: x y yaw")
    return (float(values[0]), float(values[1]), float(values[2]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Send one Nav2 goal")
    p.add_argument("--init", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                   default=None, help="AMCL initial pose; omit if already localized")
    p.add_argument("--goal", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                   required=True, help="goal pose in the map frame")
    p.add_argument("--timeout", type=float, default=120.0,
                   help="cancel if not arrived within this many seconds")
    return p
