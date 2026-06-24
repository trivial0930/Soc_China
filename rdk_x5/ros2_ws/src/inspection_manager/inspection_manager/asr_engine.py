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


def _should_retry_mic(last_try: float, now: float, interval: float) -> bool:
    """True if enough time elapsed since last_try to retry opening the mic."""
    return now - last_try >= interval


MIC_RETRY_INTERVAL_S = 3.0


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

        import numpy as np
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
        # Many USB mics only do 48kHz, not the model's 16kHz. Open at the model rate
        # if the device supports it, else fall back to the device's native rate and
        # resample each block to 16kHz in poll() (verified on-board with a 48k USB mic).
        self._queue: "queue.Queue" = queue.Queue()
        self._mode = "off"
        self._cap_sr = self._sr
        self._xruns = 0
        self._stream = None
        self._last_mic_try = 0.0   # monotonic; throttle via _should_retry_mic
        self._mic_waiting_logged = False
        # The USB mic disconnects/re-enumerates intermittently. Try once now; if it's
        # not present, DON'T crash — poll() retries every MIC_RETRY_INTERVAL_S and the
        # node keeps running (still responds to /inspection/voice_control).
        if not self._open_mic():
            print(f"[asr_engine] mic '{self._device}' not ready at startup; "
                  f"will retry in poll() every {MIC_RETRY_INTERVAL_S}s", flush=True)

    def _audio_cb(self, indata, frames, time_info, status):  # pragma: no cover - board only
        if status:  # input overflow (xrun): callback starved (e.g. GIL held by inference)
            self._xruns += 1
        self._queue.put(indata[:, 0].copy())  # mono float32

    def _open_mic(self) -> bool:  # pragma: no cover - board only
        """Open the mic stream (16k, else native rate + resample). Configure FIR and
        start the stream. Returns True on success; on failure leaves _stream=None."""
        import numpy as np
        import sounddevice as sd

        def _open(rate):
            # latency="high": large ALSA buffer so brief GIL stalls during inference
            # don't overflow/drop frames (which wrecks recognition).
            return sd.InputStream(device=self._device, samplerate=rate, channels=1,
                                  dtype="float32", blocksize=int(rate * 0.03),
                                  latency="high", callback=self._audio_cb)
        try:
            try:
                stream = _open(self._sr)
                self._cap_sr = self._sr
            except Exception:  # device rejects 16kHz -> native rate + resample
                info = sd.query_devices(self._device, "input")
                self._cap_sr = int(info.get("default_samplerate") or 48000)
                stream = _open(self._cap_sr)
        except Exception:  # noqa: BLE001 - mic absent/unavailable
            return False
        # Stateful anti-aliased decimation (FIR, not IIR: a finite input can't produce
        # inf/nan through a bounded weighted sum, so a transient glitch can't poison the
        # stream; lfilter carries state for gap-free continuity).
        if self._cap_sr != self._sr:
            from scipy.signal import firwin
            self._decim = max(1, round(self._cap_sr / self._sr))
            self._fir_b = firwin(64, 0.9 * self._sr / 2, fs=self._cap_sr).astype("float64")
            self._fir_zi = np.zeros(len(self._fir_b) - 1, dtype="float64")
            self._decim_rem = np.zeros(0, dtype="float32")
        stream.start()
        self._stream = stream
        return True

    def _ensure_mic(self) -> None:  # pragma: no cover - board only
        """If the mic isn't open, retry opening it (throttled). Auto-recovers when the
        user plugs the mic back in."""
        import time
        if self._stream is not None:
            return
        now = time.monotonic()
        if not _should_retry_mic(self._last_mic_try, now, MIC_RETRY_INTERVAL_S):
            return
        self._last_mic_try = now
        if self._open_mic():
            print(f"[asr_engine] mic opened (sr={self._cap_sr})", flush=True)
            self._mic_waiting_logged = False
        elif not self._mic_waiting_logged:
            print("[asr_engine] still waiting for mic...", flush=True)
            self._mic_waiting_logged = True  # log once per outage, don't spam

    def set_mode(self, mode: str) -> None:  # pragma: no cover - board only
        self._mode = mode
        if mode == "dialog":
            self._vad.reset()
            self._drain()  # drop the wake word's trailing audio so it isn't recognised
        elif mode == "kws":
            self._drain()

    def poll(self) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        import os
        import time

        import numpy as np

        self._ensure_mic()
        if self._stream is None:
            return None
        chunks = self._drain()
        # Anti-echo (half-duplex): the TTS daemon touches /tmp/tts_playing only while it's
        # actually playing on the speaker. Mute the mic during playback (+ a short tail for
        # echo decay) so we don't recognise our own voice — but no longer, so the user's
        # command right after the prompt isn't dropped.
        if os.path.exists("/tmp/tts_playing"):
            self._mute_until = time.monotonic() + 0.4
        if time.monotonic() < getattr(self, "_mute_until", 0.0):
            return None
        if not chunks or self._mode == "off":
            return None
        audio = np.concatenate(chunks)
        if self._cap_sr != self._sr:
            audio = self._resample(audio)
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
        import numpy as np
        self._vad.accept_waveform(audio)
        while not self._vad.empty():
            segment = self._vad.front  # 1.13.3: front is a property, not a method
            self._vad.pop()
            stream = self._recognizer.create_stream()
            # segment.samples is a Python list; accept_waveform silently yields an empty
            # transcript unless it's a float32 numpy array (on-board: '' vs correct text).
            samples = np.nan_to_num(np.asarray(segment.samples, dtype="float32"),
                                    nan=0.0, posinf=0.0, neginf=0.0)
            stream.accept_waveform(self._sr, samples)
            self._recognizer.decode_stream(stream)
            text = (stream.result.text or "").strip()
            import sys
            print(f"[asr] heard {text!r}", file=sys.stderr, flush=True)  # on-board ops log
            if text:
                return utterance_event(text)
        return None

    def _resample(self, audio):  # pragma: no cover - board only
        import numpy as np
        from scipy.signal import lfilter
        audio = np.nan_to_num(np.asarray(audio, dtype="float64"), nan=0.0, posinf=0.0, neginf=0.0)
        filt, self._fir_zi = lfilter(self._fir_b, [1.0], audio, zi=self._fir_zi)
        buf = np.concatenate([self._decim_rem, filt.astype("float32")])
        n = (len(buf) // self._decim) * self._decim   # keep decimation phase continuous
        self._decim_rem = buf[n:]
        return buf[0:n:self._decim].astype("float32")

    def _drain(self) -> list:  # pragma: no cover - board only
        import queue
        chunks = []
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return chunks
