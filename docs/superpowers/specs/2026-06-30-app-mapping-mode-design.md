# App 建图模式（一键腾资源 + 起建图栈）设计

日期：2026-06-30 ｜ 方案：A（选择性停 + command_receiver 自执行）｜ 状态：设计待实现

## 背景与目标

建图（B1）时，开机自启的重负载层（语音 ASR、认知、本地 VLM llama-server ~3GB、云台）会和建图栈抢 CPU 与内存——原地验栈时已观察到 EKF "Failed to meet update rate"、slam 丢扫描。当前需要每次手动 `systemctl`/`pkill` 腾资源再手动起 `mapping.launch`，繁琐且易出错。

目标：App 上一个**建图模式开关**，
- ON = RDK 自动停重负载层腾出 CPU/内存 + 自动起整套建图栈，翻完开关即可 App 遥控建图（**一键就绪**）；
- OFF = 拆建图栈 + 恢复重负载层（语音等）。
- 建图中可在 App 一键**存图**。

非目标（YAGNI）：Nav2 自主导航（B2）、多地图管理 UI、把重负载层重构成 systemd 正规服务（方案 B，留待以后）。

## 关键现状（探索结论）

- 消费 App 命令队列的 `command_receiver_node`（连同 `uplink_node` + `acceptance_node`）由 `start_all_voice.sh` → `start_cmd_nodes.sh` 拉起，**逻辑上长在 voice-asr 里**。
- `voice-asr.service` 用 `KillMode=process` + 各节点 `setsid` 放后台（ppid=1 孤儿）。**因此 `systemctl stop voice-asr` 杀不掉这些节点**（只停主脚本）——任何依赖 systemctl stop 关语音的设计都会静默失效。
- 正常模式不跑任何底盘/雷达节点；`mapping.launch.py` 会自起 lslidar + 底盘里程计/IMU-EKF + slam + teleop_safety。
- 重负载层各组件已有独立 `start_*.sh`（start_llm/tts_server/voice/report/cognition/gimbal/asr），命令通道是 `start_cmd_nodes.sh`。

## 核心约束

停重负载层时，**命令通道（uplink + command_receiver + acceptance）必须始终活着**，否则 App 发不进"退出建图"命令 → 卡死。方案 A 通过"切换时绝不 pkill 命令通道三件"满足此约束——于是 `command_receiver_node` 自己就能充当执行模式切换的那只手。

## 架构（三层）

| 层 | 成员 | normal | mapping |
|---|---|---|---|
| **命令通道层**（常驻） | uplink_node + command_receiver_node + acceptance_node | 活 | **活**（切换时绝不杀） |
| **重负载层** | llama-server / tts_server / voice_node / report / cognition_node / gimbal+laser / asr_node | 活 | 停 |
| **建图层** | mapping.launch（lslidar + 里程计/IMU-EKF + slam + teleop_safety） | 停 | 活 |

```
App 建图开关
  │ POST {type:set_mode, mode:mapping|normal}  /  {type:save_map, name}
  ▼ 现有命令队列(Bearer token)
后端命令队列 ──poll──► command_receiver_node ★永不被杀
                          │ set_mode/save_map 处理 + 切换锁 + 写状态文件
            ┌─────────────┴─────────────┐
            ▼ mapping                    ▼ normal
     mapping_mode_on.sh           mapping_mode_off.sh
       pkill 重负载子集               pkill 建图栈(干净)
       起 mapping.launch             重跑 start_*.sh 拉回重负载
       校验栈起来                     写 normal
       写 mapping / mapping_error
            └─────────────┬─────────────┘
                          ▼
              /root/.robot_mode  单一事实源
              (normal/switching/mapping/mapping_error)
                          │ uplink 心跳带 mode + mapping_health
                          ▼  后端 → App 显示真实模式
```

## 组件（新增/改动）

1. **`command_receiver_node` 加 `set_mode` / `save_map` 处理**
   - 调度逻辑抽成纯函数（便于 host 单测），node 仅负责取命令 + 调 subprocess + 回报。
   - `set_mode {mode}`：抢切换锁 → 写 `switching` → 调对应脚本 → 据结果写终态 → 释放锁。
   - `save_map {name}`：调 `map_saver_cli -f ~/maps/<name>`（仅 mapping 模式有效；失败回报，不切模式）。
2. **`mapping_mode_on.sh`**：pkill 重负载子集（**不动**命令通道三件）→ `setsid` 起 `mapping.launch.py`（日志 `/tmp/mapping.log`）→ 校验 → 写状态。
3. **`mapping_mode_off.sh`**：pkill 建图栈（全模式匹配 + 必要时按 cgroup，彻底清含 stm32_bridge/bmi088_imu 等 setsid 孤儿）→ 重跑重负载层各 `start_*.sh` → 写 normal。
4. **`/root/.robot_mode`**：状态文件，单一事实源。
5. **uplink 心跳**：加 `mode` + `mapping_health`（建图栈关键节点是否齐）。
6. **App prompt**（交付，另两 agent 实现）：后端透传 set_mode/save_map + 心跳暴露 mode；前端建图开关 + 真实 mode/health 显示 + 错误态 + 建图中露遥控页 + 存图按钮。

