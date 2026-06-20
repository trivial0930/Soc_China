# 语音交互(端侧 ASR + 唤醒 + 意图理解)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RDK X5 上新增端侧离线语音交互:唤醒词「小巡/巡检助手」→ VAD 断句 → 中文 ASR → 规则/小模型意图理解 → 复用现有命令分发执行 + 语音回执,并预留 App 远程开关。

**Architecture:** 与现有 `voice_node`(TTS 输出)对称新增输入侧。所有逻辑放进**不依赖 rclpy/sherpa 的纯模块**(注入式),可在开发机 pytest;rclpy 节点与 sherpa-onnx 引擎只是薄壳。命令执行从 `command_receiver_node` 抽出共享 `CommandExecutor`,语音与 App 下行走同一份代码。

**Tech Stack:** Python 3、ROS2(rclpy)、sherpa-onnx python 包(KWS zipformer-wenetspeech + silero VAD + SenseVoice-small)、sounddevice、现有 `qwen_client`(L1.5 兑底)。

设计依据:`docs/superpowers/specs/2026-06-21-voice-asr-interaction-design.md`。

## Global Constraints

- 范围仅 `rdk_x5/`(inspection_manager 包 + launch/config/setup)、`tests/`、`docs/`。**不碰 app/、不碰后端**。App 端语音开关由后续单独计划实现(本计划只在机器人侧预留)。
- 纯逻辑模块(`intent.py`/`dialog.py`/`command_executor.py`/`asr_controller.py`)**禁止 import rclpy / sherpa_onnx / sounddevice**;依赖以参数注入。这是可测性的硬约束。
- 测试沿用仓库现有风格:`unittest.TestCase`,文件头用 `sys.path.insert(0, <inspection_manager pkg dir>)` 引入模块(见 `tests/test_command_receiver.py:6-10`)。
- 测试运行:`python -m pytest tests/<file> -v`(在仓库根 `/Users/sthefirst/Desktop/Soc_China`)。
- 工位 id 格式与现有一致:`desk-01`/`desk-02`/...(见 `tests/test_command_receiver.py:17`);`station_id` 是否有效由 `dispatch_command` 配合 `stations.yaml` 判定,intent 只产出候选。
- 命令契约以 `dispatch_command()`(`command_receiver.py`)与 `app/BACKEND_PROMPT_voice_control.md` 为准。
- 提交:每个 Task 末尾按所列**显式路径** `git add`,不要 `git add -A`。

## File Structure

新增(`rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/`):
- `intent.py` — 纯:`parse_intent(text, station_fmt)`、`parse_station_id(text)`、`vlm_fallback(text, chat_fn, min_conf)`。文本→命令 `{type, params}`。
- `dialog.py` — 纯:`wake_ack`、`not_understood`、`reply_for(cmd_type, plan)`。命令+执行结果→中文话术(含移动类诚实降级措辞)。
- `command_executor.py` — `CommandExecutor`:注入 `publish`/`schedule` 原语,`execute(plan)` 跑 actions 或激光定时例程。
- `asr_controller.py` — 纯:`AsrController` 状态机(DISABLED/IDLE/DIALOG)+ 编排(唤醒→识别→意图→执行→回执→超时)。
- `asr_engine.py` — `AsrBackend` Protocol + `MockAsrBackend`(测试用)+ `SherpaAsrBackend`(真,延迟 import sherpa_onnx/sounddevice)。
- `asr_node.py` — rclpy 薄壳:装配上述模块、`/inspection/voice_control` 订阅、状态持久化、定时驱动 controller。

修改:
- `command_receiver.py` — `dispatch_command` 加 `voice_control` 分支。
- `command_receiver_node.py` — 改为委托 `CommandExecutor`(行为不变)。
- `launch/inspection.launch.py` — 增 `asr_node`。
- `setup.py` — entry_points 加 `asr_node`。

新增测试(`tests/`):`test_intent.py`、`test_dialog.py`、`test_command_executor.py`、`test_asr_controller.py`;修改 `test_command_receiver.py`(加 voice_control)。

文档:`docs/architecture/voice_asr_setup.md`。

> **范围收敛(对齐 spec):** MVP intent 规则覆盖 6 类——`voice_prompt`/`recheck_station`/`inspection_round`/`laser_point`/`acceptance`/`generate_report`。`find_item`(寻物)依赖后端 asset 查询,且其导航形态依赖底盘移动,**本计划不做语音入口**,识别不到时走兑底/引导语;留作后续(spec §10 开放问题)。

---

