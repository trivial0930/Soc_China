"""ROS node: mic -> KWS/VAD/ASR -> intent -> dispatch_command -> CommandExecutor + TTS.

Thin shell over pure modules. Subscribes /inspection/voice_control for the App remote
on/off switch and persists the enabled state so it survives restarts.
"""
from __future__ import annotations

import json
import os

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import Bool, String

from inspection_manager.asr_controller import AsrController
from inspection_manager.asr_engine import SherpaAsrBackend
from inspection_manager.command_executor import CommandExecutor
from inspection_manager.command_receiver import dispatch_command


class AsrNode(Node):
    def __init__(self) -> None:
        super().__init__("asr_node")
        gp = self.declare_parameter
        for name, default in [
            ("enabled", True), ("mic_device", ""), ("sample_rate", 16000), ("num_threads", 2),
            ("kws_model_dir", ""), ("kws_keywords_file", ""), ("vad_model", ""), ("asr_model_dir", ""),
            ("dialog_timeout_sec", 8.0), ("wake_ack_text", "我在"), ("tick_sec", 0.05),
            ("vlm_fallback_enabled", True), ("vlm_base_url", "http://localhost:8080/v1"),
            ("vlm_model", "qwen2.5-7b-instruct"), ("vlm_api_key", ""),
            ("vlm_min_confidence", 0.5), ("stations_config", ""), ("gimbal_aim_config", ""),
            ("voice_topic", "/inspection/voice"), ("voice_control_topic", "/inspection/voice_control"),
            ("enabled_state_file", "~/.asr_enabled"), ("gimbal_topic", "/gimbal/target_angle"),
            ("gimbal_enable_topic", "/gimbal/enable"), ("laser_topic", "/laser/enable"),
            ("laser_indicate_sec", 8.0),
        ]:
            gp(name, default)
        g = self.get_parameter
        self._state_file = os.path.expanduser(str(g("enabled_state_file").value))

        self._string_pubs = {
            "voice_topic": self.create_publisher(String, str(g("voice_topic").value), 10),
        }
        self._vector_pubs = {
            "gimbal_topic": self.create_publisher(Vector3, str(g("gimbal_topic").value), 10),
        }
        self._bool_pubs = {
            "gimbal_enable_topic": self.create_publisher(Bool, str(g("gimbal_enable_topic").value), 10),
            "laser_topic": self.create_publisher(Bool, str(g("laser_topic").value), 10),
        }
        executor = CommandExecutor(self._publish_primitive, self.create_timer,
                                   float(g("laser_indicate_sec").value))

        stations_cfg = self._read_yaml(str(g("stations_config").value))
        gimbal_cfg = self._read_yaml(str(g("gimbal_aim_config").value))
        vlm_chat = self._make_vlm_chat() if bool(g("vlm_fallback_enabled").value) else None

        backend = SherpaAsrBackend({
            "mic_device": str(g("mic_device").value), "sample_rate": int(g("sample_rate").value),
            "num_threads": int(g("num_threads").value), "kws_model_dir": str(g("kws_model_dir").value),
            "kws_keywords_file": str(g("kws_keywords_file").value), "vad_model": str(g("vad_model").value),
            "asr_model_dir": str(g("asr_model_dir").value),
        })

        from inspection_manager.intent import parse_intent
        self.controller = AsrController(
            backend, parse_intent, dispatch_command, executor,
            self._speak, stations_cfg=stations_cfg, gimbal_cfg=gimbal_cfg,
            dialog_timeout_sec=float(g("dialog_timeout_sec").value),
            enabled=self._load_enabled(bool(g("enabled").value)),
            vlm_chat_fn=vlm_chat, wake_ack_text=str(g("wake_ack_text").value))

        self.create_subscription(String, str(g("voice_control_topic").value), self._on_voice_control, 10)
        self._clock = self.get_clock()
        self.create_timer(float(g("tick_sec").value), self._on_tick)
        self.get_logger().info("asr_node up")

    # --- glue ---
    def _publish_primitive(self, topic_key: str, kind: str, data) -> None:
        if kind == "vector3":
            x, y, z = data
            self._vector_pubs[topic_key].publish(Vector3(x=float(x), y=float(y), z=float(z)))
        elif kind == "bool":
            self._bool_pubs[topic_key].publish(Bool(data=bool(data)))
        else:
            self._string_pubs[topic_key].publish(String(data=data))

    def _speak(self, text: str) -> None:
        self._string_pubs["voice_topic"].publish(String(data=text))

    def _on_tick(self) -> None:
        self.controller.tick(self._clock.now().nanoseconds / 1e9)

    def _on_voice_control(self, msg: String) -> None:
        try:
            enabled = bool(json.loads(msg.data).get("enabled"))
        except (ValueError, TypeError):
            return
        self.controller.set_enabled(enabled)
        self._save_enabled(enabled)

    # --- enabled persistence ---
    def _load_enabled(self, default: bool) -> bool:
        try:
            with open(self._state_file, "r", encoding="utf-8") as fh:
                return fh.read().strip() == "1"
        except OSError:
            return default

    def _save_enabled(self, enabled: bool) -> None:
        try:
            with open(self._state_file, "w", encoding="utf-8") as fh:
                fh.write("1" if enabled else "0")
        except OSError as exc:  # noqa: BLE001
            self.get_logger().warn(f"persist enabled failed: {exc}")

    def _make_vlm_chat(self):
        from inspection_manager.qwen_client import OpenAICompatVLMClient
        g = self.get_parameter
        client = OpenAICompatVLMClient(
            model=str(g("vlm_model").value),
            base_url=str(g("vlm_base_url").value),
            api_key=str(g("vlm_api_key").value),
        )

        def chat(prompt: str) -> str:
            return client.chat_text(prompt)  # text-only helper; no image
        return chat

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001
            return {}


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AsrNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
