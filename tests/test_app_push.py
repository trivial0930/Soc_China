import asyncio
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.backend import push  # noqa: E402


class SseFormatTest(unittest.TestCase):
    def test_frame_shape_and_utf8(self):
        frame = push.sse_format("hazard", {"summary": "电烙铁"})
        self.assertTrue(frame.startswith("event: hazard\ndata: "))
        self.assertTrue(frame.endswith("\n\n"))
        line = frame.split("data: ", 1)[1].strip()
        self.assertEqual(json.loads(line)["summary"], "电烙铁")  # not ascii-escaped
        self.assertIn("电烙铁", frame)


class BrokerTest(unittest.IsolatedAsyncioTestCase):
    async def test_publish_fans_out_to_subscribers(self):
        b = push.Broker()
        q1, q2 = b.subscribe(), b.subscribe()
        self.assertEqual(b.subscriber_count, 2)
        b.publish("hazard", {"x": 1})
        self.assertEqual(await q1.get(), ("hazard", {"x": 1}))
        self.assertEqual(await q2.get(), ("hazard", {"x": 1}))

    async def test_unsubscribe(self):
        b = push.Broker()
        q = b.subscribe()
        b.unsubscribe(q)
        self.assertEqual(b.subscriber_count, 0)
        b.publish("hazard", {"x": 1})  # no subscribers; must not raise

    async def test_full_queue_subscriber_is_dropped(self):
        b = push.Broker(max_queue=1)
        q = b.subscribe()
        b.publish("a", {}); b.publish("b", {})  # second overflows the size-1 queue -> drop sub
        self.assertEqual(b.subscriber_count, 0)


if __name__ == "__main__":
    unittest.main()
