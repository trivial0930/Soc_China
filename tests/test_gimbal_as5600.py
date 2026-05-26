import sys
import unittest
from pathlib import Path


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(PACKAGE_SRC))

from gimbal_laser.as5600 import AS5600AngleSensor, raw_to_degrees


class FakeI2CBus:
    def __init__(self, high: int, low: int) -> None:
        self.high = high
        self.low = low
        self.calls = []

    def read_i2c_block_data(self, address: int, register: int, length: int):
        self.calls.append((address, register, length))
        return [self.high, self.low]


class AS5600Test(unittest.TestCase):
    def test_raw_to_degrees_uses_12_bit_range_and_zero_offset(self):
        self.assertAlmostEqual(raw_to_degrees(0), 0.0)
        self.assertAlmostEqual(raw_to_degrees(1024), 90.0)
        self.assertAlmostEqual(raw_to_degrees(2048, zero_deg=45.0), 135.0)

    def test_raw_to_degrees_wraps_to_signed_angle(self):
        self.assertAlmostEqual(raw_to_degrees(4095), -0.087890625)
        self.assertAlmostEqual(raw_to_degrees(0, zero_deg=180.0), -180.0)
        self.assertAlmostEqual(raw_to_degrees(3072), -90.0)

    def test_raw_to_degrees_supports_axis_inversion(self):
        self.assertAlmostEqual(raw_to_degrees(1024, invert=True), -90.0)
        self.assertAlmostEqual(raw_to_degrees(3072, invert=True), 90.0)

    def test_sensor_reads_raw_angle_register(self):
        bus = FakeI2CBus(0x04, 0x00)
        sensor = AS5600AngleSensor(bus=bus, address=0x36, zero_deg=10.0)

        self.assertAlmostEqual(sensor.read_degrees(), 80.0)
        self.assertEqual(bus.calls, [(0x36, 0x0C, 2)])


if __name__ == "__main__":
    unittest.main()
