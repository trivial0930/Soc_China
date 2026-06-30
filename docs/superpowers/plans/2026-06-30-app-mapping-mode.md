# App 建图模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App 一键进入建图模式：RDK 自动停重负载层（语音/认知/VLM）腾 CPU+内存、起整套建图栈；OFF 拆建图栈、恢复重负载层；建图中可一键存图。

**Architecture:** 方案 A——命令通道（uplink + command_receiver + acceptance）是永不被杀的常驻层，`command_receiver_node` 收到 `set_mode`/`save_map` 命令后调用 `mapping_mode_on.sh`/`mapping_mode_off.sh` 编排切换。`/root/.robot_mode` 状态文件是单一事实源，由 command_receiver 在 2s 轮询同 tick 上报给后端。纯切换逻辑（状态机/锁/幂等）抽到 stdlib-only 的 `mode_switch.py` 做 host 单测；脚本和 rclpy node 是薄壳。

**Tech Stack:** Python 3 (stdlib only for pure logic)、rclpy (Humble)、bash、pytest、ROS2 launch。

## Global Constraints

- 纯逻辑模块 stdlib only（不引 pip 依赖），与 `command_receiver.py`/`uplink.py` 同风格。
- 切换时**绝不**杀命令通道三件：`uplink_node`、`command_receiver_node`、`acceptance_node`。
- `systemctl stop voice-asr` 对节点无效（KillMode=process + setsid 孤儿）——一律用脚本精确 `pkill -9 -f <pattern>`。
- 状态值仅四种：`normal` / `switching` / `mapping` / `mapping_error`。失败"停在安全态、不自动回滚"。
- 重负载子集 pkill 模式（确认过的真实进程名）：`llama-server`、`tts_server.py`、`voice_node`、`report_service`、`cognition_node`、`gimbal_controller_node`、`laser_node`、`asr_node`。
- 建图栈 pkill 模式：`mapping.launch`、`lslidar_driver_node`、`async_slam_toolbox_node`、`ekf_node`、`stm32_bridge_node`、`bmi088_imu_node`、`lidar_safety_node`、`teleop_receiver_node`。
- 状态文件 `/root/.robot_mode`，锁文件 `/run/robot_mode.lock`，锁超时 90s。
- 仓库路径用 `~/projects/Soc_China`；RDK 上对应 `/root/Soc_China`。新 bash 脚本放 `rdk_x5/scripts/`，部署到 RDK 后由 command_receiver 以绝对路径 `/root/Soc_China/rdk_x5/scripts/<name>` 调用。
- 提交习惯：每个 task 结束 commit；除非任务指明，不 push。

---

## File Structure

- **Create** `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py` — 纯切换逻辑：状态文件 I/O、`SwitchLock`、`ModeController`（set_mode / save_map）。stdlib only，host 可测。
- **Modify** `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver.py` — `dispatch_command` 识别 `set_mode` / `save_map`（仅校验，返回 `{"set_mode": ...}` / `{"save_map": ...}`，仿 `set_volume`/`laser_aim`）。
- **Modify** `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py` — 实例化 `ModeController`；`_handle` 里 set_mode/save_map 走后台线程执行后 `_report`；`_poll` 末尾上报当前 mode。
- **Create** `rdk_x5/scripts/mapping_mode_on.sh` — pkill 重负载子集 → 起 mapping.launch → 校验(≤30s) → 失败自清并 exit≠0。
- **Create** `rdk_x5/scripts/mapping_mode_off.sh` — pkill 建图栈 → 重跑重负载 start 脚本。
- **Create** `rdk_x5/scripts/save_map.sh` — `map_saver_cli -f ~/maps/<name>`。
- **Create** `tests/test_mode_switch.py` — ModeController/lock/state host 单测。
- **Modify** `tests/test_command_receiver.py` — set_mode/save_map dispatch 用例。
- **Modify** `docs/ops/lab_mapping_procedure.md` — 改成 App 一键为主、手动 launch 为备。
- **Create** `app/BACKEND_PROMPT_mapping_mode.md` + `app/FRONTEND_PROMPT_mapping_mode.md`。

