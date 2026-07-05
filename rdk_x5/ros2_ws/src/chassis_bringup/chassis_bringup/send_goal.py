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


def _make_pose(nav, x: float, y: float, yaw: float):
    """PoseStamped in the map frame (ROS types resolved lazily)."""
    from geometry_msgs.msg import PoseStamped
    ps = PoseStamped()
    ps.header.frame_id = "map"
    ps.header.stamp = nav.get_clock().now().to_msg()
    ps.pose.position.x = x
    ps.pose.position.y = y
    qz, qw = yaw_to_quat(yaw)
    ps.pose.orientation.z = qz
    ps.pose.orientation.w = qw
    return ps


def main() -> None:
    import time
    import rclpy
    from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

    args = build_parser().parse_args()
    init = parse_pose(args.init)
    goal = parse_pose(args.goal)

    rclpy.init()
    nav = BasicNavigator()

    if init is not None:
        nav.setInitialPose(_make_pose(nav, *init))
        nav.get_logger().info(f"initial pose set to {init}")

    nav.get_logger().info("waiting for Nav2 to become active...")
    nav.waitUntilNav2Active()

    nav.goToPose(_make_pose(nav, *goal))
    nav.get_logger().info(f"navigating to {goal} (timeout {args.timeout}s)...")

    t0 = time.time()
    while not nav.isTaskComplete():
        fb = nav.getFeedback()
        if fb is not None:
            nav.get_logger().info(f"remaining {fb.distance_remaining:.2f} m")
        if time.time() - t0 > args.timeout:
            nav.cancelTask()
            nav.get_logger().warn("timeout -> cancelled")
            break
        time.sleep(1.0)

    result = nav.getResult()
    name = getattr(result, "name", str(result))
    nav.get_logger().info(f"result: {name}")
    rclpy.shutdown()
    raise SystemExit(0 if result == TaskResult.SUCCEEDED else 1)


if __name__ == "__main__":
    main()
