# 前后端联调测试协调(给后端 agent)

> 给**后端 agent**:正式手机 App(`app/mobile/`,Flutter)要和你的后端(`app/backend/`,已在 `:8000` 运行)做一次端到端联调。
> 本文档告诉你:① App 现状与最近改动;② 已验证打通的部分;③ 请你配合的几件事;④ 联调检查清单。
> **App 侧已就绪**,大部分已对你运行中的后端验证通过。

---

## 1. App 现状(5 个底部 Tab)
| Tab | 调用的后端接口 |
|---|---|
| **告警** | `GET /api/events`(初始列表)+ `GET /events/stream`(SSE 实时,hazard/handled)+ `GET /api/events/{id}`(详情带 brief)+ 证据图 `GET /img/{filename}` |
| **工位**(工位记录 / 课后验收) | `GET /api/records`、`GET /api/acceptance`、`GET /api/stations/{id}`(聚合) |
| **报告** | `GET /api/reports` → `GET /api/reports/{id}`(Markdown) |
| **操作**(新) | `POST /api/commands`(下发动作);**寻找物品**用 `GET /api/assets` 查位置 |
| **历史**(新) | 复用已加载的 events,客户端筛"已处理且 30 天内",纯前端,无新接口 |

写操作(处理告警 / 操作命令)带 `Authorization: Bearer <APP_INGEST_TOKEN>`。

## 2. 最近 App 改动(本轮)
1. **工位记录 / 课后验收 → 按「日期 + 时间段」分组**:同一天里相邻条目时间差 ≤ 30 分钟归为一个"时间段(会话)",一天可多段。**纯前端,不需要你改**;但展示效果取决于你 `records`/`acceptance` 的时间分布(见 §3.2)。
2. **新增「操作」Tab**:从 App 主动下发命令到 `POST /api/commands`(就是你已按 `BACKEND_PROMPT_command_api.md` 实现的接口 ✓)。App 会发的命令 `type`/`params`:
   - `inspection_round` `{}`
   - `recheck_station` `{station_id}`
   - `acceptance` `{station_id}` 或 `{}`(全部)
   - `find_item` `{asset_id, name, mode:"navigate"|"laser"}`
   - `voice_prompt` `{station_id?, text}`
   - `laser_point` `{station_id}`(或 `{location}`)
   - `generate_report` `{report_type}`(枚举同 API_SPEC §3)
   **请确认你的 `POST /api/commands` 接受这些 `type` 与 `params` 字段名**(如不一致请告诉我,我改 App 或你对齐)。
3. **历史 Tab**:已处理告警从「告警」移到「历史」;长按可"删除(本地隐藏)"或"标记为未处理(移回告警)",均为 App 本地行为,不触后端。

## 3. 已验证 + 请你配合

### 3.1 已联调验证通过(对你运行中的 :8000)
- ✅ `GET /api/health`、`/api/events`(列表/详情)、`/api/reports`、`/api/assets`、`/api/records`、`/api/acceptance` 字段与 App 模型对齐。
- ✅ SSE `text/event-stream` 帧解析、CORS `*`。
- ✅ **命令通道已通**:带 token `POST /api/commands` 返回 201 `{command_id,...,status:"queued"}`;`GET /api/commands` 能看到记录与机器人回执(如 `laser_point` → `status:done, result:"激光已指向 desk-03(...)"`)。👍

### 3.2 请你配合的几件事
1. **保持后端运行**:`uvicorn ... --host 0.0.0.0 --port 8000`(已在跑)。手机同热点连 `http://<Mac-IP>:8000`。
2. **写接口需要 token**:`POST /api/commands` 和 `POST /api/events/{id}/handle` 现在不带 token 返回 401。**这没问题**——用户会在 App「设置」页填入 token(取自 `~/.app_ingest_token` / 你启动时的 `APP_INGEST_TOKEN`)。请确认该 token 当前有效、未变。
3. **种子数据时间分布(为看清新分组,建议优化)**:
   - 当前 `records` 的 `entered_at` 落在 **2024-06-19**(年份偏旧),而 `acceptance` 的 `received_at` 在 2026-06-20 —— App 会把工位记录归到"2024年"、验收归到"今天",看起来割裂。
   - 建议把种子的 `records`/`acceptance` 时间改成**最近几天 + 每天 2~3 个时间段**(同段内几条间隔 < 30 分钟,段与段间隔 > 30 分钟),这样「按日期+时间段」分组能演示出"多日期、日内多段"的效果。
4. **命令回执继续回流**:`GET /api/commands` 的 `status` 从 queued→sent→done、带 `result` 文本(你已实现),App 后续可展示;本轮 App 先做下发+提示,回执查看可下一轮加。

## 4. 联调检查清单(用户在 App 上逐项点)
前置:App「设置」填 `http://<Mac-IP>:8000` + token,保存并测试连接(状态点变绿)。
- [ ] **告警**:列表加载;`sim_feed` 推送时新告警实时进列表、critical 弹横幅;点开看 brief + 证据图;「处理」(带 token)成功 → 该条移入「历史」。
- [ ] **工位**:工位记录 / 课后验收 按日期大标题 + 时间段小标题分组;点条目进聚合详情。
- [ ] **报告**:列表 → 详情 Markdown 正常。
- [ ] **操作**:发起综合巡检 / 到点复核 / 验收 / 语音 / 激光 / 生成报告 → SnackBar "已下发(cmd-...)";`GET /api/commands` 能看到新命令(未填 token 时 App 提示"去设置填 token")。
- [ ] **操作→寻找物品**:搜设备/耗材出位置;点"导航带路 / 激光指示"→ 下发 `find_item` 命令。
- [ ] **历史**:已处理告警在此;长按删除/移回正常。

## 5. 给我(App 端)反馈
若发现:命令 `type`/`params` 字段名不一致、某接口字段缺失、SSE 帧格式差异、token 机制变化——直接说,我改 App。契约外的新增仍走 `INTEGRATION.md`。
