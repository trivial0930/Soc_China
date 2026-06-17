"""Voice prompt (TTS) executor core.

Pluggable TTS backend (``MockTTSBackend`` for tests; a real engine on-board) plus a
``VoiceThrottle`` that suppresses repeating the same prompt within a window (so a
persistent hazard doesn't nag every frame). Pure stdlib; the audio side effect lives
in the real backend / node.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Sequence


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


# --------------------------------------------------------------------------- #
# Real (on-board) TTS — injection-safe command assembly.
#
# The prompt text is model-generated (Qwen) Chinese and may contain quotes,
# semicolons, etc. It is NEVER interpolated into a shell string; it is always a
# single argv element or piped on stdin. These builders are pure and unit-tested.
# --------------------------------------------------------------------------- #
def espeak_args(text: str, voice: str = "zh", speed: int = 160) -> List[str]:
    """espeak-ng argv that speaks ``text`` directly (text is its own argument)."""
    return ["espeak-ng", "-v", str(voice), "-s", str(speed), text]


def piper_synth_args(piper_bin: str, model_path: str, out_wav: str) -> List[str]:
    """piper argv that synthesises a WAV; the text is supplied on stdin, not argv."""
    return [piper_bin, "--model", model_path, "--output_file", out_wav]


def aplay_args(wav_path: str, device: str = "") -> List[str]:
    """aplay argv to play ``wav_path`` on an optional ALSA device (e.g. 'plughw:1,0')."""
    base = ["aplay", "-q"]
    if device:
        base += ["-D", device]
    return base + [wav_path]


# (argv, stdin_text) -> None. Default spawns the process; tests inject a recorder.
Runner = Callable[[Sequence[str], Optional[str]], None]


def _subprocess_runner(args: Sequence[str], stdin_text: Optional[str] = None) -> None:  # pragma: no cover - spawns a process
    subprocess.run(
        list(args),
        input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
        check=True,
        timeout=30,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class SubprocessTTSBackend:
    """Offline TTS that shells out safely and serialises playback.

    ``engine``:
      * ``"espeak"`` — espeak-ng speaks ``text`` directly (tiny, offline, robotic).
      * ``"piper"``  — piper synthesises a WAV from stdin text, then aplay plays it
        on ``aplay_device`` (offline, natural Mandarin; needs the piper binary +
        a voice model staged on-board).

    Injection-safe (text is argv/stdin only) and lock-serialised so overlapping
    prompts don't talk over each other.
    """

    def __init__(
        self,
        engine: str = "espeak",
        *,
        espeak_voice: str = "zh",
        espeak_speed: int = 160,
        piper_bin: str = "piper",
        piper_model: str = "",
        aplay_device: str = "",
        runner: Runner = _subprocess_runner,
    ) -> None:
        self.engine = engine
        self.espeak_voice = espeak_voice
        self.espeak_speed = espeak_speed
        self.piper_bin = piper_bin
        self.piper_model = piper_model
        self.aplay_device = aplay_device
        self._run = runner
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            if self.engine == "piper":
                self._speak_piper(text)
            else:
                self._run(espeak_args(text, self.espeak_voice, self.espeak_speed), None)

    def _speak_piper(self, text: str) -> None:
        fd, wav = tempfile.mkstemp(suffix=".wav", prefix="tts_")
        os.close(fd)
        try:
            self._run(piper_synth_args(self.piper_bin, self.piper_model, wav), text)
            self._run(aplay_args(wav, self.aplay_device), None)
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass


def make_tts_backend(engine: str, **kwargs) -> TTSBackend:
    """Factory: 'none'/'mock' -> MockTTSBackend (dry-run); else SubprocessTTSBackend."""
    if engine in ("", "none", "mock"):
        return MockTTSBackend()
    return SubprocessTTSBackend(engine=engine, **kwargs)
