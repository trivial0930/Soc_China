import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/stm32_bridge"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from stm32_bridge.mecanum_odometry import (  # noqa: E402
    MecanumOdometry,
    MecanumOdometryConfig,
    body_twist_from_wheel_rates,
    wrapped_delta_u16,
)

R = 0.05
L = 0.12
W = 0.10


def firmware_mix(vx, vy, wz):
    """Replica of STM32 MecanumDrive_Mix -> wheel rad/s (LF, RF, LR, RR)."""
    # rot sign negated 2026-06-11 to match firmware (mecanum_drive.c): +wz must
    # produce CCW per REP-103. vy also negated so +vy = LEFT (after the RF<->RR
    # motor swap, +vy had strafed right). Only those two terms changed.
    rot = -(L + W) * wz
    return (
        (vx + vy - rot) / R,
        (vx - vy + rot) / R,
        (vx - vy - rot) / R,
        (vx + vy + rot) / R,
    )


class WrappedDeltaTest(unittest.TestCase):
    def test_simple_forward(self):
        self.assertEqual(wrapped_delta_u16(100, 60), 40)

    def test_simple_backward(self):
        self.assertEqual(wrapped_delta_u16(60, 100), -40)

    def test_wrap_up_through_zero(self):
        # 65530 -> 10 is +16 (rolled over the top)
        self.assertEqual(wrapped_delta_u16(10, 65530), 16)

    def test_wrap_down_through_zero(self):
        # 10 -> 65530 is -16
        self.assertEqual(wrapped_delta_u16(65530, 10), -16)


class ForwardKinematicsInverseTest(unittest.TestCase):
    """body_twist_from_wheel_rates must invert the firmware mix exactly."""

    def test_round_trip(self):
        for vx, vy, wz in [
            (0.20, 0.0, 0.0),
            (0.0, 0.15, 0.0),
            (0.0, 0.0, 0.8),
            (0.10, -0.07, 0.5),
            (-0.12, 0.09, -0.3),
        ]:
            w = firmware_mix(vx, vy, wz)
            rvx, rvy, rwz = body_twist_from_wheel_rates(*w, R, L, W)
            with self.subTest(v=(vx, vy, wz)):
                self.assertAlmostEqual(rvx, vx, places=9)
                self.assertAlmostEqual(rvy, vy, places=9)
                self.assertAlmostEqual(rwz, wz, places=9)


class OdometryIntegrationTest(unittest.TestCase):
    def make(self, **kw):
        cfg = MecanumOdometryConfig(
            wheel_radius_m=R, half_length_m=L, half_width_m=W,
            ticks_per_rev=1000.0, **kw,
        )
        return MecanumOdometry(config=cfg)

    def test_first_update_latches_baseline(self):
        odo = self.make()
        st = odo.update(500, 500, 500, 500, 0.1)
        self.assertEqual((st.x, st.y, st.theta), (0.0, 0.0, 0.0))

    def test_pure_forward_increases_x_only(self):
        odo = self.make()
        odo.update(0, 0, 0, 0, 0.1)  # baseline
        st = odo.update(100, 100, 100, 100, 0.1)  # all wheels +100
        self.assertGreater(st.x, 0.0)
        self.assertAlmostEqual(st.y, 0.0, places=9)
        self.assertAlmostEqual(st.theta, 0.0, places=9)
        self.assertGreater(st.vx, 0.0)

    def test_pure_strafe_left_increases_y_only(self):
        odo = self.make()
        odo.update(0, 0, 0, 0, 0.1)
        # +y (left) pattern wheel rates after vy-sign flip (2026-06-11): (+,-,-,+)
        st = odo.update(100, -100, -100, 100, 0.1)
        self.assertAlmostEqual(st.x, 0.0, places=9)
        self.assertGreater(st.y, 0.0)
        self.assertAlmostEqual(st.theta, 0.0, places=9)

    def test_pure_rotation_changes_theta_only(self):
        odo = self.make()
        odo.update(0, 0, 0, 0, 0.1)
        # +wz (CCW) pattern after rot-sign flip (2026-06-11): (+,-,+,-)
        st = odo.update(100, -100, 100, -100, 0.1)
        self.assertAlmostEqual(st.x, 0.0, places=9)
        self.assertAlmostEqual(st.y, 0.0, places=9)
        self.assertGreater(st.theta, 0.0)

    def test_forward_distance_matches_geometry(self):
        # all wheels turn exactly 1 rev -> robot moves forward r*2pi meters
        odo = self.make()
        tpr = 1000
        odo.update(0, 0, 0, 0, 0.1)
        st = odo.update(tpr, tpr, tpr, tpr, 0.1)
        self.assertAlmostEqual(st.x, R * 2.0 * math.pi, places=6)

    def test_encoder_sign_inverts_direction(self):
        odo = self.make(encoder_sign=(-1, -1, -1, -1))
        odo.update(0, 0, 0, 0, 0.1)
        st = odo.update(100, 100, 100, 100, 0.1)
        self.assertLess(st.x, 0.0)

    def test_resync_preserves_pose_and_relatches_baseline(self):
        # Drive forward, then simulate an STM32 watchdog reset: the encoder
        # counters jump (reset to 0) and we resync(). The accumulated pose must
        # survive, and the next sample must NOT integrate the bogus jump.
        odo = self.make()
        odo.update(0, 0, 0, 0, 0.1)
        st = odo.update(1000, 1000, 1000, 1000, 0.1)
        x_before = st.x
        self.assertGreater(x_before, 0.0)

        odo.resync()  # STM32 re-enumerated; drop tick baseline, keep pose
        # first post-reset sample: counters are back near 0 -> huge negative wrap
        # delta if it integrated. resync() must make it re-latch instead.
        st2 = odo.update(0, 0, 0, 0, 0.1)
        self.assertAlmostEqual(st2.x, x_before, places=9)  # pose unchanged
        self.assertAlmostEqual(st2.y, 0.0, places=9)
        self.assertAlmostEqual(st2.theta, 0.0, places=9)

        # and normal integration resumes from the new baseline
        st3 = odo.update(1000, 1000, 1000, 1000, 0.1)
        self.assertGreater(st3.x, x_before)


if __name__ == "__main__":
    unittest.main()