### Task 1: `dispatch_command` 新增 `voice_control` 分支

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver.py:101`(在 unknown-type 返回前插入分支)
- Test: `tests/test_command_receiver.py`(新增用例)

**Interfaces:**
- Produces: `dispatch_command({"type":"voice_control","params":{"enabled":bool}})` →
  `{"actions":[{"topic_key":"voice_control_topic","kind":"string","data":'{"enabled": <bool>}'}], "result":"语音监听已开启|已关闭"}`;缺/非布尔 `enabled` → `{"unsupported": "..."}`。

- [ ] **Step 1: Write the failing tests** — 在 `tests/test_command_receiver.py` 的 `DispatchTests` 类内加:

```python
    def test_voice_control_enable(self):
        out = dispatch_command({"type": "voice_control", "params": {"enabled": True}})
        act = self._one(out)
        self.assertEqual(act["topic_key"], "voice_control_topic")
        self.assertEqual(json.loads(act["data"]), {"enabled": True})
        self.assertEqual(out["result"], "语音监听已开启")

    def test_voice_control_disable(self):
        out = dispatch_command({"type": "voice_control", "params": {"enabled": False}})
        self.assertEqual(json.loads(self._one(out)["data"]), {"enabled": False})
        self.assertEqual(out["result"], "语音监听已关闭")

    def test_voice_control_missing_enabled_unsupported(self):
        self.assertIn("unsupported", dispatch_command({"type": "voice_control", "params": {}}))
        self.assertIn("unsupported", dispatch_command({"type": "voice_control", "params": {"enabled": "yes"}}))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_command_receiver.py -v -k voice_control`
Expected: FAIL(`voice_control` 落入 unknown-type,`result`/actions 断言不通过)。

- [ ] **Step 3: Implement** — 在 `command_receiver.py` 的 `return {"unsupported": f"机器人侧暂未接入命令类型:{ctype}"}`(行 101)**之前**插入:

```python
    if ctype == "voice_control":
        enabled = params.get("enabled")
        if not isinstance(enabled, bool):
            return {"unsupported": "voice_control 需要布尔 params.enabled"}
        return {"actions": [{"topic_key": "voice_control_topic", "kind": "string",
                             "data": json.dumps({"enabled": enabled}, ensure_ascii=False)}],
                "result": "语音监听已开启" if enabled else "语音监听已关闭"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_command_receiver.py -v`
Expected: PASS(原有用例 + 3 个新用例)。

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver.py tests/test_command_receiver.py
git commit -m "feat(asr): dispatch_command 支持 voice_control 命令"
```

---

### Task 2: 抽取 `CommandExecutor`,重构 `command_receiver_node` 委托它

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_executor.py`
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py:50-67,130-175`
- Test: `tests/test_command_executor.py`

**Interfaces:**
- Consumes: `dispatch_command()` 的返回 `plan`(Task 1)。
- Produces:
  - `CommandExecutor(publish, schedule, laser_indicate_sec=8.0)`,其中
    `publish(topic_key: str, kind: str, data) -> None`(`kind ∈ {"string","bool","vector3"}`;vector3 的 `data` 为 `[x,y,z]`),
    `schedule(period_sec: float, callback: Callable[[], None]) -> Timer`(`Timer` 有 `.cancel()`)。
  - `executor.execute(plan: dict) -> Optional[str]`:`"laser_aim"` → 跑激光例程;`"actions"` → 逐个 `publish`;返回 `plan.get("result")`。
  - 激光例程固定 topic_key:`gimbal_enable_topic`/`laser_topic`/`gimbal_topic`(与现有 node 参数一致)。

- [ ] **Step 1: Write the failing test** — `tests/test_command_executor.py`:

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.command_executor import CommandExecutor  # noqa: E402


class FakeTimer:
    def __init__(self): self.canceled = False
    def cancel(self): self.canceled = True


class Harness:
    def __init__(self):
        self.published = []          # list of (topic_key, kind, data)
        self.timers = []             # list of (period, callback, FakeTimer)
    def publish(self, topic_key, kind, data):
        self.published.append((topic_key, kind, data))
    def schedule(self, period, cb):
        t = FakeTimer(); self.timers.append((period, cb, t)); return t


class CommandExecutorTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.ex = CommandExecutor(self.h.publish, self.h.schedule, laser_indicate_sec=8.0)

    def test_execute_actions(self):
        plan = {"actions": [{"topic_key": "voice_topic", "kind": "string", "data": "请整理桌面"}],
                "result": "已播报:请整理桌面"}
        self.assertEqual(self.ex.execute(plan), "已播报:请整理桌面")
        self.assertEqual(self.h.published, [("voice_topic", "string", "请整理桌面")])

    def test_execute_laser_sequence(self):
        plan = {"laser_aim": [12.6, -11.6], "result": "激光已指向 desk-03"}
        self.assertEqual(self.ex.execute(plan), "激光已指向 desk-03")
        # FAULT 清除 + 使能 + 激光开
        self.assertEqual(self.h.published[0], ("gimbal_enable_topic", "bool", False))
        self.assertEqual(self.h.published[1], ("gimbal_enable_topic", "bool", True))
        self.assertEqual(self.h.published[2], ("laser_topic", "bool", True))
        # 注册了 sustain(0.1s) 与 stop(8.0s) 两个定时器
        periods = sorted(p for p, _, _ in self.h.timers)
        self.assertEqual(periods, [0.1, 8.0])

    def test_laser_sustain_tick_publishes_gimbal_vector(self):
        self.ex.execute({"laser_aim": [12.6, -11.6], "result": "x"})
        sustain_cb = next(cb for p, cb, _ in self.h.timers if p == 0.1)
        self.h.published.clear()
        sustain_cb()
        self.assertEqual(self.h.published, [("gimbal_topic", "vector3", [12.6, -11.6, 0.0])])

    def test_laser_stop_turns_off_and_cancels(self):
        self.ex.execute({"laser_aim": [1.0, 2.0], "result": "x"})
        stop_cb = next(cb for p, cb, _ in self.h.timers if p == 8.0)
        self.h.published.clear()
        stop_cb()
        self.assertIn(("laser_topic", "bool", False), self.h.published)
        self.assertTrue(all(t.canceled for _, _, t in self.h.timers))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_command_executor.py -v`
Expected: FAIL(`ModuleNotFoundError: command_executor`)。

- [ ] **Step 3: Implement** — `command_executor.py`:

```python
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
                 laser_indicate_sec: float = 8.0) -> None:
        self._publish = publish
        self._schedule = schedule
        self._laser_sec = float(laser_indicate_sec)
        self._aim_target: Optional[List[float]] = None
        self._sustain_timer = None
        self._stop_timer = None

    def execute(self, plan: Dict[str, Any]) -> Optional[str]:
        if "laser_aim" in plan:
            self._start_laser(plan["laser_aim"])
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
        self._publish("laser_topic", "bool", False)
        for t in (self._sustain_timer, self._stop_timer):
            if t is not None:
                t.cancel()
        self._sustain_timer = None
        self._stop_timer = None
        self._aim_target = None
```

- [ ] **Step 4: Run executor tests**

Run: `python -m pytest tests/test_command_executor.py -v`
Expected: PASS(4 用例)。

- [ ] **Step 5: Refactor `command_receiver_node` to delegate** — 在 `command_receiver_node.py`:

import 处加:`from inspection_manager.command_executor import CommandExecutor`。

替换 `__init__` 中 publisher 之后(行 64-66 的 `_aim_*` 初始化)为构造执行器(保留 `string_pubs/vector_pubs/bool_pubs` 不变):

```python
        self.executor = CommandExecutor(self._publish_primitive, self.create_timer,
                                        self.laser_indicate_sec)
```

新增私有发布原语(替代旧 `_publish`,保留同名 helper 也可,这里给执行器用):

```python
    def _publish_primitive(self, topic_key: str, kind: str, data) -> None:
        if kind == "vector3":
            x, y, z = data
            self.vector_pubs[topic_key].publish(Vector3(x=float(x), y=float(y), z=float(z)))
        elif kind == "bool":
            self.bool_pubs[topic_key].publish(Bool(data=bool(data)))
        else:
            self.string_pubs[topic_key].publish(String(data=data))
```

把 `string_pubs` 增加 `voice_control_topic`(供 Task 1 的 voice_control action 发布):在 `string_pubs` 字典加一行,并在参数声明处加 `gp("voice_control_topic", "/inspection/voice_control")`:

```python
            "voice_control_topic": self.create_publisher(String, str(g("voice_control_topic").value), 10),
```

把 `_handle()` 里执行段(行 130-140 的 try/except)改为委托:

```python
        try:
            result = self.executor.execute(plan)
            self.get_logger().info(f"{cid} -> {result}")
            self._report(cid, "done", result)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f"dispatch {cid} failed: {exc}")
            self._report(cid, "failed", f"机器人执行异常:{exc}")
