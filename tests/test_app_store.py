import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import ingest, store  # noqa: E402


def _event(eid="e1", station="desk-03", severity="warning", ts="2026-06-19T20:30:00+08:00"):
    return {
        "event_id": eid, "timestamp": ts, "station_id": station, "source": "thermal",
        "event_type": "thermal_risk", "severity": severity, "confidence": 0.85,
        "summary": "疑似未断电电烙铁",
        "evidence": {"image_path": "/root/lab_detector_deploy/evidence/e1_warning.jpg"},
        "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": True},
    }


class StoreEventTests(unittest.TestCase):
    def setUp(self):
        self.s = store.Store(":memory:")

    def test_upsert_and_get_event_shapes_per_spec(self):
        self.s.upsert_event(ingest.normalize_event(_event()))
        e = self.s.get_event("e1")
        self.assertEqual(e["station_id"], "desk-03")
        self.assertEqual(e["image"], "e1_warning.jpg")           # path -> basename
        self.assertTrue(e["action"]["reported_to_admin"])
        self.assertFalse(e["handled"])
        self.assertIn("brief", e)                                 # detail carries brief key
        self.assertIsNone(e["brief"])                             # none yet

    def test_brief_attaches_to_event_detail(self):
        self.s.upsert_event(ingest.normalize_event(_event()))
        self.s.upsert_brief(ingest.normalize_brief({
            "event": {"event_id": "e1"}, "explanation": "高温电烙铁",
            "confirmed_severity": "critical", "actions": ["voice", "recheck"], "escalate_to_cloud": True}))
        e = self.s.get_event("e1")
        self.assertEqual(e["brief"]["confirmed_severity"], "critical")
        self.assertEqual(e["brief"]["actions"], ["voice", "recheck"])
        self.assertTrue(e["brief"]["escalate_to_cloud"])

    def test_upsert_is_idempotent_on_event_id(self):
        self.s.upsert_event(ingest.normalize_event(_event(severity="warning")))
        self.s.upsert_event(ingest.normalize_event(_event(severity="critical")))  # same id
        self.assertEqual(self.s.list_events()["total"], 1)
        self.assertEqual(self.s.get_event("e1")["severity"], "critical")

    def test_list_filters_and_pagination(self):
        for i in range(5):
            sev = "critical" if i % 2 == 0 else "warning"
            self.s.upsert_event(ingest.normalize_event(_event(eid=f"e{i}", severity=sev,
                                                              ts=f"2026-06-19T20:3{i}:00+08:00")))
        self.assertEqual(self.s.list_events(severity="critical")["total"], 3)
        self.assertEqual(self.s.list_events(station="desk-03")["total"], 5)
        page = self.s.list_events(limit=2, offset=0)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["total"], 5)
        # list items omit brief
        self.assertNotIn("brief", page["items"][0])

    def test_list_events_orders_newest_first(self):
        self.s.upsert_event(ingest.normalize_event(_event(eid="old", ts="2026-06-19T08:00:00+08:00")))
        self.s.upsert_event(ingest.normalize_event(_event(eid="new", ts="2026-06-19T22:00:00+08:00")))
        self.assertEqual(self.s.list_events()["items"][0]["event_id"], "new")

    def test_handle_event(self):
        self.s.upsert_event(ingest.normalize_event(_event()))
        out = self.s.handle_event("e1", "已断电并提醒")
        self.assertTrue(out["handled"])
        self.assertEqual(out["handled_note"], "已断电并提醒")
        self.assertIsNotNone(out["handled_at"])
        self.assertEqual(self.s.list_events(handled=True)["total"], 1)
        self.assertEqual(self.s.list_events(handled=False)["total"], 0)

    def test_handle_missing_event_returns_none(self):
        self.assertIsNone(self.s.handle_event("nope", "x"))


class StoreRecordReportTests(unittest.TestCase):
    def setUp(self):
        self.s = store.Store(":memory:")

    def test_record_roundtrip(self):
        rid = self.s.insert_record(ingest.normalize_record({
            "station_id": "desk-03", "entered_at": 1718800000.0, "left_at": 1718800300.0,
            "snapshots": ["/p/a.jpg", "/p/b.jpg"], "note": "x", "acceptance_hint": "需整理"}))
        self.assertGreater(rid, 0)
        items = self.s.list_records(station="desk-03")["items"]
        self.assertEqual(items[0]["snapshots"], ["a.jpg", "b.jpg"])
        self.assertEqual(items[0]["acceptance_hint"], "需整理")

    def test_acceptance_roundtrip(self):
        self.s.insert_acceptance(ingest.normalize_acceptance({
            "station_id": "desk-03", "verdict": "需整理", "severity": "warning",
            "problems": ["导线杂乱", "仪器未归位"]}))
        items = self.s.list_acceptance(verdict="需整理")["items"]
        self.assertEqual(items[0]["problems"], ["导线杂乱", "仪器未归位"])

    def test_report_list_omits_body_detail_has_body(self):
        rid = self.s.insert_report(ingest.normalize_report({
            "title": "课后验收", "report_type": "post_class_acceptance", "verdict": "需整理",
            "severity": "warning", "event_ids": ["e1"], "body_markdown": "# 报告\n正文"}))
        lst = self.s.list_reports()["items"][0]
        self.assertNotIn("body_markdown", lst)
        full = self.s.get_report(rid)
        self.assertIn("# 报告", full["body_markdown"])
        self.assertEqual(full["event_ids"], ["e1"])

    def test_station_summary_merges_record_acceptance_events(self):
        self.s.upsert_event(ingest.normalize_event(_event(station="desk-07")))
        self.s.insert_record(ingest.normalize_record({"station_id": "desk-07", "entered_at": 1.0}))
        self.s.insert_acceptance(ingest.normalize_acceptance(
            {"station_id": "desk-07", "verdict": "合格", "severity": "info", "problems": []}))
        summ = self.s.station_summary("desk-07")
        self.assertIsNotNone(summ["latest_record"])
        self.assertEqual(summ["latest_acceptance"]["verdict"], "合格")
        self.assertEqual(len(summ["recent_events"]), 1)


if __name__ == "__main__":
    unittest.main()
