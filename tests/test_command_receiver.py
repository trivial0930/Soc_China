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
    dispatch_command, find_item_to_command, station_to_waypoint,
)
from inspection_manager.desk_acceptance import expand_targets  # noqa: E402

STATIONS = {"waypoints": {"wp_desk01": "desk-01", "wp_desk03": "desk-03"}}
GIMBAL = {"aim": {"desk-03": [12.6, -11.6], "柜2/抽屉3": [30.0, -5.0]}}


class DispatchTests(unittest.TestCase):
    def test_station_to_waypoint_reverse_lookup(self):
        self.assertEqual(station_to_waypoint("desk-03", STATIONS), "wp_desk03")
        self.assertIsNone(station_to_waypoint("desk-99", STATIONS))

    def _one(self, out):
        self.assertNotIn("unsupported", out)
        self.assertEqual(len(out["actions"]), 1)
        return out["actions"][0]

    def test_voice_prompt(self):
        act = self._one(dispatch_command({"type": "voice_prompt", "params": {"text": "请整理桌面"}}))
        self.assertEqual(act["topic_key"], "voice_topic")
        self.assertEqual(act["data"], "请整理桌面")

    def test_voice_prompt_empty_unsupported(self):
        self.assertIn("unsupported", dispatch_command({"type": "voice_prompt", "params": {"text": ""}}))

    def test_recheck_resolves_waypoint(self):
        act = self._one(dispatch_command({"type": "recheck_station", "params": {"station_id": "desk-03"}}, STATIONS))
        self.assertEqual(act["topic_key"], "recheck_topic")
        self.assertEqual(json.loads(act["data"]), {"station_id": "desk-03", "waypoint": "wp_desk03"})

    def test_recheck_unknown_station_unsupported(self):
        self.assertIn("unsupported",
                      dispatch_command({"type": "recheck_station", "params": {"station_id": "desk-99"}}, STATIONS))

    def test_generate_report_default_and_explicit(self):
        self.assertEqual(self._one(dispatch_command({"type": "generate_report", "params": {}}))["data"],
                         "periodic_summary")
        self.assertEqual(self._one(dispatch_command(
            {"type": "generate_report", "params": {"report_type": "post_class_acceptance"}}))["data"],
            "post_class_acceptance")

    def test_inspection_round_patrols_all_waypoints(self):
        out = dispatch_command({"type": "inspection_round", "params": {}}, STATIONS)
        self.assertEqual(len(out["actions"]), 2)                       # one recheck per waypoint
        self.assertTrue(all(a["topic_key"] == "recheck_topic" for a in out["actions"]))

    def test_laser_point_returns_aim_angle(self):
        out = dispatch_command({"type": "laser_point", "params": {"station_id": "desk-03"}}, STATIONS, GIMBAL)
        self.assertEqual(out["laser_aim"], [12.6, -11.6])             # node runs the timed routine
        self.assertNotIn("unsupported", out)

    def test_laser_point_no_angle_unsupported(self):
        self.assertIn("unsupported",
                      dispatch_command({"type": "laser_point", "params": {"station_id": "desk-99"}}, STATIONS, GIMBAL))

    def test_acceptance_request(self):
        act = self._one(dispatch_command({"type": "acceptance", "params": {"station_id": "desk-03"}}))
        self.assertEqual(act["topic_key"], "acceptance_request_topic")
        self.assertEqual(act["data"], "desk-03")
        self.assertEqual(self._one(dispatch_command({"type": "acceptance", "params": {}}))["data"], "all")

    def test_find_item_helper_navigate_vs_laser(self):
        asset = {"station_id": "desk-01", "location_text": "柜2/抽屉3"}
        nav = find_item_to_command(asset, "navigate")
        self.assertEqual(nav, {"type": "recheck_station", "params": {"station_id": "desk-01"}})
        laser = find_item_to_command(asset, "laser")
        self.assertEqual(laser, {"type": "laser_point", "params": {"location": "柜2/抽屉3"}})

    def test_expand_targets(self):
        self.assertEqual(expand_targets("desk-03", STATIONS), ["desk-03"])
        self.assertEqual(expand_targets("all", STATIONS), ["desk-01", "desk-03"])

    def test_voice_control_enable(self):
        out = dispatch_command({"type": "voice_control", "params": {"enabled": True}})
        act = self._one(out)
        self.assertEqual(act["topic_key"], "voice_control_topic")
        self.assertEqual(json.loads(act["data"]), {"enabled": True})
        self.assertEqual(out["result"], "语音监听已开启")

    def test_voice_control_disable(self):
        out = dispatch_command({"type": "voice_control", "params": {"enabled": False}})
        self.assertEqual(json.loads(self._one(out)["data"]), {"enabled": False})
        self.assertEqual(out["result"], "语音监听已关闭")

    def test_voice_control_missing_enabled_unsupported(self):
        self.assertIn("unsupported", dispatch_command({"type": "voice_control", "params": {}}))
        self.assertIn("unsupported", dispatch_command({"type": "voice_control", "params": {"enabled": "yes"}}))

    def test_set_volume_returns_level(self):
        out = dispatch_command({"type": "set_volume", "params": {"level": 60}})
        self.assertEqual(out["set_volume"], 60)
        self.assertEqual(out["result"], "播报音量已设为 60")
        self.assertNotIn("unsupported", out)
        self.assertIn("unsupported", dispatch_command({"type": "set_volume", "params": {"level": 150}}))
        self.assertIn("unsupported", dispatch_command({"type": "set_volume", "params": {}}))

    def test_unknown_type_reported(self):
        self.assertIn("unsupported", dispatch_command({"type": "teleport", "params": {}}, STATIONS))

    def test_set_mode_mapping_recognized(self):
        plan = dispatch_command({"type": "set_mode", "params": {"mode": "mapping"}})
        self.assertEqual(plan["set_mode"], "mapping")

    def test_set_mode_invalid_unsupported(self):
        plan = dispatch_command({"type": "set_mode", "params": {"mode": "fly"}})
        self.assertIn("unsupported", plan)

    def test_save_map_recognized_with_default_name(self):
        plan = dispatch_command({"type": "save_map", "params": {}})
        self.assertEqual(plan["save_map"], "lab_map")

    def test_save_map_uses_given_name(self):
        plan = dispatch_command({"type": "save_map", "params": {"name": "floor2"}})
        self.assertEqual(plan["save_map"], "floor2")


if __name__ == "__main__":
    unittest.main()
