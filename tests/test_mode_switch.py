import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/inspection_manager"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from inspection_manager.mode_switch import (  # noqa: E402,F811
    MODE_NORMAL, MODE_MAPPING, MODE_SWITCHING, MODE_ERROR,
    read_mode, write_mode, SwitchLock, ModeController, sanitize_map_name,
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


class _Ctl:
    """构造一个 ModeController，记录被调用的脚本。"""
    def __init__(self, tmpbase, current=MODE_NORMAL, rc=0):
        self.state = str(Path(tmpbase).with_suffix(".mode"))
        self.lock = str(Path(tmpbase).with_suffix(".lock"))
        write_mode(self.state, current)
        self.calls = []
        self.rc = rc
        self.t = [100.0]
        self.ctl = ModeController(
            run_script=self._run, state_path=self.state, lock_path=self.lock,
            on_script="ON", off_script="OFF", save_script="SAVE",
            now=lambda: self.t[0], lock_timeout_s=90.0)

    def _run(self, cmd):
        self.calls.append(cmd)
        return self.rc

    def cleanup(self):
        for p in (self.state, self.lock):
            try:
                Path(p).unlink()
            except OSError:
                pass


class SetModeTest(unittest.TestCase):
    def base(self):
        return Path(self.id().replace(".", "_"))

    def test_enter_mapping_success(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "done")
            self.assertEqual(r["mode"], MODE_MAPPING)
            self.assertEqual(c.calls, ["ON"])
            self.assertEqual(read_mode(c.state), MODE_MAPPING)
        finally:
            c.cleanup()

    def test_enter_mapping_failure_stays_error(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=1)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "failed")
            self.assertEqual(read_mode(c.state), MODE_ERROR)
        finally:
            c.cleanup()

    def test_exit_to_normal_success(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.set_mode(MODE_NORMAL)
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["OFF"])
            self.assertEqual(read_mode(c.state), MODE_NORMAL)
        finally:
            c.cleanup()

    def test_exit_partial_restore_warns_but_normal(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=2)
        try:
            r = c.ctl.set_mode(MODE_NORMAL)
            self.assertEqual(r["status"], "warn")
            self.assertEqual(read_mode(c.state), MODE_NORMAL)
        finally:
            c.cleanup()

    def test_idempotent_noop_when_already_target(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "noop")
            self.assertEqual(c.calls, [])      # 没跑脚本
        finally:
            c.cleanup()

    def test_retry_from_error_runs_on_script(self):
        c = _Ctl(self.base(), current=MODE_ERROR, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)   # error != mapping -> 重试
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["ON"])
        finally:
            c.cleanup()

    def test_invalid_mode_rejected(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.set_mode("banana")
            self.assertEqual(r["status"], "failed")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()

    def test_busy_when_lock_held(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            SwitchLock(c.lock, 90.0, lambda: c.t[0]).acquire()  # 外部占锁(新鲜)
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "busy")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()


class SaveMapTest(unittest.TestCase):
    def base(self):
        return Path(self.id().replace(".", "_"))

    def test_sanitize_strips_unsafe(self):
        self.assertEqual(sanitize_map_name("../lab map!!"), "lab_map")
        self.assertEqual(sanitize_map_name(""), "lab_map")
        self.assertEqual(sanitize_map_name("floor-2_A"), "floor-2_A")

    def test_save_map_only_in_mapping(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "failed")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()

    def test_save_map_runs_in_mapping(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["SAVE lab"])
        finally:
            c.cleanup()

    def test_save_map_failure_reported(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=1)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "failed")
        finally:
            c.cleanup()


if __name__ == "__main__":
    unittest.main()
