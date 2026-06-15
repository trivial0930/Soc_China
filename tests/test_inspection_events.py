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

from inspection_manager.events import (  # noqa: E402
    Action,
    HazardEvent,
    parse_event,
    severity_rank,
)


# A representative Layer 1 /hazard/events payload (matches event_schema.md).
SAMPLE = {
    "event_id": "20260615-0001",
    "timestamp": "2026-06-15T20:30:00+08:00",
    "station_id": "desk-03",
    "source": "thermal",
    "event_type": "thermal_risk",
    "severity": "critical",
    "confidence": 0.95,
    "summary": "CRITICAL: soldering_iron (active 145C)",
    "evidence": {"image_path": "/ev/20260615-0001_critical.jpg", "log_path": "", "serial_output": ""},
    "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
}


class EventModelTests(unittest.TestCase):
    def test_severity_rank_orders_and_defaults_unknown_to_zero(self):
        self.assertLess(severity_rank("info"), severity_rank("warning"))
        self.assertLess(severity_rank("warning"), severity_rank("critical"))
        self.assertEqual(severity_rank("nonsense"), 0)

    def test_parse_from_json_string_round_trips(self):
        event = parse_event(json.dumps(SAMPLE))
        self.assertEqual(event.event_id, "20260615-0001")
        self.assertEqual(event.station_id, "desk-03")
        self.assertEqual(event.severity, "critical")
        self.assertEqual(event.evidence.image_path, "/ev/20260615-0001_critical.jpg")
        # Round trip preserves the schema fields.
        self.assertEqual(parse_event(event.to_json()).to_dict(), event.to_dict())

    def test_parse_accepts_dict_and_fills_missing_optionals(self):
        minimal = {"event_id": "x", "timestamp": "t"}
        event = parse_event(minimal)
        self.assertEqual(event.source, "mock")
        self.assertEqual(event.severity, "info")
        self.assertEqual(event.action.reported_to_admin, False)
        self.assertEqual(event.evidence.image_path, "")

    def test_to_dict_keeps_schema_field_order(self):
        event = parse_event(SAMPLE)
        self.assertEqual(
            list(event.to_dict().keys()),
            [
                "event_id", "timestamp", "station_id", "source", "event_type",
                "severity", "confidence", "summary", "evidence", "action",
            ],
        )

    def test_action_block_is_fillable_and_serializes(self):
        event = parse_event(SAMPLE)
        event.action = Action(
            robot_task="recheck:desk-03",
            voice_prompt="3号工位电烙铁疑似未断电，请处理",
            reported_to_admin=True,
        )
        out = json.loads(event.to_json())
        self.assertEqual(out["action"]["robot_task"], "recheck:desk-03")
        self.assertTrue(out["action"]["reported_to_admin"])

    def test_missing_required_field_raises(self):
        with self.assertRaises(KeyError):
            parse_event({"timestamp": "t"})


if __name__ == "__main__":
    unittest.main()
