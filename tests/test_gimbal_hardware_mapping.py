import sys
import unittest
from pathlib import Path


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(PACKAGE_SRC))

from gimbal_laser.rdk_x5_gpio import gpio_line_from_pin
from gimbal_laser.rdk_x5_pwm import pwm_channel_from_pin


class GimbalHardwareMappingTest(unittest.TestCase):
    def test_enable_uses_board_physical_pin_numbers(self):
        self.assertEqual(gpio_line_from_pin(11).pin, 11)
        self.assertEqual(gpio_line_from_pin(13).pin, 13)

    def test_pwm_physical_pins_map_to_pwm_channels(self):
        self.assertEqual(pwm_channel_from_pin(29, 20000).chip, "pwmchip0")
        self.assertEqual(pwm_channel_from_pin(29, 20000).channel, 0)
        self.assertEqual(pwm_channel_from_pin(33, 20000).chip, "pwmchip3")
        self.assertEqual(pwm_channel_from_pin(33, 20000).channel, 7)


if __name__ == "__main__":
    unittest.main()
