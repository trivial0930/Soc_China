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

from gimbal_laser.visual_servo import (  # noqa: E402
    ServoConfig,
    config_from_dict,
    pick_target,
    servo_step,
)


CFG = ServoConfig(
    image_width=1920, image_height=1080, hfov_deg=90.0, vfov_deg=68.0,
    gain=0.6, deadband_px=30.0, max_step_deg=8.0,
    invert_pan=False, invert_tilt=False,
    pan_min_deg=-60.0, pan_max_deg=60.0, tilt_min_deg=-30.0, tilt_max_deg=45.0,
)


class ServoStepTests(unittest.TestCase):
    def test_centered_target_holds_and_flags_centered(self):
        cmd = servo_step(10.0, 5.0, (960, 540), CFG)  # exactly centre
        self.assertTrue(cmd.centered)
        self.assertEqual((cmd.pan_deg, cmd.tilt_deg), (10.0, 5.0))

    def test_within_deadband_holds(self):
        cmd = servo_step(0.0, 0.0, (960 + 20, 540), CFG)  # 20px < 30px deadband
        self.assertTrue(cmd.centered)

    def test_target_right_pans_toward_it(self):
        cmd = servo_step(0.0, 0.0, (1920, 540), CFG)  # far right, same row
        self.assertFalse(cmd.centered)
        self.assertGreater(cmd.pan_deg, 0.0)  # default sign: ex>0 -> pan increases
        self.assertAlmostEqual(cmd.tilt_deg, 0.0)

    def test_invert_pan_flips_direction(self):
        cfg = ServoConfig(**{**CFG.__dict__, "invert_pan": True})
        cmd = servo_step(0.0, 0.0, (1920, 540), cfg)
        self.assertLess(cmd.pan_deg, 0.0)

    def test_step_is_slew_capped(self):
        cfg = ServoConfig(**{**CFG.__dict__, "gain": 5.0, "max_step_deg": 3.0})
        cmd = servo_step(0.0, 0.0, (1920, 1080), cfg)
        self.assertLessEqual(abs(cmd.pan_deg), 3.0)
        self.assertLessEqual(abs(cmd.tilt_deg), 3.0)

    def test_command_is_clamped_to_axis_limits(self):
        cfg = ServoConfig(**{**CFG.__dict__, "gain": 5.0, "max_step_deg": 100.0})
        cmd = servo_step(58.0, 0.0, (1920, 540), cfg)
        self.assertLessEqual(cmd.pan_deg, 60.0)

    def test_pixel_error_reported(self):
        cmd = servo_step(0.0, 0.0, (1000, 600), CFG)
        self.assertEqual(cmd.pixel_error, (1000 - 960, 600 - 540))


class SwapAxesTests(unittest.TestCase):
    """Camera rolled 90deg on the gimbal: image-y drives pan, image-x drives tilt."""

    def _cfg(self):
        return ServoConfig(**{**CFG.__dict__, "swap_axes": True, "invert_pan": False, "invert_tilt": False})

    def test_vertical_offset_drives_pan_not_tilt(self):
        # target below centre (large y), same column -> pan moves, tilt ~0
        cmd = servo_step(0.0, 0.0, (960, 1080), self._cfg())
        self.assertNotAlmostEqual(cmd.pan_deg, 0.0)
        self.assertAlmostEqual(cmd.tilt_deg, 0.0)

    def test_horizontal_offset_drives_tilt_not_pan(self):
        # target right of centre (large x), same row -> tilt moves, pan ~0
        cmd = servo_step(0.0, 0.0, (1920, 540), self._cfg())
        self.assertNotAlmostEqual(cmd.tilt_deg, 0.0)
        self.assertAlmostEqual(cmd.pan_deg, 0.0)

    def test_no_swap_keeps_x_to_pan(self):
        cmd = servo_step(0.0, 0.0, (1920, 540), CFG)  # CFG has swap_axes default False
        self.assertGreater(cmd.pan_deg, 0.0)
        self.assertAlmostEqual(cmd.tilt_deg, 0.0)


class PickTargetTests(unittest.TestCase):
    def test_picks_highest_severity_box_centre(self):
        objects = [
            {"severity": "warning", "box": [0, 0, 100, 100]},
            {"severity": "critical", "box": [200, 200, 400, 400]},
            {"severity": "info", "box": [10, 10, 20, 20]},
        ]
        self.assertEqual(pick_target(objects), (300.0, 300.0))

    def test_none_when_empty(self):
        self.assertIsNone(pick_target([]))

    def test_ignores_objects_without_box(self):
        self.assertIsNone(pick_target([{"severity": "critical"}]))


class ConfigTests(unittest.TestCase):
    def test_from_dict_overrides_and_defaults(self):
        cfg = config_from_dict({"hfov_deg": 78.0, "gain": 0.4})
        self.assertEqual(cfg.hfov_deg, 78.0)
        self.assertEqual(cfg.gain, 0.4)
        self.assertEqual(cfg.image_width, ServoConfig().image_width)


if __name__ == "__main__":
    unittest.main()
