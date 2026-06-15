"""Pure (de)serialization for the Path B ROS2 nodes.

All stdlib-only so the message contracts are unit-tested without ROS. Topics use
std_msgs/String JSON (no custom .msg build needed):

* /perception/hazard_detections : encode_detections / decode_detections
* /hazard/status                : encode_status (FusionResult -> JSON)
* /hazard/events               : result_to_event (thermal_risk per event_schema.md)
"""

from __future__ import annotations

import json
from typing import List, Optional, Tuple

from .fusion import Detection, FusionResult


# --------------------------------------------------------------------------- #
# RGB detections  (/perception/hazard_detections)
# --------------------------------------------------------------------------- #
def encode_detections(detections, stamp: float) -> str:
    return json.dumps(
        {
            "stamp": float(stamp),
            "detections": [
                {
                    "cls_id": int(d.cls_id),
                    "label": d.label,
                    "score": float(d.score),
                    "box": [float(v) for v in d.box],
                }
                for d in detections
            ],
        }
    )


def decode_detections(payload: str) -> Tuple[List[Detection], float]:
    data = json.loads(payload)
    dets = [
        Detection(
            cls_id=int(d["cls_id"]),
            label=str(d["label"]),
            score=float(d["score"]),
            box=tuple(float(v) for v in d["box"]),
        )
        for d in data.get("detections", [])
    ]
    return dets, float(data.get("stamp", 0.0))


# --------------------------------------------------------------------------- #
# Fusion status  (/hazard/status)
# --------------------------------------------------------------------------- #
def encode_status(result: FusionResult) -> str:
    return json.dumps(
        {
            "overall_severity": result.overall_severity,
            "banner": result.banner,
            "orphan_count": len(result.orphan_hotspots),
            "objects": [
                {
                    "label": o.label,
                    "severity": o.severity,
                    "thermal_state": o.thermal_state,
                    "peak_c": None if o.peak_c is None else round(float(o.peak_c), 1),
                    "score": round(float(o.score), 3),
                    "box": [float(v) for v in o.box],
                }
                for o in result.objects
            ],
        }
    )


# --------------------------------------------------------------------------- #
# Hazard event  (/hazard/events ; docs/protocols/event_schema.md)
# --------------------------------------------------------------------------- #
def result_to_event(
    result: FusionResult,
    station_id: str,
    event_id: str,
    timestamp_iso: str,
    confidence: float = 0.0,
    image_path: str = "",
) -> Optional[dict]:
    """Build a thermal_risk event for a warning/critical result, else None."""
    if result.overall_severity not in ("warning", "critical"):
        return None
    return {
        "event_id": event_id,
        "timestamp": timestamp_iso,
        "station_id": station_id,
        "source": "thermal",
        "event_type": "thermal_risk",
        "severity": result.overall_severity,
        "confidence": round(float(confidence), 3),
        "summary": result.banner,
        "evidence": {"image_path": image_path, "log_path": "", "serial_output": ""},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
    }
