import sys
import unittest
import urllib.error
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.cognition import TierPolicy, tier_policy_from_dict  # noqa: E402
from inspection_manager.cognition import (  # noqa: E402
    CognitionRequest,
    CognitionResult,
    TieredCognitionBackend,
)
from inspection_manager.events import HazardEvent  # noqa: E402
from inspection_manager.config import tier_settings_from_dict  # noqa: E402


class TierPolicyTests(unittest.TestCase):
    def test_defaults(self):
        p = TierPolicy()
        self.assertEqual(p.escalate_below_confidence, 0.6)
        self.assertTrue(p.critical_always_deep)
        self.assertTrue(p.escalate_if_fast_critical)

    def test_from_dict_reads_values(self):
        p = tier_policy_from_dict(
            {"escalate_below_confidence": 0.4, "critical_always_deep": False,
             "escalate_if_fast_critical": False}
        )
        self.assertEqual(p.escalate_below_confidence, 0.4)
        self.assertFalse(p.critical_always_deep)
        self.assertFalse(p.escalate_if_fast_critical)

    def test_from_dict_tolerates_none_and_missing(self):
        p = tier_policy_from_dict(None)
        self.assertEqual(p.escalate_below_confidence, 0.6)
        self.assertTrue(p.critical_always_deep)


def _event(severity="warning"):
    return HazardEvent(
        event_id="e1", timestamp="2026-06-17T10:00:00+08:00", station_id="desk-03",
        source="thermal", event_type="thermal_risk", severity=severity,
        confidence=0.8, summary="检测到电烙铁",
    )


def _result(sev="warning", conf=0.9, reason="x"):
    return CognitionResult(
        explanation="e", confirmed_severity=sev, suggested_actions=["log"],
        escalate_to_cloud=False, confidence=conf, reason=reason,
    )


class FakeBackend:
    """Injectable CognitionBackend: returns a fixed result, or raises, and counts calls."""
    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls = 0

    def assess(self, request):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.result


class TieredAssessTests(unittest.TestCase):
    def _req(self, severity="warning"):
        return CognitionRequest(event=_event(severity))

    def test_critical_uses_deep_when_online_and_skips_fast(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("critical"))
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)
        self.assertEqual(fast.calls, 0)  # deep online -> fast not run

    def test_critical_falls_back_to_fast_when_deep_offline(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(raises=urllib.error.URLError("offline"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("critical"))
        self.assertEqual(fast.calls, 1)
        self.assertIn("L2 offline", out.reason)

    def test_noncritical_confident_uses_only_fast(self):
        fast = FakeBackend(_result(conf=0.95, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertEqual(out.reason, "fast")
        self.assertEqual(deep.calls, 0)  # confident -> no escalation

    def test_noncritical_uncertain_escalates_to_deep(self):
        fast = FakeBackend(_result(conf=0.3, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)

    def test_noncritical_uncertain_deep_offline_keeps_fast(self):
        fast = FakeBackend(_result(conf=0.3, reason="fast"))
        deep = FakeBackend(raises=urllib.error.URLError("offline"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))
        self.assertIn("L2 offline", out.reason)
        self.assertEqual(fast.calls, 1)
        self.assertEqual(deep.calls, 1)

    def test_escalate_if_fast_says_critical(self):
        fast = FakeBackend(_result(sev="critical", conf=0.95, reason="fast"))
        deep = FakeBackend(_result(reason="deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("warning"))  # L1 said warning; fast upgraded to critical
        self.assertEqual(out.reason, "deep")
        self.assertEqual(deep.calls, 1)

    def test_fast_failure_degrades_to_rules_fallback(self):
        fast = FakeBackend(raises=RuntimeError("model down"))
        fallback = FakeBackend(_result(reason="rules"))
        b = TieredCognitionBackend(fast=fast, deep=None, fallback=fallback)
        out = b.assess(self._req("warning"))
        self.assertEqual(fallback.calls, 1)
        self.assertIn("rules", out.reason)

    def test_no_deep_configured_uses_fast_even_for_critical(self):
        fast = FakeBackend(_result(reason="fast"))
        b = TieredCognitionBackend(fast=fast, deep=None)
        out = b.assess(self._req("critical"))
        self.assertEqual(out.reason, "fast")

    def test_deep_non_offline_error_does_not_propagate(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(raises=RuntimeError("buggy deep response"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        out = b.assess(self._req("critical"))  # must NOT raise
        self.assertIsInstance(out, CognitionResult)
        self.assertEqual(fast.calls, 1)  # degraded to fast

    def test_default_fallback_is_mock(self):
        fast = FakeBackend(raises=RuntimeError("down"))
        b = TieredCognitionBackend(fast=fast)  # no fallback -> MockCognitionBackend
        out = b.assess(self._req("warning"))  # must still return a result, not raise
        self.assertIsInstance(out, CognitionResult)
        self.assertEqual(fast.calls, 1)
        self.assertIn("rules fallback", out.reason)

    def test_unexpected_deep_error_is_logged(self):
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(raises=RuntimeError("buggy deep"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        with self.assertLogs("inspection_manager.cognition", level="WARNING") as cm:
            out = b.assess(self._req("critical"))  # still must not raise
        self.assertIsInstance(out, CognitionResult)
        self.assertTrue(any("deep backend error" in m for m in cm.output))

    def test_offline_deep_not_logged_as_warning(self):
        import urllib.error
        fast = FakeBackend(_result(reason="fast"))
        deep = FakeBackend(raises=urllib.error.URLError("offline"))
        b = TieredCognitionBackend(fast=fast, deep=deep)
        with self.assertNoLogs("inspection_manager.cognition", level="WARNING"):
            b.assess(self._req("critical"))  # offline is expected -> no warning


class TierSettingsTests(unittest.TestCase):
    def test_reads_fast_deep_and_policy(self):
        cfg = {
            "backend": "tiered",
            "tier": {
                "fast": {"vlm_model": "qwen2-vl:2b", "vlm_base_url": "http://localhost:8080/v1"},
                "deep": {"vlm_model": "qwen2.5vl:7b", "vlm_base_url": "http://192.168.128.100:11434/v1"},
                "policy": {"escalate_below_confidence": 0.5},
            },
        }
        s = tier_settings_from_dict(cfg)
        self.assertEqual(s["fast_model"], "qwen2-vl:2b")
        self.assertEqual(s["fast_base_url"], "http://localhost:8080/v1")
        self.assertEqual(s["deep_base_url"], "http://192.168.128.100:11434/v1")
        self.assertEqual(s["policy"].escalate_below_confidence, 0.5)
        # send_image defaults: L1.5 (fast) text-only, L2 (deep) sees the image.
        self.assertFalse(s["fast_send_image"])
        self.assertTrue(s["deep_send_image"])

    def test_send_image_flags_are_configurable(self):
        cfg = {"tier": {"fast": {"send_image": True}, "deep": {"send_image": False}}}
        s = tier_settings_from_dict(cfg)
        self.assertTrue(s["fast_send_image"])
        self.assertFalse(s["deep_send_image"])

    def test_missing_deep_means_empty_base_url(self):
        s = tier_settings_from_dict({"tier": {"fast": {"vlm_model": "m"}}})
        self.assertEqual(s["deep_base_url"], "")  # -> node builds no deep backend

    def test_tolerates_empty_cfg(self):
        s = tier_settings_from_dict({})
        self.assertIn("fast_base_url", s)
        self.assertEqual(s["deep_base_url"], "")


if __name__ == "__main__":
    unittest.main()
