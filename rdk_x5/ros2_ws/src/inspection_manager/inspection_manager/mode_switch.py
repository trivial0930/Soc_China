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


class ModeController:
    def __init__(self, *, run_script, state_path, lock_path, on_script, off_script,
                 save_script, now, lock_timeout_s: float = 90.0):
        self.run_script = run_script
        self.state_path = state_path
        self.on_script = on_script
        self.off_script = off_script
        self.save_script = save_script
        self.lock = SwitchLock(lock_path, lock_timeout_s, now)

    def current_mode(self) -> str:
        return read_mode(self.state_path)

    def set_mode(self, target: str) -> dict:
        if target not in VALID_MODES:
            return {"status": "failed", "mode": self.current_mode(),
                    "result": f"非法模式:{target}"}
        cur = self.current_mode()
        if cur == target:
            return {"status": "noop", "mode": cur, "result": f"已处于 {target} 模式"}
        if not self.lock.acquire():
            return {"status": "busy", "mode": cur, "result": "模式切换进行中,请稍后"}
        try:
            write_mode(self.state_path, MODE_SWITCHING)
            if target == MODE_MAPPING:
                rc = self.run_script(self.on_script)
                if rc == 0:
                    write_mode(self.state_path, MODE_MAPPING)
                    return {"status": "done", "mode": MODE_MAPPING, "result": "已进入建图模式"}
                write_mode(self.state_path, MODE_ERROR)
                return {"status": "failed", "mode": MODE_ERROR,
                        "result": f"建图栈启动失败(rc={rc}),已停在安全态"}
            rc = self.run_script(self.off_script)
            write_mode(self.state_path, MODE_NORMAL)
            if rc == 0:
                return {"status": "done", "mode": MODE_NORMAL, "result": "已恢复正常模式"}
            return {"status": "warn", "mode": MODE_NORMAL,
                    "result": f"已退出建图,但语音层部分未恢复(rc={rc}),可重试"}
        finally:
            self.lock.release()
