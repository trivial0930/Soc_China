"""Pure normalization: raw uplink JSON (ROS topic shapes) -> store-row dicts.

Self-contained (no inspection_manager import) so the Mac backend doesn't depend on
the ROS package. The uplink node already rewrites RDK image paths to bare filenames,
but these functions also accept full paths and reduce them to basenames defensively.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _basename(p: str) -> str:
    return os.path.basename(p) if p else ""


def normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Accepts a HazardEvent (with evidence{image_path}) or the rewritten form (image)."""
    image = raw.get("image", "")
    if not image:
        image = (raw.get("evidence") or {}).get("image_path", "")
    return {
        "event_id": str(raw["event_id"]),
        "timestamp": raw.get("timestamp", ""),
        "station_id": raw.get("station_id", ""),
        "source": raw.get("source", ""),
        "event_type": raw.get("event_type", ""),
        "severity": raw.get("severity", "info"),
        "confidence": float(raw.get("confidence", 0.0)),
        "summary": raw.get("summary", ""),
        "image": _basename(image),
        "action": raw.get("action") or {},
    }


def normalize_brief(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Brief topic is {event:{...}, explanation, confirmed_severity, actions, escalate_to_cloud}."""
    event_id = raw.get("event_id") or (raw.get("event") or {}).get("event_id", "")
    return {
        "event_id": str(event_id),
        "explanation": raw.get("explanation", ""),
        "confirmed_severity": raw.get("confirmed_severity", ""),
        "actions": list(raw.get("actions", [])),
        "escalate_to_cloud": bool(raw.get("escalate_to_cloud", False)),
    }


def normalize_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    snaps: List[str] = [_basename(s) for s in (raw.get("snapshots") or []) if s]
    return {
        "station_id": raw.get("station_id", ""),
        "entered_at": raw.get("entered_at"),
        "left_at": raw.get("left_at"),
        "snapshots": snaps,
        "note": raw.get("note", ""),
        "acceptance_hint": raw.get("acceptance_hint", ""),
    }


def normalize_acceptance(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "station_id": raw.get("station_id", ""),
        "verdict": raw.get("verdict", ""),
        "severity": raw.get("severity", ""),
        "problems": list(raw.get("problems", [])),
        "report_id": raw.get("report_id"),
        "received_at": raw.get("received_at"),  # honor seed-provided time; else store stamps now
    }


def normalize_report(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": raw.get("title", ""),
        "report_type": raw.get("report_type", ""),
        "verdict": raw.get("verdict", ""),
        "severity": raw.get("severity", ""),
        "event_ids": list(raw.get("event_ids", [])),
        "body_markdown": raw.get("body_markdown", ""),
        "created_at": raw.get("created_at", ""),
    }
