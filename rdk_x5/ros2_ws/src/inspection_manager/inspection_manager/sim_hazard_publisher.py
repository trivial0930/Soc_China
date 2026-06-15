"""Simulated Layer 1 publisher: replay synthetic /hazard/events with no detector.

Lets the whole inspection pipeline (cognition -> actions -> report) run on a PC
in ROS without a camera / thermal / BPU. Cycles through ``sim_scenarios.sample_events``
on a timer. The events themselves come from a pure, unit-tested builder.

  ros2 run inspection_manager sim_hazard_publisher
"""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.sim_scenarios import sample_events


class SimHazardPublisher(Node):
    def __init__(self) -> None:
        super().__init__("sim_hazard_publisher")
        self.declare_parameter("events_topic", "/hazard/events")
        self.declare_parameter("period_sec", 5.0)

        self.pub = self.create_publisher(
            String, str(self.get_parameter("events_topic").value), 10
        )
        self.events = sample_events()
        self.idx = 0
        period = max(float(self.get_parameter("period_sec").value), 0.5)
        self.create_timer(period, self._tick)

    def _tick(self) -> None:
        event = self.events[self.idx % len(self.events)]
        self.idx += 1
        self.pub.publish(String(data=json.dumps(event, ensure_ascii=False)))
        self.get_logger().info(f"sim published {event['event_id']} ({event['severity']})")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimHazardPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
