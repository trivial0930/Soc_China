# 端侧语音栈 — 运行组件清单与开机自启交接文档

> **读者:负责把这些功能做成 RDK X5 开机自启(systemd)的 agent。**
> 目标:把"本对话产出的功能"在板子上电后**全自动拉起**,无需人工 ssh 敲命令。
>
> **三条须先读的前提:**
> 1. **可能已部分做完** —— 据板上 bring-up 记录,语音的 systemd 自启(`voice-asr.service` + `/root/start_all_voice.sh`)很可能**已经 enable 且真重启验证通过**。请先按 §6 在板上核验现状,**扩展/修补而非推倒重做**。
> 2. **板上路径(`/root/...`)无法从仓库验证** —— 凡标 `板上` 的文件/脚本/模型,你必须在 RDK 上 `ls`/`cat` 核实后再用。
> 3. **代码事实源在仓库**(已合并 `main`):`rdk_x5/ros2_ws/src/inspection_manager/`。节点入口见该包 `setup.py`。

---

## 0. 本对话产出了什么(自启要覆盖的功能)

| 功能 | 组件 | 类型 | 在不在机器人自启范围 |
|---|---|---|---|
| 语音识别/交互(唤醒→ASR→意图→执行→TTS 回执) | `asr_node` + 纯逻辑模块 | RDK ROS2 节点 | ✅ 要 |
| 语音播报(TTS 输出) | `voice_node` + `/root/sherpa_say.sh` | RDK ROS2 节点 + 脚本 | ✅ 要 |
| App→机器人命令下行(含语音开关 `voice_control`) | `command_receiver_node` | RDK ROS2 节点 | ✅ 要 |
| L2 决策 / L3 报告 | `cognition_node` / `report_service` | RDK ROS2 节点 | ✅ 要(语音意图兜底依赖 L1.5) |
| 事件上行到后端 | `uplink_node` | RDK ROS2 节点 | ✅ 要(若要 App 看告警) |
| App 端语音开关 UI | `app/mobile`(Flutter) | 手机 APK | ❌ 客户端,非机器人自启 |
| 命令通道后端 | Mac FastAPI | Mac 服务 | ❌ Mac 侧,非 RDK 自启 |

---

## 1. 一图概览(数据流 + 进程)

```
[板载麦克风 ES8326] --采集--> asr_node ──(唤醒/识别/意图)──┐
                                                          ├─► dispatch_command() ─► 发布到 ROS 话题
[USB音响 Jieli CD002] <--aplay-- voice_node <--/inspection/voice-- ┘   ├─ /inspection/voice(TTS回执)
        ▲                                                              ├─ /inspection/recheck
        └── /root/sherpa_say.sh (sherpa Matcha TTS, /root/sherpa 模型)  ├─ /gimbal/* + /laser/enable(激光)
                                                                        ├─ /inspection/request_report
asr_node 意图兜底 ──HTTP──► [L1.5 小VLM: llama.cpp llama-server :8080]   └─ /inspection/acceptance_request

[手机App] ──POST /api/commands──► [Mac后端:8000] ◄──轮询 GET /api/robot/commands/pending── command_receiver_node
   语音开关 voice_control{enabled}                              command_receiver_node ──/inspection/voice_control──► asr_node(启停监听)
[告警] uplink_node ──POST /api/ingest/*──► [Mac后端]
```

---

## 2. 需要开机自启的 RDK 运行组件

### 2.1 ROS2 节点(均在 `inspection_manager` 包;入口见 `rdk_x5/ros2_ws/src/inspection_manager/setup.py`)