```

删除现已迁入 executor 的方法:`_publish`、`_start_laser_indication`、`_aim_tick`、`_stop_laser_indication`,及 `__init__` 里的 `self._aim_target/_aim_timer/_aim_stop_timer`。

- [ ] **Step 6: Run full regression**

Run: `python -m pytest tests/test_command_receiver.py tests/test_command_executor.py -v`
Expected: PASS(command_receiver 纯逻辑不受影响;executor 全过)。

> 注:`command_receiver_node` 依赖 rclpy,在开发机不直接运行;其装配正确性靠上板验证(Task 9)。纯逻辑已由两份测试覆盖。

- [ ] **Step 7: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_executor.py \
        rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/command_receiver_node.py \
        tests/test_command_executor.py
git commit -m "refactor(asr): 抽取共享 CommandExecutor,command_receiver_node 委托执行"
```

---

### Task 3: `intent.py` 规则层(文本→命令)

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/intent.py`
- Test: `tests/test_intent.py`

**Interfaces:**
- Produces:
  - `parse_station_id(text: str, station_fmt: str = "desk-{:02d}") -> Optional[str]` — 中文/阿拉伯数字 → `desk-0N`。
  - `parse_intent(text: str, station_fmt: str = "desk-{:02d}") -> Optional[Dict]` — 命中返回 `{"type":..., "params":{...}}`,否则 `None`。

- [ ] **Step 1: Write the failing tests** — `tests/test_intent.py`:

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.intent import parse_intent, parse_station_id  # noqa: E402


class StationIdTests(unittest.TestCase):
    def test_chinese_and_arabic(self):
        self.assertEqual(parse_station_id("去三号桌看看"), "desk-03")
        self.assertEqual(parse_station_id("复核5号工位"), "desk-05")
        self.assertEqual(parse_station_id("第十二号"), "desk-12")
    def test_none_when_no_number(self):
        self.assertIsNone(parse_station_id("开始巡检"))


class IntentTests(unittest.TestCase):
    def test_recheck(self):
        self.assertEqual(parse_intent("去三号桌复核"),
                         {"type": "recheck_station", "params": {"station_id": "desk-03"}})
        self.assertEqual(parse_intent("检查一下二号工位"),
                         {"type": "recheck_station", "params": {"station_id": "desk-02"}})

    def test_laser(self):
        self.assertEqual(parse_intent("激光指示三号桌"),
                         {"type": "laser_point", "params": {"station_id": "desk-03"}})

    def test_inspection_round(self):
        self.assertEqual(parse_intent("开始全面巡检"), {"type": "inspection_round", "params": {}})

    def test_acceptance_specific_and_all(self):
        self.assertEqual(parse_intent("对三号桌做课后验收"),
                         {"type": "acceptance", "params": {"station_id": "desk-03"}})
        self.assertEqual(parse_intent("全部工位验收"),
                         {"type": "acceptance", "params": {"station_id": "all"}})

    def test_voice_prompt(self):
        self.assertEqual(parse_intent("播报请大家注意用电安全"),
                         {"type": "voice_prompt", "params": {"text": "请大家注意用电安全"}})

    def test_generate_report(self):
        self.assertEqual(parse_intent("生成巡检报告"),
                         {"type": "generate_report", "params": {"report_type": "periodic_summary"}})

    def test_unmatched_returns_none(self):
        self.assertIsNone(parse_intent("今天天气怎么样"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_intent.py -v`
Expected: FAIL(`ModuleNotFoundError: intent`)。

- [ ] **Step 3: Implement** — `intent.py`:

```python
"""Pure rule-based intent parsing: Chinese ASR text -> command {type, params}.

Returns None when no rule matches (caller falls back to the small VLM). No rclpy.
Station ids match the project format desk-0N (see tests/test_command_receiver.py).
"""
from __future__ import annotations

import re
from typing import Dict, Optional

_CN_DIGIT = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str) -> Optional[int]:
    """十/十二/二十/二十三 等简单中文数字 -> int(覆盖 1..99,够工位用)。"""
    if "十" not in s:
        if len(s) == 1 and s in _CN_DIGIT:
            return _CN_DIGIT[s]
        return None
    tens, _, ones = s.partition("十")
    t = _CN_DIGIT.get(tens, 1) if tens else 1
    o = _CN_DIGIT.get(ones, 0) if ones else 0
    return t * 10 + o


def parse_station_id(text: str, station_fmt: str = "desk-{:02d}") -> Optional[str]:
    m = re.search(r"(\d{1,2})\s*[号]?\s*(?:桌|工位|号位|台)?", text)
    if m:
        return station_fmt.format(int(m.group(1)))
    m = re.search(r"([零一二两三四五六七八九十]{1,3})\s*号", text)
    if m:
        n = _cn_to_int(m.group(1))
        if n is not None:
            return station_fmt.format(n)
    return None


def parse_intent(text: str, station_fmt: str = "desk-{:02d}") -> Optional[Dict]:
    t = text.strip()
    if not t:
        return None

    # voice_prompt:播报/说/提醒 + 文本(优先抓取,文本随意)
    m = re.search(r"(?:播报|广播|提醒大家|说一句|喊话)[:：]?\s*(.+)$", t)
    if m and m.group(1).strip():
        return {"type": "voice_prompt", "params": {"text": m.group(1).strip()}}

    # generate_report
    if re.search(r"(生成|出|做).*(报告)", t) or "巡检报告" in t:
        return {"type": "generate_report", "params": {"report_type": "periodic_summary"}}

    # acceptance
    if "验收" in t:
        if re.search(r"全部|所有|全场", t):
            return {"type": "acceptance", "params": {"station_id": "all"}}
        sid = parse_station_id(t)
        return {"type": "acceptance", "params": {"station_id": sid or "all"}}

    # laser_point
    if re.search(r"激光|指一?下|照一?下|指示", t):
        sid = parse_station_id(t)
        if sid:
            return {"type": "laser_point", "params": {"station_id": sid}}

    # inspection_round
    if re.search(r"(全面|综合|挨个|开始).*巡检|巡检一圈|巡逻", t):
        return {"type": "inspection_round", "params": {}}

    # recheck_station
    if re.search(r"复核|去看|看看|检查|过去|前往", t):
        sid = parse_station_id(t)
        if sid:
            return {"type": "recheck_station", "params": {"station_id": sid}}

    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_intent.py -v`
Expected: PASS(全部用例)。

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/intent.py tests/test_intent.py
git commit -m "feat(asr): 规则意图解析(文本->命令)"
```

---

### Task 4: `intent.py` 小模型兑底(`vlm_fallback`)

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/intent.py`
- Test: `tests/test_intent.py`(新增 `VlmFallbackTests`)

