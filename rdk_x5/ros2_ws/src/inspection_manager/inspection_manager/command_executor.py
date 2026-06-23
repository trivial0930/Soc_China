"""Shared executor for dispatch_command() plans (App downlink + voice both use it).

Pure: ROS publishers/timers are injected as `publish(topic_key, kind, data)` and
`schedule(period_sec, callback) -> timer`. The laser_point indication is a timed
routine (clear FAULT -> enable -> sustain target + laser on -> off) because the
gimbal controller faults if target commands stop for >5s.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class CommandExecutor:
    def __init__(self, publish: Callable[[str, str, Any], None],
                 schedule: Callable[[float, Callable[[], None]], Any],
                 laser_indicate_sec: float = 8.0,
                 set_volume: Optional[Callable[[int], None]] = None) -> None:
        self._publish = publish
        self._schedule = schedule
        self._laser_sec = float(laser_indicate_sec)
        self._set_volume = set_volume  # int level 0-100 -> persist TTS playback volume
        self._aim_target: Optional[List[float]] = None
        self._sustain_timer = None
        self._stop_timer = None

    def execute(self, plan: Dict[str, Any]) -> Optional[str]:
        if "laser_aim" in plan:
            self._start_laser(plan["laser_aim"])
        elif "set_volume" in plan:
            if self._set_volume is not None:
                self._set_volume(int(plan["set_volume"]))
        elif "actions" in plan:
            for act in plan["actions"]:
                self._publish(act["topic_key"], act["kind"], act["data"])
        return plan.get("result")

    def _start_laser(self, angle: List[float]) -> None:
        self._aim_target = [float(angle[0]), float(angle[1])]
        self._publish("gimbal_enable_topic", "bool", False)  # clear latched FAULT
        self._publish("gimbal_enable_topic", "bool", True)   # enable closed loop
        self._publish("laser_topic", "bool", True)           # laser on
        for t in (self._sustain_timer, self._stop_timer):
            if t is not None:
                t.cancel()
        self._sustain_timer = self._schedule(0.1, self._aim_tick)
        self._stop_timer = self._schedule(self._laser_sec, self._stop_laser)

    def _aim_tick(self) -> None:
        if self._aim_target:
            self._publish("gimbal_topic", "vector3", [self._aim_target[0], self._aim_target[1], 0.0])

    def _stop_laser(self) -> None:
        # Detach timers before canceling so a re-entrant stop is a no-op.
        sustain, stop = self._sustain_timer, self._stop_timer
        self._sustain_timer = None
        self._stop_timer = None
        self._aim_target = None
        self._publish("laser_topic", "bool", False)
        for t in (sustain, stop):
            if t is not None:
                t.cancel()
