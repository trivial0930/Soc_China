"""Teleop receiver: pull latest velocity from the backend -> /cmd_vel_teleop, and
forward /safety/status back to the backend for the app to display.

Low-latency path (separate from the 2s command queue): polls
GET /api/robot/teleop at poll_hz; the backend stores only the latest setpoint
(overwritten by the app at ~10Hz). Stale setpoints -> zero (deadman).
"""
from __future__ import annotations

import json
import threading
import urllib.request

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class TeleopReceiverNode(Node):
    def __init__(self):
        super().__init__("teleop_receiver")

        self.declare_parameter("backend_url", "http://192.168.128.100:8000")
        self.declare_parameter("ingest_token", "")
        self.declare_parameter("teleop_topic", "/cmd_vel_teleop")
        self.declare_parameter("status_topic", "/safety/status")
        self.declare_parameter("poll_hz", 10.0)
        self.declare_parameter("status_post_hz", 2.0)
        self.declare_parameter("staleness_ms", 400.0)   # backend age beyond this -> zero
        self.declare_parameter("http_timeout_s", 0.3)

        def gp(n):
            return self.get_parameter(n).value

        self._base = str(gp("backend_url")).rstrip("/")
        self._token = str(gp("ingest_token"))
        self._staleness_ms = float(gp("staleness_ms"))
        self._timeout = float(gp("http_timeout_s"))

        self._pub = self.create_publisher(Twist, str(gp("teleop_topic")), 10)
        self.create_subscription(String, str(gp("status_topic")), self._on_status, 10)

        self._last_status = None
        self._status_lock = threading.Lock()

        self.create_timer(1.0 / float(gp("poll_hz")), self._poll)
        self.create_timer(1.0 / float(gp("status_post_hz")), self._post_status)
        self.get_logger().info("teleop_receiver up: %s -> %s @%.0fHz"
                               % (self._base, gp("teleop_topic"), gp("poll_hz")))

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = "Bearer " + self._token
        return h

    def _poll(self):
        t = Twist()
        try:
            req = urllib.request.Request(self._base + "/api/robot/teleop",
                                         headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            age = float(data.get("age_ms", 1e9))
            if age <= self._staleness_ms:
                # The App joystick sends the OLD flipped convention (measured
                # 2026-07-07: a left turn arrives as wz<0). Negate vy+wz here so
                # /cmd_vel is REP-103 (+wz=CCW, +vy=LEFT) like Nav2's output; the
                # stm32_bridge then translates REP-103 -> the firmware convention.
                t.linear.x = float(data.get("vx", 0.0))
                t.linear.y = -float(data.get("vy", 0.0))
                t.angular.z = -float(data.get("wz", 0.0))
            # else: stale -> zeros (deadman)
        except Exception:
            pass  # network hiccup -> publish zeros this tick (fail safe)
        self._pub.publish(t)

    def _on_status(self, msg: String):
        with self._status_lock:
            self._last_status = msg.data

    def _post_status(self):
        with self._status_lock:
            payload = self._last_status
        if payload is None:
            return
        try:
            req = urllib.request.Request(
                self._base + "/api/robot/teleop/status",
                data=payload.encode("utf-8"), headers=self._headers(), method="POST")
            urllib.request.urlopen(req, timeout=self._timeout).read()
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = TeleopReceiverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
