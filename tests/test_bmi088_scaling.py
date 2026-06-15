import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/bmi088_imu"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from bmi088_imu.bmi088 import accel_ms2, gyro_rads, to_int16  # noqa: E402


class ToInt16Test(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(to_int16(0x10, 0x00), 16)

    def test_negative(self):
        self.assertEqual(to_int16(0x00, 0x80), -32768)

    def test_minus_one(self):
        self.assertEqual(to_int16(0xFF, 0xFF), -1)


class AccelScaleTest(unittest.TestCase):
    def test_full_scale_6g(self):
        # +32767 ~ +6g ~ 6*9.80665 m/s^2
        self.assertAlmostEqual(accel_ms2(32768, 6.0), 6 * 9.80665, places=3)

    def test_zero(self):
        self.assertEqual(accel_ms2(0, 6.0), 0.0)

    def test_one_g_at_6g_range(self):
        # ~1g should be raw ~ 32768/6
        raw = round(32768 / 6)
        self.assertAlmostEqual(accel_ms2(raw, 6.0), 9.80665, places=1)


class GyroScaleTest(unittest.TestCase):
    def test_full_scale_2000dps(self):
        self.assertAlmostEqual(gyro_rads(32768, 2000.0), 2000 * math.pi / 180.0, places=4)

    def test_zero(self):
        self.assertEqual(gyro_rads(0, 2000.0), 0.0)

    def test_sign(self):
        self.assertLess(gyro_rads(-1000, 2000.0), 0.0)


if __name__ == "__main__":
    unittest.main()
