"""Lidar safety layer: gate /cmd_vel_teleop by /scan -> /cmd_vel + /safety/status.

Pure ROS glue; all decision logic lives in gate.py (host-tested). Runs locally on
the RDK so obstacle avoidance is independent of any network/teleop latency.
"""
from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

from teleop_safety.gate import GateParams, gate_twist


class LidarSafetyNode(Node):
    def __init__(self):
        super().__init__("lidar_safety")

        self.declare_parameter("scan_topic", "/scan")
        self.declare_parameter("teleop_topic", "/cmd_vel_teleop")
        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("status_topic", "/safety/status")
        self.declare_parameter("control_hz", 20.0)
        self.declare_parameter("cmd_timeout_s", 0.5)   # deadman on teleop staleness
        self.declare_parameter("sector_half_angle_deg", 35.0)
        self.declare_parameter("stop_dist_m", 0.30)
        self.declare_parameter("slow_dist_m", 0.60)
        self.declare_parameter("v_eps", 0.02)
        self.declare_parameter("range_min_m", 0.05)
        self.declare_parameter("range_max_m", 12.0)
        # Near-field self masks: flat list [center_deg, half_deg, near_m, ...].
        # Inside each cone, returns closer than near_m are the robot's own body
        # (dropped); farther returns are still avoided. Default: rear 180 +/-45,
        # body within 0.30 m (measured: lidar rear <30cm is all chassis).
        self.declare_parameter("near_masks", [180.0, 45.0, 0.30])
        # Median window on the gated translation output. The rear near-field is
        # self-occluded (chassis), so when reversing into the slow zone its noisy
        # distance bounces the safety scale frame-to-frame -> judder. A short
        # median rejects those single-frame flickers (both directions) while a
        # sustained real obstacle still slows/stops within ~n/2 ticks.
        self.declare_parameter("smooth_window", 5)

        def gp(n):
            return self.get_parameter(n).value

        import math
        flat = [float(x) for x in (gp("near_masks") or [])]
        masks = tuple((math.radians(flat[i]), math.radians(flat[i + 1]), flat[i + 2])
                      for i in range(0, len(flat) - 2, 3))
        self._params = GateParams(
            sector_half_angle=math.radians(float(gp("sector_half_angle_deg"))),
            stop_dist=float(gp("stop_dist_m")),
            slow_dist=float(gp("slow_dist_m")),
            v_eps=float(gp("v_eps")),
            range_min=float(gp("range_min_m")),
            range_max=float(gp("range_max_m")),
            near_masks=masks,
        )
        if masks:
            self.get_logger().info("near masks [center,half,near deg/m]: %s" % flat)
        self._cmd_timeout = float(gp("cmd_timeout_s"))

        self._scan = None          # latest LaserScan
        self._teleop = (0.0, 0.0, 0.0)
        self._teleop_ts = self.get_clock().now()
        self._smooth_n = max(1, int(gp("smooth_window")))
        self._hist_vx = []            # recent gated vx for median de-flicker
        self._hist_vy = []

        self.create_subscription(LaserScan, str(gp("scan_topic")), self._on_scan, 10)
        self.create_subscription(Twist, str(gp("teleop_topic")), self._on_teleop, 10)
        self._cmd_pub = self.create_publisher(Twist, str(gp("cmd_vel_topic")), 10)
        self._status_pub = self.create_publisher(String, str(gp("status_topic")), 10)

        self.create_timer(1.0 / float(gp("control_hz")), self._tick)
        self.get_logger().info("lidar_safety up: gating %s by %s -> %s"
                               % (gp("teleop_topic"), gp("scan_topic"), gp("cmd_vel_topic")))

    def _on_scan(self, msg: LaserScan):
        self._scan = msg

    def _on_teleop(self, msg: Twist):
        self._teleop = (msg.linear.x, msg.linear.y, msg.angular.z)
        self._teleop_ts = self.get_clock().now()

    def _tick(self):
        out = Twist()
        # Deadman: stale teleop -> stop.
        age = (self.get_clock().now() - self._teleop_ts).nanoseconds * 1e-9
        if age > self._cmd_timeout:
            vx = vy = wz = 0.0
        else:
            vx, vy, wz = self._teleop

        if self._scan is None:
            # No scan yet: fail safe -> only allow rotation, no translation.
            out.linear.x = 0.0
            out.linear.y = 0.0
            out.angular.z = wz
            self._cmd_pub.publish(out)
            self._publish_status("blocked", -1.0)
            return

        s = self._scan
        ovx, ovy, owz, state, front = gate_twist(
            list(s.ranges), s.angle_min, s.angle_increment, vx, vy, wz, self._params)
        # Median de-flicker: rejects single-frame safety-scale bounces (the reverse
        # judder) in both directions without much lag on sustained obstacles.
        out.linear.x = self._median_push(self._hist_vx, float(ovx))
        out.linear.y = self._median_push(self._hist_vy, float(ovy))
        out.angular.z = float(owz)   # rotation is never gated -> no smoothing
        self._cmd_pub.publish(out)
        self._publish_status(state, front)

    def _median_push(self, hist, value):
        hist.append(value)
        if len(hist) > self._smooth_n:
            hist.pop(0)
        return sorted(hist)[len(hist) // 2]

    def _publish_status(self, state, front):
        front_val = None if front == float("inf") else round(float(front), 3)
        self._status_pub.publish(String(data=json.dumps(
            {"state": state, "front_dist_m": front_val})))


def main(args=None):
    rclpy.init(args=args)
    node = LidarSafetyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
