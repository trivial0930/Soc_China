import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.dialog import wake_ack, not_understood, reply_for  # noqa: E402


class DialogTests(unittest.TestCase):
    def test_wake_ack_default_and_custom(self):
        self.assertEqual(wake_ack(), "我在")
        self.assertEqual(wake_ack("在呢"), "在呢")

    def test_not_understood_is_guiding(self):
        msg = not_understood()
        self.assertIn("没太听清", msg)

    def test_immediate_reply_uses_result(self):
        self.assertEqual(reply_for("laser_point", {"result": "激光已指向 desk-03"}),
                         "激光已指向 desk-03")

    def test_moving_command_honest_downgrade(self):
        out = reply_for("recheck_station", {"result": "已发起到 desk-03 的复核导航"})
        self.assertIn("已发起到 desk-03 的复核导航", out)
        self.assertIn("底盘移动还在调试", out)

    def test_inspection_round_also_downgrades(self):
        self.assertIn("底盘移动还在调试",
                      reply_for("inspection_round", {"result": "已发起巡检:依次复核 3 个工位"}))

    def test_unsupported_apologizes(self):
        self.assertEqual(reply_for("recheck_station", {"unsupported": "工位 desk-99 未配置 waypoint"}),
                         "抱歉,工位 desk-99 未配置 waypoint")


if __name__ == "__main__":
    unittest.main()
