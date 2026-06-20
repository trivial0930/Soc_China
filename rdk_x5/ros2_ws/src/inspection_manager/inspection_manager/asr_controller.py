"""Voice interaction state machine + orchestration. Pure (no rclpy/sherpa).

States: disabled -> (set_enabled True) -> idle(KWS only) -> (wake) -> dialog(VAD+ASR)
        dialog -> (silence > timeout) -> idle ;  any -> (set_enabled False) -> disabled
tick(now) processes at most one backend event plus the dialog-timeout check; the node
calls it on a fast timer. Rule intent first; optional VLM fallback via vlm_chat_fn.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from inspection_manager import dialog
from inspection_manager.intent import vlm_fallback


class AsrController:
    def __init__(self, backend, intent_fn: Callable[[str], Optional[Dict]],
                 dispatch_fn: Callable[[Dict, Dict, Dict], Dict], executor,
                 speak_fn: Callable[[str], None], *, stations_cfg: Dict, gimbal_cfg: Dict,
                 dialog_timeout_sec: float = 8.0, enabled: bool = True,
                 vlm_chat_fn: Optional[Callable[[str], str]] = None,
                 wake_ack_text: str = "我在") -> None:
        self._be = backend
        self._intent = intent_fn
        self._dispatch = dispatch_fn
        self._ex = executor
        self._speak = speak_fn
        self._stations = stations_cfg
        self._gimbal = gimbal_cfg
        self._timeout = float(dialog_timeout_sec)
        self._vlm_chat = vlm_chat_fn
        self._wake_text = wake_ack_text
        self._last_activity = 0.0
        self.state = "disabled"
        self.set_enabled(enabled)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.state = "idle"
            self._be.set_mode("kws")
        else:
            self.state = "disabled"
            self._be.set_mode("off")

    def tick(self, now: float) -> None:
        if self.state == "disabled":
            return
        if self.state == "dialog" and (now - self._last_activity) > self._timeout:
            self.state = "idle"
            self._be.set_mode("kws")
            return
        ev = self._be.poll()
        if not ev:
            return
        if ev["kind"] == "wake" and self.state == "idle":
            self.state = "dialog"
            self._be.set_mode("dialog")
            self._last_activity = now
            self._speak(dialog.wake_ack(self._wake_text))
        elif ev["kind"] == "utterance" and self.state == "dialog":
            self._last_activity = now
            self._handle_text(ev["text"])

    def _handle_text(self, text: str) -> None:
        cmd = self._intent(text)
        if cmd is None and self._vlm_chat is not None:
            cmd = vlm_fallback(text, self._vlm_chat)
        if cmd is None:
            self._speak(dialog.not_understood())
            return
        plan = self._dispatch(cmd, self._stations, self._gimbal)
        if "unsupported" not in plan:
            self._ex.execute(plan)
        self._speak(dialog.reply_for(cmd["type"], plan))
