import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/inspection_manager"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from inspection_manager.mode_switch import (  # noqa: E402
    MODE_NORMAL, MODE_MAPPING, read_mode, write_mode, SwitchLock,
)


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.id().replace(".", "_"))
        self.state = str(self.tmp.with_suffix(".mode"))

    def tearDown(self):
        for p in (self.state,):
            try:
                Path(p).unlink()
            except OSError:
                pass

    def test_missing_state_reads_normal(self):
        self.assertEqual(read_mode("/no/such/file"), MODE_NORMAL)

    def test_write_then_read_roundtrip(self):
        write_mode(self.state, MODE_MAPPING)
        self.assertEqual(read_mode(self.state), MODE_MAPPING)


class SwitchLockTest(unittest.TestCase):
    def setUp(self):
        self.lock_path = str(Path(self.id().replace(".", "_")).with_suffix(".lock"))
        self.t = [100.0]

    def tearDown(self):
        try:
            Path(self.lock_path).unlink()
        except OSError:
            pass

    def now(self):
        return self.t[0]

    def test_acquire_then_fresh_reacquire_busy(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        lk2 = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertFalse(lk2.acquire())   # held & fresh

    def test_stale_lock_is_stealable(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        self.t[0] += 91.0                 # past timeout
        lk2 = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk2.acquire())

    def test_release_allows_reacquire(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        lk.release()
        self.assertTrue(SwitchLock(self.lock_path, 90.0, self.now).acquire())


if __name__ == "__main__":
    unittest.main()
