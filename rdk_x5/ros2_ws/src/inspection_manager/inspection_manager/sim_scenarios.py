"""Synthetic Layer 1 events for driving the inspection pipeline with no hardware.

``sample_events()`` returns /hazard/events-shaped dicts (per event_schema.md) so a
publisher node can replay them on a PC and exercise cognition -> actions -> report
end to end without a camera / detector. Pure stdlib.
"""

from __future__ import annotations

from typing import List


def make_event(
    event_id: str,
    station_id: str,
    severity: str,
    summary: str,
    *,
    event_type: str = "thermal_risk",
    confidence: float = 0.9,
    image_path: str = "",
    timestamp: str = "2026-06-15T20:30:00+08:00",
) -> dict:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "station_id": station_id,
        "source": "thermal" if event_type == "thermal_risk" else "camera",
        "event_type": event_type,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "evidence": {"image_path": image_path, "log_path": "", "serial_output": ""},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
    }


def sample_events() -> List[dict]:
    """A small mixed scenario: confident critical, uncertain warning, desk_messy."""
    return [
        make_event("20260615-0001", "desk-03", "critical",
                   "CRITICAL: soldering_iron (active 145C)", confidence=0.92,
                   image_path="/ev/0001.jpg"),
        make_event("20260615-0002", "desk-05", "warning",
                   "WARNING: unknown hot region (62C)", confidence=0.2,
                   image_path="/ev/0002.jpg"),
        make_event("20260615-0003", "desk-01", "warning",
                   "需整理：导线杂乱拖拽", event_type="desk_messy", confidence=1.0),
    ]
