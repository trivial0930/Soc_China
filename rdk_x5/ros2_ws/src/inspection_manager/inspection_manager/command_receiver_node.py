"""ROS node: pull App->robot commands from the backend and execute them.

Mirrors the uplink node's stdlib-HTTP approach (no extra pip dep). On a timer it
polls GET /api/robot/commands/pending, and for each command: ack -> dispatch to the
right ROS topic(s) (see command_receiver.dispatch_command) -> POST a result receipt.

Supported: voice_prompt, recheck_station, generate_report, inspection_round (patrol
over all waypoints), laser_point (gimbal angle from gimbal_aim config), acceptance
(-> acceptance_node), find_item (resolves the asset via GET /api/assets then routes
to recheck/laser). Backend address/token default to the uplink node's params.
"""

from __future__ import annotations

from urllib.parse import quote

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import Bool, String

from inspection_manager.command_executor import CommandExecutor
from inspection_manager.command_receiver import dispatch_command, find_item_to_command
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
        gp("gimbal_aim_config", "")
        gp("voice_topic", "/inspection/voice")
        gp("recheck_topic", "/inspection/recheck")
        gp("request_report_topic", "/inspection/request_report")
        gp("gimbal_topic", "/gimbal/target_angle")
        gp("gimbal_enable_topic", "/gimbal/enable")
        gp("laser_topic", "/laser/enable")
        gp("laser_indicate_sec", 8.0)   # sustain aim + laser this long for one laser_point
        gp("acceptance_request_topic", "/inspection/acceptance_request")
        gp("voice_control_topic", "/inspection/voice_control")

        g = self.get_parameter
        self.poster = HttpPoster(str(g("backend_url").value), str(g("ingest_token").value))
        self.pending_limit = int(g("pending_limit").value)
        self.stations_cfg = self._read_yaml(str(g("stations_config").value))
        self.gimbal_cfg = self._read_yaml(str(g("gimbal_aim_config").value))
        self.laser_indicate_sec = float(g("laser_indicate_sec").value)
        self.string_pubs = {
            "voice_topic": self.create_publisher(String, str(g("voice_topic").value), 10),
            "recheck_topic": self.create_publisher(String, str(g("recheck_topic").value), 10),
            "request_report_topic": self.create_publisher(String, str(g("request_report_topic").value), 10),
            "acceptance_request_topic": self.create_publisher(String, str(g("acceptance_request_topic").value), 10),
            "voice_control_topic": self.create_publisher(String, str(g("voice_control_topic").value), 10),
        }
        self.vector_pubs = {
            "gimbal_topic": self.create_publisher(Vector3, str(g("gimbal_topic").value), 10),
        }
        self.bool_pubs = {
            "gimbal_enable_topic": self.create_publisher(Bool, str(g("gimbal_enable_topic").value), 10),
            "laser_topic": self.create_publisher(Bool, str(g("laser_topic").value), 10),
        }
        # NB: not self.executor — rclpy.Node.executor is a reserved property (its
        # setter calls add_node), so a plain attr name would collide and crash on init.
        self._cmd_executor = CommandExecutor(self._publish_primitive, self.create_timer,
                                             self.laser_indicate_sec)
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

    def _resolve_command(self, cmd: dict) -> dict:
        """find_item -> look the asset up on the backend, return a recheck/laser command."""
        if cmd.get("type") != "find_item":
            return cmd
        p = cmd.get("params") or {}
        mode = p.get("mode", "navigate")
        try:
            if p.get("name"):
                items = (self.poster.get_json(f"/api/assets?name={quote(str(p['name']))}") or {}).get("items", [])
            elif p.get("asset_id"):  # backend filters by name, not id -> fetch + match
                allitems = (self.poster.get_json("/api/assets?limit=500") or {}).get("items", [])
                items = [a for a in allitems if a.get("id") == int(p["asset_id"])]
            else:
                items = []
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"asset lookup failed: {exc}")
            return {"type": "find_item", "params": {"_error": str(exc)}}
        if not items:
            return {"type": "find_item", "params": {"_error": "asset not found"}}
        return find_item_to_command(items[0], mode)

    def _handle(self, cmd: dict) -> None:
        cid = cmd.get("command_id", "")
        try:
            self.poster.post_json(f"/api/robot/commands/{cid}/ack", {})
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"ack {cid} failed: {exc}")
            return

        resolved = self._resolve_command(cmd)
        if resolved.get("params", {}).get("_error"):
            self._report(cid, "failed", f"寻找物品失败:{resolved['params']['_error']}")
            return

        plan = dispatch_command(resolved, self.stations_cfg, self.gimbal_cfg)
        if "unsupported" in plan:
            self.get_logger().info(f"{cid} unsupported: {plan['unsupported']}")
            self._report(cid, "failed", plan["unsupported"])
            return
        try:
            result = self._cmd_executor.execute(plan)
            self.get_logger().info(f"{cid} -> {result}")
            self._report(cid, "done", result)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"dispatch {cid} failed: {exc}")
            self._report(cid, "failed", f"机器人执行异常:{exc}")

    def _publish_primitive(self, topic_key: str, kind: str, data) -> None:
        if kind == "vector3":
            x, y, z = data
            self.vector_pubs[topic_key].publish(Vector3(x=float(x), y=float(y), z=float(z)))
        elif kind == "bool":
            self.bool_pubs[topic_key].publish(Bool(data=bool(data)))
        else:
            self.string_pubs[topic_key].publish(String(data=data))

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
