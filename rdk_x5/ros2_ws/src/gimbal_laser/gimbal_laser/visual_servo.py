"""Image-based visual servoing: aim the gimbal so a detected hazard centres.

The RGB + thermal cameras are mounted ON the gimbal, so rotating the gimbal moves
the target within the image. Given the target's pixel location and the gimbal's
current angles, this computes the next pan/tilt command that drives the target
toward image centre (proportional control with a FOV-based pixel->angle mapping,
a centring deadband, per-step slew cap, and axis limits).

Pure stdlib — unit-tested with no ROS / hardware. The correct rotation *sign* is
hardware-dependent and set on-board via ``invert_pan`` / ``invert_tilt``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class ServoConfig:
    image_width: int = 1920
    image_height: int = 1080
    hfov_deg: float = 90.0  # camera horizontal field of view
    vfov_deg: float = 68.0  # camera vertical field of view
    gain: float = 0.6  # fraction of the angular error applied per step (damping)
    deadband_px: float = 30.0  # target within this radius of centre = centred
    max_step_deg: float = 8.0  # per-iteration slew cap
    swap_axes: bool = False  # camera mounted 90deg on gimbal: image-x->tilt, image-y->pan
    invert_pan: bool = False
    invert_tilt: bool = True  # image y grows downward; tilt+ is usually up
    pan_min_deg: float = -60.0
    pan_max_deg: float = 60.0
    tilt_min_deg: float = -30.0
    tilt_max_deg: float = 45.0


@dataclass(frozen=True)
class ServoCommand:
    pan_deg: float
    tilt_deg: float
    centered: bool
    pixel_error: Tuple[float, float]  # (ex, ey) target - centre, pixels


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def servo_step(
    current_pan: float,
    current_tilt: float,
    target_px: Sequence[float],
    cfg: ServoConfig,
) -> ServoCommand:
    """One visual-servo iteration: current angles + target pixel -> next angles."""
    u, v = float(target_px[0]), float(target_px[1])
    ex = u - cfg.image_width / 2.0
    ey = v - cfg.image_height / 2.0

    if (ex * ex + ey * ey) ** 0.5 <= cfg.deadband_px:
        return ServoCommand(current_pan, current_tilt, True, (ex, ey))

    # pixel error -> angular error using the camera FOV
    ang_x = ex * (cfg.hfov_deg / cfg.image_width)
    ang_y = ey * (cfg.vfov_deg / cfg.image_height)

    sign_pan = -1.0 if cfg.invert_pan else 1.0
    sign_tilt = -1.0 if cfg.invert_tilt else 1.0
    # swap_axes: gimbal-mounted camera rolled 90deg, so image-y drives pan, image-x tilt
    pan_ang = ang_y if cfg.swap_axes else ang_x
    tilt_ang = ang_x if cfg.swap_axes else ang_y
    dpan = _clamp(sign_pan * cfg.gain * pan_ang, -cfg.max_step_deg, cfg.max_step_deg)
    dtilt = _clamp(sign_tilt * cfg.gain * tilt_ang, -cfg.max_step_deg, cfg.max_step_deg)

    new_pan = _clamp(current_pan + dpan, cfg.pan_min_deg, cfg.pan_max_deg)
    new_tilt = _clamp(current_tilt + dtilt, cfg.tilt_min_deg, cfg.tilt_max_deg)
    return ServoCommand(new_pan, new_tilt, False, (ex, ey))


def pick_target(objects: Sequence[dict]) -> Optional[Tuple[float, float]]:
    """Pick the box centre of the highest-severity object from /hazard/status.

    ``objects`` are the per-object dicts (label/severity/box) from encode_status.
    Returns (cx, cy) or None when there is nothing worth aiming at.
    """
    rank = {"info": 0, "warning": 1, "critical": 2}
    best = None
    best_rank = -1
    for obj in objects:
        r = rank.get(obj.get("severity", "info"), 0)
        if r > best_rank and obj.get("box"):
            best_rank = r
            best = obj
    if best is None:
        return None
    x1, y1, x2, y2 = best["box"]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def config_from_dict(cfg: dict) -> ServoConfig:
    cfg = cfg or {}
    d = ServoConfig()
    return ServoConfig(
        image_width=int(cfg.get("image_width", d.image_width)),
        image_height=int(cfg.get("image_height", d.image_height)),
        hfov_deg=float(cfg.get("hfov_deg", d.hfov_deg)),
        vfov_deg=float(cfg.get("vfov_deg", d.vfov_deg)),
        gain=float(cfg.get("gain", d.gain)),
        deadband_px=float(cfg.get("deadband_px", d.deadband_px)),
        max_step_deg=float(cfg.get("max_step_deg", d.max_step_deg)),
        swap_axes=bool(cfg.get("swap_axes", d.swap_axes)),
        invert_pan=bool(cfg.get("invert_pan", d.invert_pan)),
        invert_tilt=bool(cfg.get("invert_tilt", d.invert_tilt)),
        pan_min_deg=float(cfg.get("pan_min_deg", d.pan_min_deg)),
        pan_max_deg=float(cfg.get("pan_max_deg", d.pan_max_deg)),
        tilt_min_deg=float(cfg.get("tilt_min_deg", d.tilt_min_deg)),
        tilt_max_deg=float(cfg.get("tilt_max_deg", d.tilt_max_deg)),
    )