**Interfaces:**
- Produces: `vlm_fallback(text: str, chat_fn: Callable[[str], str], min_conf: float = 0.5) -> Optional[Dict]`。
  `chat_fn(prompt)` 返回模型文本(注入,便于测试);函数解析出 `{type, params}`,非法/低置信/异常 → `None`。
- Consumes(运行期,非本任务实现):asr_node 用 `qwen_client` 包一个 `chat_fn`。

- [ ] **Step 1: Write the failing tests** — 在 `tests/test_intent.py` 追加:

```python
from inspection_manager.intent import vlm_fallback  # noqa: E402


class VlmFallbackTests(unittest.TestCase):
    def test_parses_json_command(self):
        chat = lambda p: '好的 {"type": "recheck_station", "params": {"station_id": "desk-04"}, "confidence": 0.9}'
        self.assertEqual(vlm_fallback("到四号桌那边瞧瞧", chat),
                         {"type": "recheck_station", "params": {"station_id": "desk-04"}})

    def test_low_confidence_returns_none(self):
        chat = lambda p: '{"type": "inspection_round", "params": {}, "confidence": 0.2}'
        self.assertIsNone(vlm_fallback("嗯啊这个", chat))

    def test_unknown_type_returns_none(self):
        chat = lambda p: '{"type": "dance", "params": {}, "confidence": 0.99}'
        self.assertIsNone(vlm_fallback("跳个舞", chat))

    def test_garbage_returns_none(self):
        self.assertIsNone(vlm_fallback("x", lambda p: "我不知道你在说什么"))

    def test_chat_exception_returns_none(self):
        def boom(p): raise RuntimeError("offline")
        self.assertIsNone(vlm_fallback("x", boom))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_intent.py::VlmFallbackTests -v`
Expected: FAIL(`cannot import name 'vlm_fallback'`)。

- [ ] **Step 3: Implement** — 在 `intent.py` 顶部 import 加 `import json` 与 `from typing import Callable`,并追加:

```python
_ALLOWED_TYPES = {"voice_prompt", "recheck_station", "inspection_round",
                  "laser_point", "acceptance", "generate_report"}

INTENT_SCHEMA_PROMPT = (
    "你是实验室巡检机器人的语音指令解析器。把用户的话解析成一个 JSON 命令,"
    "只输出 JSON,不要解释。命令格式:{\"type\": <类型>, \"params\": {...}, \"confidence\": 0~1}。"
    "类型枚举与参数:"
    "voice_prompt{text};recheck_station{station_id};inspection_round{};"
    "laser_point{station_id};acceptance{station_id 或 \"all\"};generate_report{report_type}。"
    "station_id 形如 desk-03。听不懂就给低 confidence。用户说:"
)


def vlm_fallback(text: str, chat_fn: "Callable[[str], str]", min_conf: float = 0.5) -> Optional[Dict]:
    try:
        raw = chat_fn(INTENT_SCHEMA_PROMPT + text)
    except Exception:  # noqa: BLE001 - model offline/timeout -> give up
        return None
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if obj.get("type") not in _ALLOWED_TYPES:
        return None
    if float(obj.get("confidence", 0.0)) < min_conf:
        return None
    return {"type": obj["type"], "params": obj.get("params") or {}}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_intent.py -v`
Expected: PASS(规则 + 兑底全部用例)。

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/intent.py tests/test_intent.py
git commit -m "feat(asr): 小模型意图兑底(规则未命中时解析 JSON 命令)"
```

---

### Task 5: `dialog.py` 语音话术(含移动类诚实降级)

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/dialog.py`
- Test: `tests/test_dialog.py`

**Interfaces:**
- Produces:
  - `wake_ack(text: str = "我在") -> str`
  - `not_understood() -> str`
  - `reply_for(cmd_type: str, plan: Dict) -> str` — `plan` 是 `dispatch_command` 返回。
    `unsupported` → `"抱歉,<原因>"`;移动类(`recheck_station`/`inspection_round`)→ `"<result>;底盘移动还在调试,稍后执行"`;其余 → `result`。

- [ ] **Step 1: Write the failing tests** — `tests/test_dialog.py`:

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.dialog import wake_ack, not_understood, reply_for  # noqa: E402


class DialogTests(unittest.TestCase):
    def test_wake_ack_default_and_custom(self):
        self.assertEqual(wake_ack(), "我在")
        self.assertEqual(wake_ack("在呢"), "在呢")

    def test_not_understood_is_guiding(self):
        msg = not_understood()
        self.assertIn("没太听清", msg)

    def test_immediate_reply_uses_result(self):
        self.assertEqual(reply_for("laser_point", {"result": "激光已指向 desk-03"}),
                         "激光已指向 desk-03")

    def test_moving_command_honest_downgrade(self):
        out = reply_for("recheck_station", {"result": "已发起到 desk-03 的复核导航"})
        self.assertIn("已发起到 desk-03 的复核导航", out)
        self.assertIn("底盘移动还在调试", out)

    def test_inspection_round_also_downgrades(self):
        self.assertIn("底盘移动还在调试",
                      reply_for("inspection_round", {"result": "已发起巡检:依次复核 3 个工位"}))

    def test_unsupported_apologizes(self):
        self.assertEqual(reply_for("recheck_station", {"unsupported": "工位 desk-99 未配置 waypoint"}),
                         "抱歉,工位 desk-99 未配置 waypoint")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_dialog.py -v`
Expected: FAIL(`ModuleNotFoundError: dialog`)。

- [ ] **Step 3: Implement** — `dialog.py`:

```python
"""Pure Chinese voice-reply phrasing. No rclpy.

Moving commands (recheck/inspection_round) get an honest downgrade suffix because
the chassis PID is not yet wired — we do not pretend the robot has arrived.
"""
from __future__ import annotations

from typing import Dict

_MOVING = {"recheck_station", "inspection_round"}
_NOT_UNDERSTOOD = "抱歉,没太听清,可以说『去三号桌复核』『激光指示二号桌』这样的指令"


def wake_ack(text: str = "我在") -> str:
    return text


def not_understood() -> str:
    return _NOT_UNDERSTOOD


def reply_for(cmd_type: str, plan: Dict) -> str:
    if "unsupported" in plan:
        return f"抱歉,{plan['unsupported']}"
    result = plan.get("result", "好的")
    if cmd_type in _MOVING:
        return f"{result};底盘移动还在调试,稍后执行"
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_dialog.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/dialog.py tests/test_dialog.py
git commit -m "feat(asr): 语音话术 dialog(唤醒应答/引导/移动类诚实降级)"
```

---

### Task 6: `asr_engine.py` — `AsrBackend` 接口 + Mock + sherpa 真实现

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py`
- Test: `tests/test_asr_controller.py`(本任务先建文件,验证 Mock 行为;controller 在 Task 7)

