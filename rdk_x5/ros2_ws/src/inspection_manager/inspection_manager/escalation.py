"""Escalation policy: the two gates of the three-layer decision pipeline.

Gate 1 (L1 -> L2): which Layer 1 events deserve Layer 2 cognition. Layer 1 already
throttles /hazard/events to warning/critical, so this mostly enforces a severity
and confidence floor (and can drop noisy low-confidence events).

Gate 2 (L2 -> L3): when a Layer 2 result must rise to the cloud report layer.
Per the design doc, urgent events are handled LOCALLY for fast response; the cloud
is reached only for (a) report generation / periodic or post-class summaries
(``needs_report``) or (b) when the local model is not confident enough.

Pure functions; thresholds come from config (escalation section of cognition.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass

from .events import HazardEvent, severity_rank


@dataclass(frozen=True)
class EscalationPolicy:
    # Gate 1 (L1 -> L2)
    min_severity_for_cognition: str = "warning"
    min_confidence_for_cognition: float = 0.0
    # Gate 2 (L2 -> L3)
    cloud_on_uncertain: bool = True
    uncertain_below_confidence: float = 0.45

    def should_cognize(self, event: HazardEvent) -> bool:
        """Gate 1: does this Layer 1 event warrant Layer 2 cognition?"""
        return (
            severity_rank(event.severity)
            >= severity_rank(self.min_severity_for_cognition)
            and float(event.confidence) >= self.min_confidence_for_cognition
        )

    def should_escalate_to_cloud(
        self, confidence: float, needs_report: bool = False
    ) -> bool:
        """Gate 2: should the Layer 2 result rise to the cloud report layer?

        Not severity-driven: urgent events are handled locally. Cloud is reached
        only for explicit report requests or when the local model is uncertain.
        """
        if needs_report:
            return True
        if self.cloud_on_uncertain and float(confidence) < self.uncertain_below_confidence:
            return True
        return False


def policy_from_dict(cfg: dict) -> EscalationPolicy:
    """Build an EscalationPolicy from the 'escalation' section of a config dict."""
    spec = (cfg or {}).get("escalation") or {}
    defaults = EscalationPolicy()
    return EscalationPolicy(
        min_severity_for_cognition=str(
            spec.get("min_severity_for_cognition", defaults.min_severity_for_cognition)
        ),
        min_confidence_for_cognition=float(
            spec.get("min_confidence_for_cognition", defaults.min_confidence_for_cognition)
        ),
        cloud_on_uncertain=bool(spec.get("cloud_on_uncertain", defaults.cloud_on_uncertain)),
        uncertain_below_confidence=float(
            spec.get("uncertain_below_confidence", defaults.uncertain_below_confidence)
        ),
    )