---

### Task 1: mode_switch 状态文件 + 锁原语

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py`
- Test: `tests/test_mode_switch.py`

**Interfaces:**
- Produces:
  - 常量 `MODE_NORMAL="normal"`, `MODE_SWITCHING="switching"`, `MODE_MAPPING="mapping"`, `MODE_ERROR="mapping_error"`, `VALID_MODES=("normal","mapping")`
  - `read_mode(state_path: str) -> str`（缺失/读失败回 `"normal"`）
  - `write_mode(state_path: str, mode: str) -> None`
  - `SwitchLock(lock_path: str, timeout_s: float, now: Callable[[], float])`，方法 `acquire() -> bool`、`release() -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mode_switch.py
import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5/ros2_ws/src/inspection_manager"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from inspection_manager.mode_switch import (  # noqa: E402
    MODE_NORMAL, MODE_MAPPING, read_mode, write_mode, SwitchLock,
)


class StateFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.id().replace(".", "_"))
        self.state = str(self.tmp.with_suffix(".mode"))

    def tearDown(self):
        for p in (self.state,):
            try:
                Path(p).unlink()
            except OSError:
                pass

    def test_missing_state_reads_normal(self):
        self.assertEqual(read_mode("/no/such/file"), MODE_NORMAL)

    def test_write_then_read_roundtrip(self):
        write_mode(self.state, MODE_MAPPING)
        self.assertEqual(read_mode(self.state), MODE_MAPPING)


