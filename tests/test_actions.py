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
    LogRecord,
    RobotRecheck,
    VoicePrompt,
    fill_event_action,
    route_actions,
)
from inspection_manager.cognition import CognitionResult  # noqa: E402
from inspection_manager.events import HazardEvent  # noqa: E402
from inspection_manager.station_map import station_map_from_dict  # noqa: E402


STATIONS = station_map_from_dict({"waypoints": {"wp_desk03": "desk-03"}})


def event(station="desk-03"):
    return HazardEvent(
        event_id="20260615-7", timestamp="t", station_id=station, source="thermal",
        event_type="thermal_risk", severity="critical", confidence=0.9,
        summary="soldering_iron active 145C",
    )


def result(actions, escalate=False, explanation="desk-03：高温电烙铁"):
    return CognitionResult(
        explanation=explanation, confirmed_severity="critical",
        suggested_actions=actions, escalate_to_cloud=escalate, confidence=0.9,
    )


class RouteActionsTests(unittest.TestCase):
    def test_full_set_routes_to_typed_actions(self):
        routed = route_actions(result(["voice", "recheck", "aim", "log"]), event(), STATIONS)
        self.assertEqual([type(a).__name__ for a in routed],
                         ["VoicePrompt", "RobotRecheck", "AimGimbal", "LogRecord"])

    def test_recheck_resolves_waypoint_from_station(self):
        routed = route_actions(result(["recheck"]), event(), STATIONS)
        self.assertEqual(routed[0].waypoint, "wp_desk03")

    def test_recheck_unknown_station_has_none_waypoint(self):
        routed = route_actions(result(["recheck"]), event(station="desk-99"), STATIONS)
        self.assertIsNone(routed[0].waypoint)

    def test_voice_carries_explanation(self):
        routed = route_actions(result(["voice"], explanation="请处理"), event(), STATIONS)
        self.assertEqual(routed[0].text, "请处理")

    def test_aim_is_placeholder_until_visual_servoing(self):
        routed = route_actions(result(["aim"]), event(), STATIONS)
        self.assertIsNone(routed[0].pan_deg)
        self.assertEqual(routed[0].station_id, "desk-03")

    def test_unknown_action_kind_ignored(self):
        routed = route_actions(result(["voice", "teleport"]), event(), STATIONS)
        self.assertEqual(len(routed), 1)


class FillEventActionTests(unittest.TestCase):
    def test_fills_voice_robot_and_admin_flag(self):
        ev = event()
        res = result(["voice", "recheck", "log"], escalate=True)
        routed = route_actions(res, ev, STATIONS)
        fill_event_action(ev, res, routed)
        self.assertEqual(ev.action.voice_prompt, res.explanation)
        self.assertEqual(ev.action.robot_task, "recheck:desk-03")
        self.assertTrue(ev.action.reported_to_admin)

    def test_no_recheck_leaves_robot_task_empty(self):
        ev = event()
        res = result(["voice", "log"], escalate=False)
        routed = route_actions(res, ev, STATIONS)
        fill_event_action(ev, res, routed)
        self.assertEqual(ev.action.robot_task, "")
        self.assertFalse(ev.action.reported_to_admin)


if __name__ == "__main__":
    unittest.main()
