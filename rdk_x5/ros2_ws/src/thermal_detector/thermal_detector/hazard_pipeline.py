"""Shared heat-source hazard pipeline: config + thermal frame -> FusionResult.

This is the single seam reused by both integration paths:

* path A: the standalone web detector (lab_mipi_web_detector.py), and
* path B: the ROS2 thermal_detector node.

Construct it directly with already-built policy/params/homography (pure, tested),
or via ``HazardPipeline.from_config(...)`` which reads the YAML files on the board.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

from .fusion import ClassPolicy, Detection, FusionResult, HotspotParams, fuse

Matrix3 = Tuple[Tuple[float, float, float], ...]


@dataclass
class HazardPipeline:
    policies: Dict[str, ClassPolicy]
    params: HotspotParams
    homography_thermal_to_rgb: Matrix3
    trust_absolute: bool = True

    def assess(self, detections: Sequence[Detection], thermal_frame) -> FusionResult:
        """Fuse RGB detections with one thermal frame into a hazard assessment."""
        return fuse(
            detections,
            thermal_frame,
            self.homography_thermal_to_rgb,
            policies=self.policies,
            params=self.params,
            trust_absolute=self.trust_absolute,
        )

    @classmethod
    def from_config(cls, hazard_path: str, calib_path: str) -> "HazardPipeline":  # pragma: no cover - needs PyYAML/board
        from .config_loader import load_calibration, load_hazard_config

        policies, params, trust_absolute = load_hazard_config(hazard_path)
        homography = load_calibration(calib_path)
        return cls(
            policies=policies,
            params=params,
            homography_thermal_to_rgb=homography,
            trust_absolute=trust_absolute,
        )
