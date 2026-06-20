"""ASR backends behind a small event interface so the controller stays pure.

Events are dicts: {"kind":"wake"} | {"kind":"utterance","text": str}.
MockAsrBackend feeds scripted events for unit tests. SherpaAsrBackend wraps the
sherpa-onnx KWS + VAD + offline SenseVoice recognizer over a sounddevice mic; it
imports sherpa_onnx/sounddevice lazily so this module imports fine on a dev box.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def wake_event() -> Dict[str, Any]:
    return {"kind": "wake"}


def utterance_event(text: str) -> Dict[str, Any]:
    return {"kind": "utterance", "text": text}


class MockAsrBackend:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = list(events)
        self.modes: List[str] = []

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def poll(self) -> Optional[Dict[str, Any]]:
        return self._events.pop(0) if self._events else None


class SherpaAsrBackend:
    """Real backend. Constructed on the RDK; verified on-board (Task 9), not in CI."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        import sherpa_onnx  # noqa: F401  (lazy: only present on the board)
        import sounddevice  # noqa: F401
        self._cfg = cfg
        # KeywordSpotter / VoiceActivityDetector / OfflineRecognizer wiring lives here;
        # implemented against the installed models during on-board bring-up (Task 9).
        raise NotImplementedError("SherpaAsrBackend wiring is completed during on-board bring-up")

    def set_mode(self, mode: str) -> None:  # pragma: no cover - board only
        ...

    def poll(self) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        ...
