# 交接文档:RDK X5 语音 ASR 全栈「开机自启」实现

> **目的**:把已经调通的「端侧语音交互(语音识别 + 命令执行 + TTS 播报)」全栈做成 **RDK X5 开机自动启动**,不用每次重启后手动跑脚本。
> **读者**:负责实现开机自启的另一个 agent。
> **现状**:所有功能已上板调通、可手动一键启动(`bash /root/start_all_voice.sh`),但**不是开机自启**——板子每次重启后节点都没了,需要手动跑。
> **板子访问**:`ssh root@192.168.128.10`(USB Type-C gadget 链路);密码 root。ROS2 Humble,Ubuntu 22.04 aarch64。

---

## 1. 要实现的目标(一句话)

让板子开机后,**自动、按正确顺序、带必要前置设置**地把下面这套语音全栈跑起来。等价于开机后自动执行 `/root/start_all_voice.sh`(但要处理好 systemd 与后台进程、USB 设备就绪时机等细节,见 §5)。

---

## 2. 这套全栈由什么组成(7 个组件 + 1 个内核设置)

按**启动顺序**列出。`/root/start_all_voice.sh` 就是按这个顺序串起来的。

| 顺序 | 组件 | 启动脚本 | 进程 | 日志 | 作用 | 依赖 |
|---|---|---|---|---|---|---|
| 0 | **USB autosuspend 禁用** | (一行 echo) | — | — | 防 USB 麦克风反复掉线(默认 2s autosuspend 太激进) | 必须在起 asr_node **之前** |
| 1 | **TTS 常驻服务** | `/root/start_tts_server.sh` | `python3 /root/tts_server.py` | `/tmp/tts_server.log` | 加载 Matcha TTS 模型**一次**(~16s),之后每句合成只要 ~0.5s(否则 CLI 每次重载模型 = 每句延迟 17s) | sherpa_onnx python 包、`/root/sherpa/` 模型 |
| 2 | **命令通道节点** | `/root/start_cmd_nodes.sh` | `uplink_node`、`acceptance_node`、`command_receiver_node` | `/tmp/uplink.log`、`/tmp/acceptance.log`、`/tmp/command_receiver.log` | App 上行/下行命令通道(连 Mac 后端 192.168.128.100:8000) | ROS2、`/root/.app_ingest_token`、Mac 后端(没有也不崩,只警告重试) |
| 3 | **语音播报节点** | `/root/start_voice.sh` | `voice_node` | `/tmp/voice.log` | 订阅 `/inspection/voice`,经 `sherpa_say.sh` → TTS 服务播报 | ROS2、TTS 服务(组件1) |
| 4 | **报告服务** | `/root/start_report.sh` | `report_service` | `/tmp/report_service.log` | 生成巡检报告(语音命令"生成报告"用) | ROS2 |
| 4.5 | **云台 + 激光节点** | `/root/start_gimbal.sh` | `gimbal_controller_node`、`laser_node` | `/tmp/gimbal.log`、`/tmp/laser.log` | 云台初始化(读 AS5600 绝对编码器知位置)+ 激光控制;laser_point/find_item(laser) 等动作用 | **TROS**(`/opt/tros/humble`,见 §4.5!)、`python3-smbus2`(I2C)、`/dev/i2c-*`、`gimbal.yaml`(已烧标定) |
| 5 | **ASR 语音识别节点** | `/root/start_asr.sh` | `asr_node`(核心) | `/tmp/asr.log` | 麦克风→唤醒词→识别→意图→执行→TTS回执;加载模型+开麦 ~10-15s | ROS2、sherpa_onnx、`/root/sherpa/` 模型、**USB 麦克风**、组件 0/1/3 |

> **云台已纳入自启**(用户要求开机自初始化)。见 §4.5 的云台专门说明——它和其它节点**用不同的 ROS 环境(TROS),且有 FOC 标定持久化**,务必读。

---

## 3. 各启动脚本的实际内容(板上现有,均可直接复用)

