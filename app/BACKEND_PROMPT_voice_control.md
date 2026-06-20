# 后端任务:新增 `voice_control` 命令(App 远程开/关机器人语音)

> 给**后端 agent**(写 `app/backend/`)的任务说明,可直接作为 prompt。
> 这是在**已实现的命令下行通道**(见 `app/BACKEND_PROMPT_command_api.md`)上**只加一个命令类型**,不新增端点、不改通道结构。
> 机器人侧的接收与执行由机器人 agent 负责,**已在 `docs/superpowers/specs/2026-06-21-voice-asr-interaction-design.md` 预留**(见本文 §4),后端无需关心其内部。
> 唯一数据契约是 `app/API_SPEC.md`:本任务需在「命令类型」表新增一行并更新 changelog。

---

## 1. 背景

机器人正在加**端侧语音交互**(唤醒词「小巡 / 巡检助手」+ 连续对话 + 中文 ASR)。语音监听常驻会占算力、且在安静场合或误唤醒多时需要能关。因此 App 需要一个**远程开关**:一键开启 / 关闭机器人的整个语音监听。

这个开关走**现有命令通道**(App `POST /api/commands` → 队列 → 机器人轮询 `GET /api/robot/commands/pending` → 执行 → `result` 回执),只是一个新的命令 `type`。

## 2. 你要做的(后端,改动很小)

命令队列表、`POST /api/commands`、机器人轮询/ack/result **全部复用,不动**。仅需:

1. **把 `voice_control` 加入 `POST /api/commands` 的合法 `type` 白名单**(现在非法 type 返回 400,需放行它)。
2. **校验 `params`**:必须含 `enabled` 且为布尔值(`true`/`false`);缺失或类型错 → 400 `{"detail":"voice_control 需要布尔 params.enabled"}`。
3. 其余流转(`queued→sent→done/failed`、机器人 `result` 回执)与其它命令**完全一致**,无需特殊处理。
4. **更新 `app/API_SPEC.md`**:在「命令类型」表加一行(见 §3),changelog 记一笔(如 `v1.2`)。

### 命令契约

```jsonc
// App → POST /api/commands  (需 token: Authorization: Bearer <APP_INGEST_TOKEN>)
{ "type": "voice_control", "params": { "enabled": false }, "issued_by": "app" }

// 201 返回(与其它命令同构)
{ "command_id": "cmd-...", "type": "voice_control",
  "params": { "enabled": false }, "status": "queued", "created_at": "..." }

// 机器人回执(经现有 POST /api/robot/commands/{id}/result)
{ "status": "done", "result": "语音监听已关闭" }   // 或 "语音监听已开启"
```

## 3. API_SPEC 命令类型表新增行

| `type` | `params` | 含义 | 机器人侧动作 |
|---|---|---|---|
| `voice_control` | `{ "enabled": true \| false }` | 远程开/关机器人语音监听 | `enabled=false` 停止唤醒/录音/识别(释放算力);`true` 恢复待唤醒 |

## 4. 机器人侧(机器人 agent 负责,后端无需做,列此对齐契约)

- `command_receiver.dispatch_command()` 新增 `voice_control` 分支 → 发布 `/inspection/voice_control`(`{"enabled": bool}`),回执 `语音监听已开启/已关闭`。
- `asr_node` 订阅该话题:`false`→进禁用态(停 KWS/VAD/ASR 采集线程);`true`→恢复;状态写本地文件,重启保持。
- 详见上述 spec §4.5。

## 5. App 侧(前端 agent 稍后实现,列此说明预期)

- 「设置」或「操作」页加一个**语音开关**(Switch):开 → 发 `{type:"voice_control",params:{enabled:true}}`;关 → `enabled:false`。
- **MVP 状态同步**:开关用**乐观更新 + result 回执**确认(发命令后本地记住状态,看 `GET /api/commands` 回执确认 `done`)。后端**无需**为此加任何状态端点。

### 可选增强(非必须,后端如有余力)

若希望 App **重新打开时也能显示机器人当前真实开/关状态**(权威源在机器人,可能被温控自动降级改变),可二选一:
- (a) 机器人经现有上行汇报一个 `voice_enabled` 状态,后端存最近值,App 用一个只读字段/端点读取;或
- (b) 不做,App 仅乐观显示(完全够用)。
默认走 (b);(a) 留作以后。

## 6. 验收要点

- `POST /api/commands` body `{type:"voice_control",params:{enabled:false}}` → 201;缺 `enabled` 或非布尔 → 400;无 token → 401。
- 机器人轮询拉到该命令、执行、回执 `result`("语音监听已关闭"),`GET /api/commands` 能看到 `done`。
- `app/API_SPEC.md` 命令表 + changelog 已更新。
