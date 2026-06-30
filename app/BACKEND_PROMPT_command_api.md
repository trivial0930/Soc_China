# 后端任务:App→机器人「命令下行」通道(Command API)

> 这份文档是给**后端 agent**(写 `app/backend/` 的)+ **机器人 agent**(写 `rdk_x5/.../inspection_manager/` 的)的任务说明,可直接作为 prompt 使用。
> 由前端 agent(写 `app/mobile/` 正式 App)发起:App 已新增「操作」Tab,需要把用户操作下发给机器人执行。**前端已按本文档约定的契约实现完毕**,只等后端落地。
> 唯一数据契约仍是 `app/API_SPEC.md`;本任务需要你**新增一节**并更新其 changelog。

---

## 1. 背景与现状

系统当前是**纯单向**数据流:
```
机器人(RDK X5, ROS2) ──POST /api/ingest/*──▶ 后端(FastAPI/SQLite) ──SSE/GET──▶ App
```
机器人侧已具备全部动作能力(巡检、到点复核 Nav2、课后验收、语音 sherpa、激光云台指示、生成报告),但这些**只能由机器人内部 L2 认知自动触发**,**没有任何可被 App/后端远程触发的入口**;后端也**只接收上行、不能下发命令**。

App 的「操作」Tab 需要用户**主动发起**:发起巡检 / 到点复核 / 课后验收 / 寻找物品(导航带路·激光指示)/ 语音提醒 / 激光指示 / 生成报告。因此需要补一条**命令下行通道**。

---

## 2. 你要做的(后端)

### 2.1 命令队列(SQLite 新表)
```sql
CREATE TABLE IF NOT EXISTS commands (
    command_id   TEXT PRIMARY KEY,     -- 形如 cmd-20260620-153000-0001
    type         TEXT NOT NULL,        -- 见 §3
    params       TEXT,                 -- JSON 对象
    status       TEXT NOT NULL,        -- queued|sent|done|failed|canceled
    issued_by    TEXT DEFAULT 'app',
    result       TEXT,                 -- 机器人回执(JSON/文本),可空
    created_at   TEXT,                 -- ISO8601 带时区
    updated_at   TEXT
);
```

### 2.2 App 侧接口
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/commands` | 下发命令。**需 token**(`Authorization: Bearer <APP_INGEST_TOKEN>`,与 handle 一致)。body `{"type": "...", "params": {...}, "issued_by": "app"}`。校验 `type` 合法、`params` 必填项齐全。返回 **201** `{command_id, type, status:"queued", created_at}`;非法 `type` → 400;缺 token → 401。 |
| GET | `/api/commands` | 命令列表(回执/状态)。query `status, type, since, limit, offset`,返回 `{items:[Command], total, limit, offset}`(分页同 §2)。**读接口,无需 token,带 CORS**。 |
| GET | `/api/commands/{command_id}` | 单条命令状态。 |

`Command` 实体(返回给 App):
```jsonc
{
  "command_id": "cmd-20260620-153000-0001",
  "type": "recheck_station",
  "params": { "station_id": "desk-03" },
  "status": "queued",            // queued|sent|done|failed|canceled
  "issued_by": "app",
  "result": "",                  // 机器人回执,可空
  "created_at": "2026-06-20T15:30:00+08:00",
  "updated_at": "2026-06-20T15:30:01+08:00"
}
```

### 2.3 机器人侧接口(下行拉取 + 回执)
机器人无公网、与后端同局域网,采用**机器人轮询**(最省事,与现有 uplink 单向 HTTP 同构):
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/robot/commands/pending` | 机器人轮询拉取 `status=queued` 的命令(可加 `?limit=`)。返回后把这些置为 `sent`(或返回时不改、由 ack 改,见实现选择)。建议**需 token**。 |
| POST | `/api/robot/commands/{command_id}/ack` | 机器人确认已接收 → `status=sent`。 |
| POST | `/api/robot/commands/{command_id}/result` | 机器人回执结果。body `{"status":"done"|"failed", "result":"..."}` → 更新 `status`+`result`+`updated_at`。 |

