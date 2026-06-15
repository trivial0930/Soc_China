import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/chassis_bringup"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from chassis_bringup.waypoint_patrol import parse_waypoints, yaw_to_quat  # noqa: E402


class WaypointParseTest(unittest.TestCase):
    def test_parses_triples(self):
        wps = parse_waypoints([0.0, 0.0, 0.0, 1.0, 2.0, 1.57])
        self.assertEqual(wps, [(0.0, 0.0, 0.0), (1.0, 2.0, 1.57)])

    def test_rejects_bad_length(self):
        with self.assertRaises(ValueError):
            parse_waypoints([0.0, 1.0])

    def test_empty_is_empty(self):
        self.assertEqual(parse_waypoints([]), [])


class YawToQuatTest(unittest.TestCase):
    def test_zero_yaw(self):
        qz, qw = yaw_to_quat(0.0)
        self.assertAlmostEqual(qz, 0.0, places=9)
        self.assertAlmostEqual(qw, 1.0, places=9)

    def test_half_pi(self):
        qz, qw = yaw_to_quat(math.pi / 2.0)
        self.assertAlmostEqual(qz, math.sin(math.pi / 4.0), places=9)
        self.assertAlmostEqual(qw, math.cos(math.pi / 4.0), places=9)

    def test_normalized(self):
        for yaw in (-2.0, -0.3, 0.7, 3.0):
            qz, qw = yaw_to_quat(yaw)
            self.assertAlmostEqual(qz * qz + qw * qw, 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
