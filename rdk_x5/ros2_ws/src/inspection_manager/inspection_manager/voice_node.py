"""Voice (TTS) executor node: speak Layer 2 voice prompts.

Subscribes /inspection/voice and speaks each prompt, throttling repeats. The TTS
side effect is a configurable shell command (``tts_cmd``, e.g. ``espeak-ng -v zh "{text}"``
or macOS ``say "{text}"``); with no command it just logs (dry-run). The pure
throttle lives in tts.py (unit-tested).
"""

from __future__ import annotations

import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.tts import VoiceThrottle


class VoiceNode(Node):
    def __init__(self) -> None:
        super().__init__("voice_node")
        self.declare_parameter("voice_topic", "/inspection/voice")
        self.declare_parameter("tts_cmd", "")  # e.g. 'espeak-ng -v zh "{text}"'
        self.declare_parameter("throttle_sec", 10.0)

        self.tts_cmd = str(self.get_parameter("tts_cmd").value)
        self.throttle = VoiceThrottle(float(self.get_parameter("throttle_sec").value))
        self.create_subscription(
            String, str(self.get_parameter("voice_topic").value), self._on_voice, 10
        )

    def _on_voice(self, msg: String) -> None:
        text = msg.data
        if not text or not self.throttle.allow(text, time.monotonic()):
            return
        if not self.tts_cmd:
            self.get_logger().info(f"[voice] {text}")
            return
        try:  # pragma: no cover - needs a TTS engine on-board
            subprocess.Popen(self.tts_cmd.format(text=text), shell=True)
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
