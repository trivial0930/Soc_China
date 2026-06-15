"""Robot-recheck executor core.

Turns a Layer 2 recheck request ({station_id, waypoint}) into a Nav2 goal pose by
looking the waypoint up in a poses config. Pure stdlib; the actual Nav2
``followWaypoints`` call lives in the node (on-board).
"""

from __future__ import annotations

import json
from typing import Optional, Tuple, Union

Pose = Tuple[float, float, float]  # x, y, yaw (map frame)


def parse_recheck(payload: Union[str, dict]) -> dict:
    """Parse a /inspection/recheck message into {station_id, waypoint}."""
    data = json.loads(payload) if isinstance(payload, str) else dict(payload)
    return {
        "station_id": str(data.get("station_id", "")),
        "waypoint": data.get("waypoint"),
    }


def pose_for_waypoint(name: Optional[str], cfg: dict) -> Optional[Pose]:
    """Look up a waypoint name -> (x, y, yaw) from a recheck-poses config dict."""
    if not name:
        return None
    poses = (cfg or {}).get("poses") or {}
    p = poses.get(name)
    if not p:
        return None
    x, y, yaw = p
    return (float(x), float(y), float(yaw))
