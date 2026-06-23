import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager import uplink  # noqa: E402


class BuildersTest(unittest.TestCase):
    def test_build_event_rewrites_image_to_basename(self):
        raw = {"event_id": "e1", "timestamp": "t", "station_id": "desk-03", "source": "thermal",
               "event_type": "thermal_risk", "severity": "warning", "confidence": 0.8, "summary": "x",
               "evidence": {"image_path": "/root/lab_detector_deploy/evidence/e1_warning.jpg"},
               "action": {"voice_prompt": "p"}}
        out = uplink.build_event(raw)
        self.assertEqual(out["image"], "e1_warning.jpg")          # basename only
        self.assertEqual(out["station_id"], "desk-03")
        self.assertEqual(out["action"]["voice_prompt"], "p")
        self.assertEqual(uplink.event_images(raw), ["/root/lab_detector_deploy/evidence/e1_warning.jpg"])

    def test_event_images_empty_when_no_path(self):
        self.assertEqual(uplink.event_images({"event_id": "e", "image": ""}), [])

    def test_build_brief_extracts_event_id_from_event(self):
        out = uplink.build_brief({"event": {"event_id": "e9"}, "explanation": "hi",
                                  "confirmed_severity": "critical", "actions": ["voice"], "escalate_to_cloud": True})
        self.assertEqual(out["event_id"], "e9")
        self.assertEqual(out["confirmed_severity"], "critical")
        self.assertTrue(out["escalate_to_cloud"])

    def test_build_record_basenames_snapshots(self):
        out = uplink.build_record({"station_id": "d3", "entered_at": 1.0, "left_at": 2.0,
                                   "snapshots": ["/p/a.jpg", "/p/b.jpg"], "acceptance_hint": "需整理"})
        self.assertEqual(out["snapshots"], ["a.jpg", "b.jpg"])
        self.assertEqual(out["acceptance_hint"], "需整理")
        self.assertEqual(uplink.record_images({"snapshots": ["/p/a.jpg", ""]}), ["/p/a.jpg"])

    def test_build_report_inlines_markdown(self):
        out = uplink.build_report({"title": "T", "report_type": "post_class_acceptance",
                                   "verdict": "需整理", "severity": "warning", "event_ids": ["e1"]}, "# md body")
        self.assertEqual(out["body_markdown"], "# md body")
        self.assertEqual(out["event_ids"], ["e1"])

    def test_read_markdown_missing_returns_empty(self):
        self.assertEqual(uplink.read_markdown("/no/such/file.md"), "")


class FakeSender:
    """Records sends; fails the first `fail_n` calls to exercise retry.

    Also supports a `succeed` flag: if given, overrides fail_n and always
    returns that value (useful for "always fail" / "always succeed" scenarios).
    """
    def __init__(self, fail_n=0, succeed=None):
        self.calls = []
        self.fail_n = fail_n
        self.succeed = succeed
    def __call__(self, kind, body):
        self.calls.append((kind, body))
        if self.succeed is not None:
            return self.succeed
        if len(self.calls) <= self.fail_n:
            return False
        return True


class RetryQueueTest(unittest.TestCase):
    def test_drain_all_success(self):
        q = uplink.RetryQueue()
        q.add("event", {"a": 1}); q.add("brief", {"b": 2})
        res = q.drain(FakeSender())
        self.assertEqual(res, {"sent": 2, "requeued": 0, "dropped": 0})
        self.assertEqual(len(q), 0)

    def test_failed_send_requeues(self):
        q = uplink.RetryQueue(max_attempts=5)
        q.add("event", {"a": 1})
        s = FakeSender(fail_n=10)  # always fail
        res = q.drain(s)
        self.assertEqual(res["requeued"], 1)
        self.assertEqual(len(q), 1)

    def test_dropped_after_max_attempts(self):
        q = uplink.RetryQueue(max_attempts=2)
        q.add("event", {"a": 1})
        s = FakeSender(fail_n=100)
        q.drain(s)          # attempt 1 -> requeue (attempts=1)
        res = q.drain(s)    # attempt 2 -> 1+1==2 == max -> drop
        self.assertEqual(res["dropped"], 1)
        self.assertEqual(len(q), 0)

    def test_sender_exception_treated_as_failure(self):
        q = uplink.RetryQueue(max_attempts=5)
        q.add("event", {"a": 1})

        def boom(kind, body):
            raise RuntimeError("net down")

        res = q.drain(boom)
        self.assertEqual(res["requeued"], 1)

    def test_bounded_length_drops_oldest(self):
        q = uplink.RetryQueue(max_len=3)
        for i in range(5):
            q.add("event", {"i": i})
        self.assertEqual(len(q), 3)
        # the three newest remain
        kinds = [b["i"] for _, b, _ in q._q]
        self.assertEqual(kinds, [2, 3, 4])

    def test_persistent_kind_never_dropped(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("event", {"a": 1})
        s = FakeSender(succeed=False)
        for _ in range(10):              # 远超 max_attempts
            res = q.drain(s)
        self.assertEqual(len(q), 1)       # 仍在队列,从未 drop
        self.assertEqual(res["dropped"], 0)

    def test_non_persistent_still_dropped(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("report", {"a": 1})
        s = FakeSender(succeed=False)
        q.drain(s)                        # attempts=1 -> requeue
        res = q.drain(s)                  # 1+1==2==max -> drop
        self.assertEqual(len(q), 0)
        self.assertEqual(res["dropped"], 1)

    def test_add_returns_true_when_oldest_dropped(self):
        q = uplink.RetryQueue(max_len=2)
        self.assertFalse(q.add("event", {"i": 0}))
        self.assertFalse(q.add("event", {"i": 1}))
        self.assertTrue(q.add("event", {"i": 2}))   # 满了,丢最旧

    def test_persistent_drains_when_sender_recovers(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("event", {"a": 1})
        down = FakeSender(succeed=False)
        for _ in range(5):
            q.drain(down)                 # 断网期:一直保留
        self.assertEqual(len(q), 1)
        up = FakeSender(succeed=True)
        res = q.drain(up)                 # 恢复:发出
        self.assertEqual(res["sent"], 1)
        self.assertEqual(len(q), 0)


if __name__ == "__main__":
    unittest.main()
