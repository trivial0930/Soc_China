"""Robot-recheck executor node: send the robot to recheck a flagged station.

Subscribes /inspection/recheck ({station_id, waypoint}), looks the waypoint up to a
map pose, and issues a Nav2 ``followWaypoints`` goal. Pose lookup is pure (recheck.py,
unit-tested); the Nav2 call needs the robot + map on-board.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.recheck import parse_recheck, pose_for_waypoint


class RecheckNode(Node):
    def __init__(self) -> None:
        super().__init__("recheck_node")
        self.declare_parameter("recheck_topic", "/inspection/recheck")
        self.declare_parameter("poses_config", "")

        self.poses_cfg = self._read_yaml(str(self.get_parameter("poses_config").value))
        self._navigator = None  # lazily created Nav2 BasicNavigator (on-board)
        self.create_subscription(
            String, str(self.get_parameter("recheck_topic").value), self._on_recheck, 10
        )

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception:  # noqa: BLE001
            return {}

    def _on_recheck(self, msg: String) -> None:
        try:
            req = parse_recheck(msg.data)
        except ValueError as exc:
            self.get_logger().warn(f"bad recheck payload: {exc}")
            return
        pose = pose_for_waypoint(req.get("waypoint"), self.poses_cfg)
        if pose is None:
            self.get_logger().warn(
                f"no pose for station {req['station_id']} (waypoint {req.get('waypoint')})"
            )
            return
        self.get_logger().info(f"recheck {req['station_id']} -> nav goal {pose}")
        self._send_nav_goal(pose)

    def _send_nav_goal(self, pose):  # pragma: no cover - needs Nav2 + robot
        from geometry_msgs.msg import PoseStamped
        from nav2_simple_commander.robot_navigator import BasicNavigator

        if self._navigator is None:
            self._navigator = BasicNavigator()
        x, y, yaw = pose
        import math

        goal = PoseStamped()
        goal.header.frame_id = "map"
        goal.pose.position.x = x
        goal.pose.position.y = y
        goal.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.orientation.w = math.cos(yaw / 2.0)
        self._navigator.followWaypoints([goal])


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RecheckNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
