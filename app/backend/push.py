"""SSE (Server-Sent Events) broker for real-time hazard alerts.

`sse_format` is the pure wire-format helper (unit-tested). `Broker` fans a published
event out to every subscriber's asyncio.Queue; the server's async generator drains
one queue per connected client.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Set


def sse_format(event_name: str, data: Dict[str, Any]) -> str:
    """One SSE frame: `event: <name>\\ndata: <json>\\n\\n` (UTF-8, no ascii escaping)."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


class Broker:
    def __init__(self, max_queue: int = 200) -> None:
        self._subs: Set[asyncio.Queue] = set()
        self._max = max_queue

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, event_name: str, data: Dict[str, Any]) -> None:
        """Enqueue (event_name, data) to all subscribers; drop slow/full ones."""
        dead = []
        for q in self._subs:
            try:
                q.put_nowait((event_name, data))
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subs.discard(q)
