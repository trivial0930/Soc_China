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

from thermal_detector.image_geometry import unrotate_box  # noqa: E402

# native camera frame
OW, OH = 1920, 1072


def rotate_point_forward(x, y, deg):
    """Forward map a native point to the rotated frame (clockwise)."""
    deg %= 360
    if deg == 0:
        return (x, y)
    if deg == 90:
        return (OH - 1 - y, x)
    if deg == 180:
        return (OW - 1 - x, OH - 1 - y)
    if deg == 270:
        return (y, OW - 1 - x)
    raise ValueError


def rotate_box_forward(box, deg):
    x1, y1, x2, y2 = box
    ax, ay = rotate_point_forward(x1, y1, deg)
    bx, by = rotate_point_forward(x2, y2, deg)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


class UnrotateBoxTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(unrotate_box((10, 20, 30, 40), 0, OW, OH), (10, 20, 30, 40))

    def test_roundtrip_all_rotations(self):
        native = (100, 50, 260, 190)  # a known native box
        for deg in (90, 180, 270):
            with self.subTest(deg=deg):
                rotated = rotate_box_forward(native, deg)
                recovered = unrotate_box(rotated, deg, OW, OH)
                self.assertEqual(tuple(map(round, recovered)), native)

    def test_90_concrete(self):
        # native top-left box -> rotated -> unrotate recovers it
        rotated = rotate_box_forward((0, 0, 10, 10), 90)
        self.assertEqual(unrotate_box(rotated, 90, OW, OH), (0, 0, 10, 10))

    def test_90_right_side_maps_to_expected_axis(self):
        # A target on the RIGHT of the native frame must come back on the right
        # (large x), so image-x still drives pan after un-rotation.
        native_right = (1800, 500, 1900, 600)
        rotated = rotate_box_forward(native_right, 90)
        out = unrotate_box(rotated, 90, OW, OH)
        cx = (out[0] + out[2]) / 2
        self.assertGreater(cx, OW * 0.8)  # still on the right

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            unrotate_box((0, 0, 1, 1), 45, OW, OH)


if __name__ == "__main__":
    unittest.main()
