"""Pure obstacle-gating logic for the lidar safety layer (no ROS dependency).

Gates a teleop body-twist (vx, vy, wz) against a laser scan so the chassis slows
and stops before driving into an obstacle, while always allowing rotation and
motion away from the obstacle. Host-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class GateParams:
    sector_half_angle: float = 0.61   # rad (~35 deg) half-width of the checked cone
    stop_dist: float = 0.30           # m: closer than this -> block translation
    slow_dist: float = 0.60           # m: between stop and slow -> scale translation
    v_eps: float = 0.02               # m/s: below this, treat as "not translating"
    range_min: float = 0.05           # m: ignore returns closer than this (noise/0)
    range_max: float = 12.0           # m: ignore returns beyond this (N10 spec)
    # Near-field self-occlusion masks: where the 360deg lidar sees the robot's own
    # body/cables. Each entry (center, half, near_dist): inside that angular cone,
    # returns CLOSER than near_dist are dropped (self body) but farther returns are
    # still real obstacles (so we keep avoiding beyond the body). Default: rear
    # cone 180deg +/-45, body within 0.30 m (measured: rear <30cm is all chassis).
    near_masks: tuple = ((math.pi, math.radians(45.0), 0.30),)


def _masked(angle, r, near_masks):
    """True if (angle, r) falls inside a near-field self mask (drop it)."""
    for center, half, near in near_masks:
        diff = math.atan2(math.sin(angle - center), math.cos(angle - center))
        if abs(diff) <= half and r < near:
            return True
    return False


def _min_dist_in_sector(ranges, angle_min, angle_increment, center, half,
                        range_min, range_max, near_masks=()):
    """Minimum valid range within +/-half of `center` (rad). inf if none.

    Invalid returns (None / NaN / <range_min / >range_max) are skipped; NaN is
    rejected by the range comparison (all comparisons with NaN are False). Returns
    inside a near-field self mask (own body within a cone) are dropped too.
    """
    best = float("inf")
    if angle_increment == 0.0:
        return best
    for i, r in enumerate(ranges):
        if r is None:
            continue
        if not (range_min <= r <= range_max):
            continue
        ang = angle_min + i * angle_increment
        if near_masks and _masked(ang, r, near_masks):
            continue
        diff = math.atan2(math.sin(ang - center), math.cos(ang - center))
        if abs(diff) <= half and r < best:
            best = r
    return best


def gate_twist(ranges, angle_min, angle_increment, vx, vy, wz, params=None):
    """Gate (vx, vy, wz) against a scan.

    Returns (out_vx, out_vy, out_wz, state, front_dist) where state is one of
    "clear" | "slow" | "blocked" and front_dist is the nearest obstacle (m) in
    the direction of travel (or the forward cone when not translating; inf=none).

    Rules:
      - wz (rotation) always passes through (rotating in place cannot translate
        the robot into an obstacle).
      - heading = atan2(vy, vx) is the translation direction (robot frame, 0=fwd,
        +=left). Only the cone around the *current* heading is checked, so
        reversing or strafing away naturally checks a different (clear) cone and
        is allowed.
      - d < stop_dist  -> translation zeroed (blocked); d < slow_dist -> scaled.
    """
    p = params or GateParams()
    speed = math.hypot(vx, vy)

    if speed <= p.v_eps:
        # Not translating: nothing to gate. Report forward cone for display.
        front = _min_dist_in_sector(ranges, angle_min, angle_increment, 0.0,
                                    p.sector_half_angle, p.range_min, p.range_max,
                                    p.near_masks)
        return 0.0 if abs(vx) <= p.v_eps else vx, \
               0.0 if abs(vy) <= p.v_eps else vy, \
               wz, "clear", front

    heading = math.atan2(vy, vx)
    d = _min_dist_in_sector(ranges, angle_min, angle_increment, heading,
                            p.sector_half_angle, p.range_min, p.range_max,
                            p.near_masks)

    if d < p.stop_dist:
        return 0.0, 0.0, wz, "blocked", d
    if d < p.slow_dist:
        scale = (d - p.stop_dist) / (p.slow_dist - p.stop_dist)
        return vx * scale, vy * scale, wz, "slow", d
    return vx, vy, wz, "clear", d
