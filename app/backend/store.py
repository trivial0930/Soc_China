"""SQLite store for the management-app backend.

Pure stdlib (sqlite3 + json). The DB path is injectable (":memory:" in tests).
All list/get methods return dicts shaped exactly as app/API_SPEC.md v1, so the
HTTP layer (server.py) is a thin pass-through. Filtering happens in SQL.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")


def now_iso() -> str:
    """Backend ingest time, ISO8601 with local tz."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def iso_days_ago(days: int) -> str:
    """ISO8601 (local tz) timestamp `days` days before now — the retention cutoff."""
    return (datetime.now(timezone.utc).astimezone() - timedelta(days=days)).isoformat(timespec="seconds")


def _loads(s: Optional[str], default):
    if not s:
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


class Store:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        with open(_SCHEMA, "r", encoding="utf-8") as fh:
            self.conn.executescript(fh.read())
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ ingest
    def upsert_event(self, e: Dict[str, Any]) -> None:
        """Insert/replace an event. `e` follows the ingest schema (flat or nested action)."""
        action = e.get("action") or {}
        self.conn.execute(
            """INSERT INTO events
               (event_id,timestamp,received_at,station_id,source,event_type,severity,
                confidence,summary,image,robot_task,voice_prompt,reported_to_admin)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 timestamp=excluded.timestamp, station_id=excluded.station_id,
                 source=excluded.source, event_type=excluded.event_type,
                 severity=excluded.severity, confidence=excluded.confidence,
                 summary=excluded.summary, image=excluded.image,
                 robot_task=excluded.robot_task, voice_prompt=excluded.voice_prompt,
                 reported_to_admin=excluded.reported_to_admin""",
            (
                str(e["event_id"]), e.get("timestamp", ""), e.get("received_at") or now_iso(),
                e.get("station_id", ""), e.get("source", ""), e.get("event_type", ""),
                e.get("severity", "info"), float(e.get("confidence", 0.0)), e.get("summary", ""),
                e.get("image", "") or "", action.get("robot_task", ""), action.get("voice_prompt", ""),
                1 if action.get("reported_to_admin") else 0,
            ),
        )
        self.conn.commit()

    def upsert_brief(self, b: Dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO briefs (event_id,explanation,confirmed_severity,actions,escalate_to_cloud,received_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(event_id) DO UPDATE SET
                 explanation=excluded.explanation, confirmed_severity=excluded.confirmed_severity,
                 actions=excluded.actions, escalate_to_cloud=excluded.escalate_to_cloud""",
            (
                str(b["event_id"]), b.get("explanation", ""), b.get("confirmed_severity", ""),
                json.dumps(b.get("actions", []), ensure_ascii=False),
                1 if b.get("escalate_to_cloud") else 0, b.get("received_at") or now_iso(),
            ),
        )
        self.conn.commit()

    def insert_record(self, r: Dict[str, Any]) -> int:
        cur = self.conn.execute(
            """INSERT INTO workstation_records
               (station_id,entered_at,left_at,snapshots,note,acceptance_hint,received_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                r.get("station_id", ""), r.get("entered_at"), r.get("left_at"),
                json.dumps(r.get("snapshots", []), ensure_ascii=False),
                r.get("note", ""), r.get("acceptance_hint", ""), r.get("received_at") or now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_acceptance(self, a: Dict[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO acceptance (station_id,verdict,severity,problems,report_id,received_at) VALUES (?,?,?,?,?,?)",
            (
                a.get("station_id", ""), a.get("verdict", ""), a.get("severity", ""),
                json.dumps(a.get("problems", []), ensure_ascii=False),
                a.get("report_id"), a.get("received_at") or now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def insert_report(self, r: Dict[str, Any]) -> int:
        cur = self.conn.execute(
            """INSERT INTO reports (title,report_type,verdict,severity,event_ids,body_markdown,created_at,received_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                r.get("title", ""), r.get("report_type", ""), r.get("verdict", ""),
                r.get("severity", ""), json.dumps(r.get("event_ids", []), ensure_ascii=False),
                r.get("body_markdown", ""), r.get("created_at") or now_iso(), r.get("received_at") or now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def upsert_asset(self, a: Dict[str, Any]) -> int:
        if a.get("id"):
            self.conn.execute(
                """UPDATE assets SET name=?,category=?,station_id=?,area=?,cabinet=?,drawer=?,box=?,
                   quantity=?,note=?,updated_at=? WHERE id=?""",
                (a.get("name", ""), a.get("category", ""), a.get("station_id", ""), a.get("area", ""),
                 a.get("cabinet", ""), a.get("drawer", ""), a.get("box", ""), int(a.get("quantity", 0)),
                 a.get("note", ""), now_iso(), int(a["id"])),
            )
            self.conn.commit()
            return int(a["id"])
        cur = self.conn.execute(
            """INSERT INTO assets (name,category,station_id,area,cabinet,drawer,box,quantity,note,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (a.get("name", ""), a.get("category", ""), a.get("station_id", ""), a.get("area", ""),
             a.get("cabinet", ""), a.get("drawer", ""), a.get("box", ""), int(a.get("quantity", 0)),
             a.get("note", ""), now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def handle_event(self, event_id: str, note: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(
            "UPDATE events SET handled=1, handled_at=?, handled_note=? WHERE event_id=?",
            (now_iso(), note, event_id),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_event(event_id)

    def purge_handled_before(self, cutoff_iso: str) -> int:
        """Delete handled events whose handled_at is strictly before cutoff_iso (ISO8601),
        together with their briefs (briefs have no FK cascade). Returns events deleted.

        Comparison uses julianday() so mixed tz offsets compare correctly; events with a
        NULL/empty handled_at are never purged (defensive — a handled event should have one).
        """
        rows = self.conn.execute(
            "SELECT event_id FROM events "
            "WHERE handled=1 AND handled_at IS NOT NULL AND handled_at != '' "
            "AND julianday(handled_at) < julianday(?)",
            (cutoff_iso,),
        ).fetchall()
        ids = [r["event_id"] for r in rows]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        self.conn.execute(f"DELETE FROM briefs WHERE event_id IN ({marks})", ids)
        self.conn.execute(f"DELETE FROM events WHERE event_id IN ({marks})", ids)
        self.conn.commit()
        return len(ids)

    def purge_reports_before(self, cutoff_iso: str) -> int:
        """Delete reports older than cutoff_iso, dated by created_at (fallback received_at).
        Returns reports deleted. Reports have no child rows to cascade."""
        cur = self.conn.execute(
            "DELETE FROM reports "
            "WHERE julianday(COALESCE(NULLIF(created_at,''), received_at)) < julianday(?)",
            (cutoff_iso,),
        )
        self.conn.commit()
        return cur.rowcount

    # -------------------------------------------------------------------- read
    def _event_row(self, row: sqlite3.Row, with_brief: bool) -> Dict[str, Any]:
        d = {
            "event_id": row["event_id"], "timestamp": row["timestamp"], "received_at": row["received_at"],
            "station_id": row["station_id"], "source": row["source"], "event_type": row["event_type"],
            "severity": row["severity"], "confidence": row["confidence"], "summary": row["summary"],
            "image": row["image"] or "",
            "action": {"robot_task": row["robot_task"], "voice_prompt": row["voice_prompt"],
                       "reported_to_admin": bool(row["reported_to_admin"])},
            "handled": bool(row["handled"]), "handled_at": row["handled_at"],
            "handled_note": row["handled_note"] or "",
        }
        if with_brief:
            d["brief"] = self.get_brief(row["event_id"])
        return d

    def get_brief(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM briefs WHERE event_id=?", (event_id,)).fetchone()
        if not row:
            return None
        return {
            "explanation": row["explanation"], "confirmed_severity": row["confirmed_severity"],
            "actions": _loads(row["actions"], []), "escalate_to_cloud": bool(row["escalate_to_cloud"]),
        }

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return self._event_row(row, with_brief=True) if row else None

    def list_events(self, *, station=None, severity=None, type=None, since=None, until=None,
                    handled=None, limit=50, offset=0) -> Dict[str, Any]:
        where, args = [], []
        if station: where.append("station_id=?"); args.append(station)
        if severity: where.append("severity=?"); args.append(severity)
        if type: where.append("event_type=?"); args.append(type)
        if since: where.append("timestamp>=?"); args.append(since)
        if until: where.append("timestamp<=?"); args.append(until)
        if handled is not None: where.append("handled=?"); args.append(1 if handled else 0)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(f"SELECT COUNT(*) c FROM events{clause}", args).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT * FROM events{clause} ORDER BY timestamp DESC, received_at DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
        return {"items": [self._event_row(r, with_brief=False) for r in rows],
                "total": total, "limit": int(limit), "offset": int(offset)}

    def _record_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {"id": row["id"], "station_id": row["station_id"], "entered_at": row["entered_at"],
                "left_at": row["left_at"], "snapshots": _loads(row["snapshots"], []),
                "note": row["note"] or "", "acceptance_hint": row["acceptance_hint"] or "",
                "received_at": row["received_at"]}

    def list_records(self, *, station=None, since=None, until=None, limit=50, offset=0) -> Dict[str, Any]:
        where, args = [], []
        if station: where.append("station_id=?"); args.append(station)
        if since: where.append("entered_at>=?"); args.append(float(since))
        if until: where.append("entered_at<=?"); args.append(float(until))
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(f"SELECT COUNT(*) c FROM workstation_records{clause}", args).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT * FROM workstation_records{clause} ORDER BY entered_at DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
        return {"items": [self._record_row(r) for r in rows], "total": total,
                "limit": int(limit), "offset": int(offset)}

    def _acc_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {"id": row["id"], "station_id": row["station_id"], "verdict": row["verdict"],
                "severity": row["severity"], "problems": _loads(row["problems"], []),
                "report_id": row["report_id"], "received_at": row["received_at"]}

    def list_acceptance(self, *, station=None, verdict=None, since=None, limit=50, offset=0) -> Dict[str, Any]:
        where, args = [], []
        if station: where.append("station_id=?"); args.append(station)
        if verdict: where.append("verdict=?"); args.append(verdict)
        if since: where.append("received_at>=?"); args.append(since)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(f"SELECT COUNT(*) c FROM acceptance{clause}", args).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT * FROM acceptance{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
        return {"items": [self._acc_row(r) for r in rows], "total": total,
                "limit": int(limit), "offset": int(offset)}

    def _report_row(self, row: sqlite3.Row, with_body: bool) -> Dict[str, Any]:
        d = {"id": row["id"], "title": row["title"], "report_type": row["report_type"],
             "verdict": row["verdict"], "severity": row["severity"],
             "event_ids": _loads(row["event_ids"], []),
             "created_at": row["created_at"], "received_at": row["received_at"]}
        if with_body:
            d["body_markdown"] = row["body_markdown"] or ""
        return d

    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM reports WHERE id=?", (int(report_id),)).fetchone()
        return self._report_row(row, with_body=True) if row else None

    def list_reports(self, *, type=None, verdict=None, limit=50, offset=0) -> Dict[str, Any]:
        where, args = [], []
        if type: where.append("report_type=?"); args.append(type)
        if verdict: where.append("verdict=?"); args.append(verdict)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.conn.execute(f"SELECT COUNT(*) c FROM reports{clause}", args).fetchone()["c"]
        rows = self.conn.execute(
            f"SELECT * FROM reports{clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
        return {"items": [self._report_row(r, with_body=False) for r in rows], "total": total,
                "limit": int(limit), "offset": int(offset)}

    def station_summary(self, station_id: str) -> Dict[str, Any]:
        rec = self.conn.execute(
            "SELECT * FROM workstation_records WHERE station_id=? ORDER BY entered_at DESC LIMIT 1",
            (station_id,)).fetchone()
        acc = self.conn.execute(
            "SELECT * FROM acceptance WHERE station_id=? ORDER BY id DESC LIMIT 1", (station_id,)).fetchone()
        evs = self.conn.execute(
            "SELECT * FROM events WHERE station_id=? ORDER BY timestamp DESC LIMIT 10", (station_id,)).fetchall()
        return {"station_id": station_id,
                "latest_record": self._record_row(rec) if rec else None,
                "latest_acceptance": self._acc_row(acc) if acc else None,
                "recent_events": [self._event_row(e, with_brief=False) for e in evs]}
