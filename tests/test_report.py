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

from inspection_manager.events import Evidence, HazardEvent  # noqa: E402
from inspection_manager.report import (  # noqa: E402
    CloudReportBackend,
    MockReportBackend,
    RateLimiter,
    ReportRequest,
    acceptance_verdict,
    build_report_prompt,
    expired_report_files,
    make_report_backend,
    worst_severity,
)


def event(station, severity, summary="x", image=""):
    return HazardEvent(
        event_id=f"e-{station}", timestamp="t", station_id=station, source="thermal",
        event_type="thermal_risk", severity=severity, confidence=0.9, summary=summary,
        evidence=Evidence(image_path=image),
    )


class HelperTests(unittest.TestCase):
    def test_worst_severity(self):
        events = [event("d1", "info"), event("d2", "critical"), event("d3", "warning")]
        self.assertEqual(worst_severity(events), "critical")

    def test_acceptance_verdict_mapping(self):
        self.assertEqual(acceptance_verdict("info"), "合格")

    def test_expired_report_files(self):
        now = 1_000_000.0
        day = 86400.0
        entries = [("old.md", now - 40 * day), ("recent.md", now - 3 * day), ("edge.md", now - 30 * day)]
        # 30-day window: only 'old' (40d) is strictly older than 30d
        self.assertEqual(expired_report_files(entries, now, 30 * day), ["old.md"])
        # disabled (0) keeps everything
        self.assertEqual(expired_report_files(entries, now, 0), [])
        self.assertEqual(acceptance_verdict("warning"), "需整理")
        self.assertEqual(acceptance_verdict("critical"), "存在安全隐患")


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_max_in_window(self):
        rl = RateLimiter(max_calls=2, window_sec=10.0)
        self.assertTrue(rl.allow(now=0.0))
        self.assertTrue(rl.allow(now=1.0))
        self.assertFalse(rl.allow(now=2.0))  # third within window blocked

    def test_window_slides_and_frees_slot(self):
        rl = RateLimiter(max_calls=1, window_sec=10.0)
        self.assertTrue(rl.allow(now=0.0))
        self.assertFalse(rl.allow(now=5.0))
        self.assertTrue(rl.allow(now=11.0))  # first call aged out


class MockReportTests(unittest.TestCase):
    def test_generates_markdown_with_verdict_and_events(self):
        req = ReportRequest(
            report_type="post_class_acceptance",
            events=[event("desk-01", "warning", "导线散落"), event("desk-02", "critical", "电烙铁未断电")],
            briefs=["desk-01 桌面有导线", "desk-02 电烙铁高温"],
            title="课后验收-A101",
        )
        result = MockReportBackend().generate(req)
        self.assertEqual(result.severity, "critical")
        self.assertEqual(result.verdict, "存在安全隐患")
        self.assertIn("课后验收-A101", result.body_markdown)
        self.assertIn("desk-02", result.body_markdown)
        self.assertIn("电烙铁高温", result.body_markdown)
        self.assertEqual(result.event_ids, ["e-desk-01", "e-desk-02"])


class CloudReportWiringTests(unittest.TestCase):
    def test_calls_client_with_prompt_and_evidence_images(self):
        class FakeCloud:
            def __init__(self):
                self.prompt = None
                self.images = None

            def complete(self, prompt, images):
                self.prompt = prompt
                self.images = images
                return "# 云端报告\n所有工位已复核。"

        client = FakeCloud()
        backend = CloudReportBackend(client=client)
        req = ReportRequest(
            report_type="multi_image_synthesis",
            events=[event("desk-01", "critical", "高温", image="/ev/a.jpg")],
        )
        result = backend.generate(req)
        self.assertIn("desk-01", client.prompt)
        self.assertEqual(client.images, ["/ev/a.jpg"])
        self.assertIn("云端报告", result.body_markdown)
        self.assertEqual(result.severity, "critical")


class PromptAndFactoryTests(unittest.TestCase):
    def test_prompt_lists_each_event_and_brief(self):
        req = ReportRequest(
            report_type="periodic_summary",
            events=[event("desk-07", "warning", "插排过热")],
            briefs=["desk-07 插排温度偏高"],
        )
        prompt = build_report_prompt(req)
        self.assertIn("desk-07", prompt)
        self.assertIn("插排过热", prompt)
        self.assertIn("插排温度偏高", prompt)

    def test_make_mock_backend_and_unknown_raises(self):
        self.assertIsInstance(make_report_backend("mock"), MockReportBackend)
        with self.assertRaises(ValueError):
            make_report_backend("gemini")


if __name__ == "__main__":
    unittest.main()
