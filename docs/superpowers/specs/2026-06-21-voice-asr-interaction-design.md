# 语音交互(端侧 ASR + 唤醒 + 意图理解)设计

- 日期:2026-06-21
- 状态:已脑暴定稿,待落实施计划
- 范围:仅 `rdk_x5/`(inspection_manager 新增节点/模块/配置 + scripts/docs)与对应 `tests/`。不碰 app/、不碰后端。

## 1. 背景与现状

麦克风已到货并接到 RDK X5。系统当前是「机器人上行 → 后端 → App 查看 / App 下行命令 → 机器人执行」的闭环,语音侧只有**输出(TTS)**:

- `voice_node` 订阅 `/inspection/voice`,经 `tts.py` 的 `CommandTTSBackend` 调 `/root/sherpa/`(sherpa-onnx v1.13.3 Matcha,USB 音响 `hw:0,0`)播报。已上板验证。
- **完全没有音频输入 / ASR / 语音命令解析**(关键词 `asr/mic/vad/recognize` 在包内零命中)。

本设计新增**语音输入侧**:一个与 `voice_node` 对称的 `asr_node`,实现「唤醒词 + 连续对话」的端侧离线语音控制。

### 已确认决策(用户)

| 项 | 决策 |
|---|---|
| 交互形态 | 唤醒词 + 连续对话(唤醒后可多轮,静默超时回到待唤醒) |
| 唤醒词 | `小巡`、`巡检助手`(可在 config 增删) |
| 意图理解 | 规则优先 + L1.5 小模型兑底 |
| VLM 兑底 | 默认开,与其它 CPU 推理加互斥锁 |
| 散热 | 有主动风扇,余量足;温控降级做成**可选**兜底 |
| 命令执行 | 复用现有 `dispatch_command()` 与话题,**不重复造命令分发** |
| App 语音开关 | 经命令通道新增 `voice_control{enabled}` 命令:本设计**预留接收+执行**(asr_node 可被远程启停);后端打通命令通道(见 `app/BACKEND_PROMPT_voice_control.md`);App 端稍后改 |

## 2. 目标 / 非目标

**目标**
- 端侧、离线、中文:唤醒(`小巡`/`巡检助手`)→ 断句录音 → ASR 出文本 → 意图理解 → 执行 + 语音回执。
- 复用现有命令分发(`command_receiver.dispatch_command`)与全部已有话题,语音与 App 下行走**同一执行路径**。
- 对"依赖移动"的命令(复核/巡检/导航寻物)**诚实降级**:照常下发,但回执措辞不假装已完成(底盘 PID 未通)。
- 算力可控:常驻负载极轻,CPU 大户(ASR/VLM)按需、错峰、可降级。

**非目标(本次不做)**
- 不做声纹识别 / 多说话人 / 远场波束成形。
- 不做开放域闲聊问答(用户未选);只做命令控制 + 听不懂时的礼貌引导。
- 不改 `cognition_node` 的自动决策流程;不改后端;不改 App。
- 移动类命令"真正能动"取决于底盘 PID(本设计之外),语音层不为其特殊兜底。

## 3. 总体架构与数据流

`asr_node`(新)与 `voice_node`(现有)对称:前者管输入,后者管输出。一次完整交互:

```
USB 麦克风 ──sounddevice 流式 16kHz 单声道──► asr_node
   │
   ├─① KWS 唤醒(KeywordSpotter)  ──听到"小巡"/"巡检助手"──► TTS"我在"
   │                                                       (走 voice_topic→voice_node)
   ├─② VAD 断句(silero)          ──检测说话起止,截出整句音频──►
   │
   ├─③ ASR 识别(SenseVoice)      ──► 中文文本
   │
   ├─④ 意图理解(intent.py)       ──规则命中?──► 命令对象 {type, params}
   │                              └─未命中─► L1.5 小模型(8080,纯文本)──► {type, params} / 放弃
   │
   └─⑤ CommandExecutor.execute(dispatch_command(cmd, stations_cfg, gimbal_cfg))
          ├─ 发布到 /inspection/voice|recheck|request_report|acceptance、/gimbal、/laser ...
          ├─ 激光类:复用激光定时例程(enable→sustain→off)
          └─ TTS 念 result 回执("好的,正在用激光指示三号工位")

   交互后:连续对话窗口内继续听下一句;静默超过 dialog_timeout_sec 回到 ① 待唤醒。
```

