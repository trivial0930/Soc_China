import sys
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

from inspection_manager.workstation_record import (  # noqa: E402
    OccupancyTracker,
    WorkstationSession,
    attach_acceptance,
    export,
    sessions_for_station,
    sessions_in_window,
)


class OccupancyTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = OccupancyTracker(enter_after_sec=2.0, leave_after_sec=5.0)

    def test_brief_presence_does_not_open_session(self):
        self.assertIsNone(self.t.observe("desk-01", True, now=0.0))  # just arrived
        self.assertIsNone(self.t.observe("desk-01", True, now=1.0))  # < 2s
        self.assertIsNone(self.t.observe("desk-01", False, now=1.5))  # left quickly
        self.assertEqual(self.t.sessions, [])

    def test_sustained_presence_opens_session_with_arrival_snapshot(self):
        self.t.observe("desk-01", True, now=0.0, snapshot="arr.jpg")
        ev = self.t.observe("desk-01", True, now=2.0, snapshot="arr.jpg")
        self.assertEqual(ev, "entered")
        sess = self.t.open_session("desk-01")
        self.assertIsNotNone(sess)
        self.assertEqual(sess.snapshots, ["arr.jpg"])

    def test_session_closes_after_sustained_absence_with_departure_snapshot(self):
        self.t.observe("desk-01", True, now=0.0)
        self.t.observe("desk-01", True, now=2.0)  # entered
        self.t.observe("desk-01", False, now=3.0)  # absent starts
        self.assertIsNone(self.t.observe("desk-01", False, now=7.0))  # 4s < 5s, still open
        ev = self.t.observe("desk-01", False, now=8.0, snapshot="dep.jpg")  # 5s absent
        self.assertEqual(ev, "left")
        self.assertEqual(len(self.t.sessions), 1)
        s = self.t.sessions[0]
        self.assertEqual(s.entered_at, 2.0)
        self.assertEqual(s.left_at, 8.0)
        self.assertEqual(s.snapshots, ["dep.jpg"])
        self.assertTrue(s.closed)

    def test_brief_absence_does_not_close(self):
        self.t.observe("desk-01", True, now=0.0)
        self.t.observe("desk-01", True, now=2.0)  # entered
        self.t.observe("desk-01", False, now=3.0)
        self.t.observe("desk-01", True, now=4.0)  # came back within 5s
        self.assertEqual(self.t.sessions, [])  # still occupied, no close
        self.assertIsNotNone(self.t.open_session("desk-01"))

    def test_two_stations_independent(self):
        self.t.observe("desk-01", True, now=0.0)
        self.t.observe("desk-02", True, now=0.0)
        self.t.observe("desk-01", True, now=2.0)  # desk-01 entered
        self.assertEqual(self.t.observe("desk-02", True, now=1.0), None)


class AttachAndQueryTests(unittest.TestCase):
    def _sessions(self):
        return [
            WorkstationSession("desk-01", entered_at=0.0, left_at=10.0),
            WorkstationSession("desk-01", entered_at=20.0, left_at=30.0),
            WorkstationSession("desk-02", entered_at=5.0, left_at=25.0),
        ]

    def test_attach_acceptance_hint_and_note(self):
        s = WorkstationSession("desk-03", entered_at=0.0, left_at=5.0)
        attach_acceptance(s, hint="存在安全隐患", note="疑似电烙铁未断电")
        self.assertEqual(s.acceptance_hint, "存在安全隐患")
        self.assertEqual(s.note, "疑似电烙铁未断电")

    def test_sessions_for_station(self):
        self.assertEqual(len(sessions_for_station(self._sessions(), "desk-01")), 2)

    def test_sessions_in_window_overlap(self):
        # window [8, 22] overlaps: desk-01(0-10), desk-01(20-30), desk-02(5-25)
        got = sessions_in_window(self._sessions(), 8.0, 22.0)
        self.assertEqual(len(got), 3)
        got2 = sessions_in_window(self._sessions(), 11.0, 19.0)  # gap
        self.assertEqual([s.station_id for s in got2], ["desk-02"])

    def test_export_is_app_friendly_dicts(self):
        out = export(self._sessions())
        self.assertEqual(out[0]["station_id"], "desk-01")
        self.assertIn("snapshots", out[0])
        self.assertIn("acceptance_hint", out[0])


if __name__ == "__main__":
    unittest.main()
