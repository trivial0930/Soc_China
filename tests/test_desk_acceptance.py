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

from inspection_manager.desk_acceptance import (  # noqa: E402
    assess_desk,
    assessment_to_event,
)


CLEAN = {
    "soldering_iron_off": True, "power_disconnected": True, "wires_tidy": True,
    "no_flammable_left": True, "instruments_stowed": True,
    "component_box_returned": True, "desk_clear": True,
}


class AssessDeskTests(unittest.TestCase):
    def test_clean_desk_passes(self):
        a = assess_desk("desk-01", CLEAN)
        self.assertEqual(a.verdict, "合格")
        self.assertEqual(a.severity, "info")
        self.assertEqual(a.problems, [])

    def test_missing_keys_assumed_clean(self):
        a = assess_desk("desk-01", {})
        self.assertEqual(a.verdict, "合格")

    def test_loose_wires_needs_tidy(self):
        obs = {**CLEAN, "wires_tidy": False}
        a = assess_desk("desk-02", obs)
        self.assertEqual(a.verdict, "需整理")
        self.assertEqual(a.severity, "warning")
        self.assertIn("导线杂乱拖拽", a.problems)

    def test_soldering_iron_on_is_safety_hazard(self):
        obs = {**CLEAN, "soldering_iron_off": False}
        a = assess_desk("desk-03", obs)
        self.assertEqual(a.verdict, "存在安全隐患")
        self.assertEqual(a.severity, "critical")

    def test_worst_severity_wins_with_multiple_problems(self):
        obs = {**CLEAN, "wires_tidy": False, "power_disconnected": False}
        a = assess_desk("desk-04", obs)
        self.assertEqual(a.severity, "critical")  # power beats wires
        self.assertEqual(len(a.problems), 2)


class AssessmentToEventTests(unittest.TestCase):
    def test_pass_yields_no_event(self):
        a = assess_desk("desk-01", CLEAN)
        self.assertIsNone(assessment_to_event(a, "id", "ts"))

    def test_hazard_yields_desk_messy_event(self):
        a = assess_desk("desk-03", {**CLEAN, "soldering_iron_off": False})
        event = assessment_to_event(a, "20260615-9", "2026-06-15T21:00:00+08:00")
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "desk_messy")
        self.assertEqual(event.severity, "critical")
        self.assertEqual(event.station_id, "desk-03")
        self.assertIn("电烙铁", event.summary)
        self.assertEqual(event.source, "camera")


if __name__ == "__main__":
    unittest.main()
