"""Load thermal fusion config (hazard policy + RGB/thermal calibration).

The dict -> object conversions are pure and unit-tested. The YAML file reading
is a thin wrapper that needs PyYAML (present in the RDK runtime venv).
"""

from __future__ import annotations

from typing import Dict, Tuple

from .fusion import ClassPolicy, HotspotParams

Matrix3 = Tuple[Tuple[float, float, float], ...]


def policies_from_dict(cfg: dict) -> Dict[str, ClassPolicy]:
    """Build {class_name: ClassPolicy} from a parsed hazard-config dict."""
    classes = cfg.get("classes") or {}
    policies: Dict[str, ClassPolicy] = {}
    for name, spec in classes.items():
        policies[name] = ClassPolicy(
            name=name,
            base_risk=str(spec["base_risk"]),
            active_c=float(spec["active_c"]),
            hot_c=float(spec["hot_c"]),
        )
    return policies


def params_from_dict(cfg: dict) -> HotspotParams:
    """Build HotspotParams from a parsed hazard-config dict (defaults if absent)."""
    spot = cfg.get("hotspot") or {}
    defaults = HotspotParams()
    return HotspotParams(
        delta_c=float(spot.get("delta_c", defaults.delta_c)),
        abs_floor_c=float(spot.get("abs_floor_c", defaults.abs_floor_c)),
        baseline_percentile=float(spot.get("baseline_percentile", defaults.baseline_percentile)),
        min_area_px=int(spot.get("min_area_px", defaults.min_area_px)),
        orphan_critical_c=float(spot.get("orphan_critical_c", defaults.orphan_critical_c)),
    )


def trust_absolute_from_dict(cfg: dict) -> bool:
    return bool(cfg.get("trust_absolute", True))


def homography_from_dict(cfg: dict) -> Matrix3:
    """Extract the 3x3 thermal->RGB homography from a parsed calibration dict."""
    rows = cfg["homography_thermal_to_rgb"]
    return tuple(tuple(float(v) for v in row) for row in rows)


def _load_yaml(path: str) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - board has PyYAML
        raise RuntimeError("PyYAML required to read thermal config files") from exc
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_hazard_config(path: str):  # pragma: no cover - thin IO wrapper
    """Read thermal_hazard.yaml -> (policies, params, trust_absolute)."""
    cfg = _load_yaml(path)
    return policies_from_dict(cfg), params_from_dict(cfg), trust_absolute_from_dict(cfg)


def load_calibration(path: str) -> Matrix3:  # pragma: no cover - thin IO wrapper
    """Read thermal_rgb_calib.yaml -> 3x3 thermal->RGB homography."""
    return homography_from_dict(_load_yaml(path))
