"""App<->robot 建图模式切换的纯逻辑（stdlib only，host 可测）。

状态文件 /root/.robot_mode 是单一事实源；ModeController 通过注入的 run_script
执行 mapping_mode_on/off.sh，不在此处直接起停进程，便于单测。
"""
from __future__ import annotations

import os
from typing import Callable

MODE_NORMAL = "normal"
MODE_SWITCHING = "switching"
MODE_MAPPING = "mapping"
MODE_ERROR = "mapping_error"
VALID_MODES = (MODE_NORMAL, MODE_MAPPING)


def read_mode(state_path: str) -> str:
    try:
        with open(state_path, "r", encoding="utf-8") as fh:
            return fh.read().strip() or MODE_NORMAL
    except OSError:
        return MODE_NORMAL


def write_mode(state_path: str, mode: str) -> None:
    with open(state_path, "w", encoding="utf-8") as fh:
        fh.write(mode)


class SwitchLock:
    """单节点用的带超时文件锁：新鲜锁占用即拒，过期锁可抢。"""

    def __init__(self, lock_path: str, timeout_s: float, now: Callable[[], float]):
        self.lock_path = lock_path
        self.timeout_s = timeout_s
        self.now = now

    def acquire(self) -> bool:
        ts = self._read_ts()
        if ts is not None and (self.now() - ts) < self.timeout_s:
            return False
        self._write_ts(self.now())
        return True

    def release(self) -> None:
        try:
            os.remove(self.lock_path)
        except OSError:
            pass

    def _read_ts(self):
        try:
            with open(self.lock_path, "r", encoding="utf-8") as fh:
                return float(fh.read().strip())
        except (OSError, ValueError):
            return None

    def _write_ts(self, ts: float) -> None:
        with open(self.lock_path, "w", encoding="utf-8") as fh:
            fh.write(str(ts))