> 这些脚本**已经在板上 `/root/` 下,内容如下**。另一个 agent **不需要重写**它们,只需要让 systemd 在开机时调用 `/root/start_all_voice.sh`(它内部按顺序调用其余脚本)。列在这里是为了让你理解每一步在干什么。

### `/root/start_all_voice.sh`(总入口 — 自启就让它在开机跑)
```bash
#!/bin/bash
echo -1 > /sys/module/usbcore/parameters/autosuspend 2>/dev/null  # USB麦防掉线
bash /root/start_tts_server.sh; sleep 16     # TTS模型加载~16s,必须等
bash /root/start_cmd_nodes.sh; sleep 3
bash /root/start_voice.sh; sleep 2
bash /root/start_report.sh; sleep 2
bash /root/start_gimbal.sh; sleep 3          # 云台+激光(TROS环境)
bash /root/start_asr.sh; sleep 10            # asr加载模型+开麦
# (末尾还有 ps 打印在跑的节点)
```

### `/root/start_gimbal.sh`(云台 + 激光 — 注意用 TROS 环境)
```bash
#!/bin/bash
# 云台 + 激光。FOC 标定已烧进 gimbal.yaml;节点读 AS5600 绝对编码器即知位置,无需运行时 homing。
# 启动后云台默认 idle 不驱动,laser_point 等命令来了才使能+转动(开机不空转、不耗电)。
source /opt/tros/humble/setup.bash          # ←注意:云台用 TROS,不是 /opt/ros !
source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash
pkill -9 -f "gimbal_controller_node"; pkill -9 -f "gimbal_laser laser_node"; sleep 2
setsid ros2 launch gimbal_laser gimbal_controller.launch.py >/tmp/gimbal.log 2>&1 </dev/null &
sleep 2
setsid ros2 run gimbal_laser laser_node >/tmp/laser.log 2>&1 </dev/null &
```

### `/root/start_tts_server.sh`
```bash
#!/bin/bash
pkill -9 -f tts_server.py 2>/dev/null; sleep 1
setsid python3 -u /root/tts_server.py >/tmp/tts_server.log 2>&1 </dev/null &
```

### `/root/start_cmd_nodes.sh`
```bash
#!/bin/bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
TOK=$(cat /root/.app_ingest_token)
SHARE=install/inspection_manager/share/inspection_manager/config
SRC=src/inspection_manager/config
pkill -9 -f "command_receiver_nod[e]"; pkill -9 -f "acceptance_nod[e]"; pkill -9 -f "inspection_manager/uplink_nod[e]"; sleep 2
setsid ros2 run inspection_manager uplink_node --ros-args --params-file $SRC/uplink.yaml -p ingest_token:=$TOK >/tmp/uplink.log 2>&1 &
setsid ros2 run inspection_manager acceptance_node --ros-args -p stations_config:=$SHARE/stations.yaml >/tmp/acceptance.log 2>&1 &
setsid ros2 run inspection_manager command_receiver_node --ros-args --params-file $SRC/command_receiver.yaml -p ingest_token:=$TOK -p stations_config:=$SHARE/stations.yaml -p gimbal_aim_config:=$SHARE/gimbal_aim.yaml >/tmp/command_receiver.log 2>&1 &
```

### `/root/start_voice.sh`
```bash
#!/bin/bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash; source install/setup.bash
pkill -9 -f "voice_nod[e]"; sleep 1
setsid ros2 run inspection_manager voice_node --ros-args -p tts_engine:=command -p tts_command:=/root/sherpa_say.sh >/tmp/voice.log 2>&1 &
```

### `/root/start_report.sh`
```bash
#!/bin/bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash; source install/setup.bash
SHARE=install/inspection_manager/share/inspection_manager/config
pkill -9 -f "report_servic[e]"; sleep 1
setsid ros2 run inspection_manager report_service --ros-args -p report_config:=$SHARE/report.yaml >/tmp/report_service.log 2>&1 &
```

