"""Pure helpers for the RDK->backend uplink (stdlib only, no ROS, no requests).

Builds the management-app ingest payloads from ROS topic JSON, lists the image
files to upload, and a bounded retry queue so WiFi blips don't lose data. The
real HTTP POST uses stdlib urllib (HttpPoster); tests inject a fake.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple


def _basename(p: str) -> str:
    return os.path.basename(p) if p else ""


# ---- payload builders: ROS topic JSON -> backend /api/ingest/{kind} body ----
def build_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    img = (raw.get("evidence") or {}).get("image_path", "") or raw.get("image", "")
    out = {k: raw.get(k) for k in
           ("event_id", "timestamp", "station_id", "source", "event_type", "severity", "confidence", "summary")}
    out["image"] = _basename(img)
    out["action"] = raw.get("action") or {}
    return out


def event_images(raw: Dict[str, Any]) -> List[str]:
    img = (raw.get("evidence") or {}).get("image_path", "") or raw.get("image", "")
    return [img] if img and os.path.sep in img else ([img] if img else [])


def build_brief(raw: Dict[str, Any]) -> Dict[str, Any]:
    # /inspection/brief is {event:{...}, explanation, confirmed_severity, actions, escalate_to_cloud}
    return {
        "event_id": raw.get("event_id") or (raw.get("event") or {}).get("event_id", ""),
        "explanation": raw.get("explanation", ""),
        "confirmed_severity": raw.get("confirmed_severity", ""),
        "actions": list(raw.get("actions", [])),
        "escalate_to_cloud": bool(raw.get("escalate_to_cloud", False)),
    }


def build_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "station_id": raw.get("station_id", ""),
        "entered_at": raw.get("entered_at"),
        "left_at": raw.get("left_at"),
        "snapshots": [_basename(s) for s in (raw.get("snapshots") or []) if s],
        "note": raw.get("note", ""),
        "acceptance_hint": raw.get("acceptance_hint", ""),
    }


def record_images(raw: Dict[str, Any]) -> List[str]:
    return [s for s in (raw.get("snapshots") or []) if s and os.path.sep in s]


def build_acceptance(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {k: raw.get(k) for k in ("station_id", "verdict", "severity", "problems", "report_id")}


def build_report(raw: Dict[str, Any], markdown_body: str) -> Dict[str, Any]:
    out = {k: raw.get(k) for k in ("title", "report_type", "verdict", "severity", "event_ids", "created_at")}
    out["body_markdown"] = markdown_body
    return out


def read_markdown(path: str) -> str:
    """Read a report .md file from disk; '' if missing (so uplink still sends metadata)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


# ---------------------------------------------------------------- retry queue
class RetryQueue:
    """Bounded FIFO of (kind, body) pending POSTs; drop after max_attempts."""

    def __init__(self, max_attempts: int = 5, max_len: int = 500) -> None:
        self.max_attempts = max_attempts
        self.max_len = max_len
        self._q: List[Tuple[str, Dict[str, Any], int]] = []  # (kind, body, attempts)

    def __len__(self) -> int:
        return len(self._q)

    def add(self, kind: str, body: Dict[str, Any]) -> None:
        if len(self._q) >= self.max_len:
            self._q.pop(0)  # drop oldest
        self._q.append((kind, body, 0))

    def drain(self, sender: Callable[[str, Dict[str, Any]], bool]) -> Dict[str, int]:
        """Try to send each queued item; requeue failures (<max_attempts), drop the rest.
        sender(kind, body) -> True on success. Returns {sent, requeued, dropped}."""
        pending = self._q
        self._q = []
        sent = requeued = dropped = 0
        for kind, body, attempts in pending:
            ok = False
            try:
                ok = bool(sender(kind, body))
            except Exception:
                ok = False
            if ok:
                sent += 1
            elif attempts + 1 < self.max_attempts:
                self._q.append((kind, body, attempts + 1)); requeued += 1
            else:
                dropped += 1
        return {"sent": sent, "requeued": requeued, "dropped": dropped}


# ---------------------------------------------------------------- HTTP poster
class HttpPoster:  # pragma: no cover - real network
    """stdlib urllib POST. No extra pip dep on the RDK."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 8.0) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self, ctype: str) -> Dict[str, str]:
        h = {"Content-Type": ctype}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def post_json(self, path: str, body: Dict[str, Any]) -> bool:
        req = urllib.request.Request(self.base + path, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers=self._headers("application/json"), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return 200 <= r.status < 300

    def get_json(self, path: str) -> Any:
        """GET + parse JSON body (used to poll the command queue)."""
        req = urllib.request.Request(self.base + path, headers=self._headers("application/json"), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def post_image(self, path: str, filename: str, data: bytes) -> bool:
        boundary = "----rdkuplink7e1f"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: image/jpeg\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + path, data=body,
                                     headers=self._headers(f"multipart/form-data; boundary={boundary}"), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return 200 <= r.status < 300
