"""Unit tests for the hardware-independent parts of the SenXor thermal driver.

The SPI/I2C/GPIO touching code lives behind a backend Protocol and can only be
validated on the RDK during Phase 1 bring-up. Everything tested here is pure:
frame reshape, orientation, unit conversion, and the ThermalCamera glue exercised
through a fake backend.
"""

import sys
import unittest
from pathlib import Path


PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5"
    / "ros2_ws"
    / "src"
    / "thermal_detector"
)
sys.path.insert(0, str(PACKAGE_SRC))

from thermal_detector.senxor_driver import (  # noqa: E402
    MockSenxorBackend,
    ThermalCamera,
    deci_kelvin_to_celsius,
    reshape_celsius,
)


class ReshapeTests(unittest.TestCase):
    def test_reshapes_row_major(self):
        flat = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        self.assertEqual(reshape_celsius(flat, 3, 2), [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    def test_flip_vertical(self):
        flat = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        self.assertEqual(
            reshape_celsius(flat, 3, 2, flip_vertical=True),
            [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]],
        )

    def test_flip_horizontal(self):
        flat = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        self.assertEqual(
            reshape_celsius(flat, 3, 2, flip_horizontal=True),
            [[3.0, 2.0, 1.0], [6.0, 5.0, 4.0]],
        )

    def test_wrong_length_raises(self):
        with self.assertRaises(ValueError):
            reshape_celsius([1.0, 2.0, 3.0], 3, 2)


class UnitConversionTests(unittest.TestCase):
    def test_deci_kelvin_to_celsius(self):
        # 2982 deci-Kelvin = 298.2 K = 25.05 C
        self.assertAlmostEqual(deci_kelvin_to_celsius(2982), 25.05, places=2)


class ThermalCameraTests(unittest.TestCase):
    def test_read_frame_reshapes_backend_output(self):
        flat = [float(v) for v in range(80 * 62)]

        class FakeBackend:
            def __init__(self):
                self.started = False
                self.stopped = False

            def start_stream(self):
                self.started = True

            def read_celsius_frame(self):
                return flat

            def stop(self):
                self.stopped = True

        backend = FakeBackend()
        cam = ThermalCamera(backend=backend, width=80, height=62)
        cam.init()
        self.assertTrue(backend.started)

        frame = cam.read_frame()
        self.assertEqual(len(frame), 62)
        self.assertEqual(len(frame[0]), 80)
        self.assertEqual(frame[0][0], 0.0)
        self.assertEqual(frame[-1][-1], float(80 * 62 - 1))

        cam.close()
        self.assertTrue(backend.stopped)

    def test_mock_backend_produces_a_hotspot(self):
        cam = ThermalCamera(backend=MockSenxorBackend(), width=80, height=62)
        cam.init()
        frame = cam.read_frame()
        self.assertEqual(len(frame), 62)
        self.assertEqual(len(frame[0]), 80)
        peak = max(v for row in frame for v in row)
        ambient = frame[0][0]
        self.assertGreater(peak, ambient + 20.0)


if __name__ == "__main__":
    unittest.main()
