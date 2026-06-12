#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time

import rclpy
from geometry_msgs.msg import Vector3
from std_msgs.msg import Bool
from std_srvs.srv import Trigger


def call_stop(node, timeout_sec: float) -> None:
    client = node.create_client(Trigger, "/gimbal/stop")
    if not client.wait_for_service(timeout_sec=timeout_sec):
        node.get_logger().warning("/gimbal/stop service is not available")
        return
    future = client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, future, timeout_sec=timeout_sec)


def interpolate(a: float, b: float, phase: float) -> float:
    return (a + b) / 2.0 + (b - a) * math.sin(phase) / 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a visible two-axis gimbal swing demo.")
    parser.add_argument("--duration", type=float, default=24.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--period", type=float, default=4.0)
    parser.add_argument("--pan-left", type=float, default=-35.0)
    parser.add_argument("--pan-right", type=float, default=35.0)
    parser.add_argument("--tilt-up", type=float, default=-20.0)
    parser.add_argument("--tilt-down", type=float, default=30.0)
    parser.add_argument("--no-final-stop", action="store_true")
    args = parser.parse_args()

    rclpy.init()
    node = rclpy.create_node("gimbal_swing_demo")
    target_pub = node.create_publisher(Vector3, "/gimbal/target_angle", 10)
    enable_pub = node.create_publisher(Bool, "/gimbal/enable", 10)

    call_stop(node, timeout_sec=3.0)
    start = time.monotonic()
    next_enable = 0.0
    interval = 1.0 / max(args.rate, 1.0)

    try:
        while rclpy.ok():
            elapsed = time.monotonic() - start
            if elapsed >= args.duration:
                break

            phase = 2.0 * math.pi * elapsed / max(args.period, 0.1)
            target = Vector3()
            target.x = interpolate(args.pan_left, args.pan_right, phase)
            target.y = interpolate(args.tilt_up, args.tilt_down, phase + math.pi / 2.0)
            target.z = 0.0
            target_pub.publish(target)

            if elapsed >= next_enable:
                enable = Bool()
                enable.data = True
                enable_pub.publish(enable)
                next_enable = elapsed + 0.5

            rclpy.spin_once(node, timeout_sec=0.0)
            time.sleep(interval)
    finally:
        if not args.no_final_stop:
            call_stop(node, timeout_sec=3.0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
