"""Hardware-independent RGB + thermal fusion core.

This module decides *heat-source hazard* severity by combining:

* **What** an object is -- RGB/YOLO detections (class + box), and
* **How hot** it is -- a radiometric thermal frame (per-pixel degrees C).

It is deliberately stdlib-only (no numpy/cv2) so it can be unit-tested on any
machine. Temperature frames may be passed as a nested ``list[list[float]]`` or a
2-D numpy array -- both support ``frame[y][x]`` indexing and are handled by the
small grid helpers below.

Coordinate spaces:

* RGB pixel space -- where detection boxes live (e.g. 1920x1072).
* Thermal pixel space -- the 80x62 SenXor frame.
* ``homography_thermal_to_rgb`` is a 3x3 matrix mapping a thermal pixel to its
  RGB pixel. Its inverse maps an RGB box back into thermal space for sampling.
  Calibrate it once (see ``scripts/thermal_rgb_calibrate.py``); for tests an
  identity / scale matrix is enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


Matrix3 = Sequence[Sequence[float]]
Box = Tuple[float, float, float, float]  # x1, y1, x2, y2

# Severity vocabulary matches docs/protocols/event_schema.md.
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# Object base-risk tiers (from the hazard handoff recommended mapping).
_SEVERITY_MATRIX: Dict[str, Dict[str, str]] = {
    "high": {"cold": "warning", "active": "critical", "hot": "critical", "unknown": "warning"},
    "medium": {"cold": "info", "active": "warning", "hot": "critical", "unknown": "info"},
    "context": {"cold": "info", "active": "info", "hot": "warning", "unknown": "info"},
}


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClassPolicy:
    """Per-class risk tier and temperature thresholds (degrees C)."""

    name: str
    base_risk: str  # "high" | "medium" | "context"
    active_c: float
    hot_c: float


@dataclass(frozen=True)
class Detection:
    """A single RGB/YOLO detection."""

    cls_id: int
    label: str
    score: float
    box: Box


@dataclass
class HotspotParams:
    """Tunables for relative-hotspot detection."""

    delta_c: float = 8.0  # how far above the scene baseline counts as hot
    abs_floor_c: float = 40.0  # never flag anything cooler than this
    baseline_percentile: float = 50.0  # scene baseline = this percentile of the frame
    min_area_px: int = 2  # ignore blobs smaller than this (noise)
    orphan_critical_c: float = 70.0  # object-less hotspot at/above this is critical


@dataclass(frozen=True)
class Hotspot:
    """A connected hot region in the thermal frame."""

    tx1: int
    ty1: int
    tx2: int
    ty2: int
    peak_c: float
    area_px: int
    rgb_cx: float  # centroid mapped into RGB space
    rgb_cy: float


@dataclass(frozen=True)
class FusedObject:
    cls_id: int
    label: str
    score: float
    box: Box
    base_risk: str
    peak_c: Optional[float]
    mean_c: Optional[float]
    thermal_state: str  # "cold" | "active" | "hot" | "unknown"
    severity: str  # "info" | "warning" | "critical"
    reason: str


@dataclass
class FusionResult:
    objects: List[FusedObject] = field(default_factory=list)
    orphan_hotspots: List[Hotspot] = field(default_factory=list)
    overall_severity: str = "info"
    banner: str = ""


# Default thresholds for the 10 hazard classes (tune on real lab data, Phase 5).
DEFAULT_POLICIES: Dict[str, ClassPolicy] = {
    "soldering_iron": ClassPolicy("soldering_iron", "high", 50.0, 150.0),
    "hot_air_gun": ClassPolicy("hot_air_gun", "high", 50.0, 150.0),
    "welding_gun": ClassPolicy("welding_gun", "high", 50.0, 150.0),
    "exposed_wire": ClassPolicy("exposed_wire", "high", 45.0, 70.0),
    "power_strip": ClassPolicy("power_strip", "medium", 45.0, 80.0),
    "plug": ClassPolicy("plug", "medium", 45.0, 80.0),
    "power_adapter": ClassPolicy("power_adapter", "medium", 45.0, 80.0),
    "wire": ClassPolicy("wire", "context", 45.0, 70.0),
    "wire_bundle": ClassPolicy("wire_bundle", "context", 45.0, 70.0),
    "soldering_station": ClassPolicy("soldering_station", "context", 50.0, 150.0),
}


# --------------------------------------------------------------------------- #
# Geometry helpers (pure stdlib)
# --------------------------------------------------------------------------- #
def apply_homography(matrix: Matrix3, x: float, y: float) -> Tuple[float, float]:
    """Map a point through a 3x3 homography."""
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if w == 0:
        raise ValueError("Degenerate homography: zero scale at point")
    px = (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w
    py = (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w
    return (px, py)


def invert_3x3(matrix: Matrix3) -> Tuple[Tuple[float, float, float], ...]:
    """Invert a 3x3 matrix via cofactors."""
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if det == 0:
        raise ValueError("Singular matrix cannot be inverted")
    inv_det = 1.0 / det
    return (
        ((e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det),
        ((f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det),
        ((d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det),
    )


# --------------------------------------------------------------------------- #
# Grid helpers (work for nested lists and numpy arrays)
# --------------------------------------------------------------------------- #
def _grid_dims(frame) -> Tuple[int, int]:
    shape = getattr(frame, "shape", None)
    if shape is not None:
        return int(shape[0]), int(shape[1])
    return len(frame), len(frame[0])


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(pct / 100.0 * len(ordered))
    if idx >= len(ordered):
        idx = len(ordered) - 1
    return float(ordered[idx])


def _point_in_box(x: float, y: float, box: Box) -> bool:
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


# --------------------------------------------------------------------------- #
# Hotspot detection
# --------------------------------------------------------------------------- #
def find_hotspots(frame, params: HotspotParams, homography_thermal_to_rgb: Matrix3) -> List[Hotspot]:
    """Find connected hot regions (relative-to-scene AND above an absolute floor)."""
    rows, cols = _grid_dims(frame)
    flat = [float(frame[y][x]) for y in range(rows) for x in range(cols)]
    baseline = _percentile(flat, params.baseline_percentile)
    threshold = max(baseline + params.delta_c, params.abs_floor_c)

    hot = [[float(frame[y][x]) >= threshold for x in range(cols)] for y in range(rows)]
    seen = [[False] * cols for _ in range(rows)]
    spots: List[Hotspot] = []

    for sy in range(rows):
        for sx in range(cols):
            if not hot[sy][sx] or seen[sy][sx]:
                continue
            # Flood-fill this connected component (4-connectivity).
            stack = [(sy, sx)]
            seen[sy][sx] = True
            cells: List[Tuple[int, int]] = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and hot[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((ny, nx))

            if len(cells) < params.min_area_px:
                continue

            xs = [c[1] for c in cells]
            ys = [c[0] for c in cells]
            peak = max(float(frame[y][x]) for y, x in cells)
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            rgb_cx, rgb_cy = apply_homography(homography_thermal_to_rgb, cx, cy)
            spots.append(
                Hotspot(
                    tx1=min(xs),
                    ty1=min(ys),
                    tx2=max(xs),
                    ty2=max(ys),
                    peak_c=peak,
                    area_px=len(cells),
                    rgb_cx=rgb_cx,
                    rgb_cy=rgb_cy,
                )
            )

    spots.sort(key=lambda s: s.peak_c, reverse=True)
    return spots


# --------------------------------------------------------------------------- #
# Severity
# --------------------------------------------------------------------------- #
def severity_for(base_risk: str, thermal_state: str) -> str:
    """Combine object base risk with thermal state into an event severity."""
    row = _SEVERITY_MATRIX.get(base_risk, _SEVERITY_MATRIX["context"])
    return row.get(thermal_state, "info")


def _max_severity(severities: Sequence[str]) -> str:
    best = "info"
    for sev in severities:
        if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK[best]:
            best = sev
    return best


def _orphan_severity(spot: Hotspot, params: HotspotParams) -> str:
    return "critical" if spot.peak_c >= params.orphan_critical_c else "warning"


# --------------------------------------------------------------------------- #
# Box -> thermal sampling
# --------------------------------------------------------------------------- #
def _sample_box(frame, box: Box, homography_rgb_to_thermal: Matrix3) -> Tuple[Optional[float], Optional[float]]:
    """Return (peak_c, mean_c) of an RGB box's footprint in the thermal frame."""
    rows, cols = _grid_dims(frame)
    x1, y1, x2, y2 = box
    corners = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    mapped = [apply_homography(homography_rgb_to_thermal, cx, cy) for cx, cy in corners]
    txs = [m[0] for m in mapped]
    tys = [m[1] for m in mapped]

    tx_lo = max(0, int(round(min(txs))))
    tx_hi = min(cols - 1, int(round(max(txs))))
    ty_lo = max(0, int(round(min(tys))))
    ty_hi = min(rows - 1, int(round(max(tys))))
    if tx_lo > tx_hi or ty_lo > ty_hi:
        return None, None  # box maps entirely outside the thermal field of view

    vals = [float(frame[y][x]) for y in range(ty_lo, ty_hi + 1) for x in range(tx_lo, tx_hi + 1)]
    if not vals:
        return None, None
    return max(vals), sum(vals) / len(vals)


