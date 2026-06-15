"""Action contract: map Layer 2 cognition decisions to concrete executor commands.

Pure routing. ``route_actions`` turns ``CognitionResult.suggested_actions`` (+ the
event's station) into typed Action objects that the cognition node publishes:

  * ``VoicePrompt``  -> /inspection/voice (String)        [TTS executor, on-board]
  * ``RobotRecheck`` -> Nav2 goal via station->waypoint   [chassis_bringup]
  * ``AimGimbal``    -> /gimbal/target_angle (Vector3)     [pan/tilt filled by #3 visual servoing]
  * ``LogRecord``    -> append to the inspection log

``fill_event_action`` writes the resolved decisions back into the event's
``action`` block (per event_schema.md) so the event can be re-logged/forwarded.
Pure stdlib; no ROS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .cognition import CognitionResult
from .events import HazardEvent
from .station_map import StationMap


@dataclass(frozen=True)
class VoicePrompt:
    text: str


@dataclass(frozen=True)
class RobotRecheck:
    station_id: str
    waypoint: Optional[str]  # resolved via StationMap; None if station has no waypoint


@dataclass(frozen=True)
class AimGimbal:
    station_id: str
    # pan/tilt are filled by detection->gimbal visual servoing (#3); None = track/centre.
    pan_deg: Optional[float] = None
    tilt_deg: Optional[float] = None


@dataclass(frozen=True)
class LogRecord:
    event_id: str
    severity: str
    text: str


def route_actions(
    result: CognitionResult, event: HazardEvent, station_map: StationMap
) -> List[object]:
    """Turn suggested action kinds into concrete, parameterized Action objects."""
    actions: List[object] = []
    for kind in result.suggested_actions:
        if kind == "voice":
            actions.append(VoicePrompt(text=result.explanation))
        elif kind == "recheck":
            actions.append(
                RobotRecheck(
                    station_id=event.station_id,
                    waypoint=station_map.waypoint_for_station(event.station_id),
                )
            )
        elif kind == "aim":
            actions.append(AimGimbal(station_id=event.station_id))
        elif kind == "log":
            actions.append(
                LogRecord(
                    event_id=event.event_id,
                    severity=result.confirmed_severity,
                    text=result.explanation,
                )
            )
        # unknown kinds are ignored (forward-compatible)
    return actions


def fill_event_action(
    event: HazardEvent, result: CognitionResult, actions: List[object]
) -> HazardEvent:
    """Write Layer 2 decisions back into the event's action block (event_schema.md)."""
    voice = next((a.text for a in actions if isinstance(a, VoicePrompt)), "")
    recheck = next((a for a in actions if isinstance(a, RobotRecheck)), None)
    event.action.voice_prompt = voice
    event.action.robot_task = f"recheck:{recheck.station_id}" if recheck else ""
    event.action.reported_to_admin = bool(result.escalate_to_cloud)
    return event
