import base64
import os
import sys
import tempfile
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

from inspection_manager.cognition import CognitionRequest, LocalVLMBackend  # noqa: E402
from inspection_manager.events import HazardEvent  # noqa: E402
from inspection_manager.qwen_client import (  # noqa: E402
    DASHSCOPE_OPENAI_BASE,
    build_messages,
    encode_image,
    ollama_vlm_client,
    qwen_cloud_client,
)
from inspection_manager.report import CloudReportBackend, ReportRequest  # noqa: E402


class EncodeTests(unittest.TestCase):
    def test_encode_image_produces_data_uri(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            fh.write(b"\xff\xd8\xff\xd9")  # tiny fake jpeg bytes
            path = fh.name
        try:
            uri = encode_image(path)
            self.assertTrue(uri.startswith("data:image/jpeg;base64,"))
            self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), b"\xff\xd8\xff\xd9")
        finally:
            os.unlink(path)


class BuildMessagesTests(unittest.TestCase):
    def test_text_then_image_parts(self):
        msgs = build_messages("说明这张图", ["data:image/jpeg;base64,AAA"])
        self.assertEqual(msgs[0]["role"], "user")
        parts = msgs[0]["content"]
        self.assertEqual(parts[0], {"type": "text", "text": "说明这张图"})
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertEqual(parts[1]["image_url"]["url"], "data:image/jpeg;base64,AAA")


class ClientTests(unittest.TestCase):
    def test_cloud_client_assembles_and_calls_transport(self):
        captured = {}

        def fake_transport(messages, model):
            captured["messages"] = messages
            captured["model"] = model
            return "ok"

        client = qwen_cloud_client(
            api_key="sk-x", transport=fake_transport, encode=lambda p: f"uri:{p}"
        )
        out = client.complete("分析", ["/ev/a.jpg", "/ev/b.jpg"])
        self.assertEqual(out, "ok")
        self.assertEqual(captured["model"], "qwen3-vl-plus")
        self.assertEqual(client.base_url, DASHSCOPE_OPENAI_BASE)
        urls = [p["image_url"]["url"] for p in captured["messages"][0]["content"][1:]]
        self.assertEqual(urls, ["uri:/ev/a.jpg", "uri:/ev/b.jpg"])

    def test_ollama_client_defaults(self):
        client = ollama_vlm_client(transport=lambda m, model: "x")
        self.assertEqual(client.model, "qwen3-vl:8b")
        self.assertIn("11434", client.base_url)


class IntegrationWithBackendsTests(unittest.TestCase):
    """Real backends + Qwen clients (fake transport) -> end-to-end, no key needed."""

    def test_local_vlm_backend_with_ollama_client(self):
        reply = '{"explanation":"现场有高温电烙铁","severity":"critical","actions":["voice","aim"],"confidence":0.9}'
        client = ollama_vlm_client(transport=lambda m, model: reply, encode=lambda p: "uri")
        backend = LocalVLMBackend(client=client)
        event = HazardEvent(
            event_id="e", timestamp="t", station_id="desk-03", source="thermal",
            event_type="thermal_risk", severity="critical", confidence=0.9, summary="s",
        )
        result = backend.assess(CognitionRequest(event=event, image_path="/ev/a.jpg"))
        self.assertEqual(result.confirmed_severity, "critical")
        self.assertIn("aim", result.suggested_actions)

    def test_cloud_report_backend_with_qwen_client(self):
        client = qwen_cloud_client(
            api_key="sk", transport=lambda m, model: "# 报告\n所有工位已复核", encode=lambda p: "uri"
        )
        backend = CloudReportBackend(client=client)
        event = HazardEvent(
            event_id="e", timestamp="t", station_id="desk-03", source="thermal",
            event_type="thermal_risk", severity="warning", confidence=0.5, summary="s",
        )
        report = backend.generate(ReportRequest(report_type="uncertain_followup", events=[event]))
        self.assertIn("报告", report.body_markdown)
        self.assertEqual(report.severity, "warning")


if __name__ == "__main__":
    unittest.main()