class SwitchLockTest(unittest.TestCase):
    def setUp(self):
        self.lock_path = str(Path(self.id().replace(".", "_")).with_suffix(".lock"))
        self.t = [100.0]

    def tearDown(self):
        try:
            Path(self.lock_path).unlink()
        except OSError:
            pass

    def now(self):
        return self.t[0]

    def test_acquire_then_fresh_reacquire_busy(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        lk2 = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertFalse(lk2.acquire())   # held & fresh

    def test_stale_lock_is_stealable(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        self.t[0] += 91.0                 # past timeout
        lk2 = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk2.acquire())

    def test_release_allows_reacquire(self):
        lk = SwitchLock(self.lock_path, 90.0, self.now)
        self.assertTrue(lk.acquire())
        lk.release()
        self.assertTrue(SwitchLock(self.lock_path, 90.0, self.now).acquire())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py -q`
Expected: FAIL（`ModuleNotFoundError: inspection_manager.mode_switch`）

- [ ] **Step 3: 写最小实现**

```python
# rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py tests/test_mode_switch.py
git commit -m "feat(mode_switch): state file + timeout switch-lock primitives"
```

---

### Task 2: ModeController.set_mode 状态机

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py`
- Test: `tests/test_mode_switch.py`

**Interfaces:**
- Consumes: Task 1 的常量、`read_mode`/`write_mode`、`SwitchLock`
- Produces:
  - `ModeController(*, run_script, state_path, lock_path, on_script, off_script, save_script, now, lock_timeout_s=90.0)`
    - `run_script: Callable[[str], int]`（执行一条 shell 命令，返回 returncode）
    - `now: Callable[[], float]`
  - `ModeController.current_mode() -> str`
  - `ModeController.set_mode(target: str) -> dict`，返回 `{"status", "mode", "result"}`，status ∈ {`done`,`failed`,`busy`,`noop`,`warn`}

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_mode_switch.py（import 行补上 MODE_SWITCHING, MODE_ERROR, ModeController）
from inspection_manager.mode_switch import (  # noqa: E402,F811
    MODE_NORMAL, MODE_MAPPING, MODE_SWITCHING, MODE_ERROR,
    read_mode, write_mode, SwitchLock, ModeController,
)


class _Ctl:
    """构造一个 ModeController，记录被调用的脚本。"""
    def __init__(self, tmpbase, current=MODE_NORMAL, rc=0):
        self.state = str(Path(tmpbase).with_suffix(".mode"))
        self.lock = str(Path(tmpbase).with_suffix(".lock"))
        write_mode(self.state, current)
        self.calls = []
        self.rc = rc
        self.t = [100.0]
        self.ctl = ModeController(
            run_script=self._run, state_path=self.state, lock_path=self.lock,
            on_script="ON", off_script="OFF", save_script="SAVE",
            now=lambda: self.t[0], lock_timeout_s=90.0)

    def _run(self, cmd):
        self.calls.append(cmd)
        return self.rc

    def cleanup(self):
        for p in (self.state, self.lock):
            try:
                Path(p).unlink()
            except OSError:
                pass


class SetModeTest(unittest.TestCase):
    def base(self):
        return Path(self.id().replace(".", "_"))

    def test_enter_mapping_success(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "done")
            self.assertEqual(r["mode"], MODE_MAPPING)
            self.assertEqual(c.calls, ["ON"])
            self.assertEqual(read_mode(c.state), MODE_MAPPING)
        finally:
            c.cleanup()

    def test_enter_mapping_failure_stays_error(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=1)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "failed")
            self.assertEqual(read_mode(c.state), MODE_ERROR)
        finally:
            c.cleanup()

    def test_exit_to_normal_success(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.set_mode(MODE_NORMAL)
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["OFF"])
            self.assertEqual(read_mode(c.state), MODE_NORMAL)
        finally:
            c.cleanup()

    def test_exit_partial_restore_warns_but_normal(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=2)
        try:
            r = c.ctl.set_mode(MODE_NORMAL)
            self.assertEqual(r["status"], "warn")
            self.assertEqual(read_mode(c.state), MODE_NORMAL)
        finally:
            c.cleanup()

    def test_idempotent_noop_when_already_target(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "noop")
            self.assertEqual(c.calls, [])      # 没跑脚本
        finally:
            c.cleanup()

    def test_retry_from_error_runs_on_script(self):
        c = _Ctl(self.base(), current=MODE_ERROR, rc=0)
        try:
            r = c.ctl.set_mode(MODE_MAPPING)   # error != mapping -> 重试
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["ON"])
        finally:
            c.cleanup()

    def test_invalid_mode_rejected(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.set_mode("banana")
            self.assertEqual(r["status"], "failed")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()

    def test_busy_when_lock_held(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            SwitchLock(c.lock, 90.0, lambda: c.t[0]).acquire()  # 外部占锁(新鲜)
            r = c.ctl.set_mode(MODE_MAPPING)
            self.assertEqual(r["status"], "busy")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py::SetModeTest -q`
Expected: FAIL（`ImportError: cannot import name 'ModeController'`）

- [ ] **Step 3: 写最小实现（追加到 mode_switch.py）**

```python
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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py -q`
Expected: PASS（全部，含 Task1 的 5 个）

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py tests/test_mode_switch.py
git commit -m "feat(mode_switch): ModeController.set_mode state machine (lock/idempotent/safe-fail)"
```

---

### Task 3: ModeController.save_map + 名字净化

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py`
- Test: `tests/test_mode_switch.py`

**Interfaces:**
- Consumes: Task 2 的 `ModeController`
- Produces:
  - `sanitize_map_name(name: str) -> str`（仅保留 `[A-Za-z0-9_-]`，空则 `"lab_map"`）
  - `ModeController.save_map(name: str) -> dict`（仅 `mapping` 模式有效；调用 `f"{save_script} {safe}"`）

- [ ] **Step 1: 写失败测试（追加 SaveMapTest）**

```python
from inspection_manager.mode_switch import sanitize_map_name  # noqa: E402


class SaveMapTest(unittest.TestCase):
    def base(self):
        return Path(self.id().replace(".", "_"))

    def test_sanitize_strips_unsafe(self):
        self.assertEqual(sanitize_map_name("../lab map!!"), "lab_map")  # 见实现说明
        self.assertEqual(sanitize_map_name(""), "lab_map")
        self.assertEqual(sanitize_map_name("floor-2_A"), "floor-2_A")

    def test_save_map_only_in_mapping(self):
        c = _Ctl(self.base(), current=MODE_NORMAL, rc=0)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "failed")
            self.assertEqual(c.calls, [])
        finally:
            c.cleanup()

    def test_save_map_runs_in_mapping(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=0)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "done")
            self.assertEqual(c.calls, ["SAVE lab"])
        finally:
            c.cleanup()

    def test_save_map_failure_reported(self):
        c = _Ctl(self.base(), current=MODE_MAPPING, rc=1)
        try:
            r = c.ctl.save_map("lab")
            self.assertEqual(r["status"], "failed")
        finally:
            c.cleanup()
