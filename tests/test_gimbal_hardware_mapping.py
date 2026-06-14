import sys
import unittest
from pathlib import Path


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(PACKAGE_SRC))

from gimbal_laser.rdk_x5_gpio import gpio_line_from_pin
from gimbal_laser.rdk_x5_pwm import pwm_channel_from_pin


CONFIG = PACKAGE_SRC / "config" / "gimbal.yaml"


class GimbalHardwareMappingTest(unittest.TestCase):
    def test_enable_uses_board_physical_pin_numbers(self):
        self.assertEqual(gpio_line_from_pin(38).pin, 38)
        self.assertEqual(gpio_line_from_pin(40).pin, 40)

    def test_pwm_physical_pins_map_to_pwm_channels(self):
        expected = {
            29: ("pwmchip0", 0),
            31: ("pwmchip0", 1),
            37: ("pwmchip2", 0),
            18: ("pwmchip2", 1),
            28: ("pwmchip4", 0),
            27: ("pwmchip4", 1),
        }
        for pin, (chip, channel) in expected.items():
            with self.subTest(pin=pin):
                pwm = pwm_channel_from_pin(pin, 20000)
                self.assertEqual(pwm.chip, chip)
                self.assertEqual(pwm.channel, channel)

    def test_config_matches_current_rdk_wiring(self):
        config = CONFIG.read_text()
        self.assertIn("pan_i2c_bus: 5", config)
        self.assertIn("pan_pwm_pins: [29, 31, 37]", config)
        self.assertIn("pan_enable_pin: 38", config)
        self.assertIn("tilt_i2c_bus: 1", config)
        self.assertIn("tilt_pwm_pins: [18, 28, 27]", config)
        self.assertIn("tilt_enable_pin: 40", config)
        self.assertIn("command_timeout_sec: 5.0", config)
        self.assertIn("proportional_gain: 0.008", config)
        self.assertIn("integral_gain: 0.01", config)
        self.assertIn("integral_limit: 0.10", config)
        self.assertIn("target_slew_rate_deg_s: 16.0", config)
        self.assertIn("duty_slew_rate_per_sec: 1.25", config)
        self.assertNotIn("tilt_i2c_bus: 0", config)
        self.assertNotIn("tilt_pwm_pins: [24, 32, 33]", config)


if __name__ == "__main__":
    unittest.main()
