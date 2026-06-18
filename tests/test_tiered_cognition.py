import sys
import unittest
from pathlib import Path

PACKAGE_SRC = (
    Path(__file__).resolve().parents[1]
    / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
)
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.cognition import TierPolicy, tier_policy_from_dict  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