# --------------------------------------------------------------------------- #
# Fusion entry point
# --------------------------------------------------------------------------- #
def fuse(
    detections: Sequence[Detection],
    frame,
    homography_thermal_to_rgb: Matrix3,
    policies: Optional[Dict[str, ClassPolicy]] = None,
    params: Optional[HotspotParams] = None,
    trust_absolute: bool = True,
) -> FusionResult:
    """Fuse RGB detections with a thermal frame into a hazard assessment.

    Args:
        detections: RGB/YOLO detections (class, score, box in RGB pixels).
        frame: thermal temperature frame (degrees C), nested list or numpy 2-D.
        homography_thermal_to_rgb: 3x3 mapping thermal pixels -> RGB pixels.
        policies: per-class risk/threshold table (defaults to DEFAULT_POLICIES).
        params: hotspot tunables (defaults to HotspotParams()).
        trust_absolute: if False, ignore absolute degC (e.g. shiny metal with low
            emissivity) and rely on relative-hotspot overlap only.
    """
    policies = policies or DEFAULT_POLICIES
    params = params or HotspotParams()
    homography_rgb_to_thermal = invert_3x3(homography_thermal_to_rgb)

    hotspots = find_hotspots(frame, params, homography_thermal_to_rgb)
    result = FusionResult()

    for det in detections:
        policy = policies.get(det.label) or ClassPolicy(det.label, "context", 45.0, 70.0)
        peak_c, mean_c = _sample_box(frame, det.box, homography_rgb_to_thermal)
        overlaps_hotspot = any(_point_in_box(s.rgb_cx, s.rgb_cy, det.box) for s in hotspots)

        if peak_c is None:
            thermal_state = "unknown"
            reason = f"{det.label}: no thermal coverage for this box"
        elif trust_absolute and peak_c >= policy.hot_c:
            thermal_state = "hot"
            reason = f"{det.label}: peak {peak_c:.0f}C >= hot {policy.hot_c:.0f}C"
        elif (trust_absolute and peak_c >= policy.active_c) or overlaps_hotspot:
            thermal_state = "active"
            reason = f"{det.label}: peak {peak_c:.0f}C >= active {policy.active_c:.0f}C"
        else:
            thermal_state = "cold"
            reason = f"{det.label}: peak {peak_c:.0f}C below active {policy.active_c:.0f}C"

        result.objects.append(
            FusedObject(
                cls_id=det.cls_id,
                label=det.label,
                score=det.score,
                box=det.box,
                base_risk=policy.base_risk,
                peak_c=peak_c,
                mean_c=mean_c,
                thermal_state=thermal_state,
                severity=severity_for(policy.base_risk, thermal_state),
                reason=reason,
            )
        )

    # Hotspots not explained by any detection box are "unidentified heat sources".
    result.orphan_hotspots = [
        s
        for s in hotspots
        if not any(_point_in_box(s.rgb_cx, s.rgb_cy, det.box) for det in detections)
    ]

    severities = [o.severity for o in result.objects]
    severities += [_orphan_severity(s, params) for s in result.orphan_hotspots]
    result.overall_severity = _max_severity(severities)
    result.banner = _build_banner(result, params)
    return result


def _build_banner(result: FusionResult, params: HotspotParams) -> str:
    """Human-readable banner describing the single worst finding."""
    worst_obj = None
    worst_rank = -1
    for obj in result.objects:
        rank = _SEVERITY_RANK.get(obj.severity, 0)
        if rank > worst_rank:
            worst_rank = rank
            worst_obj = obj

    worst_orphan = None
    worst_orphan_rank = -1
    for spot in result.orphan_hotspots:
        rank = _SEVERITY_RANK[_orphan_severity(spot, params)]
        if rank > worst_orphan_rank:
            worst_orphan_rank = rank
            worst_orphan = spot

    if worst_obj is None and worst_orphan is None:
        return "OK: no hazard"

    if worst_orphan is not None and worst_orphan_rank >= worst_rank:
        sev = _orphan_severity(worst_orphan, params)
        return f"{sev.upper()}: unidentified heat source {worst_orphan.peak_c:.0f}C"

    temp = "" if worst_obj.peak_c is None else f" {worst_obj.peak_c:.0f}C"
    return f"{worst_obj.severity.upper()}: {worst_obj.label} ({worst_obj.thermal_state}{temp})"