```

说明：`sanitize_map_name("../lab map!!")`——把非 `[A-Za-z0-9_-]` 字符整体替换为下划线后再压缩/去除首尾下划线得到 `lab_map`（见下方实现）。

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py::SaveMapTest -q`
Expected: FAIL（`cannot import name 'sanitize_map_name'`）

- [ ] **Step 3: 写最小实现（追加到 mode_switch.py）**

```python
import re

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def sanitize_map_name(name: str) -> str:
    safe = _SAFE_RE.sub("_", str(name or "")).strip("_")
    return safe or "lab_map"
```

并给 `ModeController` 加方法：

```python
    def save_map(self, name: str) -> dict:
        cur = self.current_mode()
        if cur != MODE_MAPPING:
            return {"status": "failed", "mode": cur, "result": "仅建图模式可存图"}
        safe = sanitize_map_name(name)
        rc = self.run_script(f"{self.save_script} {safe}")
        if rc == 0:
            return {"status": "done", "mode": cur, "result": f"已存图:{safe}"}
        return {"status": "failed", "mode": cur, "result": f"存图失败(rc={rc})"}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_mode_switch.py -q`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/mode_switch.py tests/test_mode_switch.py
git commit -m "feat(mode_switch): save_map (mapping-only) + map-name sanitizer"
```

---

### Task 4: dispatch_command 识别 set_mode / save_map

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver.py:120`（最后 `return {"unsupported": ...}` 之前插入两个分支）
- Test: `tests/test_command_receiver.py`

**Interfaces:**
- Produces（dispatch_command 新返回形态，仿 `set_volume`/`laser_aim`）：
  - set_mode 合法 → `{"set_mode": "mapping"|"normal", "result": "..."}`
  - save_map → `{"save_map": "<raw name>", "result": "..."}`（净化在 ModeController 内做）

- [ ] **Step 1: 写失败测试（追加到 tests/test_command_receiver.py）**

```python
def test_set_mode_mapping_recognized():
    plan = dispatch_command({"type": "set_mode", "params": {"mode": "mapping"}})
    assert plan["set_mode"] == "mapping"


def test_set_mode_invalid_unsupported():
    plan = dispatch_command({"type": "set_mode", "params": {"mode": "fly"}})
    assert "unsupported" in plan


def test_save_map_recognized_with_default_name():
    plan = dispatch_command({"type": "save_map", "params": {}})
    assert plan["save_map"] == "lab_map"


def test_save_map_uses_given_name():
    plan = dispatch_command({"type": "save_map", "params": {"name": "floor2"}})
    assert plan["save_map"] == "floor2"
```

