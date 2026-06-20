"""Pure rule-based intent parsing: Chinese ASR text -> command {type, params}.

Returns None when no rule matches (caller falls back to the small VLM). No rclpy.
Station ids match the project format desk-0N (see tests/test_command_receiver.py).
"""
from __future__ import annotations

import re
from typing import Dict, Optional

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
