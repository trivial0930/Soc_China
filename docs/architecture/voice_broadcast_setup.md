# 语音播报 (Voice Broadcast) 上板 bring-up

L2/L3 的 `voice` 动作 → `/inspection/voice` (std_msgs/String) → `voice_node` → USB 音响。
`voice_node` 与注入安全的 TTS 后端在 `inspection_manager`（`voice_node.py` / `tts.py`），
已单测。**本文档是有板子时的硬件接入清单**——离线、无需联网/apt。

## 离线 TTS 资产（已在开发 Mac 暂存）

`~/piper_staging/`（约 136MB，**不入 git**）：
- `piper/`  —— Piper 二进制 + 自带库（libonnxruntime / libespeak-ng / libpiper_phonemize）
  + `espeak-ng-data/`，**并自带一个可独立用的 `espeak-ng`**。一个包给了两个引擎。
- `zh_CN-huayan-medium.onnx` (+ `.onnx.json`) —— 中文语音模型（自然女声）。

来源：piper `2023.11.14-2` aarch64（RDK X5 是 ARM64）+ rhasspy/piper-voices 的 zh_CN-huayan-medium。

## 步骤

### 1. 接硬件 + 认设备
USB 音响插 RDK，开机后：
```bash
ssh root@192.168.128.10
lsusb                 # 应看到 USB Audio 设备
aplay -l              # 记下声卡号，例如 card 1: ... -> ALSA 设备 = plughw:1,0
```

### 2. 测基础放音（先确认喇叭能响）
```bash
speaker-test -D plughw:1,0 -c 2 -t wav -l 1    # 或: aplay -D plughw:1,0 /usr/share/sounds/alsa/Front_Center.wav
```
没声音先排查：音量 `alsamixer -c 1`（取消静音、拉高）、设备号、线/电源。

### 3. 部署 Piper（一次性 scp，无需联网）
```bash
# 在 Mac 上
scp -r ~/piper_staging/piper root@192.168.128.10:/root/piper
scp ~/piper_staging/zh_CN-huayan-medium.onnx ~/piper_staging/zh_CN-huayan-medium.onnx.json \
    root@192.168.128.10:/root/piper/
# 在板上自测（rpath=$ORIGIN，通常直接能跑；不行则加 LD_LIBRARY_PATH）
echo "三号工位电烙铁未关闭" | /root/piper/piper --model /root/piper/zh_CN-huayan-medium.onnx --output_file /tmp/t.wav
aplay -D plughw:1,0 /tmp/t.wav
# 若报找不到 .so： LD_LIBRARY_PATH=/root/piper /root/piper/piper ...
```

### 4. 起 voice_node（piper 引擎，指向 USB 音响）
```bash
source /opt/ros/humble/setup.bash && source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
# 若 piper 需要库路径，先 export LD_LIBRARY_PATH=/root/piper
ros2 run inspection_manager voice_node --ros-args \
  -p tts_engine:=piper -p aplay_device:=plughw:1,0 \
  -p piper_bin:=/root/piper/piper -p piper_model:=/root/piper/zh_CN-huayan-medium.onnx
# 或整条管线：
ros2 launch inspection_manager inspection.launch.py \
  tts_engine:=piper aplay_device:=plughw:1,0 piper_model:=/root/piper/zh_CN-huayan-medium.onnx
```

### 5. 端到端测
```bash
ros2 topic pub --once /inspection/voice std_msgs/msg/String '{data: "三号工位电烙铁未关闭，请立即处理"}'
# 应从 USB 音响听到中文播报
```

## 备选引擎：espeak-ng（机械音，但极小、最稳）
Piper 库若在板上有兼容问题，用包内自带的 espeak-ng 兜底：
```bash
LD_LIBRARY_PATH=/root/piper /root/piper/espeak-ng --path=/root/piper -v cmn "三号工位电烙铁未关闭"
```
对应 `voice_node` 参数：`tts_engine:=espeak espeak_voice:=cmn`（注意：espeak-ng 的普通话
在不同版本是 `cmn` 或 `zh`，对不上就换另一个）。espeak-ng 直接走默认 ALSA 设备；若要指定
USB 音响，设系统默认声卡或用 `aplay` 路线（piper 引擎已是 aplay 路线，可指定 `aplay_device`）。

## 注意
- 文本是模型生成的中文，可能含引号/分号——`tts.py` 已做**注入安全**（文本只作 argv/stdin，
  绝不拼进 shell）。
- `voice_node` 已对重复提示做节流（`throttle_sec`，默认 10s），持续危险不会每帧念。
- 默认 `tts_engine:=none`（只打日志,干跑），接好硬件再切 `piper`/`espeak`。
- 演示用手机热点时此链路不变（语音是板上本地，不依赖网络）。