### `/root/start_asr.sh`
```bash
#!/bin/bash
cd /root/Soc_China/rdk_x5/ros2_ws
source /opt/ros/humble/setup.bash; source install/setup.bash
SRC=src/inspection_manager/config
SHARE=install/inspection_manager/share/inspection_manager/config
pkill -9 -f "asr_nod[e]"; sleep 2
setsid ros2 run inspection_manager asr_node --ros-args --params-file $SRC/asr.yaml \
  -p stations_config:=$SHARE/stations.yaml -p gimbal_aim_config:=$SHARE/gimbal_aim.yaml \
  >/tmp/asr.log 2>&1 < /dev/null &
```

---

## 4. 关键支撑文件(已在板上,自启不用改,但要知道存在)

| 文件 | 作用 |
|---|---|
| `/root/tts_server.py` | 常驻 TTS 服务:加载 `/root/sherpa/matcha-icefall-zh-baker` + `vocos-22khz-univ.onnx` 模型,从 FIFO `/tmp/tts.fifo` 读文本→合成→`aplay -D hw:0,0` 播到 USB 音响。**播放期间 touch `/tmp/tts_playing`**(asr_node 据此做 anti-echo 静音麦) |
| `/root/sherpa_say.sh` | voice_node 调它播报:有 FIFO 就 `echo 文本 > /tmp/tts.fifo`(走常驻服务,快),否则回退 `/root/sherpa_say_cli.sh`(慢) |
| `/root/sherpa_say_cli.sh` | 旧的 CLI 版 TTS(每次重载模型,17s,仅回退用) |
| `/root/.app_ingest_token` | 命令通道鉴权 token(`chmod 600`,cmd_nodes 启动注入) |
| `/root/sherpa/` | 所有模型:`sherpa-onnx-kws-zipformer-wenetspeech`(唤醒词)、`sherpa-onnx-sense-voice-zh-int8`(识别)、`silero_vad.onnx`(断句)、`keywords.txt`(唤醒词"小巡/巡检助手")、`matcha-icefall-zh-baker`+`vocos-22khz-univ.onnx`(TTS) |
| 代码包 | `/root/Soc_China/rdk_x5/ros2_ws/`(已 `colcon build`,`install/` 里有 `inspection_manager`) |
| 麦克风 | **USB 麦** `USB Composite Device`(ALSA `hw:2,0`,**仅 48kHz**);ALSA 名在 `asr.yaml: mic_device: "USB Composite Device"`。USB 音响是另一个设备 `hw:0,0`(纯输出,放 TTS) |

---

## 4.5 云台 + 激光 专门说明(务必读 — 和语音那套不一样)

用户要求**开机后云台自初始化**,后续 laser_point / find_item(激光指示) 等动作能用。已建 `/root/start_gimbal.sh` 并加进 `start_all_voice.sh`。关键差异:

1. **不同的 ROS 环境**:云台节点用 **TROS**(`/opt/tros/humble/setup.bash`),inspection_manager 那套用 `/opt/ros/humble`。两者同为 Humble,DDS 互通(命令通道发 `/gimbal/enable`、`/gimbal/target_angle`、`/laser/enable` 给云台/激光节点能收到)。`start_gimbal.sh` 里 source 的是 TROS,**不要改成 /opt/ros**。
2. **FOC 标定已持久化、不需运行时 homing**:`rdk_x5/ros2_ws/src/gimbal_laser/config/gimbal.yaml` 里烧着 2026-06-12 标定的 `pan/tilt_zero_deg`、`phase_offset_deg`、`pole_pairs`。节点启动读 **AS5600 绝对编码器(I2C)** 即知当前位置 → 配合烧入的 zero 就完成"初始化"。`/gimbal/home` 服务只是「把当前角设为目标」(防漂移),**不是物理归中**,开机**不需要**调它。**⚠️ 绝对不要丢失/覆盖 `gimbal.yaml` 的标定值**,否则云台 FOC 失准要重新标定。
3. **上电默认 idle、不驱动**:`gimbal_controller_node` 启动后不通电驱动电机(等 `/gimbal/enable=true`)。laser_point 命令来时,`command_executor` 会自动先 enable→转到目标→开激光→关——所以开机只要把两个节点跑起来就行,云台**不会**在开机时空转或乱动(安全、不耗电)。这就是"初始化好、待命"的正确状态。
4. **依赖**:`python3-smbus2`(已装)、`/dev/i2c-*`(在)、TROS(在)。`gimbal_controller.launch.py` 起 `gimbal_controller_node`;`laser_node` 单独 `ros2 run`(默认 BOARD pin12 驱动激光)。
5. **启动顺序无所谓**:云台/激光和语音那套通过 DDS 解耦,谁先谁后都行;`start_all_voice.sh` 里放在 report 之后、asr 之前。

