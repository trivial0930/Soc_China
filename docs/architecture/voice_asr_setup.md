# 端侧语音识别 (ASR) 上板 bring-up

App→`asr_node`→`AsrController`：唤醒词检测(KWS) → 对话录音(VAD+ASR) → 意图解析 → 指令执行 → 语音回执。
`asr_node`、`SherpaAsrBackend`（`asr_engine.py`）、`AsrController`（`asr_controller.py`）均在
`inspection_manager` 包，已单测；`SherpaAsrBackend` 的真实采集循环需在板上补全（见 §5）。
全链路离线、无需联网。

## 数据流

```
mic → sounddevice 16kHz 单声道 → SherpaAsrBackend.poll()（20Hz 轮询）
  idle 态：  KeywordSpotter  → wake_event{"kind":"wake"}
             → AsrController 切 dialog 态、speak("我在")
  dialog 态：VAD + OfflineRecognizer → utterance_event{"kind":"utterance","text":...}
             → intent 规则 → dispatch → execute → reply_for → speak(回执)
  超时(dialog_timeout_sec=8.0s 无语音)：回 idle/KWS
  disabled 态：set_mode("off") 停采集
```

---

## 1. 依赖安装

```bash
# Python 包（板上 pip，需联网一次或离线 wheel）
pip install sherpa-onnx sounddevice

# 系统 PortAudio 库（sounddevice 通过 PortAudio 读麦克风）
sudo apt install -y libportaudio2
```

> **`num_threads` 说明**：`asr.yaml` 默认 `num_threads: 2`。RDK X5 8×A55，此值已在 KWS /
> VAD / ASR 三个推理器间共享；切勿超过 4，否则与热成像/VLM 争核导致卡顿。

---

## 2. 模型下载与放置

所有模型放 `/root/sherpa/`（与 TTS 资产同目录）。Mac 暂存 `~/sherpa_staging/`，**不入 git**。

### 2.1 KWS 唤醒词模型 `sherpa-onnx-kws-zipformer-wenetspeech`

```bash
# ---- 在 Mac / 有网机器上 ----
cd ~/sherpa_staging
# 到 https://github.com/k2-fsa/sherpa-onnx/releases 搜 kws-zipformer-wenetspeech，下载 aarch64 包
# 解压并重命名，使目录名与 asr.yaml 一致
tar xf sherpa-onnx-kws-zipformer-wenetspeech-*.tar.bz2
mv sherpa-onnx-kws-zipformer-wenetspeech-* sherpa-onnx-kws-zipformer-wenetspeech

# ---- scp 到板上 ----
ssh root@192.168.128.10 'mkdir -p /root/sherpa'
scp -r sherpa-onnx-kws-zipformer-wenetspeech root@192.168.128.10:/root/sherpa/
```

解压后 `/root/sherpa/sherpa-onnx-kws-zipformer-wenetspeech/` 须含：
`encoder.onnx`、`decoder.onnx`、`joiner.onnx`、`tokens.txt`。

### 2.2 VAD 模型 `silero_vad.onnx`

```bash
# snakers4/silero-vad repo → files/silero_vad.onnx，或 sherpa-onnx releases 附带
wget https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
scp silero_vad.onnx root@192.168.128.10:/root/sherpa/
```

板上路径：`/root/sherpa/silero_vad.onnx`（与 `asr.yaml` 的 `vad_model` 一致）。

### 2.3 ASR 整句识别模型 `sherpa-onnx-sense-voice-zh-int8`

```bash
# 到 https://github.com/k2-fsa/sherpa-onnx/releases 搜 sense-voice-zh int8，下载对应包
tar xf sherpa-onnx-sense-voice-zh-*.tar.bz2
# 重命名使目录名与 asr.yaml 一致
mv sherpa-onnx-sense-voice-zh-* sherpa-onnx-sense-voice-zh-int8

scp -r sherpa-onnx-sense-voice-zh-int8 root@192.168.128.10:/root/sherpa/
```

板上路径：`/root/sherpa/sherpa-onnx-sense-voice-zh-int8/`（与 `asr.yaml` 的 `asr_model_dir` 一致）。
目录须含 `model.int8.onnx`（或同名 int8 onnx）和 `tokens.txt`。

### 2.4 唤醒词文件 `keywords.txt`

