import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5"
    / "ros2_ws"
    / "src"
    / "gimbal_laser"
)
sys.path.insert(0, str(PACKAGE_SRC))

from gimbal_laser.rdk_x5_gpio import HobotGpioLine  # noqa: E402


class FakeGpio:
    BOARD = "BOARD"
    OUT = "OUT"
    HIGH = 1
    LOW = 0

    def __init__(self):
        self.writes = []
        self.setup_calls = []
        self.cleaned = []

    def setwarnings(self, enabled):
        pass

    def setmode(self, mode):
        pass

    def setup(self, pin, mode, initial=0):
        self.setup_calls.append((pin, initial))

    def output(self, pin, value):
        self.writes.append((pin, value))

    def cleanup(self, pin=None):
        self.cleaned.append(pin)


class LaserGpioLineTests(unittest.TestCase):
    def _line(self, active_high=True):
        g = FakeGpio()
        line = HobotGpioLine(pin=12, active_high=active_high)
        line.gpio_module = g  # inject fake
        return line, g

    def test_active_high_on_drives_high_off_drives_low(self):
        line, g = self._line(active_high=True)
        line.write(True)
        line.write(False)
        self.assertEqual(g.writes, [(12, g.HIGH), (12, g.LOW)])

    def test_active_low_inverts(self):
        line, g = self._line(active_high=False)
        line.enable()
        line.disable()
        self.assertEqual(g.writes, [(12, g.LOW), (12, g.HIGH)])

    def test_setup_output_initial_off_is_low_when_active_high(self):
        line, g = self._line(active_high=True)
        line.setup_output(initial=False)
        self.assertEqual(g.setup_calls, [(12, g.LOW)])

    def test_cleanup_releases_pin(self):
        line, g = self._line()
        line.cleanup()
        self.assertEqual(g.cleaned, [12])


if __name__ == "__main__":
    unittest.main()
