"""ROS node: pull App->robot commands from the backend and execute them.

Mirrors the uplink node's stdlib-HTTP approach (no extra pip dep). On a timer it
polls GET /api/robot/commands/pending, and for each command: ack -> dispatch to the
right ROS topic (see command_receiver.dispatch_command) -> POST a result receipt.
Backend address/token default to the same params as the uplink node.
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.command_receiver import dispatch_command
from inspection_manager.uplink import HttpPoster


class CommandReceiverNode(Node):
    def __init__(self) -> None:
        super().__init__("command_receiver_node")
        gp = self.declare_parameter
        gp("backend_url", "http://192.168.128.100:8000")
        gp("ingest_token", "")
        gp("poll_sec", 2.0)
        gp("pending_limit", 10)
        gp("stations_config", "")
        gp("voice_topic", "/inspection/voice")
        gp("recheck_topic", "/inspection/recheck")
        gp("request_report_topic", "/inspection/request_report")

        g = self.get_parameter
        self.poster = HttpPoster(str(g("backend_url").value), str(g("ingest_token").value))
        self.pending_limit = int(g("pending_limit").value)
        self.stations_cfg = self._read_yaml(str(g("stations_config").value))
        # one publisher per supported topic key
        self.pubs = {
            "voice_topic": self.create_publisher(String, str(g("voice_topic").value), 10),
            "recheck_topic": self.create_publisher(String, str(g("recheck_topic").value), 10),
            "request_report_topic": self.create_publisher(String, str(g("request_report_topic").value), 10),
        }
        self.create_timer(float(g("poll_sec").value), self._poll)
        self.get_logger().info(f"command_receiver_node up -> {self.poster.base}")

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001 - optional config
            return {}

    def _poll(self) -> None:
        try:
            resp = self.poster.get_json(f"/api/robot/commands/pending?limit={self.pending_limit}")
        except Exception as exc:  # noqa: BLE001 - network hiccup; retry next tick
            self.get_logger().warn(f"poll failed: {exc}")
            return
        for cmd in (resp or {}).get("items", []):
            self._handle(cmd)

    def _handle(self, cmd: dict) -> None:
        cid = cmd.get("command_id", "")
        try:
            self.poster.post_json(f"/api/robot/commands/{cid}/ack", {})
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"ack {cid} failed: {exc}")
            return

        plan = dispatch_command(cmd, self.stations_cfg)
        if "unsupported" in plan:
            self.get_logger().info(f"{cid} unsupported: {plan['unsupported']}")
            self._report(cid, "failed", plan["unsupported"])
            return
        try:
            self.pubs[plan["topic_key"]].publish(String(data=plan["data"]))
            self.get_logger().info(f"{cid} -> {plan['topic_key']}: {plan['result']}")
            self._report(cid, "done", plan["result"])
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"dispatch {cid} failed: {exc}")
            self._report(cid, "failed", f"机器人执行异常:{exc}")

    def _report(self, cid: str, status: str, result: str) -> None:
        try:
            self.poster.post_json(f"/api/robot/commands/{cid}/result", {"status": status, "result": result})
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"result {cid} failed: {exc}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CommandReceiverNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
