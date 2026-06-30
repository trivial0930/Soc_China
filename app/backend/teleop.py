"""Low-latency teleop channel: latest-only velocity + lidar safety state.

A separate, in-memory, overwrite-on-write store (no SQLite — power loss is fine)
for the real-time drive channel, kept apart from the 2s command queue. Pure (no
fastapi) so it unit-tests like the other backend cores; server.py wraps it with
the four /api/robot/teleop* endpoints and supplies a monotonic `now`.

age_ms = (now - last write) * 1000; before the first write it's a large sentinel
so the RDK deadman (default 400ms) zeroes the velocity.
"""
from __future__ import annotations

from typing import Optional

VX_LIMIT = 0.4   # m/s
VY_LIMIT = 0.4   # m/s
WZ_LIMIT = 1.5   # rad/s
STALE_AGE_MS = 1e9  # "never written" sentinel age


def _clamp(v: float, limit: float) -> float:
    return max(-limit, min(limit, float(v)))


def to_float(v, default: float = 0.0) -> float:
    """Best-effort float (missing/None/bad -> default), so a malformed body is safe."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class TeleopStore:
    def __init__(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._wz = 0.0
        self._v_ts: Optional[float] = None
        self._state = "unknown"
        self._front: Optional[float] = None
        self._s_ts: Optional[float] = None

    # --- velocity: App -> robot (clamped on store) ---
    def set_velocity(self, vx, vy, wz, now: float) -> None:
        self._vx = _clamp(vx, VX_LIMIT)
        self._vy = _clamp(vy, VY_LIMIT)
        self._wz = _clamp(wz, WZ_LIMIT)
        self._v_ts = float(now)

    def get_velocity(self, now: float) -> dict:
        if self._v_ts is None:
            return {"vx": 0.0, "vy": 0.0, "wz": 0.0, "age_ms": STALE_AGE_MS}
        return {"vx": self._vx, "vy": self._vy, "wz": self._wz,
                "age_ms": (float(now) - self._v_ts) * 1000.0}

    # --- safety status: robot -> App ---
    def set_status(self, state, front_dist_m, now: float) -> None:
        self._state = str(state)
        self._front = None if front_dist_m is None else float(front_dist_m)
        self._s_ts = float(now)

    def get_status(self, now: float) -> dict:
        if self._s_ts is None:
            return {"state": "unknown", "front_dist_m": None, "age_ms": STALE_AGE_MS}
        return {"state": self._state, "front_dist_m": self._front,
                "age_ms": (float(now) - self._s_ts) * 1000.0}


class LatestValue:
    """Generic latest-only heartbeat: stores a dict payload + receive time, adds age_ms
    on read (large sentinel before the first write). Used for the robot mode heartbeat
    (RDK POSTs its true mode every tick; App reads mode + age_ms to detect offline).
    """

    def __init__(self, default: dict) -> None:
        self._default = dict(default)
        self._value: Optional[dict] = None
        self._ts: Optional[float] = None

    def set(self, value: dict, now: float) -> None:
        self._value = dict(value)
        self._ts = float(now)

    def get(self, now: float) -> dict:
        if self._ts is None:
            return {**self._default, "age_ms": STALE_AGE_MS}
        return {**self._value, "age_ms": (float(now) - self._ts) * 1000.0}