（文件顶部已 `from inspection_manager.command_receiver import dispatch_command`；若无则补。）

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_command_receiver.py -q -k "set_mode or save_map"`
Expected: FAIL（返回 `{"unsupported": ...}`，断言不过）

- [ ] **Step 3: 写最小实现（在 command_receiver.py 末尾 `return {"unsupported": f"机器人侧暂未接入命令类型:{ctype}"}` 之前插入）**

```python
    if ctype == "set_mode":
        mode = str(params.get("mode", ""))
        if mode not in ("mapping", "normal"):
            return {"unsupported": "set_mode 需要 mode=mapping|normal"}
        return {"set_mode": mode,
                "result": "已请求进入建图模式" if mode == "mapping" else "已请求恢复正常模式"}

    if ctype == "save_map":
        name = str(params.get("name") or "lab_map")
        return {"save_map": name, "result": f"已请求存图:{name}"}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd ~/projects/Soc_China && python -m pytest tests/test_command_receiver.py -q`
Expected: PASS（全部，含原有用例）

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver.py tests/test_command_receiver.py
git commit -m "feat(command_receiver): recognize set_mode/save_map commands"
```

---

### Task 5: command_receiver_node 接线（ModeController + 后台执行 + mode 上报）

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py`

**Interfaces:**
- Consumes: `mode_switch.ModeController`、dispatch 返回的 `set_mode`/`save_map`
- Produces: node 内部行为，无新对外签名。后端新增 `POST /api/robot/mode {mode}`（后端由 App prompt 实现）。

说明：切换是长任务（pkill+launch+30s 校验），**必须**放后台线程，否则阻塞 rclpy 定时器与 spin。ModeController 的锁保证并发安全；线程结束后再 `_report`。

- [ ] **Step 1: 加 import 与参数**

在 import 区加：

```python
import subprocess
import threading

from inspection_manager.mode_switch import ModeController, read_mode
```

在 `__init__` 的参数声明区（其它 `gp(...)` 旁）加：

```python
        gp("mode_state_file", "/root/.robot_mode")
        gp("mode_lock_file", "/run/robot_mode.lock")
        gp("scripts_dir", "/root/Soc_China/rdk_x5/scripts")
        gp("mode_lock_timeout_sec", 90.0)
```

- [ ] **Step 2: 在 `__init__` 末尾（`create_timer(... self._poll)` 之前）构造 ModeController**

```python
        sd = str(g("scripts_dir").value)
        self._mode_state_file = str(g("mode_state_file").value)
        self._mode = ModeController(
            run_script=self._run_script,
            state_path=self._mode_state_file,
            lock_path=str(g("mode_lock_file").value),
            on_script=f"{sd}/mapping_mode_on.sh",
            off_script=f"{sd}/mapping_mode_off.sh",
            save_script=f"{sd}/save_map.sh",
            now=time.monotonic,
            lock_timeout_s=float(g("mode_lock_timeout_sec").value),
        )
        self._mode_thread = None
```

文件顶部 import 区补 `import time`（若无）。

- [ ] **Step 3: 加运行器与后台执行方法**

```python
    def _run_script(self, cmd: str) -> int:
        """Run a shell command (mode scripts); return its exit code."""
        try:
            return subprocess.call(["/bin/bash", "-lc", cmd])
        except OSError as exc:  # noqa: BLE001
            self.get_logger().warn(f"run_script failed: {exc}")
            return 127

    def _run_mode_job(self, cid: str, fn, arg: str) -> None:
        try:
            res = fn(arg)
            self.get_logger().info(f"{cid} mode -> {res}")
            status = "done" if res["status"] in ("done", "noop", "warn") else "failed"
            self._report(cid, status, res["result"])
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"mode job {cid} failed: {exc}")
            self._report(cid, "failed", f"模式切换异常:{exc}")
        finally:
            self._mode_thread = None
```

- [ ] **Step 4: 在 `_handle` 里、`plan = dispatch_command(...)` 之后、`if "unsupported" in plan` 之前插入 set_mode/save_map 分支**

```python
        if "set_mode" in plan or "save_map" in plan:
            if self._mode_thread and self._mode_thread.is_alive():
                self._report(cid, "failed", "模式切换进行中,请稍后")
                return
            if "set_mode" in plan:
                fn, arg = self._mode.set_mode, plan["set_mode"]
            else:
                fn, arg = self._mode.save_map, plan["save_map"]
            self._mode_thread = threading.Thread(
                target=self._run_mode_job, args=(cid, fn, arg), daemon=True)
            self._mode_thread.start()
            return