```bash
# 在板上直接创建；每行一个唤醒词（中文），可附 :阈值 控制灵敏度
cat > /root/sherpa/keywords.txt << 'EOF'
小巡 :0.25
巡检助手 :0.25
EOF
```

> - 格式以模型附带的 README / 示例 keywords.txt 为准（不同版本 token 格式有差异）。
> - `:0.25` 偏宽松，先上板测通；误唤醒率高时收紧至 `:0.5`。
> - 若模型要求拼音 token（如 `xiǎo xún`），则照 tokens.txt 里的音节写法逐字填入，
>   详见 [sherpa-onnx KWS 文档](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)。

---

## 3. 麦克风探测

```bash
ssh root@192.168.128.10

# 列出录音设备，找 USB 麦克风的 card/device 编号
arecord -l
# 示例输出：
# card 1: USBMicro [USB Microphone], device 0: USB Audio [USB Audio]

# 试录 3 秒（16kHz 单声道 S16_LE，与模型要求一致）
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 3 /tmp/test.wav
# 回放确认有声音（或 scp 到 Mac 听）
aplay /tmp/test.wav
```

得到 `card X, device 0` 后，将 `plughw:X,0` 填入 `asr.yaml`：

```yaml
asr_node:
  ros__parameters:
    mic_device: "plughw:1,0"   # ← 按 arecord -l 实际 card 号填写
```

> 若 `arecord -l` 无输出：`lsusb` 确认 USB 麦克风已枚举；尝试 `modprobe snd-usb-audio`。

---

## 4. 配置对照（asr.yaml 关键参数）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `true` | 节点启动时是否开启 ASR |
| `mic_device` | `""` | sounddevice 设备字符串，空=系统默认；**上板后必填** |
| `sample_rate` | `16000` | 采样率（Hz），与模型一致，勿改 |
| `num_threads` | `2` | sherpa-onnx 推理线程数，建议保持 ≤4 |
| `kws_model_dir` | `/root/sherpa/sherpa-onnx-kws-zipformer-wenetspeech` | KWS 模型目录 |
| `kws_keywords_file` | `/root/sherpa/keywords.txt` | 唤醒词文件路径 |
| `vad_model` | `/root/sherpa/silero_vad.onnx` | Silero VAD onnx 模型 |
| `asr_model_dir` | `/root/sherpa/sherpa-onnx-sense-voice-zh-int8` | SenseVoice 离线识别模型目录 |
| `dialog_timeout_sec` | `8.0` | 对话态无语音超时（秒），超时回 idle/KWS |
| `wake_ack_text` | `"我在"` | 唤醒词命中后播报的回执文本 |
| `tick_sec` | `0.05` | 控制器轮询间隔（20Hz） |
| `vlm_fallback_enabled` | `true` | 规则意图失败后是否调 VLM 兜底 |
| `vlm_base_url` | `http://localhost:8080/v1` | VLM 服务地址（本地推理） |
| `vlm_model` | `qwen2.5-7b-instruct` | VLM 兜底模型名 |
| `vlm_min_confidence` | `0.5` | VLM 意图最低置信度阈值 |
| `enabled_state_file` | `~/.asr_enabled` | voice_control 开关持久化文件 |
| `voice_topic` | `/inspection/voice` | TTS 播报话题 |
| `voice_control_topic` | `/inspection/voice_control` | App 发来的 ASR 开关话题 |
| `gimbal_topic` | `/gimbal/target_angle` | 云台控制话题 |
| `laser_topic` | `/laser/enable` | 激光指示话题 |
| `laser_indicate_sec` | `8.0` | 激光指示持续时间（秒） |

---

## 5. SherpaAsrBackend 实现要点

`asr_engine.py` 中 `SherpaAsrBackend.__init__` 末尾有 `raise NotImplementedError`，需在板上
补全真实采集循环。**不要修改 `MockAsrBackend` 或 `AsrBackend` Protocol**；只在
`SherpaAsrBackend` 内实现以下逻辑。

### 5.1 初始化三件套（`__init__`）

