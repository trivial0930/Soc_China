#!/usr/bin/env python3
"""ROS2 fusion node: RGB hazard detections x thermal frame -> hazard verdict.

Subscribes:
  /thermal/temperature          (sensor_msgs/Image, 32FC1)  -- degC grid
  /perception/hazard_detections (std_msgs/String, JSON)     -- RGB/YOLO detections
  /perception/image_color       (sensor_msgs/Image, bgr8)   -- optional, for evidence

Publishes:
  /hazard/status  (std_msgs/String, JSON)  -- overall severity + per-object, every assessment
  /hazard/events  (std_msgs/String, JSON)  -- thermal_risk event (warning/critical), throttled

Uses latest-frame pairing (thermal cached, fused on each detections message) and
the same HazardPipeline as the standalone detector. Events follow event_schema.md
and are intended for inspection_manager.
"""

import os
import time
from datetime import datetime, timezone

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .hazard_pipeline import HazardPipeline
from .ros_payloads import decode_detections, encode_status, result_to_event


class HazardFusionNode(Node):
    def __init__(self) -> None:
        super().__init__("hazard_fusion_node")
        p = self.declare_parameter
        p("hazard_config", "")
        p("calib_config", "")
        p("station_id", "desk-unknown")
        p("evidence_dir", "evidence")
        p("events_dir", "events")
        p("evidence_cooldown", 10.0)
        p("temperature_topic", "/thermal/temperature")
        p("detections_topic", "/perception/hazard_detections")
        p("rgb_topic", "/perception/image_color")
        p("status_topic", "/hazard/status")
        p("events_topic", "/hazard/events")
        gp = self.get_parameter

        hazard = str(gp("hazard_config").value)
        calib = str(gp("calib_config").value)
        if not hazard or not calib:
            raise RuntimeError("hazard_config and calib_config parameters are required")
        self.pipeline = HazardPipeline.from_config(hazard, calib)

        self.station_id = str(gp("station_id").value)
        self.evidence_dir = str(gp("evidence_dir").value)
        self.events_dir = str(gp("events_dir").value)
        self.cooldown = float(gp("evidence_cooldown").value)
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.events_dir, exist_ok=True)

        self._thermal = None
        self._rgb = None
        self._last_event = 0.0

        self.create_subscription(Image, str(gp("temperature_topic").value), self._on_thermal, 5)
        self.create_subscription(String, str(gp("detections_topic").value), self._on_detections, 10)
        self.create_subscription(Image, str(gp("rgb_topic").value), self._on_rgb, 2)
        self.status_pub = self.create_publisher(String, str(gp("status_topic").value), 10)
        self.events_pub = self.create_publisher(String, str(gp("events_topic").value), 10)
        self.get_logger().info("hazard_fusion_node up")

    def _on_thermal(self, msg: Image) -> None:
        try:
            self._thermal = np.frombuffer(bytes(msg.data), dtype=np.float32).reshape(msg.height, msg.width)
        except Exception as exc:
            self.get_logger().warn(f"bad thermal frame: {exc}")

    def _on_rgb(self, msg: Image) -> None:
        try:
            self._rgb = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.width, 3)
        except Exception:
            self._rgb = None

    def _on_detections(self, msg: String) -> None:
        if self._thermal is None:
            return
        try:
            detections, _stamp = decode_detections(msg.data)
        except Exception as exc:
            self.get_logger().warn(f"bad detections payload: {exc}")
            return

        result = self.pipeline.assess(detections, self._thermal)

        status = String()
        status.data = encode_status(result)
        self.status_pub.publish(status)

        if result.overall_severity in ("warning", "critical"):
            self._maybe_emit_event(result, detections)

    def _maybe_emit_event(self, result, detections) -> None:
        now = time.time()
        if now - self._last_event < self.cooldown:
            return
        self._last_event = now

        stamp = datetime.now(timezone.utc).astimezone()
        event_id = stamp.strftime("%Y%m%d-%H%M%S")
        image_path = ""
        if self._rgb is not None:
            try:
                import cv2

                image_path = os.path.join(self.evidence_dir, f"{event_id}_{result.overall_severity}.jpg")
                cv2.imwrite(image_path, self._rgb)
            except Exception:
                image_path = ""

        confidence = max((o.score for o in result.objects), default=0.0)
        event = result_to_event(
            result, self.station_id, event_id, stamp.isoformat(),
            confidence=float(confidence), image_path=image_path,
        )
        if event is None:
            return
        import json

        with open(os.path.join(self.events_dir, f"{event_id}.json"), "w", encoding="utf-8") as fh:
            json.dump(event, fh, ensure_ascii=False, indent=2)
        out = String()
        out.data = json.dumps(event, ensure_ascii=False)
        self.events_pub.publish(out)
        self.get_logger().info(f"hazard event: {result.banner}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HazardFusionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