```

- [ ] **Step 5: 在 `_poll` 末尾（for 循环之后）加 mode 上报**

```python
        try:
            self.poster.post_json("/api/robot/mode", {"mode": read_mode(self._mode_state_file)})
        except Exception as exc:  # noqa: BLE001 - heartbeat best-effort
            self.get_logger().debug(f"mode report failed: {exc}")
```

- [ ] **Step 6: 静态校验（无 rclpy 也能跑的语法/导入检查）**

Run: `cd ~/projects/Soc_China && python -m py_compile rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py && echo OK`
Expected: 输出 `OK`（编译通过）。

Run（确保没把已有测试搞挂）: `python -m pytest tests/test_command_receiver.py tests/test_mode_switch.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py
git commit -m "feat(command_receiver_node): wire ModeController (bg thread) + mode heartbeat"
```

---

### Task 6: 编排脚本 mapping_mode_on/off.sh + save_map.sh

**Files:**
- Create: `rdk_x5/scripts/mapping_mode_on.sh`
- Create: `rdk_x5/scripts/mapping_mode_off.sh`
- Create: `rdk_x5/scripts/save_map.sh`

**Interfaces:**
- Consumes: 现有 `/root/start_*.sh`、`mapping.launch.py`
- Produces: on 成功 exit 0 / 失败自清并 exit 1；off exit 0（部分未恢复 exit 2）；save_map exit 0/1。命令通道三件全程不动。

- [ ] **Step 1: 写 mapping_mode_on.sh**

```bash
#!/bin/bash
# 进建图模式:停重负载子集(保留命令通道三件)-> 起建图栈 -> 校验(<=30s)。
# 成功 exit 0;失败自清建图栈并 exit 1。
set -u
export HOME=/root
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null

# 1) 停重负载子集(绝不动 uplink/command_receiver/acceptance)
for pat in llama-server tts_server.py voice_node report_service \
           cognition_node gimbal_controller_node laser_node asr_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 2

# 2) 起建图栈(后台,孤儿化,日志独立)
TOK=$(cat /root/.app_ingest_token 2>/dev/null)
setsid ros2 launch chassis_bringup mapping.launch.py ingest_token:="$TOK" \
  >/tmp/mapping.log 2>&1 < /dev/null &

# 3) 校验:关键节点是否都起来(用 node list,不信 topic hz)
need="lslidar_driver_node async_slam_toolbox_node stm32_bridge_node ekf_node"
for i in $(seq 1 30); do
  sleep 1
  nodes=$(ros2 node list 2>/dev/null)
  ok=1
  for n in $need; do echo "$nodes" | grep -q "$n" || ok=0; done
  [ "$ok" = "1" ] && { echo "[mode] mapping stack up after ${i}s"; exit 0; }
done

echo "[mode] mapping stack FAILED to come up in 30s; tearing down" >&2
for pat in "mapping.launch" lslidar_driver_node async_slam_toolbox_node \
           ekf_node stm32_bridge_node bmi088_imu_node lidar_safety_node teleop_receiver_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
exit 1
```

- [ ] **Step 2: 写 mapping_mode_off.sh**

```bash
#!/bin/bash
# 退出建图模式:停建图栈(干净,含 setsid 孤儿)-> 重拉重负载层。
# 全部恢复 exit 0;有组件没起来 exit 2。
set -u
export HOME=/root
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null

# 1) 停建图栈(彻底清孤儿,释放 STM32 串口)
for pat in "mapping.launch" lslidar_driver_node async_slam_toolbox_node \
           ekf_node stm32_bridge_node bmi088_imu_node lidar_safety_node teleop_receiver_node; do
  pkill -9 -f "$pat" 2>/dev/null
