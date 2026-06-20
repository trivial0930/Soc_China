"""ASR backends behind a small event interface so the controller stays pure.

Events are dicts: {"kind":"wake"} | {"kind":"utterance","text": str}.
MockAsrBackend feeds scripted events for unit tests. SherpaAsrBackend wraps the
sherpa-onnx KWS + VAD + offline SenseVoice recognizer over a sounddevice mic; it
imports sherpa_onnx/sounddevice lazily so this module imports fine on a dev box.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class AsrBackend(Protocol):
    """Structural interface implemented by MockAsrBackend and SherpaAsrBackend."""

    def set_mode(self, mode: str) -> None: ...

    def poll(self) -> Optional[Dict[str, Any]]: ...


def wake_event() -> Dict[str, Any]:
    return {"kind": "wake"}


def utterance_event(text: str) -> Dict[str, Any]:
    return {"kind": "utterance", "text": text}


def _resolve_onnx(model_dir: str, prefix: str) -> str:
    """Resolve <prefix>.onnx, else the preferred epoch-tagged file in a model dir.

    The KWS wenetspeech package ships e.g. encoder-epoch-99-avg-1-...onnx (plus an
    epoch-12 set and .int8 variants). Prefer the float files and the latest epoch.
    """
    import glob
    import os

    exact = os.path.join(model_dir, f"{prefix}.onnx")
    if os.path.exists(exact):
        return exact
    cands = glob.glob(os.path.join(model_dir, f"{prefix}*.onnx"))
    pool = [c for c in cands if ".int8." not in c] or cands
    pool.sort()
    return pool[-1] if pool else exact


class MockAsrBackend:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = list(events)
        self.modes: List[str] = []

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def poll(self) -> Optional[Dict[str, Any]]:
        return self._events.pop(0) if self._events else None


class SherpaAsrBackend:
    """Real backend: sherpa-onnx KWS + VAD + offline SenseVoice over a sounddevice mic.

    Modes: "kws" (idle wake-word spotting) | "dialog" (VAD-segmented full-sentence
    recognition) | "off" (no inference). A sounddevice callback pushes 20ms float32
    blocks onto a queue; poll() (called from the single node-timer thread — sherpa
    inference is not thread-safe) drains the queue and returns at most one event.

    Heavy deps (sherpa_onnx, sounddevice, numpy) import lazily so this module stays
    importable on a dev box. On-board bring-up: see docs/architecture/voice_asr_setup.md.
    Verified on the RDK (not in CI). The KWS result API (get_result vs .result) can
    differ by sherpa-onnx version; adjust _poll_kws if the installed wheel differs.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        import os
        import queue

        import sherpa_onnx
        import sounddevice as sd

        self._cfg = cfg
        self._sr = int(cfg.get("sample_rate", 16000))
        self._device = cfg.get("mic_device") or None  # None = system default
        nthreads = int(cfg.get("num_threads", 2))

        # --- KWS: wake-word spotter ("小巡" / "巡检助手", from keywords_file) ---
        # sherpa-onnx 1.13.3 uses a flat KeywordSpotter(...) ctor (no KeywordSpotterConfig).
        # The wenetspeech model ships epoch-tagged onnx names, so resolve them (prefer the
        # float epoch-99-avg-1 set) rather than assuming encoder.onnx. Verified on-board.
        kdir = cfg["kws_model_dir"]
        self._kws = sherpa_onnx.KeywordSpotter(
            tokens=os.path.join(kdir, "tokens.txt"),
            encoder=_resolve_onnx(kdir, "encoder"),
            decoder=_resolve_onnx(kdir, "decoder"),
            joiner=_resolve_onnx(kdir, "joiner"),
            keywords_file=cfg["kws_keywords_file"],
            num_threads=nthreads,
            keywords_threshold=float(cfg.get("kws_threshold", 0.25)),
        )
        self._kws_stream = self._kws.create_stream()

        # --- VAD: segments dialog speech into utterances (attribute-style config) ---
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = cfg["vad_model"]
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.min_silence_duration = 0.5
        vad_config.silero_vad.min_speech_duration = 0.25
        vad_config.sample_rate = self._sr
        self._vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=30)

        # --- Offline ASR: SenseVoice int8 full-sentence recognition ---
        adir = cfg["asr_model_dir"]
        model = os.path.join(adir, "model.int8.onnx")
        if not os.path.exists(model):  # filename varies by release
            import glob
            cands = sorted(glob.glob(os.path.join(adir, "*.int8.onnx"))) or \
                sorted(glob.glob(os.path.join(adir, "*.onnx")))
            model = cands[0] if cands else model
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=os.path.join(adir, "tokens.txt"),
            num_threads=nthreads,
            use_itn=True,
            language="zh",
        )

        # --- mic capture thread -> queue ---
        self._queue: "queue.Queue" = queue.Queue()
        self._mode = "off"

        def _cb(indata, frames, time_info, status):  # pragma: no cover - board only
            self._queue.put(indata[:, 0].copy())  # mono float32

        self._stream = sd.InputStream(
            device=self._device, samplerate=self._sr, channels=1,
            dtype="float32", blocksize=int(self._sr * 0.02), callback=_cb,
        )
        self._stream.start()

    def set_mode(self, mode: str) -> None:  # pragma: no cover - board only
        self._mode = mode
        if mode == "dialog":
            self._vad.reset()
            self._drain()  # drop the wake word's trailing audio so it isn't recognised
        elif mode == "kws":
            self._drain()

    def poll(self) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        import numpy as np

        chunks = self._drain()
        if not chunks or self._mode == "off":
            return None
        audio = np.concatenate(chunks)
        if self._mode == "kws":
            return self._poll_kws(audio)
        if self._mode == "dialog":
            return self._poll_dialog(audio)
        return None

    def _poll_kws(self, audio) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        self._kws_stream.accept_waveform(self._sr, audio)
        # The spotter reports a hit transiently at the detection frame, so get_result
        # MUST be polled inside the decode loop (a post-loop check misses it). Verified
        # on-board: 0 hits when checked after the loop, hits when checked per-frame.
        while self._kws.is_ready(self._kws_stream):
            self._kws.decode_stream(self._kws_stream)
            if self._kws.get_result(self._kws_stream):
                self._kws.reset_stream(self._kws_stream)  # ready for the next wake
                return wake_event()
        return None

    def _poll_dialog(self, audio) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        self._vad.accept_waveform(audio)
        while not self._vad.empty():
            segment = self._vad.front()
            self._vad.pop()
            stream = self._recognizer.create_stream()
            stream.accept_waveform(self._sr, segment.samples)
            self._recognizer.decode_stream(stream)
            text = (stream.result.text or "").strip()
            if text:
                return utterance_event(text)
        return None

    def _drain(self) -> list:  # pragma: no cover - board only
        import queue
        chunks = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return chunks
