"""ROS node: on-demand 课后桌面验收 (course-end desk acceptance).

Triggered by the App command channel (command_receiver publishes a station_id /
"all" on /inspection/acceptance_request). For each target station it runs the pure
checklist (desk_acceptance.assess_desk) against the latest cached perception
observation, and publishes the assessment on /inspection/acceptance — which the
uplink node forwards to the backend (/api/ingest/acceptance) for the App.

Perception feeds per-desk observations on /perception/desk_observation as JSON
{station_id, observation:{check_key: bool}}; with no observation a desk assesses as
合格 (all checks default to pass).
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.desk_acceptance import assess_desk, expand_targets


class AcceptanceNode(Node):
    def __init__(self) -> None:
        super().__init__("acceptance_node")
        gp = self.declare_parameter
        gp("request_topic", "/inspection/acceptance_request")
        gp("observation_topic", "/perception/desk_observation")
        gp("acceptance_topic", "/inspection/acceptance")
        gp("stations_config", "")

        g = self.get_parameter
        self.stations_cfg = self._read_yaml(str(g("stations_config").value))
        self._obs = {}  # station_id -> {check_key: bool}
        self.acc_pub = self.create_publisher(String, str(g("acceptance_topic").value), 10)
        self.create_subscription(String, str(g("observation_topic").value), self._on_observation, 10)
        self.create_subscription(String, str(g("request_topic").value), self._on_request, 10)
        self.get_logger().info("acceptance_node up")

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001
            return {}

    def _on_observation(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            self._obs[str(data["station_id"])] = dict(data.get("observation", {}))
        except (ValueError, KeyError) as exc:
            self.get_logger().warn(f"bad observation: {exc}")

    def _on_request(self, msg: String) -> None:
        target = msg.data.strip() or "all"
        for station in expand_targets(target, self.stations_cfg):
            assessment = assess_desk(station, self._obs.get(station, {}))
            payload = {"station_id": assessment.station_id, "verdict": assessment.verdict,
                       "severity": assessment.severity, "problems": list(assessment.problems)}
            self.acc_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
            self.get_logger().info(f"acceptance {station}: {assessment.verdict}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AcceptanceNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