done
sleep 2

# 2) 重拉重负载层(各自 start 脚本;命令通道一直没动,不重起)
for s in start_llm start_tts_server start_voice start_report start_cognition start_gimbal start_asr; do
  bash /root/$s.sh >/tmp/${s}.relaunch.log 2>&1
  sleep 1
done

# 3) 粗校验:llama + 关键语音节点回来没
sleep 3
warn=0
pgrep -f llama-server >/dev/null || warn=1
pgrep -f voice_node >/dev/null || warn=1
pgrep -f asr_node >/dev/null || warn=1
[ "$warn" = "0" ] && { echo "[mode] normal stack restored"; exit 0; }
echo "[mode] some heavy components did not restart" >&2
exit 2
```

- [ ] **Step 3: 写 save_map.sh**

```bash
#!/bin/bash
# 存当前 slam 地图到 ~/maps/<name>.pgm|.yaml。参数:name(已由上游净化)。
set -u
export HOME=/root
source /opt/ros/humble/setup.bash
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash 2>/dev/null
name="${1:-lab_map}"
mkdir -p /root/maps
ros2 run nav2_map_server map_saver_cli -f "/root/maps/${name}" --ros-args -p save_map_timeout:=20.0
```

- [ ] **Step 4: 置可执行 + 提交（本地）**

```bash
chmod +x rdk_x5/scripts/mapping_mode_on.sh rdk_x5/scripts/mapping_mode_off.sh rdk_x5/scripts/save_map.sh
git add rdk_x5/scripts/mapping_mode_on.sh rdk_x5/scripts/mapping_mode_off.sh rdk_x5/scripts/save_map.sh
git commit -m "feat(scripts): mapping mode on/off + save_map orchestration"
```

- [ ] **Step 5: 部署到 RDK 并上板集成验证**

```bash
# 部署仓库到 RDK(rsync 或在 RDK 上 git pull),确保 /root/Soc_China 同步;然后 colcon build inspection_manager
ssh root@192.168.128.10 'cd /root/Soc_China/rdk_x5/ros2_ws && source /opt/ros/humble/setup.bash && colcon build --packages-select inspection_manager --symlink-install'
```

逐项人工验证（参照 spec 测试节）：
- 进建图：`echo mapping > /root/.robot_mode` 旁路不算——走真实链路：从 App/curl 发 `set_mode:mapping`，确认重负载子集被停、命令通道三件仍在、建图栈起来、`/root/.robot_mode=mapping`、内存释放（`free -m` 涨）。
- 命令通道存活：进 mapping 后再从 App/curl 发 `set_mode:normal` 能被执行（证明没锁死自己）。
- 失败路径：拔雷达后发 mapping → 30s 后 `/root/.robot_mode=mapping_error` 且无半死建图进程、重负载保持停。
- 存图：mapping 下发 `save_map` → `/root/maps/<name>.pgm|.yaml` 生成。
- 退出：发 normal → 建图栈干净清除（`pgrep -f stm32_bridge_node` 空）、语音层回来、`/root/.robot_mode=normal`。

记录结果到当日 validation 日志（见 Task 7）。

---

### Task 7: 文档更新 + App prompts

**Files:**
- Modify: `docs/ops/lab_mapping_procedure.md`
- Create: `app/BACKEND_PROMPT_mapping_mode.md`
- Create: `app/FRONTEND_PROMPT_mapping_mode.md`
- Create: `docs/validation/daily/2026-06-30-app-mapping-mode.md`（Task 6 验证结果）

**Interfaces:** 文档；App prompt 描述命令协议与 UI，交另两个 agent 实现。

- [ ] **Step 1: 更新操作手册**

把 `docs/ops/lab_mapping_procedure.md` 的"§1 腾 CPU + §2 起栈"改为以 **App 一键建图模式** 为主流程：App 打开"建图模式"开关 → RDK 自动腾资源+起栈 → 摇杆绕图 → App"存图"按钮。把原手动 `systemctl stop voice-asr` + `ros2 launch ... mapping.launch.py` 降级为"高级/手动备用"。保留 §3 自检判据、§4 走法、§6 常见问题。

- [ ] **Step 2: 写后端 prompt**

`app/BACKEND_PROMPT_mapping_mode.md` 要点：
- 命令队列已支持新类型,App→后端只需把命令塞进现有 `POST /api/robot/commands`:`{"type":"set_mode","params":{"mode":"mapping"|"normal"}}`、`{"type":"save_map","params":{"name":"<slug>"}}`(Bearer 写鉴权)。
- 新增 `POST /api/robot/mode {mode}`(RDK 每 2s 上报)持久化最新 mode;`GET /api/robot/mode` 给 App 读。mode ∈ normal/switching/mapping/mapping_error。
- 命令结果走现有 `/api/robot/commands/{id}/result`(status+result 文本),App 据此弹提示。

- [ ] **Step 3: 写前端 prompt**

`app/FRONTEND_PROMPT_mapping_mode.md` 要点：
- 设置/遥控页加"建图模式"开关:ON 发 set_mode:mapping、OFF 发 set_mode:normal。
- 显示 **RDK 回报的真实 mode**(轮询 `GET /api/robot/mode`),不是开关位置;switching 显示"切换中"转圈并禁用开关;mapping_error 显示红色错误态+「重试/退出」。
- mapping 模式下露出遥控页摇杆(复用已有 teleop)+「存图」按钮(发 save_map,可填名字,默认 lab_map);存图结果弹 toast。
- 命令结果/失败文本来自 command result;请求与回报 mode 不一致超过若干秒可自动重发(幂等)。

- [ ] **Step 4: 落 Task6 验证日志 + 提交**

把 Task 6 上板验证结果写入 `docs/validation/daily/2026-06-30-app-mapping-mode.md`。

```bash
git add docs/ops/lab_mapping_procedure.md app/BACKEND_PROMPT_mapping_mode.md app/FRONTEND_PROMPT_mapping_mode.md docs/validation/daily/2026-06-30-app-mapping-mode.md
git commit -m "docs(mapping-mode): App one-tap procedure + backend/frontend prompts + validation log"
```

---

## Self-Review

**Spec coverage:**
- 一键就绪（停重负载+起建图）→ Task 2 set_mode + Task 6 on.sh ✓
- OFF 恢复 → Task 2 set_mode(normal) + Task 6 off.sh ✓
- 存图 → Task 3 save_map + Task 6 save_map.sh + Task 7 前端按钮 ✓
- 命令通道永不被杀 → Task 6 on.sh 只 pkill 重负载子集（不含命令通道三件）✓
- 失败停安全态不回滚 → Task 2 mapping_error + on.sh 自清 ✓
- 退出部分恢复 warn → Task 2 warn + off.sh exit 2 ✓
- 锁/幂等/busy → Task 2 ✓
- 状态文件单一事实源 + mode 上报 → Task 1 + Task 5 _poll 上报 ✓
- KillMode=process 用 pkill → Task 6 全脚本 pkill ✓
- 测试（host 单测 + 上板集成）→ Task 1-4 host、Task 6 Step5 上板 ✓
- App prompt → Task 7 ✓
- 手册更新 → Task 7 ✓

**Placeholder scan:** 无 TBD/TODO；脚本与代码均为完整内容。Task 6 Step5 与 Task 7 的"人工验证/写要点"是集成与文档动作（非代码占位），可接受。

**Type consistency:** `run_script(cmd:str)->int`、`now()->float`、set_mode/save_map 返回 `{status,mode,result}`、dispatch 返回 `{"set_mode":..}`/`{"save_map":..}` 在 Task 2-5 一致；常量名 MODE_* 一致；脚本路径 on/off/save 与 ModeController 注入一致。

---

## Execution Handoff（计划保存后由 writing-plans 给出）
