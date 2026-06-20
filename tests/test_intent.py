import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.intent import parse_intent, parse_station_id, vlm_fallback  # noqa: E402


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

    def test_bare_number_not_a_station(self):
        # "5月" must NOT be parsed as a station -> whole sentence is None
        self.assertIsNone(parse_intent("检查一下5月份的巡检记录"))

    def test_laser_without_station_returns_none(self):
        self.assertIsNone(parse_intent("激光指示"))


class VlmFallbackTests(unittest.TestCase):
    def test_parses_json_command(self):
        chat = lambda p: '好的 {"type": "recheck_station", "params": {"station_id": "desk-04"}, "confidence": 0.9}'
        self.assertEqual(vlm_fallback("到四号桌那边瞧瞧", chat),
                         {"type": "recheck_station", "params": {"station_id": "desk-04"}})

    def test_low_confidence_returns_none(self):
        chat = lambda p: '{"type": "inspection_round", "params": {}, "confidence": 0.2}'
        self.assertIsNone(vlm_fallback("嗯啊这个", chat))

    def test_unknown_type_returns_none(self):
        chat = lambda p: '{"type": "dance", "params": {}, "confidence": 0.99}'
        self.assertIsNone(vlm_fallback("跳个舞", chat))

    def test_garbage_returns_none(self):
        self.assertIsNone(vlm_fallback("x", lambda p: "我不知道你在说什么"))

    def test_chat_exception_returns_none(self):
        def boom(p): raise RuntimeError("offline")
        self.assertIsNone(vlm_fallback("x", boom))

    def test_string_confidence_returns_none(self):
        chat = lambda p: '{"type": "inspection_round", "params": {}, "confidence": "高"}'
        self.assertIsNone(vlm_fallback("嗯", chat))


if __name__ == "__main__":
    unittest.main()
