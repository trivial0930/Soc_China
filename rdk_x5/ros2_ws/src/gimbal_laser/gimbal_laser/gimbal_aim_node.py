"""Detection -> gimbal visual-servoing node (#3).

Subscribes the hazard detections (which carry the target's pixel box, from the
gimbal-mounted camera) and the gimbal's current angle, and publishes a pan/tilt
target that drives the worst hazard toward image centre. Aiming is gated by an
enable flag so it does not fight manual / Layer-2 control.

Pure servo math lives in ``visual_servo.py`` (unit-tested); this node is the thin
ROS wrapper. On-board work is only: confirm the FOV, calibrate the rotation signs
(``invert_pan`` / ``invert_tilt``), and tune ``gain`` / ``deadband_px``.

Topics:
  in : /hazard/status    (std_msgs/String, JSON)  -- objects with boxes (Layer 1)
       /gimbal/angle     (geometry_msgs/Vector3)  -- current pan/tilt
       /gimbal/aim_enable(std_msgs/Bool)          -- gate aiming on/off
  out: /gimbal/target_angle (geometry_msgs/Vector3)
"""

from __future__ import annotations

import json

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import Bool, String

from gimbal_laser.visual_servo import config_from_dict, pick_target, servo_step


class GimbalAimNode(Node):
    def __init__(self) -> None:
        super().__init__("gimbal_aim_node")
        self.declare_parameter("status_topic", "/hazard/status")
        self.declare_parameter("angle_topic", "/gimbal/angle")
        self.declare_parameter("enable_topic", "/gimbal/aim_enable")
        self.declare_parameter("target_topic", "/gimbal/target_angle")
        # Laser marks the hazard being aimed at: on while a target is in view, off
        # when it clears or aiming stops. Empty topic disables the coupling.
        self.declare_parameter("laser_topic", "/laser/enable")
        self.declare_parameter("servo_config", "")

        self.cfg = config_from_dict(self._read_yaml(str(self.get_parameter("servo_config").value)))
        self.enabled = False
        self.cur_pan = 0.0
        self.cur_tilt = 0.0
        self._laser_on = False

        self.target_pub = self.create_publisher(
            Vector3, str(self.get_parameter("target_topic").value), 10
        )
        laser_topic = str(self.get_parameter("laser_topic").value)
        self.laser_pub = (
            self.create_publisher(Bool, laser_topic, 10) if laser_topic else None
        )
        self.create_subscription(
            Vector3, str(self.get_parameter("angle_topic").value), self._on_angle, 10
        )
        self.create_subscription(
            Bool, str(self.get_parameter("enable_topic").value), self._on_enable, 10
        )
        self.create_subscription(
            String, str(self.get_parameter("status_topic").value), self._on_status, 10
        )

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml  # type: ignore

            with open(path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}
        except Exception:  # noqa: BLE001 - optional config
            return {}

    def _on_angle(self, msg: Vector3) -> None:
        self.cur_pan = float(msg.x)
        self.cur_tilt = float(msg.y)

    def _on_enable(self, msg: Bool) -> None:
        self.enabled = bool(msg.data)
        if not self.enabled:
            self._set_laser(False)  # stop pointing when aiming is disabled

    def _set_laser(self, on: bool) -> None:
        """Publish laser on/off, de-bounced (only on change)."""
        if on == self._laser_on or self.laser_pub is None:
            return
        self._laser_on = on
        self.laser_pub.publish(Bool(data=on))

    def _on_status(self, msg: String) -> None:
        if not self.enabled:
            return
        try:
            objects = json.loads(msg.data).get("objects", [])
        except ValueError:
            return
        target = pick_target(objects)
        # Laser on iff there is a hazard target to point at (stays on once centered).
        self._set_laser(target is not None)
        if target is None:
            return
        cmd = servo_step(self.cur_pan, self.cur_tilt, target, self.cfg)
        if cmd.centered:
            return
        self.target_pub.publish(Vector3(x=float(cmd.pan_deg), y=float(cmd.tilt_deg), z=0.0))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GimbalAimNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
