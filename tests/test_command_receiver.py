import json
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.command_receiver import (  # noqa: E402
    dispatch_command, station_to_waypoint,
)

STATIONS = {"waypoints": {"wp_desk01": "desk-01", "wp_desk03": "desk-03"}}


class DispatchTests(unittest.TestCase):
    def test_station_to_waypoint_reverse_lookup(self):
        self.assertEqual(station_to_waypoint("desk-03", STATIONS), "wp_desk03")
        self.assertIsNone(station_to_waypoint("desk-99", STATIONS))

    def test_voice_prompt(self):
        out = dispatch_command({"type": "voice_prompt", "params": {"text": "请整理桌面"}})
        self.assertEqual(out["topic_key"], "voice_topic")
        self.assertEqual(out["data"], "请整理桌面")

    def test_voice_prompt_empty_unsupported(self):
        self.assertIn("unsupported", dispatch_command({"type": "voice_prompt", "params": {"text": ""}}))

    def test_recheck_resolves_waypoint(self):
        out = dispatch_command({"type": "recheck_station", "params": {"station_id": "desk-03"}}, STATIONS)
        self.assertEqual(out["topic_key"], "recheck_topic")
        self.assertEqual(json.loads(out["data"]), {"station_id": "desk-03", "waypoint": "wp_desk03"})

    def test_recheck_unknown_station_unsupported(self):
        out = dispatch_command({"type": "recheck_station", "params": {"station_id": "desk-99"}}, STATIONS)
        self.assertIn("unsupported", out)

    def test_generate_report_default_and_explicit(self):
        d1 = dispatch_command({"type": "generate_report", "params": {}})
        self.assertEqual(d1["topic_key"], "request_report_topic")
        self.assertEqual(d1["data"], "periodic_summary")
        d2 = dispatch_command({"type": "generate_report", "params": {"report_type": "post_class_acceptance"}})
        self.assertEqual(d2["data"], "post_class_acceptance")

    def test_unsupported_types_reported(self):
        for t in ("inspection_round", "acceptance", "find_item", "laser_point"):
            self.assertIn("unsupported", dispatch_command({"type": t, "params": {}}, STATIONS))


if __name__ == "__main__":
    unittest.main()
