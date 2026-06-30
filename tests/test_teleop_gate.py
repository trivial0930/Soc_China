import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/teleop_safety"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from teleop_safety.gate import GateParams, gate_twist  # noqa: E402

N = 360
ANGLE_MIN = -math.pi
INC = 2.0 * math.pi / N
P = GateParams()  # stop 0.30, slow 0.60, sector 35deg


def scan(default=5.0, near=None):
    """ranges all `default`; near = list of (center_rad, dist) point obstacles."""
    r = [default] * N
    for center, dist in (near or []):
        i = int(round((center - ANGLE_MIN) / INC)) % N
        r[i] = dist
    return r


def g(ranges, vx, vy, wz):
    return gate_twist(ranges, ANGLE_MIN, INC, vx, vy, wz, P)


class TeleopGateTest(unittest.TestCase):
    def test_clear_passes_through(self):
        ovx, ovy, owz, state, _ = g(scan(), 0.3, 0.0, 0.2)
        self.assertAlmostEqual(ovx, 0.3)
        self.assertAlmostEqual(owz, 0.2)
        self.assertEqual(state, "clear")

    def test_obstacle_ahead_blocks_translation_keeps_rotation(self):
        # obstacle 0.2m straight ahead, driving forward + turning
        ovx, ovy, owz, state, front = g(scan(near=[(0.0, 0.2)]), 0.3, 0.0, 0.5)
        self.assertEqual(state, "blocked")
        self.assertEqual(ovx, 0.0)
        self.assertEqual(ovy, 0.0)
        self.assertAlmostEqual(owz, 0.5)        # rotation always allowed
        self.assertAlmostEqual(front, 0.2, places=3)

    def test_obstacle_in_slow_band_scales(self):
        # 0.45m ahead -> scale = (0.45-0.30)/(0.60-0.30) = 0.5
        ovx, ovy, owz, state, _ = g(scan(near=[(0.0, 0.45)]), 0.4, 0.0, 0.0)
        self.assertEqual(state, "slow")
        self.assertAlmostEqual(ovx, 0.2, places=3)

    def test_reverse_allowed_when_rear_clear(self):
        # obstacle ahead, but commanding reverse -> heading=pi, rear clear -> pass
        ovx, ovy, owz, state, _ = g(scan(near=[(0.0, 0.2)]), -0.3, 0.0, 0.0)
        self.assertEqual(state, "clear")
        self.assertAlmostEqual(ovx, -0.3)

    def test_side_obstacle_does_not_block_forward(self):
        # obstacle at +90deg (left), driving straight forward -> not in front cone
        ovx, ovy, owz, state, _ = g(scan(near=[(math.pi / 2, 0.2)]), 0.3, 0.0, 0.0)
        self.assertEqual(state, "clear")
        self.assertAlmostEqual(ovx, 0.3)

    def test_not_translating_passes_rotation_only(self):
        ovx, ovy, owz, state, _ = g(scan(near=[(0.0, 0.2)]), 0.0, 0.0, 0.4)
        self.assertEqual(ovx, 0.0)
        self.assertEqual(ovy, 0.0)
        self.assertAlmostEqual(owz, 0.4)
        self.assertEqual(state, "clear")

    def test_strafe_left_into_obstacle_blocks(self):
        # commanding +vy (left) into a left obstacle -> heading=+90deg -> blocked
        ovx, ovy, owz, state, _ = g(scan(near=[(math.pi / 2, 0.2)]), 0.0, 0.3, 0.1)
        self.assertEqual(state, "blocked")
        self.assertEqual(ovy, 0.0)
        self.assertAlmostEqual(owz, 0.1)

    def test_rear_body_within_30cm_masked_allows_reverse(self):
        # 0.2m directly behind = robot's own chassis (<30cm); near-mask drops it
        # so reverse is NOT blocked.
        ovx, _, _, state, _ = g(scan(near=[(math.pi, 0.2)]), -0.3, 0.0, 0.0)
        self.assertEqual(state, "clear")
        self.assertAlmostEqual(ovx, -0.3)

    def test_rear_obstacle_beyond_30cm_still_blocks_reverse(self):
        # 0.25m behind is body (masked), but a real obstacle at 0.28m... use 0.28<0.30
        # -> still masked. A wall at 0.5m behind (>=0.30) is a REAL obstacle -> avoided.
        ovx, _, _, state, _ = g(scan(near=[(math.pi, 0.5)]), -0.3, 0.0, 0.0)
        self.assertEqual(state, "slow")          # 0.5m in slow band -> scaled
        self.assertGreater(abs(ovx), 0.0)
        ovx2, _, _, st2, _ = g(scan(near=[(math.pi, 0.25)]), -0.3, 0.0, 0.0)
        self.assertEqual(st2, "clear")           # 0.25m<0.30 -> body, masked

    def test_reverse_blocked_when_mask_disabled(self):
        # same rear obstacle at 0.2m, masking off -> reverse blocked.
        p0 = GateParams(near_masks=())
        ovx, _, _, state, _ = gate_twist(
            scan(near=[(math.pi, 0.2)]), ANGLE_MIN, INC, -0.3, 0.0, 0.0, p0)
        self.assertEqual(state, "blocked")
        self.assertEqual(ovx, 0.0)

    def test_nan_and_zero_returns_ignored(self):
        r = scan()
        r[180] = float("nan")   # front
        r[181] = 0.0            # invalid 0
        ovx, _, _, state, _ = g(r, 0.3, 0.0, 0.0)
        self.assertEqual(state, "clear")        # bad returns skipped, rest far
        self.assertAlmostEqual(ovx, 0.3)


if __name__ == "__main__":
    unittest.main()
