"""Pure Chinese voice-reply phrasing. No rclpy.

Moving commands (recheck/inspection_round) get an honest downgrade suffix because
the chassis PID is not yet wired — we do not pretend the robot has arrived.
"""
from __future__ import annotations

from typing import Dict

_MOVING = {"recheck_station", "inspection_round"}
_NOT_UNDERSTOOD = "抱歉,没太听清,可以说『去三号桌复核』『激光指示二号桌』这样的指令"


def wake_ack(text: str = "我在") -> str:
    return text


def not_understood() -> str:
    return _NOT_UNDERSTOOD


def reply_for(cmd_type: str, plan: Dict) -> str:
    if "unsupported" in plan:
        return f"抱歉,{plan['unsupported']}"
    result = plan.get("result", "好的")
    if cmd_type in _MOVING:
        return f"{result};底盘移动还在调试,稍后执行"
    return result
