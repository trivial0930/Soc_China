"""Config loading for inspection_manager.

Pure dict->object helpers are unit-tested; the YAML file IO is a thin wrapper that
needs PyYAML (present in the RDK runtime venv), mirroring thermal_detector's
config_loader.py.
"""

from __future__ import annotations

from .cognition import tier_policy_from_dict
from .escalation import EscalationPolicy, policy_from_dict
from .station_map import StationMap, station_map_from_dict


def cognition_backend_name(cfg: dict) -> str:
    return str((cfg or {}).get("backend", "mock"))


def station_context(cfg: dict) -> str:
    return str((cfg or {}).get("station_context", ""))


def report_settings_from_dict(cfg: dict) -> dict:
    spec = (cfg or {}).get("report") or {}
    return {
        "backend": str(spec.get("backend", "mock")),
        "model": str(spec.get("model", "qwen3-vl-plus")),
        "max_calls": int(spec.get("max_calls", 5)),
        "window_sec": float(spec.get("window_sec", 3600.0)),
    }


def tier_settings_from_dict(cfg: dict) -> dict:
    """Read the 'tier' block of cognition.yaml -> fast/deep model+base_url + TierPolicy.

    Empty deep_base_url signals 'no deep backend' (the node then builds fast-only).
    """
    t = (cfg or {}).get("tier") or {}
    fast = t.get("fast") or {}
    deep = t.get("deep") or {}
    return {
        "fast_model": str(fast.get("vlm_model", "qwen2-vl:2b")),
        "fast_base_url": str(fast.get("vlm_base_url", "http://localhost:8080/v1")),
        "deep_model": str(deep.get("vlm_model", "qwen2.5vl:7b")),
        "deep_base_url": str(deep.get("vlm_base_url", "")),
        "policy": tier_policy_from_dict(t.get("policy") or {}),
    }


def _load_yaml(path: str) -> dict:  # pragma: no cover - thin IO wrapper
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML required to read inspection_manager config") from exc
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_cognition(path: str):  # pragma: no cover - thin IO wrapper
    """Read cognition.yaml -> (backend_name, EscalationPolicy, station_context)."""
    cfg = _load_yaml(path)
    return cognition_backend_name(cfg), policy_from_dict(cfg), station_context(cfg)


def load_stations(path: str) -> StationMap:  # pragma: no cover - thin IO wrapper
    return station_map_from_dict(_load_yaml(path))


def load_report(path: str) -> dict:  # pragma: no cover - thin IO wrapper
    return report_settings_from_dict(_load_yaml(path))