**核心原则**:`asr_node` 只做「听懂→映射→下发→念回执」。命令分发逻辑 100% 复用 `command_receiver.dispatch_command()`(已单测的纯函数),执行(publish + 激光例程)复用抽出的 `CommandExecutor`。

## 4. 组件详设

### 4.1 `asr_node.py`(新增 ROS2 节点)

- 节点名 `asr_node`,遵循现有节点的参数声明 / 日志(`self.get_logger()`)模式。
- 一个后台采集线程跑 sherpa-onnx 流式管线(KWS→VAD→ASR);识别出文本后通过线程安全队列交给节点主线程处理意图与执行(避免在 ROS executor 线程里做阻塞推理)。
- 状态机:`待唤醒(只跑 KWS)` → `对话中(跑 VAD+ASR)` →(静默超时)→ `待唤醒`。对话中关 KWS 省算力。
- 发布:复用 `CommandExecutor` 的 publisher(见 4.4);另发一个 `/inspection/asr_text`(std_msgs/String)调试话题,便于观测与录回放。
- 三件套引擎封装为可注入的 backend(见 4.3),便于用 mock 做节点逻辑单测。

### 4.2 `intent.py`(新增纯模块,无 rclpy,易单测)

输入识别文本,输出 `{type, params}` 或 `None`。

- **规则层**:关键词 + 槽位抽取 + 中文数字归一。覆盖:
  - `recheck_station` — "复核/去看/检查/看看 + N 号(桌/工位)"→ `{station_id}`
  - `laser_point` — "激光/指/照一下 + 工位/位置"→ `{station_id|location}`
  - `inspection_round` — "开始/全面/挨个 巡检"
  - `acceptance` — "(全部/N号)验收/课后验收"→ `{station_id|"all"}`
  - `voice_prompt` — "播报/说/提醒 + 文本"→ `{text}`
  - `generate_report` — "生成/出 报告(+类型)"→ `{report_type}`
  - `find_item` — "找/在哪 + 物品名"(+"带路"→navigate / "激光指"→laser)→ `{name, mode}`
  - 工位号归一:`三号/3号/三/station_3` → 与 stations.yaml 一致的 `station_id`(归一表随 stations 配置)。
- **兑底层**(`vlm_intent` helper):规则返回 `None` 时,把识别文本 + 命令 schema(type 枚举 + 各 params)作为**纯文本** prompt 发给 L1.5(复用 `qwen_client.OpenAICompatVLMClient`,`localhost:8080`,无图像),要求只输出 `{type, params}` JSON。解析失败 / 低置信 / 调用异常 → 返回 `None`。
- `asr_node` 对 `None` 的处理:TTS"抱歉,没太听清,可以说『去三号桌复核』『激光指示二号桌』这样的指令"。

### 4.3 ASR 引擎封装(`asr_engine.py` 或并入 asr_node)

- 用 **python `sherpa_onnx` 包**(aarch64 有 wheel),而非现有 TTS 的 CLI 二进制——因为唤醒/断句/识别要在一个进程内流式处理音频帧。
- 三件套 + 模型(下载到 `/root/sherpa/`):

| 阶段 | sherpa_onnx 组件 | 模型 | 备注 |
|---|---|---|---|
| 唤醒 | `KeywordSpotter` | `sherpa-onnx-kws-zipformer-wenetspeech` | 唤醒词用拼音 token 写 `keywords.txt`(`小巡`/`巡检助手`),可增删 |
| 断句 | `VoiceActivityDetector` | `silero_vad.onnx` | 自动截句,免固定时长录音 |
| 识别 | `OfflineRecognizer` | `sherpa-onnx-sense-voice-zh-...-int8` | SenseVoice-small,中文准、离线、int8 轻 |

- `num_threads` 配置项(默认 2),给视觉/VLM 留核。
- 定义 `MockAsrBackend`(沿用 `tts.py` 的 `MockTTSBackend` 思路):喂入预设文本序列,供节点逻辑单测,无需真模型/麦克风。

### 4.4 `CommandExecutor`(新增共享执行器,重构点)

现状:`command_receiver_node` 内联持有 publisher(`string_pubs/vector_pubs/bool_pubs`)、`_publish()`、激光定时例程(`_start_laser_indication/_aim_tick/_stop_laser_indication`)。`asr_node` 需要同一套。

