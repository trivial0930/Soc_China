"""Map a detection to a lab workstation (``station_id``), and back to a waypoint.

Two ways a hazard gets a station:
  * fixed camera: the detection's pixel location falls inside a named camera region;
  * mobile robot: the robot's current navigation waypoint maps to a station.

The reverse (station -> waypoint) lets a Layer 2 "robot recheck" action turn a
station into a Nav2 goal. Pure + config-driven (stations.yaml); unit-tested with
no ROS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class StationRegion:
    station_id: str
    camera: str
    rect: Tuple[float, float, float, float]  # x1, y1, x2, y2 (pixel or normalized)

    def contains(self, x: float, y: float) -> bool:
        x1, y1, x2, y2 = self.rect
        return x1 <= x <= x2 and y1 <= y <= y2


@dataclass
class StationMap:
    regions: List[StationRegion] = field(default_factory=list)
    waypoint_to_station: Dict[str, str] = field(default_factory=dict)

    def station_for_pixel(self, camera: str, x: float, y: float) -> Optional[str]:
        for region in self.regions:
            if region.camera == camera and region.contains(x, y):
                return region.station_id
        return None

    def station_for_box(
        self, camera: str, box: Sequence[float]
    ) -> Optional[str]:
        """Station for a detection box [x1, y1, x2, y2] using its centre."""
        x1, y1, x2, y2 = box
        return self.station_for_pixel(camera, (x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def station_for_waypoint(self, waypoint: str) -> Optional[str]:
        return self.waypoint_to_station.get(waypoint)

    def waypoint_for_station(self, station_id: str) -> Optional[str]:
        for waypoint, station in self.waypoint_to_station.items():
            if station == station_id:
                return waypoint
        return None


def station_map_from_dict(cfg: dict) -> StationMap:
    """Build a StationMap from the parsed stations.yaml dict.

    Expected shape::

        regions:
          - {station_id: desk-01, camera: cam-front, rect: [0, 0, 960, 540]}
        waypoints:
          wp_desk01: desk-01
    """
    cfg = cfg or {}
    regions = [
        StationRegion(
            station_id=str(r["station_id"]),
            camera=str(r.get("camera", "")),
            rect=tuple(float(v) for v in r["rect"]),  # type: ignore[arg-type]
        )
        for r in (cfg.get("regions") or [])
    ]
    waypoints = {str(k): str(v) for k, v in (cfg.get("waypoints") or {}).items()}
    return StationMap(regions=regions, waypoint_to_station=waypoints)
