# asr 麦克风启动韧性 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** asr 开麦失败不再崩溃 asr_node;`poll()` 每 3s 后台限流重试,麦插上后自动开始收音、无需手动重起。

**Architecture:** 把开麦从 `SherpaAsrBackend.__init__` 的"重试 60s 后 raise"改为"尝试一次、失败不崩";新增 `_ensure_mic()` 在单线程 `poll()` 里限流重试(复用现有 poll 线程,不引入新线程,契合 sherpa 单线程约束)。限流时机抽成纯函数 `_should_retry_mic` 单测覆盖;开麦/采集本身 board-only,靠上板验证。

**Tech Stack:** Python 3.10(ROS2 Humble, ament_python)、sounddevice/sherpa-onnx(board-only)、unittest。

## Global Constraints

- 测试运行(仓库根 `/Users/sthefirst/Desktop/Soc_China`):`python3 -m unittest tests.test_asr_engine -v`(无 pytest)。
- 改 `.py` 后上板部署:`rm -rf build/inspection_manager install/inspection_manager && colcon build --packages-select inspection_manager`(ament_python 缓存坑)。
- 范围:**仅启动场景**(麦启动时不可用 → 不崩 → 后台重试 → 插上自动开)。**不管运行中掉线恢复**(非目标)。
- **不改** `asr.yaml`、`asr_node.py`、开麦成功后的音频回调/poll 处理/FIR 重采样/anti-echo 逻辑。只改"何时开麦 + 失败不崩"。
- 限流间隔 `MIC_RETRY_INTERVAL_S = 3.0`(秒)。
- asr_engine 无 rclpy logger,用 `print(..., flush=True)`(输出进 /tmp/asr.log)。
- 分支已在 `feat/asr-mic-resilient-retry`。

---

### Task 1: 限流纯函数 `_should_retry_mic` + 单测

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py`(模块级加函数)
- Test: `tests/test_asr_engine.py`(新建)

**Interfaces:**
- Produces: `_should_retry_mic(last_try: float, now: float, interval: float) -> bool` —— `now - last_try >= interval` 时返回 True。Task 2 的 `_ensure_mic()` 用它。

- [ ] **Step 1: 写失败测试(新建 tests/test_asr_engine.py)**

```python
import sys
import unittest
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "rdk_x5" / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(PACKAGE_SRC))

from inspection_manager.asr_engine import _should_retry_mic  # noqa: E402