> 若用户希望开机时云台**物理转到某个中位**(而不只是软件就绪),可在 start_gimbal 之后追加:发一次 `/gimbal/enable=true` + 目标角 `/gimbal/target_angle`(Vector3,如 0,0,0),停几秒后 `/gimbal/enable=false`。**默认不做**(没必要且会动);除非用户明确要。

---

## 5. 推荐实现方式:systemd 服务(给另一个 agent 的具体方案)

我(上一个 agent)本想直接创建,但被权限策略拦了(创建开机持久化服务需用户授权)。**请你来创建**。推荐如下 unit 文件:

### `/etc/systemd/system/voice-asr.service`
```ini
[Unit]
Description=Voice ASR stack (TTS daemon + asr/voice/cmd/report ROS2 nodes)
After=multi-user.target sound.target network-online.target
Wants=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
# 关键:等 USB 麦克风枚举 + 声卡就绪(板子启动早期 USB 设备可能还没好)
ExecStartPre=/bin/sleep 20
ExecStart=/root/start_all_voice.sh
# 关键:start_all_voice.sh 用 setsid 把各节点放后台后自己退出;
# KillMode=process 让 systemd 只管主脚本、不连带杀掉后台节点
KillMode=process
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
```

### 启用命令
```bash
ssh root@192.168.128.10
# 把上面内容写到 /etc/systemd/system/voice-asr.service
systemctl daemon-reload
systemctl enable voice-asr.service
systemctl start voice-asr.service        # 立即测一次(不用真重启)
systemctl status voice-asr.service
```

### 为什么这么设计(请务必理解,否则节点会被 systemd 杀掉)
- **`Type=oneshot` + `RemainAfterExit=yes`**:`start_all_voice.sh` 跑完(把节点用 `setsid &` 丢后台后)就退出。oneshot 表示「跑一次脚本」,RemainAfterExit 让服务保持 active 状态,**不会因主脚本退出就清理子进程**。
- **`KillMode=process`**:默认 `control-group` 会在服务停止时杀掉整个 cgroup(包括后台节点)。改 `process` 让它只管主脚本进程。配合 setsid,节点能在服务"完成"后继续活着。
- **`ExecStartPre=/bin/sleep 20`**:**最重要的坑**——板子开机早期 USB 麦克风可能还没枚举好;asr_node 开麦失败虽然会重试 60s 不崩,但加 20s 延迟更稳。也给声卡/网络就绪留时间。可按实测调大。

> ⚠️ **如果你更想用别的机制**(rc.local / cron `@reboot` / 各节点独立 systemd 服务),也行,但务必满足:① autosuspend 禁用在 asr 之前;② TTS 服务先起且等 ~16s 模型加载;③ 后台进程不被框架回收;④ 等 USB 麦就绪。**最省事 = 就用一个 oneshot 服务调 `start_all_voice.sh`**(它内部顺序/sleep 都已调好)。

---

## 6. 验证(自启是否成功)

