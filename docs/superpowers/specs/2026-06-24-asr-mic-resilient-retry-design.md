# 设计:asr 麦克风启动韧性(开麦失败不崩、后台重试自动恢复)

> 日期:2026-06-24
> 状态:设计已评审通过,待写实现计划
> 相关代码:`rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/asr_engine.py`(`SherpaAsrBackend`)

## 1. 背景与问题

USB 麦克风硬件不稳(反复掉线、接触不良——多次记录在案)。开机时若麦未枚举,`SherpaAsrBackend.__init__` 开麦重试 30 次×2s=60s 后 `raise RuntimeError`,导致 `asr_node` 崩溃退出、语音识别完全不工作(说"小巡"无反应),只能人工重插麦 + 重起 asr。一次真实开机故障即由此引起(`lsusb`/`/proc/asound/cards` 均无麦 → asr.log `No input device matching 'USB Composite Device'` → 进程 exit 1)。

## 2. 目标与非目标

### 目标
- 起 asr 时麦不可用:`asr_node` **不崩溃**、正常 spin(仍响应 `/inspection/voice_control` 远程开关等)。
- 后台**持续重试**开麦;用户把麦插上后**自动**开始收音,无需手动重起 asr。

### 非目标(用户选 A,明确排除)
- **不管运行中麦掉线恢复**:asr 正常跑着时麦被拔/掉线的检测与自愈,不在本次范围(需检测音频流中途死亡,sounddevice 行为复杂)。
- **不改开麦成功后的任何逻辑**:音频回调、`poll()` 处理、FIR 重采样、anti-echo 全部不动。仅改"何时开麦 + 开麦失败的处理"。

## 3. 现状(代码事实)

`asr_engine.py` `SherpaAsrBackend.__init__`(约 line 73-184):
1. 加载 KWS / VAD / SenseVoice 模型(不依赖麦)。
2. 定义音频回调 `_cb`(push 单声道 float32 到 `self._queue`)。
3. `_open(rate)` / `_open_best()`:开 `sd.InputStream`,16kHz 失败则查设备原生率(48k)重开。
4. **重试循环**(line ~161-167):`for _ in range(30): try _open_best() ... except: sleep(2.0)` → 30 次失败 `else: raise RuntimeError(...)` ← **崩溃点**。
5. 开麦成功后:若 `_cap_sr != _sr` 配置 FIR 抗混叠重采样(`firwin`/`lfilter` 状态);`self._stream.start()`。

`poll()`(单线程,从 node-timer 调,sherpa 推理非线程安全):drain `self._queue`,跑 KWS/VAD/ASR,返回至多一个事件。开麦/采集全部标 `# pragma: no cover - board only`。

## 4. 设计(方案1:poll 限流重试)

在现有单线程 poll 模型内重试,不引入新线程(契合"sherpa 必须单线程"约束)。

### 4.1 抽 `_open_mic() -> bool`
把现有"开麦成功后"的整段(line ~163 的 `_open_best()` 赋值 + line ~169-184 的 FIR 配置 + `self._stream.start()`)封装成一个方法。成功设 `self._stream`、配 FIR、start、返回 `True`;失败(异常)返回 `False` 且保持 `self._stream = None`。FIR 配置必须在此方法内(采样率开麦时才确定)。

### 4.2 `__init__` 改为不崩
模型加载与回调定义照旧。把重试循环替换为:`self._stream = None`,调一次 `self._open_mic()`;无论成功与否都不 `raise`。失败时 `log`:"mic '<device>' not ready, will keep retrying in poll"。

### 4.3 新增 `_ensure_mic()`
```
def _ensure_mic(self):
    if self._stream is not None:
        return
    now = time.monotonic()
    if now - self._last_mic_try < MIC_RETRY_INTERVAL_S:   # 限流,默认 3.0s
        return
    self._last_mic_try = now
    if self._open_mic():
        log "mic opened (sr=<cap_sr>)"
    # 失败不刷屏:仅每 N 次或间隔更久 log 一次 "waiting for mic"
```
`self._last_mic_try` 在 `__init__` 初始化(如 `-inf` 或 0)。

### 4.4 `poll()` 开头调用
`poll()` 第一行(import 之后)调 `self._ensure_mic()`;若 `self._stream is None` 直接返回 `None`(麦没好,无事件;node 照常 spin)。麦 ready 后 `poll()` 余下逻辑完全不变。

### 4.5 行为
起 asr 麦不在 → `__init__` 不崩、`asr_node up` → `poll()` 每 3s 后台重试开麦 → 用户插上麦 → 下次重试 `_open_mic()` 成功 → 日志 "mic opened" → 自动开始收音。全程 node 响应、无需人工重起。

## 5. 测试

- 开麦/采集是 **board-only**(`# pragma: no cover`,依赖板上麦 + sherpa + 模型,无法纯单测)。本改动核心靠**上板验证**。
- **上板验证步骤**:① 拔掉 USB 麦,起 asr → `asr_node` 不崩、`asr.log` 有 "mic ... not ready"/"waiting for mic"、`asr_node up` 出现、进程存活;② 插上 USB 麦,等几秒 → 日志 "mic opened"、`fuser /dev/snd/*` 显示 asr 持有麦;③ 说"小巡" → 正常唤醒。
- **纯逻辑单测(兜底)**:把限流判定抽为可测的纯函数/小方法(给定 `last_try`、`now`、`interval` → 是否该重试),加单测覆盖"间隔内不重试 / 超间隔重试"。这是唯一不依赖板载硬件、可在 CI 跑的部分。

## 6. 风险 / 注意

- 限流间隔 `MIC_RETRY_INTERVAL_S=3.0` 为经验值(够快恢复、又不刷屏/不抢 poll 时间)。
- `sd.InputStream` 在 poll 线程内 open/start:与现有"poll 单线程"一致,无新线程安全问题。
- 日志必须限流,否则麦长期不在会刷屏 `/tmp/asr.log`。
- 不改 `asr.yaml`、不改 `asr_node.py`(node 生命周期不变,backend 内部自愈)。
- 本设计依赖"仅启动场景";运行中掉线恢复留作后续(非目标)。
