import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import ingest  # noqa: E402


class IngestTest(unittest.TestCase):
    def test_normalize_event_from_hazardevent(self):
        out = ingest.normalize_event({
            "event_id": "e1", "timestamp": "t", "station_id": "d3", "source": "thermal",
            "event_type": "thermal_risk", "severity": "warning", "confidence": 0.8, "summary": "s",
            "evidence": {"image_path": "/root/ev/e1_warning.jpg"},
            "action": {"voice_prompt": "p", "reported_to_admin": True}})
        self.assertEqual(out["image"], "e1_warning.jpg")
        self.assertEqual(out["action"]["voice_prompt"], "p")
        self.assertEqual(out["confidence"], 0.8)

    def test_normalize_event_accepts_rewritten_image_field(self):
        out = ingest.normalize_event({"event_id": "e", "image": "already.jpg"})
        self.assertEqual(out["image"], "already.jpg")

    def test_normalize_brief_extracts_event_id(self):
        out = ingest.normalize_brief({"event": {"event_id": "e9"}, "explanation": "x",
                                      "confirmed_severity": "info", "actions": ["log"]})
        self.assertEqual(out["event_id"], "e9")
        self.assertEqual(out["actions"], ["log"])

    def test_normalize_record_basenames_snapshots(self):
        out = ingest.normalize_record({"station_id": "d3", "entered_at": 1.0,
                                       "snapshots": ["/p/a.jpg", "/p/b.jpg"]})
        self.assertEqual(out["snapshots"], ["a.jpg", "b.jpg"])

    def test_normalize_acceptance_and_report(self):
        a = ingest.normalize_acceptance({"station_id": "d3", "verdict": "需整理", "severity": "warning",
                                         "problems": ["导线杂乱"]})
        self.assertEqual(a["problems"], ["导线杂乱"])
        r = ingest.normalize_report({"title": "T", "verdict": "合格", "severity": "info",
                                     "event_ids": ["e1"], "body_markdown": "# x"})
        self.assertEqual(r["body_markdown"], "# x")
        self.assertEqual(r["event_ids"], ["e1"])


if __name__ == "__main__":
    unittest.main()
