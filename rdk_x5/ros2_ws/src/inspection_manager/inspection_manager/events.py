"""Pure event model for the inspection_manager (Layer 2 / Layer 3) decision layers.

Mirrors ``docs/protocols/event_schema.md``. stdlib-only, so it is unit-tested
with no ROS and no hardware. Layer 1 (``thermal_detector``) emits these events on
``/hazard/events``; this module parses them, and Layer 2 fills the ``action``
block back in before re-publishing / logging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Union

SEVERITIES = ("info", "warning", "critical")
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# Allowed vocab from event_schema.md (kept for validation / documentation).
SOURCES = ("camera", "thermal", "stm32", "manual", "mock")
EVENT_TYPES = ("thermal_risk", "desk_messy", "device_missing", "estop", "fault")


def severity_rank(severity: str) -> int:
    """Ordinal rank of a severity string (unknown -> 0)."""
    return SEVERITY_RANK.get(severity, 0)


@dataclass
class Evidence:
    image_path: str = ""
    log_path: str = ""
    serial_output: str = ""

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "log_path": self.log_path,
            "serial_output": self.serial_output,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        data = data or {}
        return cls(
            image_path=str(data.get("image_path", "")),
            log_path=str(data.get("log_path", "")),
            serial_output=str(data.get("serial_output", "")),
        )


@dataclass
class Action:
    robot_task: str = ""
    voice_prompt: str = ""
    reported_to_admin: bool = False

    def to_dict(self) -> dict:
        return {
            "robot_task": self.robot_task,
            "voice_prompt": self.voice_prompt,
            "reported_to_admin": self.reported_to_admin,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        data = data or {}
        return cls(
            robot_task=str(data.get("robot_task", "")),
            voice_prompt=str(data.get("voice_prompt", "")),
            reported_to_admin=bool(data.get("reported_to_admin", False)),
        )


@dataclass
class HazardEvent:
    """One hazard event, matching docs/protocols/event_schema.md."""

    event_id: str
    timestamp: str
    station_id: str
    source: str
    event_type: str
    severity: str
    confidence: float = 0.0
    summary: str = ""
    evidence: Evidence = field(default_factory=Evidence)
    action: Action = field(default_factory=Action)

    @property
    def severity_rank(self) -> int:
        return severity_rank(self.severity)

    def to_dict(self) -> dict:
        """Serialize in event_schema.md field order."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "station_id": self.station_id,
            "source": self.source,
            "event_type": self.event_type,
            "severity": self.severity,
            "confidence": round(float(self.confidence), 3),
            "summary": self.summary,
            "evidence": self.evidence.to_dict(),
            "action": self.action.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def parse_event(payload: Union[str, dict]) -> HazardEvent:
    """Parse a /hazard/events JSON string (or dict) into a HazardEvent.

    Tolerant of missing optional fields so a partially-populated Layer 1 event
    still loads. Raises KeyError only for the truly required identity fields.
    """
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    return HazardEvent(
        event_id=str(data["event_id"]),
        timestamp=str(data["timestamp"]),
        station_id=str(data.get("station_id", "")),
        source=str(data.get("source", "mock")),
        event_type=str(data.get("event_type", "fault")),
        severity=str(data.get("severity", "info")),
        confidence=float(data.get("confidence", 0.0)),
        summary=str(data.get("summary", "")),
        evidence=Evidence.from_dict(data.get("evidence")),
        action=Action.from_dict(data.get("action")),
    )
