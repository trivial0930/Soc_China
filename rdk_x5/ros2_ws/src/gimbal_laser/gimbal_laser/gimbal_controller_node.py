from __future__ import annotations

import json
import time

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger

from gimbal_laser.as5600 import AS5600AngleSensor, open_smbus
from gimbal_laser.gimbal_controller import AxisConfig, AxisIO, ControlConfig, GimbalController
from gimbal_laser.rdk_x5_gpio import gpio_line_from_pin
from gimbal_laser.rdk_x5_pwm import PhasePwmMotor, pwm_channel_from_pin


class GimbalControllerNode(Node):
    def __init__(self) -> None:
        super().__init__("gimbal_controller_node")
        self._declare_parameters()

        status_topic = str(self.get_parameter("status_topic").value)
        angle_topic = str(self.get_parameter("angle_topic").value)
        target_topic = str(self.get_parameter("target_topic").value)
        enable_topic = str(self.get_parameter("enable_topic").value)

        self.status_pub = self.create_publisher(String, status_topic, 10)
        self.angle_pub = self.create_publisher(Vector3, angle_topic, 10)
        self.create_subscription(Vector3, target_topic, self._on_target, 10)
        self.create_subscription(Bool, enable_topic, self._on_enable, 10)
        self.create_service(Trigger, "/gimbal/home", self._on_home)
        self.create_service(Trigger, "/gimbal/stop", self._on_stop)

        self.controller = self._build_controller()
        loop_hz = max(float(self.get_parameter("loop_hz").value), 1.0)
        self.timer = self.create_timer(1.0 / loop_hz, self._tick)

    def _declare_parameters(self) -> None:
        defaults = {
            "pan_i2c_bus": 5,
            "pan_encoder_address": 0x36,
            "pan_zero_deg": 47.99,
            "pan_min_deg": -60.0,
            "pan_max_deg": 60.0,
            "pan_invert": False,
            "pan_pole_pairs": 8,
            "pan_phase_offset_deg": 66.0,
            "pan_pwm_pins": [29, 31, 37],
            "pan_enable_pin": 38,
            "tilt_i2c_bus": 1,
            "tilt_encoder_address": 0x36,
            "tilt_zero_deg": -108.28,
            "tilt_min_deg": -30.0,
            "tilt_max_deg": 45.0,
            "tilt_invert": False,
            "tilt_pole_pairs": 7,
            "tilt_phase_offset_deg": 138.0,
            "tilt_pwm_pins": [18, 28, 27],
            "tilt_enable_pin": 40,
            "loop_hz": 100.0,
            "pwm_frequency_hz": 20000,
            "max_duty": 0.08,
            "startup_duty": 0.022,
            "angle_deadband_deg": 1.0,
            "command_timeout_sec": 5.0,
            "proportional_gain": 0.005,
            "target_slew_rate_deg_s": 32.0,
            "duty_slew_rate_per_sec": 1.25,
            "status_topic": "/gimbal/status",
            "angle_topic": "/gimbal/angle",
            "target_topic": "/gimbal/target_angle",
            "enable_topic": "/gimbal/enable",
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)

    def _build_controller(self) -> GimbalController:
        pwm_frequency = int(self.get_parameter("pwm_frequency_hz").value)

        pan_bus = open_smbus(int(self.get_parameter("pan_i2c_bus").value))
        tilt_bus = open_smbus(int(self.get_parameter("tilt_i2c_bus").value))

        pan_sensor = AS5600AngleSensor(
            bus=pan_bus,
            address=int(self.get_parameter("pan_encoder_address").value),
            zero_deg=float(self.get_parameter("pan_zero_deg").value),
            invert=bool(self.get_parameter("pan_invert").value),
        )
        tilt_sensor = AS5600AngleSensor(
            bus=tilt_bus,
            address=int(self.get_parameter("tilt_encoder_address").value),
            zero_deg=float(self.get_parameter("tilt_zero_deg").value),
            invert=bool(self.get_parameter("tilt_invert").value),
        )

        pan_motor = self._build_motor("pan", pwm_frequency)
        tilt_motor = self._build_motor("tilt", pwm_frequency)
        pan_motor.setup()
        tilt_motor.setup()

        return GimbalController(
            pan=AxisIO(
                config=AxisConfig(
                    name="pan",
                    min_deg=float(self.get_parameter("pan_min_deg").value),
                    max_deg=float(self.get_parameter("pan_max_deg").value),
                    invert=bool(self.get_parameter("pan_invert").value),
                    pole_pairs=int(self.get_parameter("pan_pole_pairs").value),
                    phase_offset_deg=float(self.get_parameter("pan_phase_offset_deg").value),
                ),
                sensor=pan_sensor,
                motor=pan_motor,
            ),
            tilt=AxisIO(
                config=AxisConfig(
                    name="tilt",
                    min_deg=float(self.get_parameter("tilt_min_deg").value),
                    max_deg=float(self.get_parameter("tilt_max_deg").value),
                    invert=bool(self.get_parameter("tilt_invert").value),
                    pole_pairs=int(self.get_parameter("tilt_pole_pairs").value),
                    phase_offset_deg=float(self.get_parameter("tilt_phase_offset_deg").value),
                ),
                sensor=tilt_sensor,
                motor=tilt_motor,
            ),
            config=ControlConfig(
                max_duty=float(self.get_parameter("max_duty").value),
                startup_duty=float(self.get_parameter("startup_duty").value),
                angle_deadband_deg=float(self.get_parameter("angle_deadband_deg").value),
                command_timeout_sec=float(self.get_parameter("command_timeout_sec").value),
                proportional_gain=float(self.get_parameter("proportional_gain").value),
                target_slew_rate_deg_s=float(
                    self.get_parameter("target_slew_rate_deg_s").value
                ),
                duty_slew_rate_per_sec=float(
                    self.get_parameter("duty_slew_rate_per_sec").value
                ),
            ),
        )

    def _build_motor(self, prefix: str, pwm_frequency: int) -> PhasePwmMotor:
        pins = [int(pin) for pin in self.get_parameter(f"{prefix}_pwm_pins").value]
        enable_pin = int(self.get_parameter(f"{prefix}_enable_pin").value)
        channels = [pwm_channel_from_pin(pin, pwm_frequency) for pin in pins]
        enable_line = gpio_line_from_pin(enable_pin)
        return PhasePwmMotor(channels=channels, enable_line=enable_line)

    def _on_target(self, msg: Vector3) -> None:
        status = self.controller.set_target(float(msg.x), float(msg.y), self._now_sec())
        self._publish_status(status)

    def _on_enable(self, msg: Bool) -> None:
        status = self.controller.set_enabled(bool(msg.data), self._now_sec())
        self._publish_status(status)

    def _on_home(self, request, response):
        self.controller.target_pan_deg = self.controller.last_pan_deg
        self.controller.target_tilt_deg = self.controller.last_tilt_deg
        response.success = True
        response.message = "current angle captured as target"
        return response

    def _on_stop(self, request, response):
        status = self.controller.stop("operator_stop")
        self._publish_status(status)
        response.success = True
        response.message = "gimbal stopped"
        return response

    def _tick(self) -> None:
        status = self.controller.step(self._now_sec())
        self._publish_status(status)
        angle_msg = Vector3()
        angle_msg.x = status.pan_deg
        angle_msg.y = status.tilt_deg
        angle_msg.z = 0.0
        self.angle_pub.publish(angle_msg)

    def _publish_status(self, status) -> None:
        msg = String()
        msg.data = json.dumps(status.as_dict(), ensure_ascii=True)
        self.status_pub.publish(msg)

    def _now_sec(self) -> float:
        return time.monotonic()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GimbalControllerNode()
    try:
        rclpy.spin(node)
    finally:
        node.controller.stop("shutdown")
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