## 数据流

**进建图（ON）**：App POST set_mode:mapping → command_receiver 抢锁（`/run/robot_mode.lock`，已 mapping 则幂等返回）→ 写 `switching` → `mapping_mode_on.sh`：pkill 重负载子集 → 起 mapping.launch → **校验**（轮询最多 30s，判据用 node list + `tf2_echo map odom`，**不信 `topic hz`**，因 best_effort/transient_local + 每次 ssh 临时节点 DDS 发现慢会假空）→ 成功写 `mapping`，失败见下 → 释放锁 → uplink 上报。

**建图中**：App 遥控页摇杆开车（mapping.launch 含 teleop_safety，链路不变）；`save_map` 命令存图到 `~/maps/<name>`。

**退出（OFF）**：App POST set_mode:normal → 抢锁 → 写 `switching` → `mapping_mode_off.sh`：pkill 建图栈（干净）→ 重跑重负载层 start 脚本 → 写 `normal` → 释放锁 → 上报。

**状态一致性**：事实源是 RDK 的 `/root/.robot_mode`，**不是** App 开关位置。App 始终显示 RDK 回报的 mode；开关只是"请求"。命令幂等，可重复发；命令丢了 App 靠心跳发现 mode 未变再补发。命令本身也回 ack/结果给即时反馈，心跳兜底最终一致。

## 错误处理与安全（停在安全态，不自动回滚）

- **进建图失败**（栈没起 / 校验超时）：拆掉刚起的建图栈（不留半死进程占串口），重负载层保持已停，写 `mapping_error` + 失败原因上报。**车不动、状态明确、不自动回滚**；用户在 App 决定点 OFF 回正常或重试 ON。
- **退建图失败**（语音层没完全拉回）：建图栈仍正常拆除（优先保证车能停）；重负载重启尽力而为，未起来的在 health 标出，mode 记 normal 附 `restore_warn`，App 提示可重试 OFF。
- **并发/重复/丢命令**：切换锁，`switching` 期间拒新 set_mode（返回"忙"）；锁带超时（90s）防卡死，超时强制释放并置 `mapping_error`；幂等。
- **运动安全**：退出前先停建图栈 → teleop/bridge 一停，deadman 0.5s 自动刹停。切换中摇杆不影响安全（避障/deadman 均为建图栈内本地逻辑）。
- **资源清理**：off 用全模式匹配 + 按需 cgroup 彻底清 setsid 孤儿（根治串口被占）；llama-server（~3GB）停掉是腾内存主力，off 时拉回。
- **存图失败**：`map_saver_cli` 失败（没图/超时）回报错误，不切模式、不影响当前建图。

## 测试

**Host 单测**（`tests/test_mode_switch.py`，纯逻辑、mock subprocess）：命令解析（含非法 mode 拒绝）、状态机（normal↔switching↔mapping、失败→mapping_error）、幂等（已在目标态 no-op）、锁（switching 拒新命令、超时强制释放置 error）、选脚本正确（on/off）、save_map 参数拼装。

**上板集成**（RDK 现场）：
- ON：重负载子集停 + 命令通道三件仍活 + 建图栈起 + 状态=mapping + 心跳带 mapping + 内存释放（llama 没了）；摇杆能开车、save_map 存出 .pgm/.yaml。
- OFF：建图栈干净清除（串口释放、无孤儿）+ 语音层拉回 + 状态=normal。
- 失败路径：故意让建图栈起不来（拔雷达）→ mapping_error + 无半死进程 + 语音保持停。
- 命令通道存活：进 mapping 后仍能从 App 发 OFF 并被执行（证明没把自己锁死）。

## 交付物

- RDK：command_receiver_node 加 set_mode + save_map（+ 抽纯逻辑函数）；`mapping_mode_on.sh` / `mapping_mode_off.sh`；`/root/.robot_mode`；uplink 心跳加 `mode`+`mapping_health`。
- 测试：`tests/test_mode_switch.py`。
- 文档：本 spec + 更新 `docs/ops/lab_mapping_procedure.md`（改成"App 一键进建图模式"为主、手动 launch 为备）。
- App prompt：`app/BACKEND_PROMPT_mapping_mode.md` + `app/FRONTEND_PROMPT_mapping_mode.md`。
- 分工：我负责 RDK 端落地 + 现场验证；App 由 prompt 交付。

## 命令协议（补充）

复用现有命令队列，新增两类命令（JSON）：
- `{"type": "set_mode", "mode": "mapping" | "normal"}`
- `{"type": "save_map", "name": "<slug>"}`（默认 `lab_map`；存到 `~/maps/<name>.pgm|.yaml`）

心跳新增字段：`mode`（normal/switching/mapping/mapping_error）、`mapping_health`（关键节点齐全的布尔/明细）、可选 `restore_warn`。

关联：`rdk_x5/ros2_ws/src/chassis_bringup/launch/mapping.launch.py`、`docs/ops/lab_mapping_procedure.md`、teleop_safety 包、[[voice-asr-systemd-autostart]]、[[b1-mapping-onecmd-launch]]、[[mgmt-app-uplink-deploy]]。
