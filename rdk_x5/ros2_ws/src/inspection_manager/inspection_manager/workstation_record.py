"""Workstation occupancy records (功能4) — an app-oriented log for管理员.

Keeps one record per occupancy session: {工位, 进入, 离开, 快照, 文字说明, 粗略验收提示}.
The intent is a future mobile app that uploads/shows the **photos + text** so a manager
**judges manually** — precise pass/fail is NOT required; a rough hint is enough.

Pure stdlib: a debounced occupancy state machine + session records + query/export.
On-board feeds it: a per-desk "is someone present?" signal and snapshot capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class WorkstationSession:
    station_id: str
    entered_at: float  # seconds (caller supplies the clock)
    left_at: Optional[float] = None
    snapshots: List[str] = field(default_factory=list)  # image paths (arrival / departure)
    note: str = ""  # free text, e.g. a Layer 2 explanation or acceptance summary
    acceptance_hint: str = ""  # rough: "" | 合格 | 需整理 | 存在安全隐患

    @property
    def closed(self) -> bool:
        return self.left_at is not None

    def to_dict(self) -> dict:
        """App-friendly record."""
        return {
            "station_id": self.station_id,
            "entered_at": self.entered_at,
            "left_at": self.left_at,
            "snapshots": list(self.snapshots),
            "note": self.note,
            "acceptance_hint": self.acceptance_hint,
        }


@dataclass
class _StationState:
    occupied: bool = False
    present_since: Optional[float] = None
    absent_since: Optional[float] = None
    session: Optional[WorkstationSession] = None


class OccupancyTracker:
    """Debounced per-station occupancy -> sessions.

    ``observe(station_id, present, now, snapshot)`` is fed a stream of "is someone
    here?" samples; it opens a session after ``enter_after_sec`` of presence and
    closes it after ``leave_after_sec`` of absence. Returns "entered"/"left"/None.
    Closed sessions accumulate in ``self.sessions``.
    """

    def __init__(self, enter_after_sec: float = 2.0, leave_after_sec: float = 5.0) -> None:
        self.enter_after_sec = enter_after_sec
        self.leave_after_sec = leave_after_sec
        self._state: Dict[str, _StationState] = {}
        self.sessions: List[WorkstationSession] = []

    def observe(
        self, station_id: str, present: bool, now: float, snapshot: str = ""
    ) -> Optional[str]:
        s = self._state.setdefault(station_id, _StationState())
        if present:
            s.absent_since = None
            if not s.occupied:
                if s.present_since is None:
                    s.present_since = now
                if now - s.present_since >= self.enter_after_sec:
                    s.occupied = True
                    s.session = WorkstationSession(station_id=station_id, entered_at=now)
                    if snapshot:
                        s.session.snapshots.append(snapshot)
                    return "entered"
        else:
            s.present_since = None
            if s.occupied:
                if s.absent_since is None:
                    s.absent_since = now
                if now - s.absent_since >= self.leave_after_sec:
                    assert s.session is not None
                    s.session.left_at = now
                    if snapshot:
                        s.session.snapshots.append(snapshot)
                    self.sessions.append(s.session)
                    s.occupied = False
                    s.session = None
                    s.absent_since = None
                    return "left"
        return None

    def open_session(self, station_id: str) -> Optional[WorkstationSession]:
        s = self._state.get(station_id)
        return s.session if s else None


def attach_acceptance(
    session: WorkstationSession, hint: str = "", note: str = ""
) -> WorkstationSession:
    """Attach a rough acceptance hint / text note to a session (for the app)."""
    if hint:
        session.acceptance_hint = hint
    if note:
        session.note = note
    return session


def sessions_for_station(sessions: List[WorkstationSession], station_id: str) -> List[WorkstationSession]:
    return [s for s in sessions if s.station_id == station_id]


def sessions_in_window(
    sessions: List[WorkstationSession], start: float, end: float
) -> List[WorkstationSession]:
    """Sessions that overlap [start, end] (open sessions treated as ongoing)."""
    out = []
    for s in sessions:
        s_end = s.left_at if s.left_at is not None else end
        if s.entered_at <= end and s_end >= start:
            out.append(s)
    return out


def export(sessions: List[WorkstationSession]) -> List[dict]:
    """Serialize sessions for upload to the management app."""
    return [s.to_dict() for s in sessions]
