import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.asr_engine import MockAsrBackend, wake_event, utterance_event  # noqa: E402


class MockBackendTests(unittest.TestCase):
    def test_poll_pops_events_then_none(self):
        be = MockAsrBackend([wake_event(), utterance_event("去三号桌复核")])
        self.assertEqual(be.poll(), {"kind": "wake"})
        self.assertEqual(be.poll(), {"kind": "utterance", "text": "去三号桌复核"})
        self.assertIsNone(be.poll())

    def test_set_mode_recorded(self):
        be = MockAsrBackend([])
        be.set_mode("dialog"); be.set_mode("kws")
        self.assertEqual(be.modes, ["dialog", "kws"])


from inspection_manager.asr_controller import AsrController  # noqa: E402
from inspection_manager.intent import parse_intent  # noqa: E402

STATIONS = {"waypoints": {"wp_desk03": "desk-03"}}
GIMBAL = {"aim": {"desk-03": [12.6, -11.6]}}


def _dispatch(cmd, stations_cfg, gimbal_cfg):
    from inspection_manager.command_receiver import dispatch_command
    return dispatch_command(cmd, stations_cfg, gimbal_cfg)


class FakeExecutor:
    def __init__(self): self.plans = []
    def execute(self, plan):
        self.plans.append(plan); return plan.get("result")


def _make(events, **kw):
    be = MockAsrBackend(events)
    spoken = []
    ex = FakeExecutor()
    c = AsrController(be, parse_intent, _dispatch, ex, spoken.append,
                      stations_cfg=STATIONS, gimbal_cfg=GIMBAL, dialog_timeout_sec=8.0, **kw)
    return c, be, spoken, ex


class ControllerTests(unittest.TestCase):
    def test_starts_idle_in_kws_mode(self):
        c, be, _, _ = _make([])
        self.assertEqual(c.state, "idle")
        self.assertEqual(be.modes[-1], "kws")

    def test_wake_acks_and_enters_dialog(self):
        c, be, spoken, _ = _make([wake_event()])
        c.tick(0.0)
        self.assertEqual(c.state, "dialog")
        self.assertEqual(spoken, ["我在"])
        self.assertEqual(be.modes[-1], "dialog")

    def test_utterance_dispatches_and_replies(self):
        c, be, spoken, ex = _make([wake_event(), utterance_event("激光指示三号桌")])
        c.tick(0.0); c.tick(0.1)
        self.assertEqual(ex.plans[-1]["laser_aim"], [12.6, -11.6])
        self.assertEqual(spoken[-1], "激光已指向 desk-03(pan=12.6,tilt=-11.6)")

    def test_moving_command_downgrade_phrasing(self):
        c, _, spoken, _ = _make([wake_event(), utterance_event("去三号桌复核")])
        c.tick(0.0); c.tick(0.1)
        self.assertIn("底盘移动还在调试", spoken[-1])

    def test_not_understood(self):
        c, _, spoken, ex = _make([wake_event(), utterance_event("今天星期几")])
        c.tick(0.0); c.tick(0.1)
        self.assertIn("没太听清", spoken[-1])
        self.assertEqual(ex.plans, [])

    def test_dialog_timeout_returns_to_idle(self):
        c, be, _, _ = _make([wake_event()])
        c.tick(0.0)
        c.tick(9.0)                          # 9s 静默 > 8s 超时
        self.assertEqual(c.state, "idle")
        self.assertEqual(be.modes[-1], "kws")

    def test_set_enabled_false_disables(self):
        c, be, _, _ = _make([])
        c.set_enabled(False)
        self.assertEqual(c.state, "disabled")
        self.assertEqual(be.modes[-1], "off")
        c.tick(0.0)                          # disabled 时 tick 不处理事件
        self.assertEqual(c.state, "disabled")

    def test_vlm_fallback_used_when_rule_misses(self):
        c, _, spoken, ex = _make(
            [wake_event(), utterance_event("麻烦到三号桌那边瞅一眼")],
            vlm_chat_fn=lambda p: '{"type":"recheck_station","params":{"station_id":"desk-03"},"confidence":0.9}')
        c.tick(0.0); c.tick(0.1)
        self.assertEqual(ex.plans[-1]["actions"][0]["topic_key"], "recheck_topic")

    def test_unsupported_plan_not_executed_but_replies(self):
        # desk-09 is NOT in STATIONS waypoints -> dispatch_command returns unsupported
        c, _, spoken, ex = _make([wake_event(), utterance_event("去九号桌复核")])
        c.tick(0.0); c.tick(0.1)
        self.assertEqual(ex.plans, [])                  # unsupported -> executor NOT called
        self.assertTrue(spoken[-1].startswith("抱歉"))  # but a reply is still spoken

    def test_wake_while_dialog_is_ignored(self):
        c, be, spoken, _ = _make([wake_event(), wake_event()])
        c.tick(0.0)                                     # 1st wake: idle -> dialog, ack "我在"
        c.tick(0.1)                                     # 2nd wake while dialog -> ignored
        self.assertEqual(spoken, ["我在"])              # no second ack
        self.assertEqual(c.state, "dialog")

    def test_utterance_while_idle_is_ignored(self):
        c, _, spoken, ex = _make([utterance_event("去三号桌复核")])
        c.tick(0.0)                                     # utterance in idle -> consumed, no action
        self.assertEqual(ex.plans, [])
        self.assertEqual(spoken, [])

    def test_execute_error_is_spoken_not_raised(self):
        class BoomExecutor:
            def execute(self, plan):
                raise RuntimeError("publish failed")
        be = MockAsrBackend([wake_event(), utterance_event("激光指示三号桌")])
        spoken = []
        c = AsrController(be, parse_intent, _dispatch, BoomExecutor(), spoken.append,
                          stations_cfg=STATIONS, gimbal_cfg=GIMBAL, dialog_timeout_sec=8.0)
        c.tick(0.0)
        c.tick(0.1)            # must NOT raise
        self.assertIn("出错", spoken[-1])


if __name__ == "__main__":
    unittest.main()
