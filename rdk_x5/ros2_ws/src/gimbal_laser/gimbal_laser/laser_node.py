"""Laser pointer control node: /laser/enable (Bool) -> GPIO on/off.

Marks the hazard the gimbal is aiming at. A 2N7000 N-MOSFET low-side switch on
BOARD 12 drives the <1mW laser (laser+ -> 3.3V, laser- -> drain, source -> GND,
gate <- BOARD 12 with a 10k gate pulldown). BOARD 12 is the one free pin verified
Hobot.GPIO-drivable on this RDK X5 (the other free pins give EINVAL / "no channel").

Reuses HobotGpioLine (active_high handling + noop fallback off-board).
"""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

from gimbal_laser.rdk_x5_gpio import HobotGpioLine


class LaserNode(Node):
    def __init__(self) -> None:
        super().__init__("laser_node")
        self.declare_parameter("laser_pin", 12)
        self.declare_parameter("enable_topic", "/laser/enable")
        self.declare_parameter("active_high", True)

        pin = int(self.get_parameter("laser_pin").value)
        self.line = HobotGpioLine(
            pin=pin, active_high=bool(self.get_parameter("active_high").value)
        )
        self.line.setup_output(initial=False)  # off at boot
        self._on = False

        self.create_subscription(
            Bool, str(self.get_parameter("enable_topic").value), self._on_enable, 10
        )
        self.get_logger().info(f"laser_node up (BOARD {pin})")

    def _on_enable(self, msg: Bool) -> None:
        on = bool(msg.data)
        if on == self._on:
            return  # de-bounce: only write on change
        self._on = on
        try:  # pragma: no cover - needs board GPIO
            self.line.write(on)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"laser write failed: {exc}")
        self.get_logger().info(f"[laser] {'ON' if on else 'OFF'}")

    def destroy_node(self) -> None:  # pragma: no cover - board
        try:
            self.line.disable()
            self.line.cleanup()
        except Exception:  # noqa: BLE001
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LaserNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
