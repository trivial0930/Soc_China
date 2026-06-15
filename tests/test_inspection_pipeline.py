"""End-to-end proof that the three-layer decision wiring works with no hardware.

L1 event JSON -> parse -> Gate 1 -> Layer 2 cognition (mock) -> action routing +
event.action fill -> Gate 2 -> Layer 3 report (mock). Pure Python, no ROS.
"""

import json
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5"
    / "ros2_ws"
    / "src"
    / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.actions import (  # noqa: E402
    AimGimbal,
    RobotRecheck,
    VoicePrompt,
    fill_event_action,
    route_actions,
)
from inspection_manager.cognition import CognitionRequest, MockCognitionBackend  # noqa: E402
from inspection_manager.config import (  # noqa: E402
    cognition_backend_name,
    report_settings_from_dict,
    station_context,
)
from inspection_manager.escalation import EscalationPolicy  # noqa: E402
from inspection_manager.events import parse_event  # noqa: E402
from inspection_manager.report import MockReportBackend, ReportRequest  # noqa: E402
from inspection_manager.station_map import station_map_from_dict  # noqa: E402


L1_EVENT_JSON = json.dumps(
    {
        "event_id": "20260615-0001",
        "timestamp": "2026-06-15T20:30:00+08:00",
        "station_id": "desk-03",
        "source": "thermal",
        "event_type": "thermal_risk",
        "severity": "critical",
        "confidence": 0.92,
        "summary": "CRITICAL: soldering_iron (active 145C)",
        "evidence": {"image_path": "/ev/20260615-0001_critical.jpg", "log_path": "", "serial_output": ""},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
    }
)

STATIONS = station_map_from_dict({"waypoints": {"wp_desk03": "desk-03"}})


class ConfigHelperTests(unittest.TestCase):
    def test_backend_name_default_and_explicit(self):
        self.assertEqual(cognition_backend_name({}), "mock")
        self.assertEqual(cognition_backend_name({"backend": "local_vlm"}), "local_vlm")

    def test_station_context(self):
        self.assertEqual(station_context({"station_context": "课中"}), "课中")

    def test_report_settings_defaults(self):
        s = report_settings_from_dict({})
        self.assertEqual(s["backend"], "mock")
        self.assertEqual(s["max_calls"], 5)


class FullPipelineTests(unittest.TestCase):
    def setUp(self):
        self.policy = EscalationPolicy(
            min_severity_for_cognition="warning", uncertain_below_confidence=0.45
        )
        self.cognition = MockCognitionBackend(policy=self.policy)
        self.report = MockReportBackend()

    def test_confident_critical_handled_locally_no_cloud(self):
        event = parse_event(L1_EVENT_JSON)
        self.assertTrue(self.policy.should_cognize(event))  # Gate 1

        result = self.cognition.assess(CognitionRequest(event=event))
        actions = route_actions(result, event, STATIONS)
        fill_event_action(event, result, actions)

        # Layer 2 produced a usable brief + concrete actions, all local.
        self.assertIn("desk-03", result.explanation)
        self.assertTrue(any(isinstance(a, VoicePrompt) for a in actions))
        recheck = next(a for a in actions if isinstance(a, RobotRecheck))
        self.assertEqual(recheck.waypoint, "wp_desk03")
        self.assertTrue(any(isinstance(a, AimGimbal) for a in actions))
        self.assertEqual(event.action.robot_task, "recheck:desk-03")
        self.assertFalse(result.escalate_to_cloud)  # confident -> stays local

    def test_uncertain_event_escalates_to_cloud_report(self):
        data = json.loads(L1_EVENT_JSON)
        data["confidence"] = 0.2  # local model would be unsure
        event = parse_event(data)

        result = self.cognition.assess(CognitionRequest(event=event))
        self.assertTrue(result.escalate_to_cloud)  # Gate 2

        report = self.report.generate(
            ReportRequest(
                report_type="uncertain_followup",
                events=[event],
                briefs=[result.explanation],
            )
        )
        self.assertEqual(report.severity, "critical")
        self.assertIn("desk-03", report.body_markdown)
        self.assertEqual(report.event_ids, ["20260615-0001"])

    def test_info_event_is_filtered_before_layer2(self):
        data = json.loads(L1_EVENT_JSON)
        data["severity"] = "info"
        event = parse_event(data)
        self.assertFalse(self.policy.should_cognize(event))  # dropped at Gate 1

    def test_post_class_acceptance_report_aggregates_multiple_desks(self):
        e1 = parse_event(L1_EVENT_JSON)
        d2 = json.loads(L1_EVENT_JSON)
        d2.update(event_id="20260615-0002", station_id="desk-05", severity="warning",
                  summary="导线散落")
        e2 = parse_event(d2)
        report = self.report.generate(
            ReportRequest(report_type="post_class_acceptance", events=[e1, e2],
                          title="课后验收-A101")
        )
        self.assertEqual(report.verdict, "存在安全隐患")  # worst across desks
        self.assertIn("desk-05", report.body_markdown)


if __name__ == "__main__":
    unittest.main()
