#!/usr/bin/env python3
"""Waypoint patrol for the mecanum chassis using nav2_simple_commander.

Reads waypoints (x, y, yaw) from a ROS param and drives them in order via Nav2's
followWaypoints, optionally looping. Requires a running Nav2 stack + a localized
robot (map->odom from amcl/slam). The pure helpers (waypoint parsing, yaw->quat)
are unit-tested in tests/test_waypoint_patrol.py without ROS.

Run:
  ros2 run chassis_bringup waypoint_patrol --ros-args \
    -p waypoints:="[0.0,0.0,0.0, 1.0,0.0,0.0, 1.0,1.0,1.57]" -p loop:=true
"""

from __future__ import annotations

import math
from typing import List, Tuple


def yaw_to_quat(yaw: float) -> Tuple[float, float]:
    """Planar yaw (rad) -> (qz, qw)."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def parse_waypoints(flat: List[float]) -> List[Tuple[float, float, float]]:
    """Flat [x,y,yaw, x,y,yaw, ...] -> list of (x, y, yaw). Validates length."""
    if len(flat) % 3 != 0:
        raise ValueError("waypoints must be a flat list of x,y,yaw triples")
    return [(float(flat[i]), float(flat[i + 1]), float(flat[i + 2]))
            for i in range(0, len(flat), 3)]


def _build_pose(nav, x: float, y: float, yaw: float):
    """Build a PoseStamped in the map frame (ROS types resolved lazily)."""
    from geometry_msgs.msg import PoseStamped
    pose = PoseStamped()
    pose.header.frame_id = "map"
    pose.header.stamp = nav.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y
    qz, qw = yaw_to_quat(yaw)
    pose.pose.orientation.z = qz
    pose.pose.orientation.w = qw
    return pose


def main() -> None:
    import rclpy
    from rclpy.node import Node
    from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

    rclpy.init()
    cfg = Node("waypoint_patrol_cfg")
    cfg.declare_parameter("waypoints", [0.0, 0.0, 0.0])
    cfg.declare_parameter("loop", False)
    flat = list(cfg.get_parameter("waypoints").value)
    loop = bool(cfg.get_parameter("loop").value)
    wps = parse_waypoints(flat)
    cfg.get_logger().info(f"patrol: {len(wps)} waypoints, loop={loop}")

    nav = BasicNavigator()
    nav.waitUntilNav2Active()

    try:
        while rclpy.ok():
            poses = [_build_pose(nav, x, y, yaw) for (x, y, yaw) in wps]
            nav.followWaypoints(poses)
            while not nav.isTaskComplete():
                pass
            result = nav.getResult()
            nav.get_logger().info(f"patrol lap result: {result}")
            if not loop or result != TaskResult.SUCCEEDED:
                break
    finally:
        cfg.destroy_node()
        nav.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
