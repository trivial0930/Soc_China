import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5"
    / "ros2_ws"
    / "src"
    / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.escalation import EscalationPolicy, policy_from_dict  # noqa: E402
from inspection_manager.events import HazardEvent  # noqa: E402


def event(severity="warning", confidence=0.9):
    return HazardEvent(
        event_id="e", timestamp="t", station_id="desk-01", source="thermal",
        event_type="thermal_risk", severity=severity, confidence=confidence,
    )


class Gate1CognitionTests(unittest.TestCase):
    def setUp(self):
        self.policy = EscalationPolicy(
            min_severity_for_cognition="warning", min_confidence_for_cognition=0.3
        )

    def test_info_event_is_dropped(self):
        self.assertFalse(self.policy.should_cognize(event(severity="info")))

    def test_warning_and_critical_pass(self):
        self.assertTrue(self.policy.should_cognize(event(severity="warning")))
        self.assertTrue(self.policy.should_cognize(event(severity="critical")))

    def test_low_confidence_is_dropped(self):
        self.assertFalse(self.policy.should_cognize(event(confidence=0.1)))


class Gate2CloudTests(unittest.TestCase):
    def setUp(self):
        self.policy = EscalationPolicy(
            cloud_on_uncertain=True, uncertain_below_confidence=0.45
        )

    def test_needs_report_always_escalates(self):
        self.assertTrue(self.policy.should_escalate_to_cloud(confidence=0.99, needs_report=True))

    def test_uncertain_escalates(self):
        self.assertTrue(self.policy.should_escalate_to_cloud(confidence=0.30))

    def test_confident_non_report_stays_local(self):
        # Urgent/confident events are handled locally, not auto-sent to cloud.
        self.assertFalse(self.policy.should_escalate_to_cloud(confidence=0.95))

    def test_uncertain_disabled(self):
        policy = EscalationPolicy(cloud_on_uncertain=False, uncertain_below_confidence=0.45)
        self.assertFalse(policy.should_escalate_to_cloud(confidence=0.10))


class PolicyFromDictTests(unittest.TestCase):
    def test_reads_escalation_section_with_defaults(self):
        cfg = {"escalation": {"min_severity_for_cognition": "critical", "uncertain_below_confidence": 0.6}}
        policy = policy_from_dict(cfg)
        self.assertEqual(policy.min_severity_for_cognition, "critical")
        self.assertEqual(policy.uncertain_below_confidence, 0.6)
        # untouched key keeps its default
        self.assertTrue(policy.cloud_on_uncertain)

    def test_empty_dict_yields_defaults(self):
        self.assertEqual(policy_from_dict({}), EscalationPolicy())


if __name__ == "__main__":
    unittest.main()