class ShouldRetryMicTests(unittest.TestCase):
    def test_within_interval_no_retry(self):
        # 距上次尝试不足 interval -> 不重试
        self.assertFalse(_should_retry_mic(last_try=10.0, now=12.0, interval=3.0))

    def test_exactly_interval_retries(self):
        # 恰好等于 interval -> 重试(>=)
        self.assertTrue(_should_retry_mic(last_try=10.0, now=13.0, interval=3.0))

    def test_past_interval_retries(self):
        self.assertTrue(_should_retry_mic(last_try=10.0, now=20.0, interval=3.0))

    def test_first_try_from_zero(self):
        # last_try=0(从未尝试) + now 远大于 interval -> 重试
        self.assertTrue(_should_retry_mic(last_try=0.0, now=100.0, interval=3.0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m unittest tests.test_asr_engine -v`
Expected: FAIL —— `ImportError: cannot import name '_should_retry_mic'`

- [ ] **Step 3: 加纯函数(asr_engine.py 模块级,放在文件顶部 helper 区,如 `_resolve_onnx` 附近)**

```python
def _should_retry_mic(last_try: float, now: float, interval: float) -> bool:
    """True if enough time elapsed since last_try to retry opening the mic."""
    return now - last_try >= interval
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m unittest tests.test_asr_engine -v`
Expected: PASS —— 4 tests OK。

- [ ] **Step 5: 提交**

```bash
cd /Users/sthefirst/Desktop/Soc_China
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py tests/test_asr_engine.py
git commit -m "feat(asr): _should_retry_mic throttle helper + tests

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: asr_engine 开麦韧性重构

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py`(`SherpaAsrBackend.__init__` 开麦段、新增方法、`poll()` 开头)

**Interfaces:**
- Consumes: `_should_retry_mic(last_try, now, interval)`(Task 1)。
- Produces: `_open_mic() -> bool`、`_ensure_mic()`、`_audio_cb(...)` 方法;模块常量 `MIC_RETRY_INTERVAL_S = 3.0`。

**背景(当前代码,约 line 132-184):** `__init__` 末尾有嵌套 `_cb`、`_open`、`_open_best`,一个 `for _ in range(30): ... else: raise RuntimeError(...)` 重试循环,随后 FIR 配置 + `self._stream.start()`。本任务把这整段(从 `self._queue = queue.Queue()` 之后的 `_cb` 定义起,到 `self._stream.start()` 止)替换为:初始化 state + 调用 `_open_mic()` 不崩;并新增三个方法。

- [ ] **Step 1: 加模块常量(asr_engine.py 模块级,`_should_retry_mic` 附近)**

```python
MIC_RETRY_INTERVAL_S = 3.0
```

- [ ] **Step 2: 替换 `__init__` 的开麦段**

把当前 `__init__` 中从 `self._queue: "queue.Queue" = queue.Queue()` 到 `self._stream.start()` 之间的全部内容(即 `_cb`/`_open`/`_open_best` 嵌套定义、`for _ in range(30)` 重试循环+`raise`、FIR 配置、`self._stream.start()`),替换为:

```python
        self._queue: "queue.Queue" = queue.Queue()
        self._mode = "off"
        self._cap_sr = self._sr
        self._xruns = 0
        self._stream = None
        self._last_mic_try = 0.0   # monotonic; throttle via _should_retry_mic
        self._mic_waiting_logged = False
        # The USB mic disconnects/re-enumerates intermittently. Try once now; if it's
        # not present, DON'T crash — poll() retries every MIC_RETRY_INTERVAL_S and the
        # node keeps running (still responds to /inspection/voice_control).
        if not self._open_mic():
            print(f"[asr_engine] mic '{self._device}' not ready at startup; "
                  f"will retry in poll() every {MIC_RETRY_INTERVAL_S}s", flush=True)
```

- [ ] **Step 3: 新增 `_audio_cb` + `_open_mic` 方法(放在 `__init__` 之后、`set_mode` 之前)**

```python
    def _audio_cb(self, indata, frames, time_info, status):  # pragma: no cover - board only
        if status:  # input overflow (xrun): callback starved (e.g. GIL held by inference)
            self._xruns += 1
        self._queue.put(indata[:, 0].copy())  # mono float32

    def _open_mic(self) -> bool:  # pragma: no cover - board only
        """Open the mic stream (16k, else native rate + resample). Configure FIR and
        start the stream. Returns True on success; on failure leaves _stream=None."""
        import numpy as np
        import sounddevice as sd

        def _open(rate):
            # latency="high": large ALSA buffer so brief GIL stalls during inference
            # don't overflow/drop frames (which wrecks recognition).
            return sd.InputStream(device=self._device, samplerate=rate, channels=1,
                                  dtype="float32", blocksize=int(rate * 0.03),
                                  latency="high", callback=self._audio_cb)
        try:
            try:
                stream = _open(self._sr)
                self._cap_sr = self._sr
            except Exception:  # device rejects 16kHz -> native rate + resample
                info = sd.query_devices(self._device, "input")
                self._cap_sr = int(info.get("default_samplerate") or 48000)
                stream = _open(self._cap_sr)
        except Exception:  # noqa: BLE001 - mic absent/unavailable
            return False
        # Stateful anti-aliased decimation (FIR, not IIR: a finite input can't produce
        # inf/nan through a bounded weighted sum, so a transient glitch can't poison the
        # stream; lfilter carries state for gap-free continuity).
        if self._cap_sr != self._sr:
            from scipy.signal import firwin
            self._decim = max(1, round(self._cap_sr / self._sr))
            self._fir_b = firwin(64, 0.9 * self._sr / 2, fs=self._cap_sr).astype("float64")
            self._fir_zi = np.zeros(len(self._fir_b) - 1, dtype="float64")
            self._decim_rem = np.zeros(0, dtype="float32")
        stream.start()
        self._stream = stream
        return True

    def _ensure_mic(self) -> None:  # pragma: no cover - board only
        """If the mic isn't open, retry opening it (throttled). Auto-recovers when the
        user plugs the mic back in."""
        import time
        if self._stream is not None:
            return
        now = time.monotonic()
        if not _should_retry_mic(self._last_mic_try, now, MIC_RETRY_INTERVAL_S):
            return
        self._last_mic_try = now
        if self._open_mic():
            print(f"[asr_engine] mic opened (sr={self._cap_sr})", flush=True)
            self._mic_waiting_logged = False
        elif not self._mic_waiting_logged:
            print("[asr_engine] still waiting for mic...", flush=True)
            self._mic_waiting_logged = True  # log once per outage, don't spam
```

- [ ] **Step 4: `poll()` 开头调用 `_ensure_mic`**

在 `poll()` 方法体最前面(现有 `import os` / `import time` / `import numpy as np` 之后、`chunks = self._drain()` 之前)插入:

```python
        self._ensure_mic()
        if self._stream is None:
            return None
```

(其余 poll 逻辑——anti-echo、drain、KWS/VAD/ASR——完全不动。)

- [ ] **Step 5: 编译检查(board-only,无纯单测;功能由 Task 3 上板验证)**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m py_compile rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py`
Expected: 无输出(编译通过)。
再跑 Task 1 的纯函数测试确认没破坏:`python3 -m unittest tests.test_asr_engine -v` → 4 tests OK。

- [ ] **Step 6: 提交**

```bash
cd /Users/sthefirst/Desktop/Soc_China
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py
git commit -m "feat(asr): mic open failure no longer crashes; poll() auto-retries

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 上板验证(拔麦起→不崩→插→自动恢复)

**Files:** 无(部署 + 验证)

**Interfaces:** 验证 Task 2 在真机端到端正确。

- [ ] **Step 1: 部署到板上(重建包)**

```bash
cd /Users/sthefirst/Desktop/Soc_China
scp rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py root@192.168.128.10:/root/Soc_China/rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/
ssh root@192.168.128.10 'cd /root/Soc_China/rdk_x5/ros2_ws && rm -rf build/inspection_manager install/inspection_manager && source /opt/ros/humble/setup.bash && colcon build --packages-select inspection_manager 2>&1 | tail -2'
```
Expected: colcon build 成功。

- [ ] **Step 2: 拔麦场景 —— 麦不在时起 asr,确认不崩**

(若不便物理拔麦,用一个不存在的设备名模拟:临时起 `ros2 run inspection_manager asr_node --ros-args -p mic_device:="NO_SUCH_MIC" ...`;否则物理拔掉 USB 麦后 `bash /root/start_asr.sh`。)

```bash
ssh root@192.168.128.10 'pkill -9 -f "lib/inspection_manager/asr_node"; sleep 2; bash /root/start_asr.sh; sleep 14; echo "=== asr 进程(应=1,不崩) ==="; ps -ef|grep "lib/inspection_manager/asr_node"|grep -v grep|wc -l; echo "=== asr.log ==="; tail -8 /tmp/asr.log'
```
Expected: asr 进程=1(**没崩**);asr.log 有 "mic ... not ready"/"still waiting for mic" 和 `asr_node up`;**无** Traceback/`Process exited with failure`。

- [ ] **Step 3: 插麦场景 —— 插上后自动恢复**

物理插上 USB 麦(或若用 NO_SUCH_MIC 模拟则重起为正确 mic_device),等几秒:

```bash
ssh root@192.168.128.10 'sleep 6; echo "=== mic opened? ==="; grep "mic opened" /tmp/asr.log | tail -1; echo "=== asr 持有麦? ==="; fuser -v /dev/snd/* 2>&1 | grep -i asr_node && echo ">>> 持有麦,自动恢复" || echo ">>> 未持有"'
```
Expected: asr.log 出现 "mic opened (sr=...)";`fuser` 显示 asr_node 持有 `/dev/snd/pcmC?D0c`(在收音)。

- [ ] **Step 4: 端到端 —— 说"小巡"验证(人工)**

对麦说"小巡" → 应听到音响回"我在"。确认唤醒链路在自愈后正常工作。

- [ ] **Step 5: 验证记录(可选)**

将验证结果记入 `docs/validation/daily/2026-06-24-asr-mic-resilient-retry.md`(若该目录惯例存在),commit;否则跳过。

---

## Self-Review

**Spec 覆盖:** ① 开麦失败不崩(`__init__` 调 `_open_mic` 不 raise)→ Task 2 Step 2。② 后台限流重试 → Task 2 Step 3-4(`_ensure_mic` + poll 调用)+ Task 1(`_should_retry_mic`)。③ 麦插上自动恢复 → Task 2 + Task 3 Step 3 验证。④ node 照常 spin(`poll` 麦没好返回 None)→ Task 2 Step 4。⑤ 限流纯函数单测 → Task 1。⑥ 上板验证 → Task 3。全覆盖。

**Placeholder 扫描:** Task 3 Step 2 的"若不便物理拔麦用 NO_SUCH_MIC 模拟"是明确的可选路径,非占位。其余无 TBD/TODO,代码步骤均含完整代码。

**类型一致:** `_should_retry_mic(last_try, now, interval) -> bool`(Task 1 定义、Task 2 `_ensure_mic` 调用,签名一致);`_open_mic() -> bool`、`_ensure_mic()`、`_audio_cb`、`MIC_RETRY_INTERVAL_S` 在 Task 2 内自洽;`poll()` 调 `_ensure_mic` + 检查 `self._stream`(Task 2 设的 state)。一致。
