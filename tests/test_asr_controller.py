import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.asr_engine import MockAsrBackend, wake_event, utterance_event  # noqa: E402


class MockBackendTests(unittest.TestCase):
    def test_poll_pops_events_then_none(self):
        be = MockAsrBackend([wake_event(), utterance_event("去三号桌复核")])
        self.assertEqual(be.poll(), {"kind": "wake"})
        self.assertEqual(be.poll(), {"kind": "utterance", "text": "去三号桌复核"})
        self.assertIsNone(be.poll())

    def test_set_mode_recorded(self):
        be = MockAsrBackend([])
        be.set_mode("dialog"); be.set_mode("kws")
        self.assertEqual(be.modes, ["dialog", "kws"])


if __name__ == "__main__":
    unittest.main()
