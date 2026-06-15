"""Unit tests for the hardware-independent thermal/RGB fusion core.

Runs under the standard suite: ``python3 -m unittest discover -s tests``.
The fusion core is intentionally stdlib-only so these tests need no numpy/cv2.
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

from thermal_detector.fusion import (  # noqa: E402
    ClassPolicy,
    Detection,
    HotspotParams,
    apply_homography,
    fuse,
    find_hotspots,
    invert_3x3,
    severity_for,
)


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def make_grid(height, width, baseline, hot_rect=None, hot_value=0.0):
    """Build a HxW nested-list temperature grid, optionally with a hot rectangle.

    hot_rect is (x1, y1, x2, y2) inclusive in thermal pixel coordinates.
    """
    grid = [[float(baseline)] * width for _ in range(height)]
    if hot_rect is not None:
        x1, y1, x2, y2 = hot_rect
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                grid[y][x] = float(hot_value)
    return grid


class HomographyTests(unittest.TestCase):
    def test_identity_maps_point_to_itself(self):
        self.assertEqual(apply_homography(IDENTITY, 5.0, 7.0), (5.0, 7.0))

    def test_scale_homography_maps_point(self):
        scale = ((2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 1.0))
        self.assertEqual(apply_homography(scale, 4.0, 5.0), (8.0, 15.0))

    def test_inverse_of_scale_round_trips(self):
        scale = ((2.0, 0.0, 0.0), (0.0, 3.0, 0.0), (0.0, 0.0, 1.0))
        inv = invert_3x3(scale)
        x, y = apply_homography(inv, 8.0, 15.0)
        self.assertAlmostEqual(x, 4.0)
        self.assertAlmostEqual(y, 5.0)


class HotspotTests(unittest.TestCase):
    def test_single_hot_block_is_detected(self):
        grid = make_grid(6, 6, baseline=25.0, hot_rect=(3, 2, 4, 3), hot_value=80.0)
        params = HotspotParams(delta_c=8.0, abs_floor_c=40.0, min_area_px=2)
        spots = find_hotspots(grid, params, IDENTITY)
        self.assertEqual(len(spots), 1)
        spot = spots[0]
        self.assertEqual(spot.area_px, 4)
        self.assertAlmostEqual(spot.peak_c, 80.0)
        # thermal bbox of the block
        self.assertEqual((spot.tx1, spot.ty1, spot.tx2, spot.ty2), (3, 2, 4, 3))
        # centroid mapped through identity homography
        self.assertAlmostEqual(spot.rgb_cx, 3.5)
        self.assertAlmostEqual(spot.rgb_cy, 2.5)

    def test_warm_room_below_absolute_floor_is_not_a_hotspot(self):
        # Whole frame warm-ish but below the absolute floor -> nothing flagged.
        grid = make_grid(6, 6, baseline=35.0, hot_rect=(2, 2, 3, 3), hot_value=39.0)
        params = HotspotParams(delta_c=2.0, abs_floor_c=40.0, min_area_px=1)
        self.assertEqual(find_hotspots(grid, params, IDENTITY), [])

    def test_tiny_blob_below_min_area_is_ignored(self):
        grid = make_grid(6, 6, baseline=25.0, hot_rect=(3, 3, 3, 3), hot_value=90.0)
        params = HotspotParams(delta_c=8.0, abs_floor_c=40.0, min_area_px=2)
        self.assertEqual(find_hotspots(grid, params, IDENTITY), [])


class SeverityMatrixTests(unittest.TestCase):
    def test_high_risk_matrix(self):
        self.assertEqual(severity_for("high", "cold"), "warning")
        self.assertEqual(severity_for("high", "active"), "critical")
        self.assertEqual(severity_for("high", "hot"), "critical")

    def test_medium_risk_matrix(self):
        self.assertEqual(severity_for("medium", "cold"), "info")
        self.assertEqual(severity_for("medium", "active"), "warning")
        self.assertEqual(severity_for("medium", "hot"), "critical")

    def test_context_risk_matrix(self):
        self.assertEqual(severity_for("context", "cold"), "info")
        self.assertEqual(severity_for("context", "active"), "info")
        self.assertEqual(severity_for("context", "hot"), "warning")


class FuseTests(unittest.TestCase):
    def setUp(self):
        self.policies = {
            "soldering_iron": ClassPolicy("soldering_iron", "high", active_c=50.0, hot_c=150.0),
            "power_strip": ClassPolicy("power_strip", "medium", active_c=45.0, hot_c=80.0),
            "wire": ClassPolicy("wire", "context", active_c=45.0, hot_c=70.0),
        }
        self.params = HotspotParams(delta_c=8.0, abs_floor_c=40.0, min_area_px=2)

    def test_high_risk_object_over_hot_region_is_critical(self):
        grid = make_grid(20, 20, baseline=25.0, hot_rect=(5, 5, 9, 9), hot_value=200.0)
        det = Detection(cls_id=0, label="soldering_iron", score=0.9, box=(5, 5, 9, 9))
        result = fuse([det], grid, IDENTITY, policies=self.policies, params=self.params)
        obj = result.objects[0]
        self.assertEqual(obj.thermal_state, "hot")
        self.assertEqual(obj.severity, "critical")
        self.assertAlmostEqual(obj.peak_c, 200.0)
        self.assertEqual(result.overall_severity, "critical")

    def test_high_risk_object_when_cold_is_only_warning(self):
        grid = make_grid(20, 20, baseline=24.0)
        det = Detection(cls_id=0, label="soldering_iron", score=0.9, box=(5, 5, 9, 9))
        result = fuse([det], grid, IDENTITY, policies=self.policies, params=self.params)
        obj = result.objects[0]
        self.assertEqual(obj.thermal_state, "cold")
        self.assertEqual(obj.severity, "warning")

    def test_medium_risk_object_warm_is_warning(self):
        # 60C is above active_c (45) but below hot_c (80) -> active -> medium+active=warning
        grid = make_grid(20, 20, baseline=25.0, hot_rect=(5, 5, 9, 9), hot_value=60.0)
        det = Detection(cls_id=4, label="power_strip", score=0.8, box=(5, 5, 9, 9))
        result = fuse([det], grid, IDENTITY, policies=self.policies, params=self.params)
        obj = result.objects[0]
        self.assertEqual(obj.thermal_state, "active")
        self.assertEqual(obj.severity, "warning")

    def test_context_object_cold_is_info(self):
        grid = make_grid(20, 20, baseline=24.0)
        det = Detection(cls_id=7, label="wire", score=0.5, box=(5, 5, 9, 9))
        result = fuse([det], grid, IDENTITY, policies=self.policies, params=self.params)
        self.assertEqual(result.objects[0].severity, "info")

    def test_hot_region_without_object_is_orphan_hotspot(self):
        grid = make_grid(20, 20, baseline=25.0, hot_rect=(12, 12, 15, 15), hot_value=120.0)
        det = Detection(cls_id=0, label="soldering_iron", score=0.9, box=(2, 2, 5, 5))
        result = fuse([det], grid, IDENTITY, policies=self.policies, params=self.params)
        # The object box is cold; the heat is elsewhere with no object -> orphan.
        self.assertEqual(result.objects[0].thermal_state, "cold")
        self.assertEqual(len(result.orphan_hotspots), 1)
        self.assertGreaterEqual(result.orphan_hotspots[0].peak_c, 120.0)

    def test_overall_severity_and_banner_reflect_worst(self):
        grid = make_grid(20, 20, baseline=25.0, hot_rect=(5, 5, 9, 9), hot_value=200.0)
        dets = [
            Detection(cls_id=0, label="soldering_iron", score=0.9, box=(5, 5, 9, 9)),
            Detection(cls_id=7, label="wire", score=0.5, box=(15, 15, 18, 18)),
        ]
        result = fuse(dets, grid, IDENTITY, policies=self.policies, params=self.params)
        self.assertEqual(result.overall_severity, "critical")
        self.assertIn("soldering_iron", result.banner)


if __name__ == "__main__":
    unittest.main()