方案:把这部分抽成 `command_executor.py` 的 `CommandExecutor` 类(持有 publisher map + `execute(plan)` + 激光例程),`command_receiver_node` 与 `asr_node` 都组合它。

- `execute(plan)`:`plan` 即 `dispatch_command()` 的返回;`actions`→逐个 publish,`laser_aim`→跑激光例程,`unsupported`→返回原因(由调用方决定如何反馈)。
- `command_receiver_node` 改为委托 `CommandExecutor`(行为不变,回归用现有 `tests/test_command_receiver.py` 保护)。
- 收益:语音与 App 下行命令执行**完全同一份代码**,激光例程不重复。

### 4.5 App 语音开关(`voice_control` 命令,预留)

App 需要能远程**开启/关闭整个语音监听**(省算力 / 安静场合 / 误唤醒太多时)。走现有命令通道,本设计预留机器人侧的接收与执行:

- 命令契约:`{type: "voice_control", params: {enabled: bool}}`(`true`=开启监听,`false`=关闭)。详见 `app/BACKEND_PROMPT_voice_control.md`。
- `dispatch_command()` 新增分支:`voice_control` → action 发布到 `/inspection/voice_control`(String JSON `{"enabled": bool}`),回执 `语音监听已开启/已关闭`。
- `asr_node` 订阅 `/inspection/voice_control`:
  - `enabled=false` → 进入**禁用态**:停止 KWS/VAD/ASR 采集线程(彻底释放那 ~1 核常驻 + 不再录音),只保留对该话题的订阅以便被重新唤起。
  - `enabled=true` → 恢复采集,回到 `待唤醒`。
- 持久化:enabled 状态写本地文件(如 `~/.asr_enabled`),节点启动时读取——重启后保持上次开/关。
- 状态权威源在机器人;App 端 MVP 用「下发命令 + result 回执」确认,乐观显示开关(后端可选做状态上行,见 prompt 文档)。

### 4.6 "依赖移动"命令的诚实降级

`dispatch_command` 对移动类(`recheck_station`/`inspection_round`/`find_item navigate`)照常产出 actions 并下发(与 App 同路径、下游解耦)。差异只在**语音回执措辞**,由 `asr_node` 按命令类型分类:

- 立即可执行(voice_prompt/laser_point/generate_report/acceptance):"好的,正在用激光指示三号工位"。
- 依赖移动(recheck/inspection_round/navigate):"收到,已记下到三号工位复核;底盘移动还在调试,稍后执行"——不假装完成。

→ 现在就能端到端真跑通:**唤醒 → 识别 → 激光指示 / 语音播报 / 生成报告 / 课后验收**;移动类待 PID 通后自动生效,语音层无需改动。

## 5. 算力与发热预算

RDK X5 = 8×A55 @1.5GHz(无 GPU) + Bayes-e BPU ~10 TOPS + 8GB RAM。

- **BPU**:YOLOv11s 独占,不吃 CPU,与语音零冲突。
- **内存**:常驻粗算 ~4.3GB / 8GB(系统+ROS2 ~1.5G、VLM 常驻 ~1.8G、ASR 三件套 ~0.7G、TTS ~0.3G),余 ~3.5G,不是瓶颈。
- **CPU(唯一瓶颈)**:KWS+VAD 常驻极轻(~1 核, <15%);ASR(RTF<0.3)、TTS(RTF~0.4)、VLM 推理均为**按需短脉冲**;最坏是三者瞬时抢满 8 核,但语音人触发、低频、与密集视觉错峰。
- **发热**:A55 满载会降频;已有主动风扇,余量足。

**缓解(写入实现)**:
1. 规则优先——90%+ 常用指令不碰 VLM(最大减负)。
2. ASR/VLM 互斥锁——两个 CPU 大户不同时推理。
3. ASR `num_threads` 限 2~3,给视觉/VLM 留核。
4. (可选)温控降级:读 thermal zone,过热自动转纯规则模式 + 关 VLM 兑底。有风扇,默认关此项,留配置开关。

## 6. 配置 `config/asr.yaml`

