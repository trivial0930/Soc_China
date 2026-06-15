"""Layer 3 ROS service node: aggregate escalated events into a cloud report.

Buffers Layer 2 escalations and, on a report request (or periodic trigger),
aggregates them and calls the report backend (mock by default; cloud later).
Rate-limited so the cloud layer stays a small fraction of traffic.

Topics:
  in : /inspection/escalate        (std_msgs/String, JSON brief)  -- from Layer 2
       /inspection/request_report  (std_msgs/String, report_type) -- trigger
  out: /inspection/report          (std_msgs/String, JSON)        -- structured report
"""

from __future__ import annotations

import json
import os
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.config import report_settings_from_dict
from inspection_manager.events import parse_event
from inspection_manager.report import RateLimiter, ReportRequest, make_report_backend


class ReportService(Node):
    def __init__(self) -> None:
        super().__init__("report_service")
        self.declare_parameter("escalate_topic", "/inspection/escalate")
        self.declare_parameter("request_topic", "/inspection/request_report")
        self.declare_parameter("report_topic", "/inspection/report")
        self.declare_parameter("report_config", "")
        self.declare_parameter("reports_dir", "inspection_reports")

        cfg = self._read_yaml(str(self.get_parameter("report_config").value))
        settings = report_settings_from_dict(cfg)
        self.backend = make_report_backend(settings["backend"])
        self.limiter = RateLimiter(settings["max_calls"], settings["window_sec"])
        self.reports_dir = str(self.get_parameter("reports_dir").value)
        os.makedirs(self.reports_dir, exist_ok=True)

        self._buffer = []  # list of (HazardEvent, brief_text)

        self.report_pub = self.create_publisher(
            String, str(self.get_parameter("report_topic").value), 10
        )
        self.create_subscription(
            String, str(self.get_parameter("escalate_topic").value), self._on_escalate, 10
        )
        self.create_subscription(
            String, str(self.get_parameter("request_topic").value), self._on_request, 10
        )

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception:  # noqa: BLE001 - optional config
            return {}

    def _on_escalate(self, msg: String) -> None:
        try:
            brief = json.loads(msg.data)
            event = parse_event(brief["event"])
        except (ValueError, KeyError) as exc:
            self.get_logger().warn(f"bad escalate payload: {exc}")
            return
        self._buffer.append((event, str(brief.get("explanation", ""))))

    def _on_request(self, msg: String) -> None:
        report_type = msg.data.strip() or "periodic_summary"
        if not self._buffer:
            return
        if not self.limiter.allow(time.monotonic()):
            self.get_logger().info("report rate-limited; skipping")
            return

        events = [e for e, _ in self._buffer]
        briefs = [b for _, b in self._buffer]
        result = self.backend.generate(
            ReportRequest(report_type=report_type, events=events, briefs=briefs)
        )
        self._buffer.clear()

        path = os.path.join(self.reports_dir, f"{report_type}_{int(time.time())}.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(result.body_markdown)
        self.report_pub.publish(
            String(
                data=json.dumps(
                    {
                        "title": result.title,
                        "verdict": result.verdict,
                        "severity": result.severity,
                        "event_ids": result.event_ids,
                        "path": path,
                    },
                    ensure_ascii=False,
                )
            )
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ReportService()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