| 节点名 / executable | 作用 | 配置文件 | 自启关键参数 / 备注 |
|---|---|---|---|
| `asr_node`(本对话新增) | 语音输入主节点:KWS 唤醒「小巡/巡检助手」→ VAD → SenseVoice ASR → 意图(规则优先+小模型兜底)→ 复用 `dispatch_command` 执行 → TTS 回执;订阅 `/inspection/voice_control` 远程启停 | `config/asr.yaml` | 真采集循环依赖 `SherpaAsrBackend`(板上由 bring-up agent 补全)+ `/root/sherpa` 下 KWS/VAD/SenseVoice 模型 + `sherpa_onnx`/`sounddevice` python 包。`mic_device` 须指**板载 ES8326**(不是 USB) |
| `voice_node` | TTS 输出执行器:订阅 `/inspection/voice`,调 TTS 引擎播报 | (启动参数) | **自启必须传** `tts_engine:=command tts_command:=/root/sherpa_say.sh`;`aplay` 设备见 §4 声卡坑 |
| `cognition_node` | L2 本地认知决策(事件→解释+动作) | `config/cognition.yaml`、`stations.yaml` | 依赖 L1.5 小 VLM(`:8080`)/ L2 端点 |
| `report_service` | L3 报告生成(云端/本地 VLM) | `config/report.yaml` | 按需触发 |
| `command_receiver_node`(本对话重构) | 轮询 Mac 后端取 App 下行命令,`dispatch_command()` 分发执行,回执;**含 `voice_control` 语音开关分发** | 节点参数(见 §5) | `backend_url`(默认 `http://192.168.128.100:8000`)、`ingest_token`、`stations_config`、`gimbal_aim_config` |
| `uplink_node` | 事件/快照上行到 Mac 后端 | `config/uplink.yaml` | `backend_url` + token(`~/.app_ingest_token`) |
| `recheck_node` / `workstation_record_node` / `acceptance_node` | 复核导航 / 工位记录 / 课后验收 | `recheck_poses.yaml` / `stations.yaml` | 按需;移动类依赖底盘(PID 见相关记忆) |

> ⚠️ **注意:`launch/inspection.launch.py` 只启动 4 个核心节点**:`cognition_node`、`report_service`、`voice_node`、`asr_node`。
> `command_receiver_node`、`uplink_node`、`recheck_node` 等**不在该 launch 里**,自启时需另行 `ros2 run inspection_manager <node>` 或写进启动脚本。

### 2.2 支撑进程(非 ROS,但语音栈依赖,须先于/伴随节点起)

| 进程 | 作用 | 板上位置 / 启动 | 依赖 |
|---|---|---|---|
| sherpa Matcha **TTS** | `voice_node` 通过 `tts_command` 调用它合成中文语音 | `板上 /root/sherpa_say.sh`(脚本,内部 `sherpa-onnx-offline-tts | ffmpeg | aplay`) | `/root/sherpa` 下 TTS 模型(`model-steps-3.onnx` + `vocos`);USB 音响 |
| **L1.5 小 VLM** | `asr_node` 意图兜底 + `cognition` L1.5 分级 | `板上` llama.cpp `llama-server`,OpenAI 兼容,`http://localhost:8080/v1` | gguf 模型(InternVL2.5-2B / Qwen2.5-VL-3B) |
| sherpa **ASR** 模型 | `asr_node` 真采集识别用 | `板上 /root/sherpa/`:`sherpa-onnx-kws-zipformer-wenetspeech`、`silero_vad.onnx`、`sherpa-onnx-sense-voice-zh` int8;`keywords.txt`(小巡/巡检助手) | 由 bring-up agent 离线装 |

---

## 3. 启动方式(命令级)

```bash
# 0) ROS 环境(每个 shell/服务都要)
source /opt/ros/<distro>/setup.bash
source ~/ros2_ws/install/setup.bash          # 板上工作区实际路径以板为准

# 1) 核心 4 节点(含语音输入+输出)
ros2 launch inspection_manager inspection.launch.py \
    tts_engine:=command tts_command:=/root/sherpa_say.sh

# 2) 命令下行 + 上行(launch 不含,单独起)
ros2 run inspection_manager command_receiver_node --ros-args \
    -p backend_url:=http://<MAC_IP>:8000 -p ingest_token:=<TOKEN> \
    -p stations_config:=<.../stations.yaml> -p gimbal_aim_config:=<.../gimbal_aim.yaml>
ros2 run inspection_manager uplink_node --ros-args -p backend_url:=http://<MAC_IP>:8000 ...

# 3) 支撑进程(应在节点之前就绪)
#   - llama.cpp L1.5 server 监听 :8080
#   - /root/sherpa_say.sh 可被 voice_node 调用(TTS 模型就位)
```

