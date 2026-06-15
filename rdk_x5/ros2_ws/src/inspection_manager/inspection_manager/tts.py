"""Voice prompt (TTS) executor core.

Pluggable TTS backend (``MockTTSBackend`` for tests; a real engine on-board) plus a
``VoiceThrottle`` that suppresses repeating the same prompt within a window (so a
persistent hazard doesn't nag every frame). Pure stdlib; the audio side effect lives
in the real backend / node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol


class TTSBackend(Protocol):
    def speak(self, text: str) -> None:
        ...


class MockTTSBackend:
    """Records spoken texts instead of producing audio (testable / dry-run)."""

    def __init__(self) -> None:
        self.spoken: List[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


@dataclass
class VoiceThrottle:
    """Suppress identical prompts repeated within ``window_sec`` (caller passes now)."""

    window_sec: float = 10.0
    _last: Dict[str, float] = field(default_factory=dict)

    def allow(self, text: str, now: float) -> bool:
        last = self._last.get(text)
        if last is not None and now - last < self.window_sec:
            return False
        self._last[text] = now
        return True
