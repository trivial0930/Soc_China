import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import teleop  # noqa: E402


class VelocityTests(unittest.TestCase):
    def test_never_set_returns_zero_and_big_age(self):
        s = teleop.TeleopStore()
        g = s.get_velocity(now=100.0)
        self.assertEqual((g["vx"], g["vy"], g["wz"]), (0.0, 0.0, 0.0))
        self.assertGreaterEqual(g["age_ms"], 1e8)

    def test_roundtrip_and_age_ms(self):
        s = teleop.TeleopStore()
        s.set_velocity(0.2, -0.1, 0.5, now=100.0)
        g = s.get_velocity(now=100.0)            # same instant -> age 0
        self.assertAlmostEqual(g["vx"], 0.2)
        self.assertAlmostEqual(g["vy"], -0.1)
        self.assertAlmostEqual(g["wz"], 0.5)
        self.assertAlmostEqual(g["age_ms"], 0.0)
        self.assertAlmostEqual(s.get_velocity(now=101.0)["age_ms"], 1000.0)  # 1s later

    def test_clamp(self):
        s = teleop.TeleopStore()
        s.set_velocity(5.0, -5.0, 9.0, now=0.0)
        g = s.get_velocity(now=0.0)
        self.assertEqual((g["vx"], g["vy"], g["wz"]), (0.4, -0.4, 1.5))
        s.set_velocity(-9.0, 9.0, -9.0, now=0.0)
        g = s.get_velocity(now=0.0)
        self.assertEqual((g["vx"], g["vy"], g["wz"]), (-0.4, 0.4, -1.5))


class StatusTests(unittest.TestCase):
    def test_never_reported(self):
        s = teleop.TeleopStore()
        g = s.get_status(now=10.0)
        self.assertEqual(g["state"], "unknown")
        self.assertIsNone(g["front_dist_m"])
        self.assertGreaterEqual(g["age_ms"], 1e8)

    def test_roundtrip(self):
        s = teleop.TeleopStore()
        s.set_status("slow", 0.8, now=10.0)
        g = s.get_status(now=10.5)
        self.assertEqual(g["state"], "slow")
        self.assertAlmostEqual(g["front_dist_m"], 0.8)
        self.assertAlmostEqual(g["age_ms"], 500.0)

    def test_null_front_dist(self):
        s = teleop.TeleopStore()
        s.set_status("blocked", None, now=20.0)
        self.assertIsNone(s.get_status(now=20.0)["front_dist_m"])


class LatestValueTests(unittest.TestCase):
    """Generic latest-only heartbeat store (used for robot mode)."""

    def test_default_before_first_set(self):
        v = teleop.LatestValue({"mode": "unknown"})
        g = v.get(now=5.0)
        self.assertEqual(g["mode"], "unknown")
        self.assertGreaterEqual(g["age_ms"], 1e8)

    def test_set_get_and_age(self):
        v = teleop.LatestValue({"mode": "unknown"})
        v.set({"mode": "mapping"}, now=10.0)
        self.assertEqual(v.get(now=10.0), {"mode": "mapping", "age_ms": 0.0})
        self.assertAlmostEqual(v.get(now=12.0)["age_ms"], 2000.0)
        v.set({"mode": "normal"}, now=20.0)             # overwrite + reset age
        self.assertEqual(v.get(now=20.0)["mode"], "normal")
        self.assertAlmostEqual(v.get(now=20.0)["age_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