```python
import queue
import sherpa_onnx
import sounddevice as sd

# --- KWS（唤醒词检测器）---
kws_config = sherpa_onnx.KeywordSpotterConfig(
    keywords_file=cfg["kws_keywords_file"],
    model=sherpa_onnx.KeywordSpotterModelConfig(
        encoder=f"{cfg['kws_model_dir']}/encoder.onnx",
        decoder=f"{cfg['kws_model_dir']}/decoder.onnx",
        joiner=f"{cfg['kws_model_dir']}/joiner.onnx",
        tokens=f"{cfg['kws_model_dir']}/tokens.txt",
        num_threads=cfg.get("num_threads", 2),
    ),
)
self._kws = sherpa_onnx.KeywordSpotter(kws_config)
self._kws_stream = self._kws.create_stream()

# --- VAD（语音活动检测，用于 dialog 态分句）---
vad_config = sherpa_onnx.VadModelConfig(
    silero_vad=sherpa_onnx.SileroVadModelConfig(
        model=cfg["vad_model"],
        threshold=0.5,
        min_silence_duration=0.5,
        min_speech_duration=0.25,
    ),
    sample_rate=cfg.get("sample_rate", 16000),
)
self._vad = sherpa_onnx.VoiceActivityDetector(
    vad_config, buffer_size_in_seconds=30
)

# --- Offline ASR（SenseVoice 整句识别）---
import os
model_dir = cfg["asr_model_dir"]
# 找 int8 onnx（文件名因版本而异，优先 model.int8.onnx）
int8_onnx = os.path.join(model_dir, "model.int8.onnx")
asr_config = sherpa_onnx.OfflineRecognizerConfig(
    model=sherpa_onnx.OfflineModelConfig(
        sense_voice=sherpa_onnx.OfflineSenseVoiceModelConfig(
            model=int8_onnx,
            use_itn=True,
            language="zh",
        ),
        tokens=os.path.join(model_dir, "tokens.txt"),
        num_threads=cfg.get("num_threads", 2),
    ),
)
self._recognizer = sherpa_onnx.OfflineRecognizer(asr_config)

# --- 内部状态 ---
self._mode = "off"
self._sr = cfg.get("sample_rate", 16000)
self._device = cfg.get("mic_device") or None  # None=系统默认
self._buf_q: queue.Queue = queue.Queue()
self._sd_stream = None
self._start_stream()
```

### 5.2 sounddevice 采集线程

```python
def _start_stream(self):
    def _cb(indata, frames, time_info, status):
        # indata: shape (frames, 1), dtype float32
        self._buf_q.put(indata[:, 0].copy())

    self._sd_stream = sd.InputStream(
        device=self._device,
        samplerate=self._sr,
        channels=1,
        dtype="float32",
        blocksize=int(self._sr * 0.02),   # 20ms 块
        callback=_cb,
    )
    self._sd_stream.start()
```

### 5.3 `set_mode` 三态切换

```python
def set_mode(self, mode: str) -> None:
    """mode: "kws" | "dialog" | "off"
    kws:    唤醒词检测（idle 态）
    dialog: VAD + 离线整句识别（对话态）
    off:    停止推理（disabled 态）
    """
    self._mode = mode
    if mode == "dialog":
        # 重置 VAD 内部状态，清空旧音频
        self._vad.reset()
        # 丢弃积压的 KWS 音频块，避免误触
        while not self._buf_q.empty():
            try:
                self._buf_q.get_nowait()
            except queue.Empty:
                break
```

### 5.4 `poll()` 驱动推理

`poll()` 由 `asr_node` 的 timer callback（`tick_sec=0.05`，20Hz）调用，每次返回至多一个事件。

```python
def poll(self):
    import numpy as np

    # 取出本轮所有音频块
    chunks = []
    while not self._buf_q.empty():
        try:
            chunks.append(self._buf_q.get_nowait())
        except queue.Empty:
            break
    if not chunks or self._mode == "off":
        return None

    audio = np.concatenate(chunks)

    if self._mode == "kws":
        self._kws_stream.accept_waveform(self._sr, audio)
        self._kws.decode_stream(self._kws_stream)
        result = self._kws_stream.result
        if result.keyword:
            # 重置 KWS 流以备下次唤醒
            self._kws_stream = self._kws.create_stream()
            return wake_event()

    elif self._mode == "dialog":
        self._vad.accept_waveform(audio)
        while not self._vad.empty():
            segment = self._vad.front()
            self._vad.pop()
            s = self._recognizer.create_stream()
            s.accept_waveform(self._sr, segment.samples)
            self._recognizer.decode_stream(s)
            text = s.result.text.strip()
            if text:
                return utterance_event(text)

    return None
```