**Interfaces:**
- Produces:
  - 事件类型(plain dict):`{"kind": "wake"}` 与 `{"kind": "utterance", "text": str}`。
  - `class AsrBackend(Protocol)`:`set_mode(mode: str) -> None`(`"kws"|"dialog"|"off"`);`poll() -> Optional[dict]`(无事件返回 `None`)。
  - `MockAsrBackend(events: list[dict])`:`poll()` 依次弹出预设事件;记录 `set_mode` 调用到 `.modes`。
  - `SherpaAsrBackend(cfg)`:真实现,延迟 import `sherpa_onnx`/`sounddevice`;本计划不在开发机测真推理(Task 9 上板)。

- [ ] **Step 1: Write the failing test** — `tests/test_asr_controller.py`(先只测 Mock):

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.asr_engine import MockAsrBackend, wake_event, utterance_event  # noqa: E402


class MockBackendTests(unittest.TestCase):
    def test_poll_pops_events_then_none(self):
        be = MockAsrBackend([wake_event(), utterance_event("去三号桌复核")])
        self.assertEqual(be.poll(), {"kind": "wake"})
        self.assertEqual(be.poll(), {"kind": "utterance", "text": "去三号桌复核"})
        self.assertIsNone(be.poll())

    def test_set_mode_recorded(self):
        be = MockAsrBackend([])
        be.set_mode("dialog"); be.set_mode("kws")
        self.assertEqual(be.modes, ["dialog", "kws"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_asr_controller.py -v`
Expected: FAIL(`ModuleNotFoundError: asr_engine`)。

- [ ] **Step 3: Implement** — `asr_engine.py`:

```python
"""ASR backends behind a small event interface so the controller stays pure.

Events are dicts: {"kind":"wake"} | {"kind":"utterance","text": str}.
MockAsrBackend feeds scripted events for unit tests. SherpaAsrBackend wraps the
sherpa-onnx KWS + VAD + offline SenseVoice recognizer over a sounddevice mic; it
imports sherpa_onnx/sounddevice lazily so this module imports fine on a dev box.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def wake_event() -> Dict[str, Any]:
    return {"kind": "wake"}


def utterance_event(text: str) -> Dict[str, Any]:
    return {"kind": "utterance", "text": text}


class MockAsrBackend:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self._events = list(events)
        self.modes: List[str] = []

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def poll(self) -> Optional[Dict[str, Any]]:
        return self._events.pop(0) if self._events else None


class SherpaAsrBackend:
    """Real backend. Constructed on the RDK; verified on-board (Task 9), not in CI."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        import sherpa_onnx  # noqa: F401  (lazy: only present on the board)
        import sounddevice  # noqa: F401
        self._cfg = cfg
        # KeywordSpotter / VoiceActivityDetector / OfflineRecognizer wiring lives here;
        # implemented against the installed models during on-board bring-up (Task 9).
        raise NotImplementedError("SherpaAsrBackend wiring is completed during on-board bring-up")

    def set_mode(self, mode: str) -> None:  # pragma: no cover - board only
        ...

    def poll(self) -> Optional[Dict[str, Any]]:  # pragma: no cover - board only
        ...
```

> `SherpaAsrBackend` 的真实采集/识别循环在上板 bring-up(Task 9)按已装模型补全;开发机只需 `MockAsrBackend` 驱动 controller 测试。模块顶层不 import sherpa,故 CI 可正常 import。

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_asr_controller.py -v`
Expected: PASS(Mock 用例)。

- [ ] **Step 5: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py tests/test_asr_controller.py
git commit -m "feat(asr): ASR backend 事件接口 + MockAsrBackend + sherpa 真实现骨架"
```

---

### Task 7: `asr_controller.py` — 状态机与编排

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_controller.py`
- Test: `tests/test_asr_controller.py`(追加 `ControllerTests`)

**Interfaces:**
- Consumes:`AsrBackend`(Task 6)、`intent_fn(text)->cmd|None`(Task 3/4)、`CommandExecutor.execute`(Task 2)、`dialog.*`(Task 5)、`dispatch_command`(Task 1)。
- Produces:
  - `AsrController(backend, intent_fn, dispatch_fn, executor, speak_fn, *, stations_cfg, gimbal_cfg, dialog_timeout_sec=8.0, enabled=True)`。
    `dispatch_fn(cmd, stations_cfg, gimbal_cfg) -> plan`;`speak_fn(text)->None`。
  - `controller.tick(now: float) -> None` — 处理一个 backend 事件 + 超时。
  - `controller.set_enabled(enabled: bool) -> None` — 远程开关(DISABLED ↔ IDLE)。
  - `controller.state -> str`(`"disabled"|"idle"|"dialog"`)。

- [ ] **Step 1: Write the failing tests** — 在 `tests/test_asr_controller.py` 追加:

```python
from inspection_manager.asr_controller import AsrController  # noqa: E402
from inspection_manager.intent import parse_intent  # noqa: E402

STATIONS = {"waypoints": {"wp_desk03": "desk-03"}}
GIMBAL = {"aim": {"desk-03": [12.6, -11.6]}}


def _dispatch(cmd, stations_cfg, gimbal_cfg):
    from inspection_manager.command_receiver import dispatch_command
    return dispatch_command(cmd, stations_cfg, gimbal_cfg)


class FakeExecutor:
    def __init__(self): self.plans = []
    def execute(self, plan):
        self.plans.append(plan); return plan.get("result")


def _make(events, **kw):
    be = MockAsrBackend(events)
    spoken = []
    ex = FakeExecutor()
    c = AsrController(be, parse_intent, _dispatch, ex, spoken.append,
                      stations_cfg=STATIONS, gimbal_cfg=GIMBAL, dialog_timeout_sec=8.0, **kw)
    return c, be, spoken, ex


class ControllerTests(unittest.TestCase):
    def test_starts_idle_in_kws_mode(self):
        c, be, _, _ = _make([])
        self.assertEqual(c.state, "idle")
        self.assertEqual(be.modes[-1], "kws")

    def test_wake_acks_and_enters_dialog(self):
        c, be, spoken, _ = _make([wake_event()])
        c.tick(0.0)
        self.assertEqual(c.state, "dialog")
        self.assertEqual(spoken, ["我在"])
        self.assertEqual(be.modes[-1], "dialog")

    def test_utterance_dispatches_and_replies(self):
        c, be, spoken, ex = _make([wake_event(), utterance_event("激光指示三号桌")])
        c.tick(0.0); c.tick(0.1)
        self.assertEqual(ex.plans[-1]["laser_aim"], [12.6, -11.6])
        self.assertEqual(spoken[-1], "激光已指向 desk-03(pan=12.6,tilt=-11.6)")

    def test_moving_command_downgrade_phrasing(self):
        c, _, spoken, _ = _make([wake_event(), utterance_event("去三号桌复核")])
        c.tick(0.0); c.tick(0.1)
        self.assertIn("底盘移动还在调试", spoken[-1])

    def test_not_understood(self):
        c, _, spoken, ex = _make([wake_event(), utterance_event("今天星期几")])
        c.tick(0.0); c.tick(0.1)
        self.assertIn("没太听清", spoken[-1])
        self.assertEqual(ex.plans, [])

    def test_dialog_timeout_returns_to_idle(self):
        c, be, _, _ = _make([wake_event()])
        c.tick(0.0)
        c.tick(9.0)                          # 9s 静默 > 8s 超时
        self.assertEqual(c.state, "idle")
        self.assertEqual(be.modes[-1], "kws")

    def test_set_enabled_false_disables(self):
        c, be, _, _ = _make([])
        c.set_enabled(False)
        self.assertEqual(c.state, "disabled")
        self.assertEqual(be.modes[-1], "off")
        c.tick(0.0)                          # disabled 时 tick 不处理事件
        self.assertEqual(c.state, "disabled")

    def test_vlm_fallback_used_when_rule_misses(self):
        c, _, spoken, ex = _make(
            [wake_event(), utterance_event("麻烦到三号桌那边瞅一眼")],
            vlm_chat_fn=lambda p: '{"type":"recheck_station","params":{"station_id":"desk-03"},"confidence":0.9}')
        c.tick(0.0); c.tick(0.1)
        self.assertEqual(ex.plans[-1]["actions"][0]["topic_key"], "recheck_topic")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_asr_controller.py::ControllerTests -v`
Expected: FAIL(`ModuleNotFoundError: asr_controller`)。

- [ ] **Step 3: Implement** — `asr_controller.py`:

```python
"""Voice interaction state machine + orchestration. Pure (no rclpy/sherpa).

States: disabled -> (set_enabled True) -> idle(KWS only) -> (wake) -> dialog(VAD+ASR)
        dialog -> (silence > timeout) -> idle ;  any -> (set_enabled False) -> disabled
tick(now) processes at most one backend event plus the dialog-timeout check; the node
calls it on a fast timer. Rule intent first; optional VLM fallback via vlm_chat_fn.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from inspection_manager import dialog
from inspection_manager.intent import vlm_fallback


class AsrController:
    def __init__(self, backend, intent_fn: Callable[[str], Optional[Dict]],
                 dispatch_fn: Callable[[Dict, Dict, Dict], Dict], executor,
                 speak_fn: Callable[[str], None], *, stations_cfg: Dict, gimbal_cfg: Dict,
                 dialog_timeout_sec: float = 8.0, enabled: bool = True,
                 vlm_chat_fn: Optional[Callable[[str], str]] = None,
                 wake_ack_text: str = "我在") -> None:
        self._be = backend
        self._intent = intent_fn
        self._dispatch = dispatch_fn
        self._ex = executor
        self._speak = speak_fn
        self._stations = stations_cfg
        self._gimbal = gimbal_cfg
        self._timeout = float(dialog_timeout_sec)
        self._vlm_chat = vlm_chat_fn
        self._wake_text = wake_ack_text
        self._last_activity = 0.0
        self.state = "disabled"
        self.set_enabled(enabled)

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.state = "idle"
            self._be.set_mode("kws")
        else:
            self.state = "disabled"
            self._be.set_mode("off")

    def tick(self, now: float) -> None:
        if self.state == "disabled":
            return
        if self.state == "dialog" and (now - self._last_activity) > self._timeout:
            self.state = "idle"
            self._be.set_mode("kws")
            return
        ev = self._be.poll()
        if not ev:
            return
        if ev["kind"] == "wake" and self.state == "idle":
            self.state = "dialog"
            self._be.set_mode("dialog")
            self._last_activity = now
            self._speak(dialog.wake_ack(self._wake_text))
        elif ev["kind"] == "utterance" and self.state == "dialog":
            self._last_activity = now
            self._handle_text(ev["text"])

    def _handle_text(self, text: str) -> None:
        cmd = self._intent(text)
        if cmd is None and self._vlm_chat is not None:
            cmd = vlm_fallback(text, self._vlm_chat)
        if cmd is None:
            self._speak(dialog.not_understood())
            return
        plan = self._dispatch(cmd, self._stations, self._gimbal)
        if "unsupported" not in plan:
            self._ex.execute(plan)
        self._speak(dialog.reply_for(cmd["type"], plan))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_asr_controller.py -v`
Expected: PASS(Mock + Controller 全部用例)。

- [ ] **Step 5: Run all pure-logic tests**

Run: `python -m pytest tests/test_intent.py tests/test_dialog.py tests/test_command_executor.py tests/test_asr_controller.py tests/test_command_receiver.py -v`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_controller.py tests/test_asr_controller.py
git commit -m "feat(asr): 语音状态机与编排 AsrController(唤醒/识别/意图/执行/超时/远程开关)"
```

---

### Task 8: `asr_node.py` rclpy 薄壳 + 配线(config/launch/setup)

**Files:**
- Create: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_node.py`
- Create: `rdk_x5/ros2_ws/src/inspection_manager/config/asr.yaml`
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/setup.py:33`(entry_points 加一行)
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/launch/inspection.launch.py`

**Interfaces:**
- Consumes:`AsrController`、`SherpaAsrBackend`、`CommandExecutor`、`dispatch_command`、`qwen_client`(包 `vlm_chat_fn`)。
- 无新单测(纯逻辑已全覆盖);本任务产出靠 Task 9 上板验证。装配正确性以 `python -c` import-smoke 检查不依赖 rclpy 的部分。

- [ ] **Step 1: Write `asr.yaml`** — `config/asr.yaml`:

```yaml
asr_node:
  ros__parameters:
    enabled: true
    mic_device: ""
    sample_rate: 16000
    num_threads: 2
    kws_model_dir: "/root/sherpa/sherpa-onnx-kws-zipformer-wenetspeech"
    kws_keywords_file: "/root/sherpa/keywords.txt"
    vad_model: "/root/sherpa/silero_vad.onnx"
    asr_model_dir: "/root/sherpa/sherpa-onnx-sense-voice-zh-int8"
    dialog_timeout_sec: 8.0
    wake_ack_text: "我在"
    tick_sec: 0.05
    vlm_fallback_enabled: true
    vlm_base_url: "http://localhost:8080/v1"
    vlm_min_confidence: 0.5
    stations_config: ""
    gimbal_aim_config: ""
    voice_topic: "/inspection/voice"
    voice_control_topic: "/inspection/voice_control"
    enabled_state_file: "~/.asr_enabled"
    gimbal_topic: "/gimbal/target_angle"
    gimbal_enable_topic: "/gimbal/enable"
    laser_topic: "/laser/enable"
    laser_indicate_sec: 8.0
```

- [ ] **Step 2: Write `asr_node.py`** — rclpy 薄壳(装配 + 持久化 + 订阅 + 定时驱动):

```python
"""ROS node: mic -> KWS/VAD/ASR -> intent -> dispatch_command -> CommandExecutor + TTS.

Thin shell over pure modules. Subscribes /inspection/voice_control for the App remote
on/off switch and persists the enabled state so it survives restarts.
"""
from __future__ import annotations

import json
import os

import rclpy
from geometry_msgs.msg import Vector3
from rclpy.node import Node
from std_msgs.msg import Bool, String

from inspection_manager.asr_controller import AsrController
from inspection_manager.asr_engine import SherpaAsrBackend
from inspection_manager.command_executor import CommandExecutor
from inspection_manager.command_receiver import dispatch_command


class AsrNode(Node):
    def __init__(self) -> None:
        super().__init__("asr_node")
        gp = self.declare_parameter
        for name, default in [
            ("enabled", True), ("mic_device", ""), ("sample_rate", 16000), ("num_threads", 2),
            ("kws_model_dir", ""), ("kws_keywords_file", ""), ("vad_model", ""), ("asr_model_dir", ""),
            ("dialog_timeout_sec", 8.0), ("wake_ack_text", "我在"), ("tick_sec", 0.05),
            ("vlm_fallback_enabled", True), ("vlm_base_url", "http://localhost:8080/v1"),
            ("vlm_min_confidence", 0.5), ("stations_config", ""), ("gimbal_aim_config", ""),
            ("voice_topic", "/inspection/voice"), ("voice_control_topic", "/inspection/voice_control"),
            ("enabled_state_file", "~/.asr_enabled"), ("gimbal_topic", "/gimbal/target_angle"),
            ("gimbal_enable_topic", "/gimbal/enable"), ("laser_topic", "/laser/enable"),
            ("laser_indicate_sec", 8.0),
        ]:
            gp(name, default)
        g = self.get_parameter
        self._state_file = os.path.expanduser(str(g("enabled_state_file").value))

        self._string_pubs = {
            "voice_topic": self.create_publisher(String, str(g("voice_topic").value), 10),
        }
        self._vector_pubs = {
            "gimbal_topic": self.create_publisher(Vector3, str(g("gimbal_topic").value), 10),
        }
        self._bool_pubs = {
            "gimbal_enable_topic": self.create_publisher(Bool, str(g("gimbal_enable_topic").value), 10),
            "laser_topic": self.create_publisher(Bool, str(g("laser_topic").value), 10),
        }
        executor = CommandExecutor(self._publish_primitive, self.create_timer,
                                   float(g("laser_indicate_sec").value))

        stations_cfg = self._read_yaml(str(g("stations_config").value))
        gimbal_cfg = self._read_yaml(str(g("gimbal_aim_config").value))
        vlm_chat = self._make_vlm_chat() if bool(g("vlm_fallback_enabled").value) else None

        backend = SherpaAsrBackend({
            "mic_device": str(g("mic_device").value), "sample_rate": int(g("sample_rate").value),
            "num_threads": int(g("num_threads").value), "kws_model_dir": str(g("kws_model_dir").value),
            "kws_keywords_file": str(g("kws_keywords_file").value), "vad_model": str(g("vad_model").value),
            "asr_model_dir": str(g("asr_model_dir").value),
        })

        from inspection_manager.intent import parse_intent
        self.controller = AsrController(
            backend, parse_intent, dispatch_command, executor,
            self._speak, stations_cfg=stations_cfg, gimbal_cfg=gimbal_cfg,
            dialog_timeout_sec=float(g("dialog_timeout_sec").value),
            enabled=self._load_enabled(bool(g("enabled").value)),
            vlm_chat_fn=vlm_chat, wake_ack_text=str(g("wake_ack_text").value))

        self.create_subscription(String, str(g("voice_control_topic").value), self._on_voice_control, 10)
        self._clock = self.get_clock()
        self.create_timer(float(g("tick_sec").value), self._on_tick)
        self.get_logger().info("asr_node up")

    # --- glue ---
    def _publish_primitive(self, topic_key: str, kind: str, data) -> None:
        if kind == "vector3":
            x, y, z = data
            self._vector_pubs[topic_key].publish(Vector3(x=float(x), y=float(y), z=float(z)))
        elif kind == "bool":
            self._bool_pubs[topic_key].publish(Bool(data=bool(data)))
        else:
            self._string_pubs[topic_key].publish(String(data=data))

    def _speak(self, text: str) -> None:
        self._string_pubs["voice_topic"].publish(String(data=text))

    def _on_tick(self) -> None:
        self.controller.tick(self._clock.now().nanoseconds / 1e9)

    def _on_voice_control(self, msg: String) -> None:
        try:
            enabled = bool(json.loads(msg.data).get("enabled"))
        except (ValueError, TypeError):
            return
        self.controller.set_enabled(enabled)
        self._save_enabled(enabled)

    # --- enabled persistence ---
    def _load_enabled(self, default: bool) -> bool:
        try:
            with open(self._state_file, "r", encoding="utf-8") as fh:
                return fh.read().strip() == "1"
        except OSError:
            return default

    def _save_enabled(self, enabled: bool) -> None:
        try:
            with open(self._state_file, "w", encoding="utf-8") as fh:
                fh.write("1" if enabled else "0")
        except OSError as exc:  # noqa: BLE001
            self.get_logger().warn(f"persist enabled failed: {exc}")

    def _make_vlm_chat(self):
        from inspection_manager.qwen_client import OpenAICompatVLMClient
        base = str(self.get_parameter("vlm_base_url").value)
        client = OpenAICompatVLMClient(base_url=base)

        def chat(prompt: str) -> str:
            return client.chat_text(prompt)  # text-only helper; see Task 8 Step 3
        return chat

    @staticmethod
    def _read_yaml(path: str) -> dict:
        if not path:
            return {}
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except Exception:  # noqa: BLE001
            return {}


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AsrNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add a text-only helper to `qwen_client`** — 若 `OpenAICompatVLMClient` 无纯文本方法,加一个(读现有类后按其 HTTP 风格实现):

```python
    def chat_text(self, prompt: str) -> str:
        """Text-only chat (no image) for voice intent fallback. Returns model text."""
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.0, "max_tokens": 128}
        data = self._post_json("/chat/completions", payload)   # reuse existing HTTP path
        return data["choices"][0]["message"]["content"]
```
> 先读 `qwen_client.py` 现有 `OpenAICompatVLMClient` 的 HTTP 发送方法名与字段(base_url/model/超时),对齐后再落上面方法;不要新造一套 HTTP。

- [ ] **Step 4: Register entry point** — `setup.py` 的 `console_scripts` 列表(行 33 后)加:

```python
            "asr_node = inspection_manager.asr_node:main",
```

- [ ] **Step 5: Add to launch** — `launch/inspection.launch.py` 仿现有 `voice_node` 增一个 `Node`(用 `config/asr.yaml`,`condition` 可按已有参数风格留开关),关键片段:

```python
    Node(
        package="inspection_manager", executable="asr_node", name="asr_node",
        parameters=[os.path.join(get_package_share_directory("inspection_manager"), "config", "asr.yaml")],
        output="screen",
    ),
```
(若该 launch 已用其它方式加载 config,沿用其既有写法。)

- [ ] **Step 6: Import-smoke the pure parts**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS(纯模块测试不受 node 影响)。

Run(确认纯模块无语法/import 回归,不触发 rclpy):
`python -c "import sys; sys.path.insert(0,'rdk_x5/ros2_ws/src/inspection_manager'); import inspection_manager.asr_controller, inspection_manager.asr_engine, inspection_manager.command_executor, inspection_manager.intent, inspection_manager.dialog; print('ok')"`
Expected: 打印 `ok`(`asr_node`/`SherpaAsrBackend` 不在此 import,故无需 rclpy/sherpa)。

- [ ] **Step 7: Commit**

```bash
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_node.py \
        rdk_x5/ros2_ws/src/inspection_manager/config/asr.yaml \
        rdk_x5/ros2_ws/src/inspection_manager/setup.py \
        rdk_x5/ros2_ws/src/inspection_manager/launch/inspection.launch.py \
        rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/qwen_client.py
git commit -m "feat(asr): asr_node 薄壳 + asr.yaml + launch/setup 配线 + 文本兑底 chat helper"
```

---

### Task 9: 部署文档与上板验证清单

**Files:**
- Create: `docs/architecture/voice_asr_setup.md`

**Interfaces:** 无代码;落地 `SherpaAsrBackend` 真实现 + 上板验证(在板上完成,文档指导)。

- [ ] **Step 1: Write `voice_asr_setup.md`** — 对齐 `docs/architecture/voice_broadcast_setup.md` 风格,含:
  - 依赖安装:`pip install sherpa-onnx sounddevice`、系统 `libportaudio2`(`sudo apt install libportaudio2`);`num_threads` 说明。
  - 模型下载与放置(到 `/root/sherpa/`):KWS `sherpa-onnx-kws-zipformer-wenetspeech`、`silero_vad.onnx`、`sherpa-onnx-sense-voice-zh-...-int8`;`keywords.txt` 写入唤醒词拼音 token(`小巡`/`巡检助手`,格式见 sherpa KWS 文档)。
  - 麦克风探测:`arecord -l` 找 USB 麦克风 card/device,`arecord -D plughw:X,0 -f S16_LE -r 16000 -c 1 t.wav` 试录,得到 `mic_device` 值填进 `asr.yaml`。
  - `SherpaAsrBackend` 实现要点(在板上补全 `asr_engine.py` 的真采集循环):sounddevice 16kHz 单声道流 → `set_mode("kws")` 跑 `KeywordSpotter`、`"dialog"` 跑 `VAD`+`OfflineRecognizer`、`"off"` 停采集;命中唤醒/整句识别分别 `poll()` 出 `wake_event()`/`utterance_event(text)`。
  - 算力保护:`num_threads=2`、规则优先、(可选)thermal_zone 监控降级开关说明。
  - **上板验证清单**(勾选项):
    - [ ] `arecord` 能录到麦克风音频。
    - [ ] 唤醒词「小巡」「巡检助手」命中,误唤醒率可接受。
    - [ ] 端到端真跑通(立即类):激光指示 / 语音播报 / 生成报告 / 课后验收。
    - [ ] 移动类(复核/巡检)回执措辞为"…;底盘移动还在调试,稍后执行"(不假装完成)。
    - [ ] App 发 `voice_control{enabled:false}` → asr_node 停止监听;`true` → 恢复;重启后保持上次状态(读 `~/.asr_enabled`)。
    - [ ] 语音与 VLM 同时触发时无明显卡顿,风扇下温度可控。

- [ ] **Step 2: Commit**

```bash
git add docs/architecture/voice_asr_setup.md
git commit -m "docs(asr): 端侧语音识别部署指南与上板验证清单"
```

---

## Self-Review

**Spec coverage:**
- §3 数据流(唤醒→VAD→ASR→意图→执行→回执→超时)→ Task 6(事件接口)+ Task 7(状态机)。✓
- §4.1 asr_node 壳/采集线程 → Task 8 + Task 9(真采集循环上板补全)。✓
- §4.2 intent 规则 + VLM 兑底 → Task 3 + Task 4。✓(find_item 明确收敛为后续,见 File Structure 注)
- §4.3 ASR 三件套 + Mock → Task 6 + Task 9(模型/真实现)。✓
- §4.4 CommandExecutor 抽取 + node 委托 → Task 2。✓
- §4.5 voice_control 预留(dispatch 分支 + 话题 + 禁用态 + 持久化)→ Task 1 + Task 7(set_enabled)+ Task 8(订阅/持久化)。✓
- §4.6 移动类诚实降级 → Task 5(reply_for)+ Task 7(编排)。✓
- §5 算力缓解:规则优先(Task 3/7)、num_threads(Task 8 config)、互斥锁/温控 → 互斥锁与温控为运行期策略,在 Task 9 文档与真 backend 落地说明(纯逻辑不涉)。✓
- §6 config → Task 8。✓ §7 测试 → 各 Task 自带。✓ §8 部署/验证 → Task 9。✓

**Placeholder scan:** 无 TBD/TODO;每个代码步给出完整代码;Task 8 Step 3 显式要求先读 `qwen_client` 再对齐(非占位,是防止重造 HTTP)。

**Type consistency:** `publish(topic_key, kind, data)`/`schedule(period, cb)`(Task 2)在 Task 8 `_publish_primitive`/`create_timer` 一致;事件 `wake_event()`/`utterance_event(text)`(Task 6)在 Task 7 测试与 controller 一致;`dispatch_command` 返回 `actions`/`laser_aim`/`unsupported`(Task 1)在 Task 2 executor 与 Task 5 dialog 一致;`reply_for(cmd_type, plan)`(Task 5)在 Task 7 `_handle_text` 一致。✓
