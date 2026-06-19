"""Post-class desk acceptance (课后桌面验收 — design doc feature 6).

Given a per-desk *observation* (booleans derived on-board from detection + thermal:
is the soldering iron off & stowed, power disconnected, wires tidy, no flammables
left, instruments / component boxes returned, desk clear), this evaluates a
checklist into a verdict (合格 / 需整理 / 存在安全隐患) + a problem list, and turns
a non-pass result into a ``desk_messy`` event that flows through the same L2/L3
pipeline (cognition -> voice/recheck/log; report aggregates all desks post-class).

Pure stdlib; the detection that fills the observation is on-board, this logic is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import HazardEvent, severity_rank
from .report import acceptance_verdict


def expand_targets(target: str, stations_cfg: Dict) -> List[str]:
    """Acceptance target -> station list. 'all'/'' => every station in stations.yaml waypoints."""
    if target and target != "all":
        return [target]
    return sorted(set((stations_cfg.get("waypoints") or {}).values()))


@dataclass(frozen=True)
class Check:
    key: str  # observation key
    expect: bool  # the safe/clean expected value
    severity: str  # severity contributed if this check fails
    message: str  # problem text if failed


# Order roughly by risk; missing observation keys are assumed OK (clean).
DEFAULT_CHECKS: List[Check] = [
    Check("soldering_iron_off", True, "critical", "电烙铁未关闭或未归位"),
    Check("power_disconnected", True, "critical", "电源/排插未断开"),
    Check("wires_tidy", True, "warning", "导线杂乱拖拽"),
    Check("no_flammable_left", True, "warning", "遗留纸张/包装等可燃物"),
    Check("instruments_stowed", True, "warning", "仪器设备未归位"),
    Check("component_box_returned", True, "warning", "元器件盒未放回指定区域"),
    Check("desk_clear", True, "warning", "桌面存在散落器件或垃圾"),
]


@dataclass
class DeskAssessment:
    station_id: str
    verdict: str  # 合格 | 需整理 | 存在安全隐患
    severity: str  # info | warning | critical
    problems: List[str] = field(default_factory=list)


def assess_desk(
    station_id: str, observation: Dict[str, bool], checks: List[Check] = DEFAULT_CHECKS
) -> DeskAssessment:
    """Evaluate the acceptance checklist for one desk."""
    problems: List[str] = []
    worst = "info"
    for check in checks:
        value = observation.get(check.key, check.expect)  # missing key = assume OK
        if value != check.expect:
            problems.append(check.message)
            if severity_rank(check.severity) > severity_rank(worst):
                worst = check.severity
    return DeskAssessment(
        station_id=station_id,
        verdict=acceptance_verdict(worst),
        severity=worst,
        problems=problems,
    )


def assessment_to_event(
    assessment: DeskAssessment, event_id: str, timestamp_iso: str
) -> Optional[HazardEvent]:
    """Turn a non-pass desk assessment into a desk_messy event (else None)."""
    if assessment.severity == "info":
        return None
    summary = f"{assessment.verdict}：" + "；".join(assessment.problems)
    return HazardEvent(
        event_id=event_id,
        timestamp=timestamp_iso,
        station_id=assessment.station_id,
        source="camera",
        event_type="desk_messy",
        severity=assessment.severity,
        confidence=1.0,
        summary=summary,
    )