> - sherpa-onnx 推理非线程安全；`poll()` 需在同一线程调用（node timer callback 已满足）。
> - `set_mode` 在 `AsrController.tick()` 内调用，也在同一线程，无需额外加锁。

---

## 6. 算力保护

| 策略 | 配置 / 操作 |
|------|-------------|
| **线程数限制** | `num_threads: 2`（asr.yaml 默认），三个推理器共享，保持不变 |
| **规则意图优先** | `intent.py` 正则命中直接返回，不调 VLM；VLM 仅在规则完全失败时触发 |
| **VLM 完全禁用** | 演示前如模型服务未就绪，置 `vlm_fallback_enabled: false` |
| **温控降级（可选）** | 运行时读 `/sys/class/thermal/thermal_zone0/temp`；若板温 > 75000（℃×1000）临时禁用 VLM fallback，降温后恢复 |

```bash
# 查看板温（单位：毫摄氏度）
cat /sys/class/thermal/thermal_zone0/temp
# 示例：72000 → 72 ℃
```

---

## 7. 起 asr_node

```bash
source /opt/ros/humble/setup.bash && source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash

# 单独启动（指定 asr.yaml）
ros2 run inspection_manager asr_node \
  --ros-args --params-file \
  /root/Soc_China/rdk_x5/ros2_ws/src/inspection_manager/config/asr.yaml

# 或整条管线
ros2 launch inspection_manager inspection.launch.py
```

> **改 `.py` 后必须干净重建**：`rm -rf build/inspection_manager install/inspection_manager`
> 再 `colcon build --packages-select inspection_manager`——ament_python 增量构建有缓存坑，
> 只改 `.py` 不删旧目录的话 install 里仍是旧代码（与 TTS 节点同坑，实测踩过）。

---

## 8. 上板验证清单

完成以下所有项即视为 ASR 链路上板验收通过：

- [ ] `arecord -D plughw:X,0 -f S16_LE -r 16000 -c 1 -d 3 /tmp/t.wav` 能录到麦克风音频（回放可辨识人声）。
- [ ] `asr_node` 启动后说"**小巡**"或"**巡检助手**"→ `/inspection/voice` 发布 `"我在"`；
      静音环境误唤醒率可接受（< 1 次/分钟）。
- [ ] **立即类指令端到端验证**（每条说完后无需再唤醒，在 `dialog_timeout_sec=8.0s` 内续说）：
  - [ ] "激光指示二号桌" → `laser_topic`（`/laser/enable`）发布指示指令，语音播报激光指示中。
  - [ ] "语音播报…" / "生成报告" / "课后验收" → 播报对应回执，**无**降级后缀。
- [ ] **移动类诚实降级**：说"去三号桌复核"或"开始巡检" → 播报回执**结尾为** `";底盘移动还在调试,稍后执行"`，不假装已完成移动。
- [ ] **voice_control 开关与持久化**：
  - [ ] App 发 `voice_control{enabled:false}` → `asr_node` 停止监听（`set_mode("off")`），
        `~/.asr_enabled` 写入 `false`。
  - [ ] App 发 `voice_control{enabled:true}` → 恢复 KWS 监听，`~/.asr_enabled` 写入 `true`。
  - [ ] 重启 `asr_node` 后读取 `~/.asr_enabled`，保持上次状态。
- [ ] **算力共存**：语音与 VLM 分析同时触发时无明显卡顿（`tick_sec=0.05` 20Hz 轮询），
      风扇运转后板温 ≤ 75 ℃。

---

## 注意

- `mic_device: ""`（默认）时 sounddevice 使用系统默认录音设备；上板后**必须**填入
  `arecord -l` 查到的实际设备名（如 `plughw:1,0`）。
- `dialog_timeout_sec: 8.0`——对话态若 8 秒内无新语音，`AsrController` 自动回到 idle/KWS。
- `enabled_state_file: "~/.asr_enabled"`——节点启动时若此文件存在，其内容覆盖 `enabled` 参数。
- 建议先验证 TTS（`voice_node`）正常工作（见 `voice_broadcast_setup.md`），再接入 ASR，
  避免音频链路问题与识别问题混淆排障。
- `vlm_fallback_enabled: true` 时 VLM 兜底调 `vlm_base_url: "http://localhost:8080/v1"`
  的本地 LLM 服务；演示前确认该服务已启动，或将此项置 `false` 关闭 VLM 兜底。
