"""Layer 3 — on-demand cloud report layer.

Aggregates one or more hazard events (+ Layer 2 briefs) into a structured report:
post-class desk acceptance (课后验收), multi-image synthesis, an uncertain-event
follow-up, or a periodic summary. Reached only on demand (escalation flag /
periodic request) and rate-limited so it stays a small fraction of traffic.

Pluggable backend:
  * ``MockReportBackend`` — deterministic template report (no model). Demo-ready, testable.
  * ``CloudReportBackend`` — calls an injected cloud multimodal client (Claude). The
    wiring is unit-tested with a fake client; the real client is added in Phase C
    (via the claude-api skill + API key).

Pure stdlib; no ROS, no model dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from .events import HazardEvent, severity_rank

REPORT_TYPES = (
    "post_class_acceptance",
    "multi_image_synthesis",
    "uncertain_followup",
    "periodic_summary",
)

# Post-class desk acceptance verdict (design doc: 合格 / 需整理 / 存在安全隐患).
_ACCEPTANCE_VERDICT = {"info": "合格", "warning": "需整理", "critical": "存在安全隐患"}


@dataclass
class ReportRequest:
    report_type: str
    events: List[HazardEvent]
    briefs: List[str] = field(default_factory=list)  # Layer 2 explanations
    title: str = ""


@dataclass
class ReportResult:
    title: str
    body_markdown: str
    severity: str
    verdict: str
    event_ids: List[str] = field(default_factory=list)


class ReportBackend(Protocol):
    def generate(self, request: ReportRequest) -> ReportResult:
        ...


@dataclass
class RateLimiter:
    """Pure sliding-window limiter; the caller passes a monotonic ``now``."""

    max_calls: int
    window_sec: float
    _stamps: List[float] = field(default_factory=list)

    def allow(self, now: float) -> bool:
        self._stamps = [t for t in self._stamps if now - t < self.window_sec]
        if len(self._stamps) >= self.max_calls:
            return False
        self._stamps.append(now)
        return True


def worst_severity(events: List[HazardEvent]) -> str:
    worst = "info"
    for e in events:
        if severity_rank(e.severity) > severity_rank(worst):
            worst = e.severity
    return worst


def acceptance_verdict(severity: str) -> str:
    return _ACCEPTANCE_VERDICT.get(severity, "需整理")


def build_report_prompt(request: ReportRequest) -> str:
    """Assemble the cloud-model prompt from aggregated events + briefs (pure)."""
    lines = [
        "你是电子实验室巡检系统的云端汇总助手。请根据下面多条告警与本地说明，",
        f"生成一份「{request.report_type}」结构化报告（中文，Markdown）。",
        "",
    ]
    for i, e in enumerate(request.events):
        brief = request.briefs[i] if i < len(request.briefs) else ""
        lines.append(
            f"- 工位 {e.station_id} | {e.event_type} | {e.severity} | {e.summary} | 本地说明: {brief}"
        )
    return "\n".join(lines)


class MockReportBackend:
    """Deterministic template report (no model). Demo-ready and testable."""

    def generate(self, request: ReportRequest) -> ReportResult:
        severity = worst_severity(request.events)
        verdict = acceptance_verdict(severity)
        title = request.title or f"巡检报告 ({request.report_type})"
        lines = [f"# {title}", "", f"**总体结论**: {verdict}（最高严重度 {severity}）", ""]
        for i, e in enumerate(request.events):
            brief = request.briefs[i] if i < len(request.briefs) else ""
            lines.append(f"- **{e.station_id}** [{e.severity}] {e.summary}")
            if brief:
                lines.append(f"  - 本地说明: {brief}")
        return ReportResult(
            title=title,
            body_markdown="\n".join(lines),
            severity=severity,
            verdict=verdict,
            event_ids=[e.event_id for e in request.events],
        )


class CloudClient(Protocol):
    def complete(self, prompt: str, images: List[str]) -> str:
        ...


class CloudReportBackend:
    """Calls an injected cloud multimodal client (Claude). Real client deferred."""

    def __init__(self, client: CloudClient) -> None:
        self.client = client

    def generate(self, request: ReportRequest) -> ReportResult:
        prompt = build_report_prompt(request)
        images = [e.evidence.image_path for e in request.events if e.evidence.image_path]
        body = self.client.complete(prompt, images)
        severity = worst_severity(request.events)
        return ReportResult(
            title=request.title or f"巡检报告 ({request.report_type})",
            body_markdown=body,
            severity=severity,
            verdict=acceptance_verdict(severity),
            event_ids=[e.event_id for e in request.events],
        )


def make_report_backend(name: str, **kwargs) -> ReportBackend:
    if name == "mock":
        return MockReportBackend()
    if name == "cloud":  # pragma: no cover - needs a real client on-board
        return CloudReportBackend(client=kwargs["client"])
    raise ValueError(f"unknown report backend: {name}")
