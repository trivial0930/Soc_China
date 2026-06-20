import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.intent import parse_intent, parse_station_id  # noqa: E402


class StationIdTests(unittest.TestCase):
    def test_chinese_and_arabic(self):
        self.assertEqual(parse_station_id("去三号桌看看"), "desk-03")
        self.assertEqual(parse_station_id("复核5号工位"), "desk-05")
        self.assertEqual(parse_station_id("第十二号"), "desk-12")
    def test_none_when_no_number(self):
        self.assertIsNone(parse_station_id("开始巡检"))


class IntentTests(unittest.TestCase):
    def test_recheck(self):
        self.assertEqual(parse_intent("去三号桌复核"),
                         {"type": "recheck_station", "params": {"station_id": "desk-03"}})
        self.assertEqual(parse_intent("检查一下二号工位"),
                         {"type": "recheck_station", "params": {"station_id": "desk-02"}})

    def test_laser(self):
        self.assertEqual(parse_intent("激光指示三号桌"),
                         {"type": "laser_point", "params": {"station_id": "desk-03"}})

    def test_inspection_round(self):
        self.assertEqual(parse_intent("开始全面巡检"), {"type": "inspection_round", "params": {}})

    def test_acceptance_specific_and_all(self):
        self.assertEqual(parse_intent("对三号桌做课后验收"),
                         {"type": "acceptance", "params": {"station_id": "desk-03"}})
        self.assertEqual(parse_intent("全部工位验收"),
                         {"type": "acceptance", "params": {"station_id": "all"}})

    def test_voice_prompt(self):
        self.assertEqual(parse_intent("播报请大家注意用电安全"),
                         {"type": "voice_prompt", "params": {"text": "请大家注意用电安全"}})

    def test_generate_report(self):
        self.assertEqual(parse_intent("生成巡检报告"),
                         {"type": "generate_report", "params": {"report_type": "periodic_summary"}})

    def test_unmatched_returns_none(self):
        self.assertIsNone(parse_intent("今天天气怎么样"))


if __name__ == "__main__":
    unittest.main()
