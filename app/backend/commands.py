"""Pure validation + defaults for the App->robot command channel.

Stdlib only, unit-tested. The HTTP layer (server.py) and store stay thin: they
call validate_command()/normalize_params() and persist the result. The command
type registry below is the single source of truth and mirrors app/API_SPEC.md.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

VALID_FIND_MODES = {"navigate", "laser"}
RESULT_STATUSES = {"done", "failed", "canceled"}


def _has(params: Dict[str, Any], key: str) -> bool:
    return params.get(key) not in (None, "")


def _v_inspection_round(p: Dict[str, Any]) -> Optional[str]:
    return None  # no params


def _v_recheck_station(p: Dict[str, Any]) -> Optional[str]:
    return None if _has(p, "station_id") else "params.station_id is required"


def _v_acceptance(p: Dict[str, Any]) -> Optional[str]:
    return None  # station_id optional ({} == all stations)


def _v_find_item(p: Dict[str, Any]) -> Optional[str]:
    if not (_has(p, "asset_id") or _has(p, "name")):
        return "params requires asset_id or name"
    mode = p.get("mode", "navigate")
    if mode not in VALID_FIND_MODES:
        return "params.mode must be one of: navigate, laser"
    return None


def _v_voice_prompt(p: Dict[str, Any]) -> Optional[str]:
    return None if _has(p, "text") else "params.text is required"


def _v_laser_point(p: Dict[str, Any]) -> Optional[str]:
    if not (_has(p, "station_id") or _has(p, "location")):
        return "params requires station_id or location"
    return None


def _v_generate_report(p: Dict[str, Any]) -> Optional[str]:
    return None  # report_type optional (defaulted)


# type -> validator(params) -> error string or None
COMMAND_VALIDATORS = {
    "inspection_round": _v_inspection_round,
    "recheck_station": _v_recheck_station,
    "acceptance": _v_acceptance,
    "find_item": _v_find_item,
    "voice_prompt": _v_voice_prompt,
    "laser_point": _v_laser_point,
    "generate_report": _v_generate_report,
}
COMMAND_TYPES = frozenset(COMMAND_VALIDATORS)


def validate_command(ctype: str, params: Any) -> Optional[str]:
    """Return None if (ctype, params) is valid, else a human-readable error string."""
    if ctype not in COMMAND_VALIDATORS:
        return f"unknown command type: {ctype!r}"
    if not isinstance(params, dict):
        return "params must be an object"
    return COMMAND_VALIDATORS[ctype](params)


def normalize_params(ctype: str, params: Any) -> Dict[str, Any]:
    """Copy params and apply per-type defaults (called after validate_command passes)."""
    p = dict(params) if isinstance(params, dict) else {}
    if ctype == "find_item":
        p.setdefault("mode", "navigate")
    elif ctype == "generate_report":
        p.setdefault("report_type", "periodic_summary")
    return p
