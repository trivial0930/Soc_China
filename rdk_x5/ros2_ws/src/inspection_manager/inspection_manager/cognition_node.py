"""Layer 2 ROS node: subscribe Layer 1 events, run cognition, dispatch actions.

Thin wrapper around the pure cores (events / escalation / cognition / actions /
station_map). Runs on the RDK / a local edge box; off-board it only needs the
pure modules, which are unit-tested separately.

Topics:
  in : /hazard/events            (std_msgs/String, JSON)  -- Layer 1
  out: /inspection/brief         (std_msgs/String, JSON)  -- Layer 2 brief + filled event
       /inspection/voice         (std_msgs/String)        -- voice prompt text (TTS executor)
       /gimbal/target_angle      (geometry_msgs/Vector3)  -- aim (pan/tilt; filled by #3)
       /inspection/escalate      (std_msgs/String, JSON)  -- hand-off to Layer 3
"""

from __future__ import annotations

import json
import os
import time

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.actions import (
    AimGimbal,
    RobotRecheck,
    VoicePrompt,
    fill_event_action,
    route_actions,
)
from inspection_manager.cognition import CognitionRequest, make_backend
from inspection_manager.config import (
    cognition_backend_name,
    policy_from_dict,
    station_context,
    station_map_from_dict,
)
from inspection_manager.events import parse_event


class CognitionNode(Node):
    def __init__(self) -> None:
        super().__init__("cognition_node")
        self.declare_parameter("events_topic", "/hazard/events")
        self.declare_parameter("brief_topic", "/inspection/brief")
        self.declare_parameter("voice_topic", "/inspection/voice")
        self.declare_parameter("gimbal_topic", "/gimbal/target_angle")
        self.declare_parameter("recheck_topic", "/inspection/recheck")
        self.declare_parameter("escalate_topic", "/inspection/escalate")
        self.declare_parameter("cognition_config", "")
        self.declare_parameter("stations_config", "")
        self.declare_parameter("log_dir", "inspection_log")

        cfg = self._read_yaml(str(self.get_parameter("cognition_config").value))
        stations_cfg = self._read_yaml(str(self.get_parameter("stations_config").value))
        self.policy = policy_from_dict(cfg)
        self.station_context = station_context(cfg)
        self.station_map = station_map_from_dict(stations_cfg)
        self.backend = self._build_backend(cognition_backend_name(cfg), cfg)
        self.log_dir = str(self.get_parameter("log_dir").value)
        os.makedirs(self.log_dir, exist_ok=True)

        self.brief_pub = self.create_publisher(String, str(self.get_parameter("brief_topic").value), 10)
        self.voice_pub = self.create_publisher(String, str(self.get_parameter("voice_topic").value), 10)
        self.gimbal_pub = self.create_publisher(Vector3, str(self.get_parameter("gimbal_topic").value), 10)
        self.recheck_pub = self.create_publisher(String, str(self.get_parameter("recheck_topic").value), 10)
        self.escalate_pub = self.create_publisher(String, str(self.get_parameter("escalate_topic").value), 10)
        self.create_subscription(
            String, str(self.get_parameter("events_topic").value), self._on_event, 10
        )

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception:  # noqa: BLE001 - config is optional; fall back to defaults
            return {}

    def _build_backend(self, name: str, cfg: dict):
        if name == "local_vlm":
            from inspection_manager.qwen_client import ollama_vlm_client

            client = ollama_vlm_client(
                model=str(cfg.get("vlm_model", "qwen3-vl:8b")),
                base_url=str(cfg.get("vlm_base_url", "http://localhost:11434/v1")),
            )
            return make_backend("local_vlm", policy=self.policy, client=client)
        return make_backend(name, policy=self.policy)

    def _on_event(self, msg: String) -> None:
        try:
            event = parse_event(msg.data)
        except (ValueError, KeyError) as exc:
            self.get_logger().warn(f"bad event payload: {exc}")
            return

        if not self.policy.should_cognize(event):  # Gate 1
            return

        request = CognitionRequest(
            event=event,
            station_context=self.station_context,
            image_path=event.evidence.image_path,
        )
        result = self.backend.assess(request)
        actions = route_actions(result, event, self.station_map)
        fill_event_action(event, result, actions)

        brief = {
            "event": event.to_dict(),
            "explanation": result.explanation,
            "confirmed_severity": result.confirmed_severity,
            "actions": result.suggested_actions,
            "escalate_to_cloud": result.escalate_to_cloud,
        }
        self.brief_pub.publish(String(data=json.dumps(brief, ensure_ascii=False)))
        self._dispatch(actions)

        if result.escalate_to_cloud:  # Gate 2
            self.escalate_pub.publish(
                String(data=json.dumps(brief, ensure_ascii=False))
            )

    def _dispatch(self, actions) -> None:
        for action in actions:
            if isinstance(action, VoicePrompt):
                self.voice_pub.publish(String(data=action.text))
            elif isinstance(action, AimGimbal):
                if action.pan_deg is not None and action.tilt_deg is not None:
                    self.gimbal_pub.publish(
                        Vector3(x=float(action.pan_deg), y=float(action.tilt_deg), z=0.0)
                    )
                else:
                    # pan/tilt are filled once #3 visual-servoing lands; log for now.
                    self.get_logger().info(f"aim requested at {action.station_id} (await servoing)")
            elif isinstance(action, RobotRecheck):
                self.recheck_pub.publish(
                    String(
                        data=json.dumps(
                            {"station_id": action.station_id, "waypoint": action.waypoint},
                            ensure_ascii=False,
                        )
                    )
                )
            else:  # LogRecord
                self._log(action)

    def _log(self, record) -> None:
        line = {
            "ts": time.time(),
            "event_id": record.event_id,
            "severity": record.severity,
            "text": record.text,
        }
        path = os.path.join(self.log_dir, "inspection.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CognitionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
