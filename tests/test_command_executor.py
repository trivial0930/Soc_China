import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.command_executor import CommandExecutor  # noqa: E402


class FakeTimer:
    def __init__(self): self.canceled = False
    def cancel(self): self.canceled = True


class Harness:
    def __init__(self):
        self.published = []          # list of (topic_key, kind, data)
        self.timers = []             # list of (period, callback, FakeTimer)
    def publish(self, topic_key, kind, data):
        self.published.append((topic_key, kind, data))
    def schedule(self, period, cb):
        t = FakeTimer(); self.timers.append((period, cb, t)); return t


class CommandExecutorTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.ex = CommandExecutor(self.h.publish, self.h.schedule, laser_indicate_sec=8.0)

    def test_execute_actions(self):
        plan = {"actions": [{"topic_key": "voice_topic", "kind": "string", "data": "请整理桌面"}],
                "result": "已播报:请整理桌面"}
        self.assertEqual(self.ex.execute(plan), "已播报:请整理桌面")
        self.assertEqual(self.h.published, [("voice_topic", "string", "请整理桌面")])

    def test_execute_laser_sequence(self):
        plan = {"laser_aim": [12.6, -11.6], "result": "激光已指向 desk-03"}
        self.assertEqual(self.ex.execute(plan), "激光已指向 desk-03")
        # FAULT 清除 + 使能 + 激光开
        self.assertEqual(self.h.published[0], ("gimbal_enable_topic", "bool", False))
        self.assertEqual(self.h.published[1], ("gimbal_enable_topic", "bool", True))
        self.assertEqual(self.h.published[2], ("laser_topic", "bool", True))
        # 注册了 sustain(0.1s) 与 stop(8.0s) 两个定时器
        periods = sorted(p for p, _, _ in self.h.timers)
        self.assertEqual(periods, [0.1, 8.0])

    def test_laser_sustain_tick_publishes_gimbal_vector(self):
        self.ex.execute({"laser_aim": [12.6, -11.6], "result": "x"})
        sustain_cb = next(cb for p, cb, _ in self.h.timers if p == 0.1)
        self.h.published.clear()
        sustain_cb()
        self.assertEqual(self.h.published, [("gimbal_topic", "vector3", [12.6, -11.6, 0.0])])

    def test_laser_stop_turns_off_and_cancels(self):
        self.ex.execute({"laser_aim": [1.0, 2.0], "result": "x"})
        stop_cb = next(cb for p, cb, _ in self.h.timers if p == 8.0)
        self.h.published.clear()
        stop_cb()
        self.assertIn(("laser_topic", "bool", False), self.h.published)
        self.assertTrue(all(t.canceled for _, _, t in self.h.timers))


if __name__ == "__main__":
    unittest.main()