> 也可选 SSE:在现有 `/events/stream` 增加 `event: command`,推送命令状态变更给 App(非必须;App 可轮询 `GET /api/commands` 看回执)。

### 2.4 CORS / 鉴权 / 风格
- 写接口(`POST /api/commands`、机器人 ack/result)需 `Authorization: Bearer`;读接口(`GET /api/commands*`)无需 token、带 `Access-Control-Allow-Origin: *`(与现有约定一致)。
- 时间字段 ISO8601 带时区;错误体 `{"detail":"..."}`;字段名/枚举以本文件为准并同步进 `API_SPEC.md`。

---

## 3. 命令类型全集(App 会发这些 `type`)

| `type` | `params` | 含义 | 机器人侧动作 |
|---|---|---|---|
| `inspection_round` | `{}` | 发起一次综合巡检 | 启动巡检流程(各工位走一圈) |
| `recheck_station` | `{ "station_id": "desk-03" }` | 到指定工位复核 | Nav2 导航到该工位 + 近距复核(复用现有 recheck) |
| `acceptance` | `{ "station_id": "desk-03" }` 或 `{}`(全部) | 课后验收(指定/全部工位) | 切验收模式,产出"合格/需整理/存在安全隐患"+问题清单(走现有 desk_acceptance,结果仍按 ingest 上行) |
| `find_item` | `{ "asset_id": 3 }` 或 `{ "name": "示波器" }`,`"mode": "navigate"\|"laser"` | 寻找物品:带路或激光指示 | navigate=导航到设备工位/区域;laser=激光云台指示耗材柜盒 |
| `voice_prompt` | `{ "station_id": "desk-03"?, "text": "请整理桌面" }` | 语音提醒 | sherpa TTS 在指定工位播报 |
| `laser_point` | `{ "station_id": "desk-03" }` 或 `{ "location": "元件柜2/抽屉3/盒B" }` | 激光指示某点 | 激光云台指向 |
| `generate_report` | `{ "report_type": "periodic_summary" }` | 触发生成巡检报告 | 触发 L3 云端报告,结果按现有 report ingest 上行 |

> `report_type` 取值见 `API_SPEC.md §3` 枚举;`station_id` 与现有工位编号一致。`params` 校验失败返回 400。

---

## 4. 你要做的(机器人 agent)

现状:`cognition_node` / `recheck_node` / `voice_node` / `gimbal_controller` / 报告/验收 全由内部 ROS topic 驱动,无外部入口。需:
1. **新增命令接收节点**(如 `command_receiver_node.py`):定时 `GET /api/robot/commands/pending`(后端地址同 uplink 的 `backend_url`),取到命令后 `ack`,执行,再 `POST .../result` 回执。
2. **把现有动作解耦为可外部触发**:把 `recheck` / `voice` / `gimbal 激光` / `acceptance` / `report` 的触发入口暴露成内部 ROS service 或 topic,让 command_receiver 能按 `type` 调用(自动 L2 决策仍保留)。
3. `find_item` 的 navigate 复用 recheck 的 Nav2 导航;laser 复用 gimbal 云台指向。

---

## 5. 验收要点
- App 端「操作」Tab 各按钮 → `POST /api/commands` 返回 201,`GET /api/commands` 能看到记录与状态流转(queued→sent→done)。
- 机器人轮询拉到命令并执行,回执 `result` 可在 App 看到。
- 鉴权:无 token 的 `POST /api/commands` 返回 401;读接口跨源 OK。
- 更新 `app/API_SPEC.md`:新增「命令(Command)」一节 + 实体 + 路由 + changelog 记一笔(`v1.1`)。

---

## 6. 前端现状(已就绪,供你对齐)
- App `app/mobile/lib/services/command_client.dart` 已实现:`POST /api/commands`,body `{type, params, issued_by:"app"}`,带 `Authorization: Bearer`。
- 后端**尚未实现**该接口时,App 收 404/405/501 会优雅提示"后端暂未支持该命令",不崩——所以你**逐步实现也不会破坏 App**。
- 「寻找物品」的查位置已用现有只读 `GET /api/assets`,无需你改;只有"导航带路/激光指示"按钮走 `find_item` 命令。
