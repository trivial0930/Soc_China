# 后端 Prompt:建图模式（mapping mode）+ 存图

给后端 agent。目标:让 App 能一键让机器人进入/退出「建图模式」,并在建图时一键存图。机器人侧(RDK)已实现命令消费与执行,**后端基本只需透传 + 暴露当前模式**。

## 背景(已就绪的机器人侧)
RDK 上常驻的 `command_receiver_node` 每 ~2s 轮询 `GET /api/robot/commands/pending`,新增支持两种命令类型并在本地执行(停语音栈→起建图栈 / 反之 / 存图),结果回 `POST /api/robot/commands/{id}/result`。它还每个轮询 tick `POST /api/robot/mode` 上报当前真实模式。

## 你要做的

### 1. 命令队列透传(多半已支持,确认即可)
现有 `POST /api/robot/commands`(Bearer 写鉴权)已能塞任意命令;确认这两种 type 能正常入队、被 `/pending` 返回、并接受 `/ack` 与 `/result`:
- `{"type": "set_mode", "params": {"mode": "mapping"}}` —— 进建图模式
- `{"type": "set_mode", "params": {"mode": "normal"}}` —— 退出,恢复语音栈
- `{"type": "save_map", "params": {"name": "<slug>"}}` —— 存图(name 可省,默认 `lab_map`)

命令结果(`/result`)的 `status`(done/failed)+ `result`(中文文案,如「已进入建图模式」「建图栈启动失败(rc=1),已停在安全态」)原样存好,供 App 拉取显示。

### 2. 新增模式状态端点
- `POST /api/robot/mode`(Bearer 写鉴权,RDK 调):body `{"mode": "<normal|switching|mapping|mapping_error>"}`。持久化「最新一次上报的 mode + 服务器接收时间戳」。覆盖式即可(只存最新)。
- `GET /api/robot/mode`(App 读):返回 `{"mode": "...", "age_ms": <收到至今毫秒>}`。`age_ms` 让 App 能判断 RDK 是否还在上报(类似 teleop 的 age 机制)。

mode 取值含义:`normal` 正常(语音在跑)、`switching` 切换中、`mapping` 建图中、`mapping_error` 进建图失败已停在安全态。

## 约束 / 注意
- **事实源是 RDK 上报的 mode**,后端只存转发,不要自己推断或改写 mode。
- 写端点(`POST /api/robot/commands`、`POST /api/robot/mode`)都要 Bearer token 鉴权,沿用现有 `~/.app_ingest_token` 机制。
- 不要给 set_mode/save_map 加业务校验(合法性由 RDK 判;非法 mode 机器人会回 failed)。
- `age_ms` 建议:RDK 每 ~2s 上报一次,App 超过 ~6s 没更新即可视为掉线(与 teleop staleness 一致)。

## 验收
- POST 一条 `set_mode:mapping` 命令 → `/pending` 能取到 → RDK ack+result。
- `GET /api/robot/mode` 在 RDK 上报后返回最新 mode 且 age_ms 随时间增长、下次上报清零。
- 断网时 `GET /api/robot/mode` 的 age_ms 持续增大(App 据此提示「机器人离线」)。
