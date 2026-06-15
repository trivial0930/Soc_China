"""Workstation record node (功能4): turn occupancy signals into app-ready records.

Subscribes a per-desk occupancy signal (on-board person detection + snapshot path)
and, when a session ends, writes the record to a JSONL log and publishes it so a
future management app can upload / display the photos + text. The debounce / session
logic is pure (workstation_record.py, unit-tested).

Topics:
  in : /perception/occupancy        (std_msgs/String, JSON {station_id, present, snapshot})
       /inspection/brief            (std_msgs/String, JSON)  -- optional: attach note/hint
  out: /inspection/workstation_record (std_msgs/String, JSON record on session close)
"""

from __future__ import annotations

import json
import os
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_manager.workstation_record import OccupancyTracker, attach_acceptance


class WorkstationRecordNode(Node):
    def __init__(self) -> None:
        super().__init__("workstation_record_node")
        self.declare_parameter("occupancy_topic", "/perception/occupancy")
        self.declare_parameter("brief_topic", "/inspection/brief")
        self.declare_parameter("record_topic", "/inspection/workstation_record")
        self.declare_parameter("enter_after_sec", 2.0)
        self.declare_parameter("leave_after_sec", 5.0)
        self.declare_parameter("records_dir", "workstation_records")

        self.tracker = OccupancyTracker(
            enter_after_sec=float(self.get_parameter("enter_after_sec").value),
            leave_after_sec=float(self.get_parameter("leave_after_sec").value),
        )
        # latest rough note/hint per station, attached to a session when it closes
        self._pending: dict = {}
        self.records_dir = str(self.get_parameter("records_dir").value)
        os.makedirs(self.records_dir, exist_ok=True)

        self.record_pub = self.create_publisher(
            String, str(self.get_parameter("record_topic").value), 10
        )
        self.create_subscription(
            String, str(self.get_parameter("occupancy_topic").value), self._on_occupancy, 10
        )
        self.create_subscription(
            String, str(self.get_parameter("brief_topic").value), self._on_brief, 10
        )

    def _on_brief(self, msg: String) -> None:
        try:
            brief = json.loads(msg.data)
            station = brief.get("event", {}).get("station_id", "")
        except (ValueError, AttributeError):
            return
        if station:
            self._pending[station] = {
                "note": str(brief.get("explanation", "")),
                "hint": str(brief.get("confirmed_severity", "")),
            }

    def _on_occupancy(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            station = str(data["station_id"])
            present = bool(data["present"])
        except (ValueError, KeyError):
            return
        snapshot = str(data.get("snapshot", ""))
        event = self.tracker.observe(station, present, time.monotonic(), snapshot)
        if event == "left":
            session = self.tracker.sessions[-1]
            pending = self._pending.pop(station, None)
            if pending:
                attach_acceptance(session, hint=pending["hint"], note=pending["note"])
            self._emit(session)

    def _emit(self, session) -> None:
        record = session.to_dict()
        path = os.path.join(self.records_dir, "workstation_log.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.record_pub.publish(String(data=json.dumps(record, ensure_ascii=False)))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WorkstationRecordNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
