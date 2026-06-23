"""Pure command->ROS dispatch logic for the App->robot command channel.

stdlib only, unit-tested (no rclpy). The node (command_receiver_node.py) is a thin
shell: it polls the backend, calls dispatch_command() to decide which ROS topic(s)
to publish and what payload, publishes, then posts a result receipt.

dispatch_command() handles the deterministic types. ``find_item`` needs an async
backend asset lookup, so the node resolves the asset first, then re-dispatches it as
a recheck_station (navigate) or laser_point (laser) — keeping this module pure.

An action is {"topic_key", "kind": "string"|"vector3", "data": str | [pan,tilt,0.0]}.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# types resolved by the node (need a backend lookup) rather than here
NODE_RESOLVED = {"find_item"}


def station_to_waypoint(station_id: str, stations_cfg: Dict[str, Any]) -> Optional[str]:
    """Reverse stations.yaml `waypoints: {wp_desk01: desk-01}` -> waypoint for a station."""
    for wp, sid in (stations_cfg.get("waypoints") or {}).items():
        if sid == station_id:
            return wp
    return None


def all_waypoints(stations_cfg: Dict[str, Any]) -> List[str]:
    return list((stations_cfg.get("waypoints") or {}).keys())


def aim_angle(target: str, gimbal_cfg: Dict[str, Any]) -> Optional[List[float]]:
    """Look up a station_id or location string -> [pan_deg, tilt_deg] from gimbal aim config."""
    angle = (gimbal_cfg.get("aim") or {}).get(target)
    if isinstance(angle, (list, tuple)) and len(angle) >= 2:
        return [float(angle[0]), float(angle[1])]
    return None


def _recheck_action(station_id: str, waypoint: str) -> Dict[str, Any]:
    return {"topic_key": "recheck_topic", "kind": "string",
            "data": json.dumps({"station_id": station_id, "waypoint": waypoint}, ensure_ascii=False)}


def dispatch_command(cmd: Dict[str, Any], stations_cfg: Optional[Dict[str, Any]] = None,
                     gimbal_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map a Command to ROS action(s).

    Returns {"actions": [action...], "result": <receipt text>} or {"unsupported": <reason>}.
    """
    stations_cfg = stations_cfg or {}
    gimbal_cfg = gimbal_cfg or {}
    ctype = cmd.get("type", "")
    params = cmd.get("params") or {}

    if ctype == "voice_prompt":
        text = str(params.get("text", "")).strip()
        if not text:
            return {"unsupported": "voice_prompt 缺 text"}
        return {"actions": [{"topic_key": "voice_topic", "kind": "string", "data": text}],
                "result": f"已播报:{text}"}

    if ctype == "recheck_station":
        sid = str(params.get("station_id", ""))
        wp = station_to_waypoint(sid, stations_cfg)
        if wp is None:
            return {"unsupported": f"工位 {sid} 未在 stations.yaml 配置 waypoint,无法导航"}
        return {"actions": [_recheck_action(sid, wp)], "result": f"已发起到 {sid} 的复核导航"}

    if ctype == "generate_report":
        rtype = str(params.get("report_type", "periodic_summary"))
        return {"actions": [{"topic_key": "request_report_topic", "kind": "string", "data": rtype}],
                "result": f"已触发报告生成:{rtype}"}

    if ctype == "inspection_round":
        wps = all_waypoints(stations_cfg)
        if not wps:
            return {"unsupported": "stations.yaml 未配置 waypoints,无法巡检"}
        actions = [_recheck_action(stations_cfg["waypoints"][wp], wp) for wp in wps]
        return {"actions": actions, "result": f"已发起巡检:依次复核 {len(wps)} 个工位"}

    if ctype == "laser_point":
        target = str(params.get("station_id") or params.get("location") or "")
        angle = aim_angle(target, gimbal_cfg)
        if angle is None:
            return {"unsupported": f"目标 {target!r} 未在云台角度表(gimbal aim)配置,无法指示"}
        # The node runs a timed routine: clear any FAULT, enable, sustain the target so
        # the gimbal slews there (the controller faults if commands stop for >5s), laser
        # on for the indication window, then laser off.
        return {"laser_aim": [angle[0], angle[1]],
                "result": f"激光已指向 {target}(pan={angle[0]},tilt={angle[1]})"}

    if ctype == "acceptance":
        target = str(params.get("station_id", "") or "all")
        return {"actions": [{"topic_key": "acceptance_request_topic", "kind": "string", "data": target}],
                "result": f"已发起课后验收:{target}"}

    if ctype == "voice_control":
        enabled = params.get("enabled")
        if not isinstance(enabled, bool):
            return {"unsupported": "voice_control 需要布尔 params.enabled"}
        return {"actions": [{"topic_key": "voice_control_topic", "kind": "string",
                             "data": json.dumps({"enabled": enabled}, ensure_ascii=False)}],
                "result": "语音监听已开启" if enabled else "语音监听已关闭"}

    if ctype == "set_volume":
        # TTS playback volume 0-100 (the USB speaker has no ALSA volume control, so the
        # node persists the level to a file the TTS daemon reads + applies as gain).
        try:
            level = int(params.get("level"))
        except (TypeError, ValueError):
            level = -1
        if not 0 <= level <= 100:
            return {"unsupported": "set_volume 需要整数 level (0-100)"}
        return {"set_volume": level, "result": f"播报音量已设为 {level}"}

    return {"unsupported": f"机器人侧暂未接入命令类型:{ctype}"}


def find_item_to_command(asset: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Turn a resolved asset (from GET /api/assets) + mode into a re-dispatchable command.

    navigate -> drive to the asset's station (recheck_station, large assets);
    laser    -> point at the asset's location (laser_point; station or location_text).
    """
    if mode == "laser":
        target = asset.get("location_text") or asset.get("station_id") or asset.get("area") or ""
        return {"type": "laser_point", "params": {"location": target}}
    return {"type": "recheck_station", "params": {"station_id": asset.get("station_id", "")}}