> **板上很可能已有一键脚本** `板上 /root/start_all_voice.sh`(per bring-up)把上述都串起来了 —— 见 §6,优先复用它。

---

## 4. 自启依赖与顺序(systemd 必读的坑)

这些是**血泪坑**,做 service 时务必处理:

1. **`HOME=/root` 必须显式设置。** systemd 服务默认无 `HOME`,ROS2 找不到日志目录会让**节点几乎全崩(只剩 tts_server 活)**。service 里必须 `Environment=HOME=/root`(以及 `Environment=` 注入 ROS 的 setup)。
2. **USB 声卡用 `plughw:CARD=CD002AUDIO`,不要用 `hw:0,0`。** 重启后 card 号会重排,写死 `hw:0,0` 会导致 TTS 哑(现象像"唤不醒")。`aplay` / `sherpa_say.sh` 里改用按名寻址 `plughw:CARD=CD002AUDIO`。
3. **麦克风是板载 ES8326**(`arecord -l` 可见);**USB 的 Jieli CD002-AUDIO 是 TTS 扬声器(输出),不是采集卡**。`asr.yaml` 的 `mic_device` 指 ES8326 capture。
4. **真重启后 USB CDC(底盘链路)重枚举慢约 4–5 分钟** ssh 才回来 —— 自启脚本宜 `sleep ~20s` 等设备/网络稳定再拉节点(已有 service 用 oneshot + RemainAfterExit + sleep20)。
5. **网络:** 后端在 Mac(`backend_url` 默认 `192.168.128.100:8000`),需与板同网或经 Tailscale;**板上无外网**(模型/pip 包必须离线装好,不能指望联网)。
6. **进程级清理:** 重启 laser/gimbal 类时须 `pkill` 真实进程名防 restart 累积(已有 `start_gimbal.sh` 处理)。

---

## 5. 关键配置文件与参数

目录:`rdk_x5/ros2_ws/src/inspection_manager/config/`(随包安装到 `share/inspection_manager/config/`)。

- **`asr.yaml`(`asr_node`)** —— 自启相关重点项:
  - `enabled`(总开关)、`mic_device`(**须指板载 ES8326 capture**,不能留空自动找 USB)、`num_threads`(给视觉/VLM 留核)
  - 模型路径:`kws_model_dir` / `vad_model` / `asr_model_dir` / `kws_keywords_file`(都在 `/root/sherpa/`)
  - 意图兜底:`vlm_fallback_enabled`、`vlm_base_url`(`http://localhost:8080/v1`)、`vlm_model`、`vlm_min_confidence`
  - 远程开关:`voice_control_topic`(`/inspection/voice_control`)、`enabled_state_file`(`~/.asr_enabled`,**重启保持上次开/关状态**)
  - 命令话题:`voice_topic`/`recheck_topic`/`request_report_topic`/`acceptance_request_topic`/`gimbal_topic`/`gimbal_enable_topic`/`laser_topic`
- **`command_receiver` 参数**:`backend_url`、`ingest_token`、`poll_sec`、`stations_config`、`gimbal_aim_config`、各输出话题。
- **`voice_node` 启动参数**:`tts_engine=command`、`tts_command=/root/sherpa_say.sh`、`aplay_device`。
- 其它:`cognition.yaml`、`report.yaml`、`stations.yaml`、`gimbal_aim.yaml`、`uplink.yaml`。

> Token 不进 git,存 `~/.app_ingest_token`(或环境变量 `APP_INGEST_TOKEN`)。

---

