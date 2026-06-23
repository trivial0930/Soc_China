"""Uplink node: forward inspection ROS topics to the management-app backend (Mac).

Subscribes /hazard/events, /inspection/brief, /inspection/workstation_record,
/inspection/report; builds backend ingest payloads (uplink.py); uploads referenced
evidence/snapshot images; POSTs with a retry queue so WiFi blips don't lose data.

Params (all declare_parameter): backend_url, ingest_token, upload_images,
hazard_topic/brief_topic/record_topic/report_topic, flush_sec, max_attempts.
"""

from __future__ import annotations

import json
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.uplink import (
    HttpPoster, RetryQueue, build_acceptance, build_brief, build_event, build_record,
    build_report, event_images, read_markdown, record_images,
)


class UplinkNode(Node):
    def __init__(self) -> None:
        super().__init__("uplink_node")
        p = self.declare_parameter
        p("backend_url", "http://192.168.128.100:8000")
        p("ingest_token", "")
        p("upload_images", True)
        p("hazard_topic", "/hazard/events")
        p("brief_topic", "/inspection/brief")
        p("record_topic", "/inspection/workstation_record")
        p("report_topic", "/inspection/report")
        p("acceptance_topic", "/inspection/acceptance")
        p("flush_sec", 5.0)
        p("max_attempts", 5)
        p("max_len", 2000)

        gp = self.get_parameter
        self.upload_images = bool(gp("upload_images").value)
        self.poster = HttpPoster(str(gp("backend_url").value), str(gp("ingest_token").value))
        self.queue = RetryQueue(
            max_attempts=int(gp("max_attempts").value),
            max_len=int(gp("max_len").value),
            persistent_kinds=frozenset({"event", "brief"}),
        )

        self.create_subscription(String, str(gp("hazard_topic").value), self._on_event, 10)
        self.create_subscription(String, str(gp("brief_topic").value), self._on_brief, 10)
        self.create_subscription(String, str(gp("record_topic").value), self._on_record, 10)
        self.create_subscription(String, str(gp("report_topic").value), self._on_report, 10)
        self.create_subscription(String, str(gp("acceptance_topic").value), self._on_acceptance, 10)
        self.create_timer(float(gp("flush_sec").value), self._flush)
        self.get_logger().info(f"uplink_node -> {gp('backend_url').value}")

    # ---- senders (used directly + via retry queue) ----
    def _send(self, kind: str, body: dict) -> bool:  # pragma: no cover - network
        try:
            return self.poster.post_json(f"/api/ingest/{kind}", body)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"POST {kind} failed: {exc}")
            return False

    def _upload(self, paths) -> None:  # pragma: no cover - network/fs
        if not self.upload_images:
            return
        for full in paths:
            try:
                with open(full, "rb") as fh:
                    self.poster.post_image("/api/ingest/image", os.path.basename(full), fh.read())
            except Exception as exc:  # noqa: BLE001
                self.get_logger().debug(f"image upload skipped {full}: {exc}")

    def _enqueue(self, kind: str, body: dict, images=None) -> None:
        self._upload(images or [])
        if not self._send(kind, body):
            if self.queue.add(kind, body):
                self.get_logger().warn(
                    f"uplink queue full (max_len), dropped oldest to enqueue {kind}")

    # ---- subscriptions ----
    def _parse(self, msg: String):
        try:
            return json.loads(msg.data)
        except (ValueError, TypeError):
            self.get_logger().warn("bad JSON on a subscribed topic")
            return None

    def _on_event(self, msg: String) -> None:
        raw = self._parse(msg)
        if raw:
            self._enqueue("event", build_event(raw), event_images(raw))

    def _on_brief(self, msg: String) -> None:
        raw = self._parse(msg)
        if raw:
            self._enqueue("brief", build_brief(raw))

    def _on_record(self, msg: String) -> None:
        raw = self._parse(msg)
        if raw:
            self._enqueue("record", build_record(raw), record_images(raw))

    def _on_report(self, msg: String) -> None:
        raw = self._parse(msg)
        if not raw:
            return
        body = build_report(raw, read_markdown(raw.get("path", "")))
        self._enqueue("report", body)
        # also surface per-station acceptance if the report carries it (optional)
        for acc in raw.get("acceptance", []) or []:
            self._enqueue("acceptance", build_acceptance(acc))

    def _on_acceptance(self, msg: String) -> None:
        raw = self._parse(msg)
        if raw:
            self._enqueue("acceptance", build_acceptance(raw))

    def _flush(self) -> None:  # pragma: no cover - network
        if len(self.queue):
            res = self.queue.drain(self._send)
            if res["sent"] or res["dropped"]:
                self.get_logger().info(f"uplink flush: {res}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UplinkNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
