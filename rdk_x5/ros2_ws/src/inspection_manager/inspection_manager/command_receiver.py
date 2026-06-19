"""Pure command->ROS dispatch logic for the App->robot command channel.

stdlib only, unit-tested (no rclpy). The node (command_receiver_node.py) is a thin
shell: it polls the backend, calls dispatch_command() to decide which ROS topic to
publish and what String to send, publishes, then posts a result back.

Supported now (map 1:1 to existing ROS topics): voice_prompt, recheck_station,
generate_report. Other types return {"unsupported": reason} so the node reports an
honest 'failed' receipt instead of silently dropping the command — they can be wired
incrementally as the robot exposes triggers for patrol/acceptance/laser.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

SUPPORTED = {"voice_prompt", "recheck_station", "generate_report"}


def station_to_waypoint(station_id: str, stations_cfg: Dict[str, Any]) -> Optional[str]:
    """Reverse stations.yaml `waypoints: {wp_desk01: desk-01}` -> waypoint for a station."""
    for wp, sid in (stations_cfg.get("waypoints") or {}).items():
        if sid == station_id:
            return wp
    return None


def dispatch_command(cmd: Dict[str, Any], stations_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map a Command to a ROS publish descriptor.

    Returns either:
      {"topic_key": <param name>, "data": <String payload>, "result": <receipt text>}
      or {"unsupported": <reason>}.
    """
    stations_cfg = stations_cfg or {}
    ctype = cmd.get("type", "")
    params = cmd.get("params") or {}

    if ctype == "voice_prompt":
        text = str(params.get("text", "")).strip()
        if not text:
            return {"unsupported": "voice_prompt 缺 text"}
        return {"topic_key": "voice_topic", "data": text, "result": f"已播报:{text}"}

    if ctype == "recheck_station":
        sid = str(params.get("station_id", ""))
        wp = station_to_waypoint(sid, stations_cfg)
        if wp is None:
            return {"unsupported": f"工位 {sid} 未在 stations.yaml 配置 waypoint,无法导航"}
        data = json.dumps({"station_id": sid, "waypoint": wp}, ensure_ascii=False)
        return {"topic_key": "recheck_topic", "data": data, "result": f"已发起到 {sid} 的复核导航"}

    if ctype == "generate_report":
        rtype = str(params.get("report_type", "periodic_summary"))
        return {"topic_key": "request_report_topic", "data": rtype, "result": f"已触发报告生成:{rtype}"}

    return {"unsupported": f"机器人侧暂未接入命令类型:{ctype}"}