```bash
# 真重启板子后(或 systemctl start voice-asr 后)等 ~60s,然后:
ssh root@192.168.128.10
# 1) 进程都在?
ps -ef | grep -E "tts_server|asr_nod[e]|voice_nod[e]|command_receiver_nod[e]|uplink_nod[e]|acceptance_nod[e]|report_servic[e]|gimbal_controller_nod[e]|gimbal_laser laser_nod[e]" | grep -v grep
# 期望:tts_server.py / asr_node / voice_node / command_receiver_node / uplink_node / acceptance_node / report_service / gimbal_controller_node / laser_node
# 2) asr_node 正常起来(没因麦掉线崩)?
grep "asr_node up" /tmp/asr.log        # 有这行=成功
grep -i "unavailable\|Traceback" /tmp/asr.log   # 不该有
# 3) TTS 服务加载完?
grep "TTS server ready" /tmp/tts_server.log
# 4) USB 麦在?
arecord -l | grep "card 2"             # 有 card 2 = USB麦在
# 5) autosuspend 禁了?
cat /sys/module/usbcore/parameters/autosuspend   # 应为 -1
# 6) 端到端:对 USB 麦说"小巡"→应听到音响播"我在"→说"播报请大家注意安全"→应播报该句
# 7) 云台节点起来了?(TROS 环境)
grep -iE "error|Traceback|i2c|smbus" /tmp/gimbal.log | tail -5    # 不该有致命错
ros2 node list 2>/dev/null | grep -E "gimbal|laser"              # 应看到 gimbal_controller_node / laser_node
# 8) 云台动作端到端(需 Mac 后端在,或本地发命令):对麦说"激光指示三号桌"→云台转向+激光亮
#    (前提:gimbal_aim.yaml 里该工位有角度;desk-03 已有 [12.6,-11.6])
```

---

## 7. 已知坑 / 注意事项(务必读)

1. **USB 麦克风会偶尔物理掉线/重新枚举**(硬件不稳)。已用 `autosuspend=-1` + asr_node 开麦重试 60s 缓解。开机自启时若麦刚好没枚举,`ExecStartPre` 的 20s 延迟 + asr 重试一般能扛过去;实在不行重插一下 USB 麦再 `systemctl restart voice-asr`。
2. **顺序敏感**:autosuspend 必须在 asr 前;TTS 服务必须先起并等模型加载(~16s),否则 voice_node 第一次播报会回退慢速 CLI。`start_all_voice.sh` 里的 `sleep` 不要删。
3. **后台进程别被 systemd 回收**:见 §5 的 `KillMode=process` + `RemainAfterExit=yes`。这是最容易踩的坑——如果配错,`systemctl start` 后节点会瞬间被杀。
4. **命令通道(cmd_nodes)连 Mac 后端 192.168.128.100:8000**,开机时若 Mac 没连/没开后端,uplink/command_receiver 只会日志警告重试,**不影响语音本身**(语音全在板上自包含)。
5. **不要动这些已调好的配置**:`asr.yaml`(`mic_device: "USB Composite Device"`、`kws_threshold: 0.10`、`vlm_fallback_enabled: false`)、`/root/tts_server.py`、`/root/sherpa_say.sh`、**`gimbal.yaml`(FOC 标定值,丢了云台失准)**。
6. **日志都在 `/tmp/*.log`**(重启清空,正常)。排障先看 `/tmp/asr.log`、`/tmp/tts_server.log`、`/tmp/gimbal.log`。
7. **云台用 TROS 不是 ROS**:`start_gimbal.sh` source 的是 `/opt/tros/humble/setup.bash`。systemd 服务里别只 source `/opt/ros`——`start_gimbal.sh` 内部自己 source 好了,只要让 systemd 调 `start_all_voice.sh`(它会调 start_gimbal.sh)即可,不用在 service 里设 ROS 环境。
8. **云台开机不会乱动**:`gimbal_controller_node` 启动后是 idle(不驱动电机),读编码器知位置即可,等命令才动。所以开机自启云台是安全的,不会甩臂。

---

## 8. 背景:这套语音功能本身(已全部调通并提交)

代码在仓库 `rdk_x5/ros2_ws/src/inspection_manager/`,已 push 到 `origin/main`。语音相关核心:`asr_node.py`、`asr_engine.py`(SherpaAsrBackend:KWS唤醒+VAD断句+SenseVoice识别+FIR重采样+anti-echo)、`asr_controller.py`、`intent.py`、`command_executor.py`、`dialog.py`、`config/asr.yaml`。详细设计见 `docs/architecture/voice_asr_setup.md` 和 `docs/superpowers/specs/2026-06-21-voice-asr-interaction-design.md`。**你只需要做开机自启,不用改这些代码。**
