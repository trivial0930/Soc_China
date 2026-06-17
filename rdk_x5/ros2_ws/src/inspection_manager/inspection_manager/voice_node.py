"""Voice (TTS) executor node: speak Layer 2 voice prompts.

Subscribes /inspection/voice and speaks each prompt through an offline TTS engine,
throttling repeats. The engine is selected by ``tts_engine`` (none|espeak|piper);
the prompt text is passed safely (argv/stdin, never a shell string). With engine
``none`` it just logs (dry-run). The pure throttle + injection-safe command
assembly live in tts.py (unit-tested).

Params:
  tts_engine    : "none" (log only) | "espeak" | "piper"
  aplay_device  : ALSA device for piper playback, e.g. "plughw:1,0" (the USB speaker)
  piper_bin     : path to the piper binary on-board
  piper_model   : path to the piper voice model (.onnx) on-board
  espeak_voice  : espeak-ng voice (Mandarin: "zh", some builds "cmn")
  espeak_speed  : words per minute
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.tts import VoiceThrottle, make_tts_backend


class VoiceNode(Node):
    def __init__(self) -> None:
        super().__init__("voice_node")
        self.declare_parameter("voice_topic", "/inspection/voice")
        self.declare_parameter("tts_engine", "none")  # none|espeak|piper
        self.declare_parameter("aplay_device", "")  # e.g. "plughw:1,0" (USB speaker)
        self.declare_parameter("piper_bin", "piper")
        self.declare_parameter("piper_model", "")
        self.declare_parameter("espeak_voice", "zh")
        self.declare_parameter("espeak_speed", 160)
        self.declare_parameter("throttle_sec", 10.0)

        gp = self.get_parameter
        self.engine = str(gp("tts_engine").value)
        self.backend = make_tts_backend(
            self.engine,
            espeak_voice=str(gp("espeak_voice").value),
            espeak_speed=int(gp("espeak_speed").value),
            piper_bin=str(gp("piper_bin").value),
            piper_model=str(gp("piper_model").value),
            aplay_device=str(gp("aplay_device").value),
        )
        self.throttle = VoiceThrottle(float(gp("throttle_sec").value))
        self.create_subscription(
            String, str(gp("voice_topic").value), self._on_voice, 10
        )
        self.get_logger().info(f"voice_node up (engine={self.engine})")

    def _on_voice(self, msg: String) -> None:
        text = msg.data
        if not text or not self.throttle.allow(text, time.monotonic()):
            return
        if self.engine in ("", "none"):
            self.get_logger().info(f"[voice] {text}")
            return
        try:  # pragma: no cover - needs a TTS engine on-board
            self.backend.speak(text)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"tts failed: {exc}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VoiceNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