## 6. 已有的开机自启现状(先核验,别重做)

据板上 bring-up 记录,**很可能已存在**以下,且**真重启验证通过(9 节点全自动起)**:

- `板上 /etc/systemd/system/voice-asr.service`:`oneshot` + `RemainAfterExit=yes` + `KillMode=process` + `sleep 20` → 调 `/root/start_all_voice.sh`,且已 `systemctl enable`。
- `板上 /root/start_all_voice.sh`:一键拉起语音 + 云台全栈。
- service 已含的三个修补(**若你重写/扩展务必保留**):
  1. `Environment=HOME=/root`(否则节点全崩);
  2. `start_gimbal.sh` 内 `pkill` 真实 `laser_node` 进程防 restart 累积;
  3. `aplay` 用 `plughw:CARD=CD002AUDIO`(防 card 号重排致 TTS 哑)。

**接手第一步(在板上跑):**
```bash
systemctl status voice-asr
systemctl is-enabled voice-asr
cat /etc/systemd/system/voice-asr.service
cat /root/start_all_voice.sh
journalctl -u voice-asr -b --no-pager | tail -50    # 看上次开机自启日志
```
按上面清单核对**哪些节点/支撑进程已被拉起、哪些漏了**(尤其 §2.1 里 launch 不含的 `command_receiver_node`/`uplink_node` 是否进了脚本),缺什么补什么。

---

## 7. 本对话范围外、但完整机器人自启会用到的(指针,非本对话产出)

这些子系统**不是本对话的工作**,细节见各自记忆/包,自启时按需纳入(据记忆 `voice-asr.service` 已含云台):

- **底盘** `chassis_bringup`:STM32 经 **Type-C 原生 USB CDC** 通信(by-id 端口);四轮速度 PID 闭环。
- **云台 + 激光** gimbal 节点:FOC + homing(须补 phase_offset)+ PI;激光经 MOSFET(GPIO BOARD 12)。
- **热成像融合** `thermal_detector`:Thermal-90(SPI)+ RGB 单应标定融合,出 `/hazard/events`。
- **IMU** `bmi088_imu`、激光雷达等。

---

## 8. App 与后端(客户端/服务端,**不在机器人开机自启范围**,仅供完整理解)

- **App**(`app/mobile`,Flutter):APK 已构建(`app/mobile/build/app/outputs/flutter-apk/app-debug.apk`)。设置页有「机器人语音」开关 → 发 `voice_control{enabled}` → 后端 → `command_receiver_node` → `/inspection/voice_control` → `asr_node` 启停监听(乐观更新+失败回滚,状态本地持久化)。装手机即可,不是机器人自启项。
- **后端**(Mac):FastAPI,`uvicorn` 须绑 `0.0.0.0:8000`;命令通道(`/api/commands`、`/api/robot/commands/*`)+ 上行(`/api/ingest/*`)。后端开机自启是 **Mac 侧**(launchd/手动),不是 RDK 的事。

---

## 9. 验收(自启做完后在板上验证)

1. 断电重启 RDK,**不 ssh 敲任何命令**,等约 5 分钟(USB CDC 重枚举)。
2. `ros2 node list` 应见:`asr_node`、`voice_node`、`cognition_node`、`report_service`、`command_receiver_node`、`uplink_node`(+ 云台/底盘等)。
3. 对机器人说「**小巡**」→ 应听到 TTS「我在」;再说「激光指示三号桌」→ 激光指向 + 语音回执。
4. 手机 App 设置页拨「机器人语音」开关 → 板上 `asr_node` 应启停监听(看 `journalctl`)。
5. `journalctl -u voice-asr -b` 无 `HOME`/声卡/模型缺失类报错。

> 语音相关代码与上板部署细节另见:`docs/architecture/voice_asr_setup.md`(模型下载/麦克风/SherpaAsrBackend 实现要点)、`docs/superpowers/specs/2026-06-21-voice-asr-interaction-design.md`(设计)。
