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

from inspection_manager.events import parse_event  # noqa: E402
from inspection_manager.recheck import parse_recheck, pose_for_waypoint  # noqa: E402
from inspection_manager.sim_scenarios import make_event, sample_events  # noqa: E402
from inspection_manager.tts import MockTTSBackend, VoiceThrottle  # noqa: E402


class VoiceThrottleTests(unittest.TestCase):
    def test_same_text_suppressed_within_window(self):
        t = VoiceThrottle(window_sec=10.0)
        self.assertTrue(t.allow("请处理", now=0.0))
        self.assertFalse(t.allow("请处理", now=3.0))
        self.assertTrue(t.allow("请处理", now=11.0))  # window passed

    def test_different_text_not_suppressed(self):
        t = VoiceThrottle(window_sec=10.0)
        self.assertTrue(t.allow("A", now=0.0))
        self.assertTrue(t.allow("B", now=1.0))

    def test_mock_backend_records(self):
        b = MockTTSBackend()
        b.speak("hi")
        b.speak("bye")
        self.assertEqual(b.spoken, ["hi", "bye"])


class RecheckTests(unittest.TestCase):
    CFG = {"poses": {"wp_desk03": [1.5, 2.0, 0.0], "wp_desk05": [3.0, 1.0, 1.57]}}

    def test_parse_recheck_string_and_dict(self):
        self.assertEqual(
            parse_recheck('{"station_id":"desk-03","waypoint":"wp_desk03"}'),
            {"station_id": "desk-03", "waypoint": "wp_desk03"},
        )
        self.assertEqual(parse_recheck({"station_id": "x"})["waypoint"], None)

    def test_pose_lookup(self):
        self.assertEqual(pose_for_waypoint("wp_desk05", self.CFG), (3.0, 1.0, 1.57))

    def test_pose_lookup_missing_returns_none(self):
        self.assertIsNone(pose_for_waypoint("nope", self.CFG))
        self.assertIsNone(pose_for_waypoint(None, self.CFG))
        self.assertIsNone(pose_for_waypoint("wp_desk03", {}))


class SimScenarioTests(unittest.TestCase):
    def test_make_event_is_parseable(self):
        ev = make_event("e1", "desk-01", "warning", "x")
        parsed = parse_event(ev)  # must satisfy the schema
        self.assertEqual(parsed.station_id, "desk-01")
        self.assertEqual(parsed.event_type, "thermal_risk")

    def test_desk_messy_event_uses_camera_source(self):
        ev = make_event("e2", "desk-01", "warning", "乱", event_type="desk_messy")
        self.assertEqual(ev["source"], "camera")

    def test_sample_events_mixed_and_valid(self):
        events = sample_events()
        self.assertEqual(len(events), 3)
        for e in events:
            parse_event(e)  # all valid
        severities = {e["severity"] for e in events}
        self.assertIn("critical", severities)


if __name__ == "__main__":
    unittest.main()
