#!/usr/bin/env python3
"""Offline demo of L1.5 TieredCognitionBackend — no model, no ROS.

Feeds sample events through the real TieredCognitionBackend with FAKE fast/deep
backends to show the 3-tier degradation (deep -> fast -> rules) and policy D.

Run: python3 rdk_x5/scripts/tiered_cognition_demo.py
"""
import sys
from dataclasses import replace
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PKG))

import urllib.error  # noqa: E402

from inspection_manager.cognition import (  # noqa: E402
    CognitionRequest,
    CognitionResult,
    TieredCognitionBackend,
    TierPolicy,
)
from inspection_manager.events import HazardEvent  # noqa: E402


class Fake:
    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises

    def assess(self, request):
        if self.raises is not None:
            raise self.raises
        return replace(self.result)


def event(severity, summary):
    return HazardEvent(
        event_id="e", timestamp="2026-06-17T10:00:00+08:00", station_id="desk-03",
        source="thermal", event_type="thermal_risk", severity=severity,
        confidence=0.8, summary=summary,
    )


def result(sev, conf, reason):
    return CognitionResult(
        explanation=f"[{reason}] {sev}", confirmed_severity=sev, suggested_actions=["log"],
        escalate_to_cloud=False, confidence=conf, reason=reason,
    )


def show(title, backend, ev):
    out = backend.assess(CognitionRequest(event=ev))
    print(f"  {title:32s} -> severity={out.confirmed_severity:8s} reason={out.reason}")


def main():
    deep_ok = Fake(result("critical", 0.95, "deep(7B)"))
    deep_off = Fake(raises=urllib.error.URLError("offline"))
    fast_sure = Fake(result("warning", 0.95, "fast(L1.5)"))
    fast_unsure = Fake(result("warning", 0.3, "fast(L1.5)"))
    fast_down = Fake(raises=RuntimeError("model down"))
    policy = TierPolicy()

    print("L1.5 tiered cognition — 3-tier degradation demo\n")
    print("[critical event]")
    show("deep online", TieredCognitionBackend(fast_sure, deep_ok, policy=policy), event("critical", "电烙铁145C"))
    show("deep OFFLINE -> fast", TieredCognitionBackend(fast_sure, deep_off, policy=policy), event("critical", "电烙铁145C"))
    print("\n[warning event]")
    show("fast confident -> local only", TieredCognitionBackend(fast_sure, deep_ok, policy=policy), event("warning", "插排"))
    show("fast unsure -> deep", TieredCognitionBackend(fast_unsure, deep_ok, policy=policy), event("warning", "插排"))
    show("fast unsure + deep OFFLINE", TieredCognitionBackend(fast_unsure, deep_off, policy=policy), event("warning", "插排"))
    show("fast DOWN -> rules fallback", TieredCognitionBackend(fast_down, deep_ok, policy=policy), event("warning", "插排"))


if __name__ == "__main__":
    main()
