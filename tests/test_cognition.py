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

from inspection_manager.cognition import (  # noqa: E402
    CognitionRequest,
    LocalVLMBackend,
    MockCognitionBackend,
    build_prompt,
    make_backend,
    parse_vlm_result,
)
from inspection_manager.escalation import EscalationPolicy  # noqa: E402
from inspection_manager.events import HazardEvent  # noqa: E402


def request(severity="critical", event_type="thermal_risk", confidence=0.9, needs_report=False):
    event = HazardEvent(
        event_id="e", timestamp="t", station_id="desk-03", source="thermal",
        event_type=event_type, severity=severity, confidence=confidence,
        summary="soldering_iron active 145C",
    )
    return CognitionRequest(event=event, station_context="课中, 学生在场", needs_report=needs_report)


class FakeVLMClient:
    def __init__(self, reply):
        self.reply = reply
        self.last_prompt = None
        self.last_images = None

    def complete(self, prompt, images):
        self.last_prompt = prompt
        self.last_images = images
        return self.reply


class MockBackendTests(unittest.TestCase):
    def setUp(self):
        self.backend = MockCognitionBackend(policy=EscalationPolicy(uncertain_below_confidence=0.45))

    def test_explanation_mentions_station_and_summary(self):
        result = self.backend.assess(request())
        self.assertIn("desk-03", result.explanation)
        self.assertIn("soldering_iron", result.explanation)

    def test_critical_thermal_suggests_voice_recheck_aim_log(self):
        result = self.backend.assess(request(severity="critical"))
        self.assertEqual(result.suggested_actions, ["voice", "recheck", "aim", "log"])

    def test_warning_suggests_voice_and_log_only(self):
        result = self.backend.assess(request(severity="warning"))
        self.assertEqual(result.suggested_actions, ["voice", "log"])

    def test_confident_event_stays_local(self):
        result = self.backend.assess(request(confidence=0.9))
        self.assertFalse(result.escalate_to_cloud)

    def test_uncertain_event_escalates(self):
        result = self.backend.assess(request(confidence=0.2))
        self.assertTrue(result.escalate_to_cloud)

    def test_report_request_escalates_even_when_confident(self):
        result = self.backend.assess(request(confidence=0.99, needs_report=True))
        self.assertTrue(result.escalate_to_cloud)


class PromptTests(unittest.TestCase):
    def test_prompt_includes_event_fields_and_json_instruction(self):
        prompt = build_prompt(request())
        self.assertIn("desk-03", prompt)
        self.assertIn("thermal_risk", prompt)
        self.assertIn("soldering_iron", prompt)
        self.assertIn("JSON", prompt)


class VLMBackendTests(unittest.TestCase):
    def test_parses_clean_json_reply(self):
        raw = '{"explanation": "现场有高温电烙铁", "severity": "critical", "actions": ["voice","aim"], "escalate_to_cloud": false, "confidence": 0.88}'
        result = parse_vlm_result(raw)
        self.assertEqual(result.confirmed_severity, "critical")
        self.assertEqual(result.suggested_actions, ["voice", "aim"])
        self.assertAlmostEqual(result.confidence, 0.88)

    def test_tolerates_prose_and_code_fences_around_json(self):
        raw = 'Sure!\n```json\n{"explanation":"x","severity":"warning","actions":["log"],"confidence":0.6}\n```\n'
        result = parse_vlm_result(raw)
        self.assertEqual(result.confirmed_severity, "warning")

    def test_backend_calls_client_with_prompt_and_images(self):
        client = FakeVLMClient('{"explanation":"x","severity":"warning","actions":["log"],"confidence":0.7}')
        backend = LocalVLMBackend(client=client, policy=EscalationPolicy())
        req = request()
        req.image_path = "/ev/a.jpg"
        req.thermal_path = "/ev/a_thermal.jpg"
        result = backend.assess(req)
        self.assertIn("desk-03", client.last_prompt)
        self.assertEqual(client.last_images, ["/ev/a.jpg", "/ev/a_thermal.jpg"])
        self.assertEqual(result.confirmed_severity, "warning")

    def test_policy_overrides_escalation_when_model_uncertain(self):
        # Model says don't escalate, but confidence is low and policy says escalate.
        client = FakeVLMClient('{"explanation":"x","severity":"warning","actions":["log"],"escalate_to_cloud":false,"confidence":0.1}')
        backend = LocalVLMBackend(client=client, policy=EscalationPolicy(uncertain_below_confidence=0.45))
        result = backend.assess(request())
        self.assertTrue(result.escalate_to_cloud)


class FactoryTests(unittest.TestCase):
    def test_make_mock_backend(self):
        self.assertIsInstance(make_backend("mock"), MockCognitionBackend)

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            make_backend("gpt5")


if __name__ == "__main__":
    unittest.main()
