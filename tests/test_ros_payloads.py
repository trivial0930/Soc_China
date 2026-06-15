"""Tests for the pure ROS2 payload (de)serialization used by Path B nodes.

The rclpy nodes are thin wrappers around these stdlib-only functions, so the
message <-> object conversion and event generation are tested here without ROS.
"""

import json
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
    FusionResult,
    HotspotParams,
)
from thermal_detector.hazard_pipeline import HazardPipeline  # noqa: E402
from thermal_detector.ros_payloads import (  # noqa: E402
    decode_detections,
    encode_detections,
    encode_status,
    result_to_event,
)

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


class DetectionCodecTests(unittest.TestCase):
    def test_round_trip(self):
        dets = [
            Detection(0, "soldering_iron", 0.91, (5.0, 6.0, 9.0, 10.0)),
            Detection(7, "wire", 0.4, (1.0, 2.0, 3.0, 4.0)),
        ]
        out, stamp = decode_detections(encode_detections(dets, 12.5))
        self.assertEqual(stamp, 12.5)
        self.assertEqual(out, dets)

    def test_empty(self):
        out, _ = decode_detections(encode_detections([], 0.0))
        self.assertEqual(out, [])

    def test_decode_is_valid_json_with_expected_fields(self):
        payload = json.loads(encode_detections([Detection(1, "plug", 0.5, (0, 0, 2, 2))], 1.0))
        self.assertEqual(payload["detections"][0]["label"], "plug")
        self.assertIn("box", payload["detections"][0])


class StatusEncodingTests(unittest.TestCase):
    def _pipeline(self):
        policies = {"soldering_iron": ClassPolicy("soldering_iron", "high", 50.0, 150.0)}
        return HazardPipeline(policies=policies, params=HotspotParams(), homography_thermal_to_rgb=IDENTITY)

    def test_status_has_severity_and_objects(self):
        grid = [[200.0 if (5 <= x <= 9 and 5 <= y <= 9) else 25.0 for x in range(20)] for y in range(20)]
        det = Detection(0, "soldering_iron", 0.9, (5, 5, 9, 9))
        result = self._pipeline().assess([det], grid)
        payload = json.loads(encode_status(result))
        self.assertEqual(payload["overall_severity"], "critical")
        self.assertIn("soldering_iron", payload["banner"])
        self.assertEqual(payload["objects"][0]["label"], "soldering_iron")
        self.assertEqual(payload["objects"][0]["severity"], "critical")


class EventGenerationTests(unittest.TestCase):
    def test_no_event_for_info(self):
        result = FusionResult(overall_severity="info", banner="OK")
        self.assertIsNone(result_to_event(result, "desk-1", "20260607-0001", "2026-06-07T10:00:00+08:00"))

    def test_event_for_critical_matches_schema(self):
        result = FusionResult(overall_severity="critical", banner="CRITICAL: soldering_iron (hot 200C)")
        ev = result_to_event(result, "desk-1", "20260607-0001", "2026-06-07T10:00:00+08:00", confidence=0.9)
        self.assertEqual(ev["source"], "thermal")
        self.assertEqual(ev["event_type"], "thermal_risk")
        self.assertEqual(ev["severity"], "critical")
        self.assertEqual(ev["station_id"], "desk-1")
        self.assertEqual(ev["confidence"], 0.9)
        self.assertIn("soldering_iron", ev["summary"])
        self.assertIn("evidence", ev)
        self.assertIn("action", ev)


if __name__ == "__main__":
    unittest.main()
