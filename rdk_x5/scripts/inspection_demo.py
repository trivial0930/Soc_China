#!/usr/bin/env python3
"""Offline demo of the three-layer hazard decision pipeline (no ROS, no hardware).

Feeds a sample Layer 1 /hazard/events JSON through Gate 1 -> Layer 2 cognition
(mock) -> action routing -> Gate 2 -> Layer 3 report (mock), and prints each step.

  python3 rdk_x5/scripts/inspection_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(_PKG))

from inspection_manager.actions import fill_event_action, route_actions  # noqa: E402
from inspection_manager.cognition import CognitionRequest, MockCognitionBackend  # noqa: E402
from inspection_manager.escalation import EscalationPolicy  # noqa: E402
from inspection_manager.events import parse_event  # noqa: E402
from inspection_manager.report import MockReportBackend, ReportRequest  # noqa: E402
from inspection_manager.station_map import station_map_from_dict  # noqa: E402

SAMPLE_EVENTS = [
    {
        "event_id": "20260615-0001", "timestamp": "2026-06-15T20:30:00+08:00",
        "station_id": "desk-03", "source": "thermal", "event_type": "thermal_risk",
        "severity": "critical", "confidence": 0.92,
        "summary": "CRITICAL: soldering_iron (active 145C)",
        "evidence": {"image_path": "/ev/0001.jpg", "log_path": "", "serial_output": ""},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
    },
    {
        "event_id": "20260615-0002", "timestamp": "2026-06-15T20:31:00+08:00",
        "station_id": "desk-05", "source": "thermal", "event_type": "thermal_risk",
        "severity": "warning", "confidence": 0.20,  # low confidence -> uncertain
        "summary": "WARNING: unknown hot region (62C)",
        "evidence": {"image_path": "/ev/0002.jpg", "log_path": "", "serial_output": ""},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
    },
]


def main() -> None:
    policy = EscalationPolicy(min_severity_for_cognition="warning", uncertain_below_confidence=0.45)
    cognition = MockCognitionBackend(policy=policy)
    report = MockReportBackend()
    stations = station_map_from_dict({"waypoints": {"wp_desk03": "desk-03", "wp_desk05": "desk-05"}})

    escalated = []
    for raw in SAMPLE_EVENTS:
        event = parse_event(raw)
        print(f"\n=== L1 事件 {event.event_id} | {event.station_id} | {event.severity} | conf={event.confidence} ===")
        if not policy.should_cognize(event):
            print("  Gate1: 丢弃（未达认知门限）")
            continue

        result = cognition.assess(CognitionRequest(event=event, image_path=event.evidence.image_path))
        actions = route_actions(result, event, stations)
        fill_event_action(event, result, actions)
        print(f"  L2 说明: {result.explanation}")
        print(f"  L2 动作: {[type(a).__name__ for a in actions]}")
        print(f"  事件 action 块: {json.dumps(event.action.to_dict(), ensure_ascii=False)}")
        print(f"  Gate2 上云: {result.escalate_to_cloud}")
        if result.escalate_to_cloud:
            escalated.append((event, result.explanation))

    if escalated:
        print("\n=== L3 云端报告（按需，聚合升级事件）===")
        rep = report.generate(
            ReportRequest(
                report_type="uncertain_followup",
                events=[e for e, _ in escalated],
                briefs=[b for _, b in escalated],
                title="不确定事件追问报告",
            )
        )
        print(rep.body_markdown)


if __name__ == "__main__":
    main()