```yaml
asr_node:
  ros__parameters:
    enabled: true
    mic_device: ""              # 空=自动探测 USB 声卡;或 ALSA 名/索引
    sample_rate: 16000
    num_threads: 2
    # 模型路径(/root/sherpa/ 下)
    kws_model_dir: "/root/sherpa/sherpa-onnx-kws-zipformer-wenetspeech"
    kws_keywords_file: "/root/sherpa/keywords.txt"   # 小巡 / 巡检助手
    vad_model: "/root/sherpa/silero_vad.onnx"
    asr_model_dir: "/root/sherpa/sherpa-onnx-sense-voice-zh-int8"
    # 交互
    dialog_timeout_sec: 8.0     # 连续对话静默超时,回到待唤醒
    wake_ack_text: "我在"
    # 意图
    vlm_fallback_enabled: true
    vlm_base_url: "http://localhost:8080/v1"
    vlm_min_confidence: 0.5
    # 复用 command_receiver 的话题 + 配置(同名参数,保持一致)
    stations_config: ""
    gimbal_aim_config: ""
    voice_topic: "/inspection/voice"
    voice_control_topic: "/inspection/voice_control"   # App 远程启停语音(预留)
    enabled_state_file: "~/.asr_enabled"               # 远程开关状态持久化,重启保持
    # ...(recheck/request_report/gimbal/laser/acceptance 同 command_receiver)
    # 算力保护
    thermal_guard_enabled: false
    thermal_zone: "/sys/class/thermal/thermal_zone0/temp"
    thermal_throttle_c: 80
```

`launch/inspection.launch.py` 增加 `asr_node`(`enabled` 参数开关,默认随核心起)。

## 7. 测试策略

- `tests/test_intent.py`(新):规则层纯单测——各句式→命令断言、中文数字归一、未命中返回 None(走兑底);`vlm_intent` 用打桩 client 测 JSON 解析与低置信丢弃。
- `tests/test_command_executor.py`(新):用 fake publisher 验证 `execute()` 对 actions / laser_aim / unsupported 的行为;激光例程的 enable→sustain→off 顺序。
- `tests/test_command_receiver.py`(现有):重构 `command_receiver_node` 委托 `CommandExecutor` 后回归保护,行为不变。
- `asr_node` 节点逻辑:用 `MockAsrBackend` 喂预设文本,断言状态机(唤醒/对话/超时)与回执措辞分类(立即 vs 依赖移动)。
- 真模型 / 真麦克风 / KWS 误唤醒率:靠上板手测(见 §8)。

## 8. 部署与上板验证清单

- 新增 `docs/architecture/voice_asr_setup.md`:模型下载链接与放置、`sherpa_onnx`+`sounddevice`(系统 `libportaudio2`)安装、ALSA 录音设备探测(`arecord -l`/`arecord -D ... test.wav`)、bring-up,对齐 `voice_broadcast_setup.md` 风格。
- 上板手测:① `arecord` 能录到麦克风;② 唤醒词命中率 / 误唤醒;③ 典型指令端到端(激光指示、语音播报、生成报告、验收)真跑通;④ 移动类命令回执措辞正确(不假装完成);⑤ 与 VLM 同时触发时无明显卡顿、温度可控。

## 9. 关键文件

- 新增:`inspection_manager/asr_node.py`、`inspection_manager/asr_engine.py`、`inspection_manager/intent.py`、`inspection_manager/command_executor.py`、`config/asr.yaml`、`docs/architecture/voice_asr_setup.md`、`tests/test_intent.py`、`tests/test_command_executor.py`
- 修改:`inspection_manager/command_receiver_node.py`(委托 CommandExecutor)、`inspection_manager/command_receiver.py`(`dispatch_command` 加 `voice_control` 分支)、`launch/inspection.launch.py`(加 asr_node)、`setup.py`(注册 asr_node entry point)、`package.xml`(如需声明依赖)
- 复用:`command_receiver.dispatch_command/find_item_to_command`、`qwen_client.OpenAICompatVLMClient`、`tts.py`(Mock 模式参考)

## 10. 开放问题(实现时定,不阻塞)

- KWS 唤醒词的拼音 token 具体写法,需按 wenetspeech KWS 模型的 tokens 微调(`小巡`=`x iǎo x ún` 等),上板按误唤醒率调阈值。
- SenseVoice 对实验室术语(元件名)的识别率,必要时在意图层加同音/近音纠错词表。
