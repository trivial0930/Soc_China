"""Pure rule-based intent parsing: Chinese ASR text -> command {type, params}.

Returns None when no rule matches (caller falls back to the small VLM). No rclpy.
Station ids match the project format desk-0N (see tests/test_command_receiver.py).
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, Optional

_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str) -> Optional[int]:
    """十/十二/二十/二十三 等简单中文数字 -> int(覆盖 1..99,够工位用)。"""
    if "十" not in s:
        if len(s) == 1 and s in _CN_DIGIT:
            return _CN_DIGIT[s]
        return None
    tens, _, ones = s.partition("十")
    t = _CN_DIGIT.get(tens, 1) if tens else 1
    o = _CN_DIGIT.get(ones, 0) if ones else 0
    return t * 10 + o


def parse_station_id(text: str, station_fmt: str = "desk-{:02d}") -> Optional[str]:
    m = re.search(r"(\d{1,2})\s*(?:号|桌|台|工位|号位)", text)
    if m:
        return station_fmt.format(int(m.group(1)))
    m = re.search(r"([零一二两三四五六七八九十]{1,3})\s*号", text)
    if m:
        n = _cn_to_int(m.group(1))
        if n is not None:
            return station_fmt.format(n)
    return None


def parse_intent(text: str, station_fmt: str = "desk-{:02d}") -> Optional[Dict]:
    t = text.strip()
    if not t:
        return None

    # voice_prompt:播报/说/提醒 + 文本(优先抓取,文本随意)
    m = re.search(r"(?:播报|广播|提醒大家|说一句|喊话)[:：]?\s*(.+)$", t)
    if m and m.group(1).strip():
        return {"type": "voice_prompt", "params": {"text": m.group(1).strip()}}

    # generate_report
    if re.search(r"(生成|导出|汇总|出具).*(报告)", t) or "巡检报告" in t:
        return {"type": "generate_report", "params": {"report_type": "periodic_summary"}}

    # acceptance
    if "验收" in t:
        if re.search(r"全部|所有|全场", t):
            return {"type": "acceptance", "params": {"station_id": "all"}}
        sid = parse_station_id(t)
        return {"type": "acceptance", "params": {"station_id": sid or "all"}}

    # laser_point
    if re.search(r"激光|指一?下|照一?下|指示", t):
        sid = parse_station_id(t)
        if sid:
            return {"type": "laser_point", "params": {"station_id": sid}}

    # inspection_round
    if re.search(r"(全面|综合|挨个|开始).*巡检|巡检一圈|巡逻", t):
        return {"type": "inspection_round", "params": {}}

    # recheck_station
    if re.search(r"复核|去看|看看|检查|过去|前往", t):
        sid = parse_station_id(t)
        if sid:
            return {"type": "recheck_station", "params": {"station_id": sid}}

    return None


_ALLOWED_TYPES = {"voice_prompt", "recheck_station", "inspection_round",
                  "laser_point", "acceptance", "generate_report"}

INTENT_SCHEMA_PROMPT = (
    "你是实验室巡检机器人的语音指令解析器。把用户的话解析成一个 JSON 命令,"
    "只输出 JSON,不要解释。命令格式:{\"type\": <类型>, \"params\": {...}, \"confidence\": 0~1}。"
    "类型枚举与参数:"
    "voice_prompt{text};recheck_station{station_id};inspection_round{};"
    "laser_point{station_id};acceptance{station_id 或 \"all\"};generate_report{report_type}。"
    "station_id 形如 desk-03。听不懂就给低 confidence。用户说:"
)


def vlm_fallback(text: str, chat_fn: "Callable[[str], str]", min_conf: float = 0.5) -> Optional[Dict]:
    try:
        raw = chat_fn(INTENT_SCHEMA_PROMPT + text)
    except Exception:  # noqa: BLE001 - model offline/timeout -> give up
        return None
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if obj.get("type") not in _ALLOWED_TYPES:
        return None
    if float(obj.get("confidence", 0.0)) < min_conf:
        return None
    return {"type": obj["type"], "params": obj.get("params") or {}}
