"""Layer 2 — local cognition.

Turns a Layer 1 hazard event into a short human-readable explanation plus
remediation suggestions, and decides what is handled locally vs escalated to the
cloud (Layer 3).

Pluggable backend (``CognitionBackend`` protocol):
  * ``MockCognitionBackend`` — deterministic rule/template, no model. Demo-ready
    and fully unit-tested.
  * ``LocalVLMBackend`` — assembles a prompt, calls an injected VLM *client*, and
    parses the reply. The wiring is unit-tested with a fake client; only the real
    client (a small local VLM over HTTP/Ollama) is deferred to on-board work.

Pure stdlib; no ROS, no model dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from .escalation import EscalationPolicy
from .events import HazardEvent

# Per-event-type Chinese remediation hint used by the mock backend / prompt.
_ADVICE = {
    "thermal_risk": "建议复核温度并提醒在场人员处理",
    "desk_messy": "建议提醒该工位学生整理桌面",
    "device_missing": "建议核对设备位置并更新记录",
    "estop": "建议立即现场确认并排查急停原因",
    "fault": "建议检查设备状态并记录",
}


@dataclass
class CognitionRequest:
    event: HazardEvent
    station_context: str = ""  # e.g. "课中, 3号工位, 学生在场"
    image_path: str = ""  # evidence RGB crop
    thermal_path: str = ""  # evidence thermal overlay
    needs_report: bool = False  # a report/summary was explicitly requested


@dataclass
class CognitionResult:
    explanation: str
    confirmed_severity: str
    suggested_actions: List[str] = field(default_factory=list)  # "voice"|"recheck"|"aim"|"log"
    escalate_to_cloud: bool = False
    confidence: float = 0.0
    reason: str = ""


class CognitionBackend(Protocol):
    def assess(self, request: CognitionRequest) -> CognitionResult:
        ...


def build_prompt(request: CognitionRequest) -> str:
    """Assemble the local-VLM prompt from the structured event + context (pure)."""
    e = request.event
    advice = _ADVICE.get(e.event_type, "建议复核现场情况")
    lines = [
        "你是电子实验室巡检系统的本地分析助手。根据下面的结构化告警和现场图像，",
        "用一句中文简要说明现场情况，并给出处置建议。",
        "",
        f"工位: {e.station_id or '未知'}",
        f"事件类型: {e.event_type}",
        f"初筛严重度: {e.severity}",
        f"初筛置信度: {e.confidence:.2f}",
        f"初筛摘要: {e.summary}",
        f"现场上下文: {request.station_context or '无'}",
        f"参考处置方向: {advice}",
        "",
        "只输出 JSON，字段为: "
        '{"explanation": str, "severity": "info|warning|critical", '
        '"actions": ["voice"|"recheck"|"aim"|"log"], '
        '"escalate_to_cloud": bool, "confidence": 0-1}',
    ]
    return "\n".join(lines)


class MockCognitionBackend:
    """Deterministic rule/template backend (no model). Demo-ready and testable."""

    def __init__(self, policy: Optional[EscalationPolicy] = None) -> None:
        self.policy = policy or EscalationPolicy()

    def assess(self, request: CognitionRequest) -> CognitionResult:
        e = request.event
        advice = _ADVICE.get(e.event_type, "建议复核现场情况")
        station = e.station_id or "未知工位"
        explanation = (
            f"{station}：{e.summary or e.event_type}"
            f"（严重度 {e.severity}，置信度 {e.confidence:.0%}）。{advice}。"
        )

        actions: List[str] = []
        if e.severity in ("warning", "critical"):
            actions.append("voice")
        if e.event_type == "thermal_risk" and e.severity == "critical":
            actions.append("recheck")
            actions.append("aim")
        actions.append("log")

        confidence = float(e.confidence)
        escalate = self.policy.should_escalate_to_cloud(confidence, request.needs_report)
        return CognitionResult(
            explanation=explanation,
            confirmed_severity=e.severity,
            suggested_actions=actions,
            escalate_to_cloud=escalate,
            confidence=confidence,
            reason="mock: rule-based from L1 event",
        )


def _extract_json(raw: str) -> str:
    """Pull the first {...} JSON object out of a model reply (tolerates fences/prose)."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in model reply")
    return raw[start : end + 1]


def parse_vlm_result(raw: str, fallback_confidence: float = 0.5) -> CognitionResult:
    """Parse a VLM's JSON reply into a CognitionResult (pure, testable)."""
    data = json.loads(_extract_json(raw))
    return CognitionResult(
        explanation=str(data.get("explanation", "")),
        confirmed_severity=str(data.get("severity", "info")),
        suggested_actions=[str(a) for a in data.get("actions", [])],
        escalate_to_cloud=bool(data.get("escalate_to_cloud", False)),
        confidence=float(data.get("confidence", fallback_confidence)),
        reason="local_vlm",
    )


class VLMClient(Protocol):
    def complete(self, prompt: str, images: List[str]) -> str:
        ...


class LocalVLMBackend:
    """Calls an injected local-VLM client and parses its reply.

    The real client (small VLM over HTTP/Ollama) is supplied on-board; the assess
    logic here is unit-tested with a fake client.
    """

    def __init__(self, client: VLMClient, policy: Optional[EscalationPolicy] = None) -> None:
        self.client = client
        self.policy = policy or EscalationPolicy()

    def assess(self, request: CognitionRequest) -> CognitionResult:
        prompt = build_prompt(request)
        images = [p for p in (request.image_path, request.thermal_path) if p]
        raw = self.client.complete(prompt, images)
        result = parse_vlm_result(raw)
        # Policy has the final say if the model didn't already ask for the cloud.
        if not result.escalate_to_cloud:
            result.escalate_to_cloud = self.policy.should_escalate_to_cloud(
                result.confidence, request.needs_report
            )
        return result


def make_backend(name: str, policy: Optional[EscalationPolicy] = None, **kwargs) -> CognitionBackend:
    """Factory used by the node to select a backend by config name."""
    if name == "mock":
        return MockCognitionBackend(policy=policy)
    if name == "local_vlm":  # pragma: no cover - needs a real client on-board
        return LocalVLMBackend(client=kwargs["client"], policy=policy)
    raise ValueError(f"unknown cognition backend: {name}")
