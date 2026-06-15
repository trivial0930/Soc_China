"""Tests for converting parsed config dicts into fusion-core objects.

The YAML *reading* is a thin wrapper (needs PyYAML, only on the board); the
dict -> object conversion is pure and tested here.
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

from thermal_detector.config_loader import (  # noqa: E402
    homography_from_dict,
    params_from_dict,
    policies_from_dict,
    trust_absolute_from_dict,
)
from thermal_detector.fusion import ClassPolicy, HotspotParams  # noqa: E402


class PolicyConfigTests(unittest.TestCase):
    def test_policies_from_dict(self):
        cfg = {
            "classes": {
                "soldering_iron": {"base_risk": "high", "active_c": 50, "hot_c": 150},
                "wire": {"base_risk": "context", "active_c": 45, "hot_c": 70},
            }
        }
        policies = policies_from_dict(cfg)
        self.assertEqual(
            policies["soldering_iron"],
            ClassPolicy("soldering_iron", "high", 50.0, 150.0),
        )
        self.assertEqual(policies["wire"], ClassPolicy("wire", "context", 45.0, 70.0))

    def test_missing_classes_yields_empty(self):
        self.assertEqual(policies_from_dict({}), {})


class ParamsConfigTests(unittest.TestCase):
    def test_params_from_dict(self):
        cfg = {
            "hotspot": {
                "delta_c": 6,
                "abs_floor_c": 42,
                "baseline_percentile": 60,
                "min_area_px": 3,
                "orphan_critical_c": 75,
            }
        }
        params = params_from_dict(cfg)
        self.assertEqual(
            params,
            HotspotParams(
                delta_c=6.0,
                abs_floor_c=42.0,
                baseline_percentile=60.0,
                min_area_px=3,
                orphan_critical_c=75.0,
            ),
        )

    def test_params_defaults_when_absent(self):
        self.assertEqual(params_from_dict({}), HotspotParams())

    def test_trust_absolute_defaults_true(self):
        self.assertTrue(trust_absolute_from_dict({}))
        self.assertFalse(trust_absolute_from_dict({"trust_absolute": False}))


class HomographyConfigTests(unittest.TestCase):
    def test_homography_from_dict(self):
        cfg = {"homography_thermal_to_rgb": [[24, 0, 0], [0, 17, 0], [0, 0, 1]]}
        h = homography_from_dict(cfg)
        self.assertEqual(h, ((24.0, 0.0, 0.0), (0.0, 17.0, 0.0), (0.0, 0.0, 1.0)))

    def test_missing_homography_raises(self):
        with self.assertRaises(KeyError):
            homography_from_dict({})


if __name__ == "__main__":
    unittest.main()
