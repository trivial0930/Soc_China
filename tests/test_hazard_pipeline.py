"""End-to-end test of the shared hazard pipeline (driver frame -> fusion result).

Exercises the seam that both path A (web detector) and path B (ROS2 node) reuse,
without any hardware: a mock thermal frame + a fake RGB detection.
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

from thermal_detector.config_loader import policies_from_dict  # noqa: E402
from thermal_detector.fusion import Detection, HotspotParams  # noqa: E402
from thermal_detector.hazard_pipeline import HazardPipeline  # noqa: E402
from thermal_detector.senxor_driver import MockSenxorBackend, ThermalCamera  # noqa: E402


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class HazardPipelineTests(unittest.TestCase):
    def setUp(self):
        policies = policies_from_dict(
            {"classes": {"soldering_iron": {"base_risk": "high", "active_c": 50, "hot_c": 150}}}
        )
        self.pipeline = HazardPipeline(
            policies=policies,
            params=HotspotParams(),
            homography_thermal_to_rgb=IDENTITY,
            trust_absolute=True,
        )
        # A mock thermal frame: ambient with a hot square at thermal x37-42, y28-33.
        self.frame = ThermalCamera(backend=MockSenxorBackend()).read_frame()

    def test_object_over_mock_hotspot_is_critical(self):
        # Mock hotspot is 120C: above soldering_iron active_c (50) but below
        # hot_c (150) -> "active". A high-risk class that is active is critical.
        det = Detection(cls_id=0, label="soldering_iron", score=0.9, box=(37, 28, 42, 33))
        result = self.pipeline.assess([det], self.frame)
        self.assertEqual(result.objects[0].thermal_state, "active")
        self.assertEqual(result.overall_severity, "critical")

    def test_no_detection_over_hotspot_yields_orphan(self):
        result = self.pipeline.assess([], self.frame)
        self.assertEqual(result.objects, [])
        self.assertEqual(len(result.orphan_hotspots), 1)


if __name__ == "__main__":
    unittest.main()
