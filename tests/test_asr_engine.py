import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.asr_engine import _should_retry_mic  # noqa: E402


class ShouldRetryMicTests(unittest.TestCase):
    def test_within_interval_no_retry(self):
        # 距上次尝试不足 interval -> 不重试
        self.assertFalse(_should_retry_mic(last_try=10.0, now=12.0, interval=3.0))

    def test_exactly_interval_retries(self):
        # 恰好等于 interval -> 重试(>=)
        self.assertTrue(_should_retry_mic(last_try=10.0, now=13.0, interval=3.0))

    def test_past_interval_retries(self):
        self.assertTrue(_should_retry_mic(last_try=10.0, now=20.0, interval=3.0))

    def test_first_try_from_zero(self):
        # last_try=0(从未尝试) + now 远大于 interval -> 重试
        self.assertTrue(_should_retry_mic(last_try=0.0, now=100.0, interval=3.0))


if __name__ == "__main__":
    unittest.main()
