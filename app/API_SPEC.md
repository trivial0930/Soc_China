# 实验室巡检机器人 · 管理端 App 工程文档 / API 契约

> 面向**正式手机 App 开发者**(你)。本文档是后端 API 的**唯一契约**——我(后端 + 演示 PWA)和你(正式 App)都按这份实现,可并行开发。
> 版本 `v1`。字段名/枚举值以本文档为准,变更会在末尾 changelog 记录。

---

## 1. 系统概览

```
RDK 机器人(已有数据)        Mac/边缘机后端(本文档)            你的 App / 演示 PWA
┌──────────────┐  POST    ┌──────────────────────────┐  HTTP + SSE  ┌──────────┐
│ uplink 节点   │ ───────► │ FastAPI                   │ ◄─────────► │  客户端   │
│ 订阅ROS话题   │  JSON+图  │ SQLite + 图片目录 + SSE推送 │  (同热点)    │          │
└──────────────┘          └──────────────────────────┘             └──────────┘
```
- 机器人把**安全告警/认知简报/工位记录/课后验收/巡检报告**(+证据图)推到后端;后端落库 + 实时推送给客户端。
- 你的 App = **管理端**:看实时告警(含证据图)、工位记录、课后验收、巡检报告,查物资位置,做人工判断/处理。
- **后端跑在 Mac/边缘机**(macOS,Python FastAPI),**不在机器人板子上**。

---

## 2. 连接与基础约定

| 项 | 值 |
|---|---|
| **Base URL** | `http://<后端IP>:8000`(演示时后端跑 Mac,`<后端IP>` = Mac 在热点下的局域网 IP,如 `192.168.x.x`)|
| **协议** | HTTP/1.1,JSON(`Content-Type: application/json; charset=utf-8`);图片走二进制 |
| **实时推送** | Server-Sent Events(SSE),端点 `GET /events/stream` |
| **编码** | 全程 UTF-8;中文不转义 |
| **时间** | 事件时间 `timestamp` 为 **ISO8601 带时区**(如 `2026-06-19T20:30:00+08:00`);工位记录的 `entered_at/left_at` 为 **Unix 秒(float)**;后端落库时间 `received_at` 为 ISO8601 |
| **分页** | `?limit=&offset=`(默认 limit=50,offset=0);返回 `{items:[...], total, limit, offset}` |
| **CORS** | 后端开 `Access-Control-Allow-Origin: *`(读接口),便于原生 App / 跨域调试。演示 PWA 与后端同源无需 CORS |
| **健康检查** | `GET /api/health` → `{"status":"ok","version":"v1","time":"..."}` |

**鉴权**:读接口(GET)演示期**开放、无需 token**。写接口(POST/PUT,主要给 uplink + 管理动作)需请求头
`Authorization: Bearer <APP_INGEST_TOKEN>`(后端启动时 env 配置)。你的 App 若只读则无需 token;若要做"标记处理/编辑物资"等写操作,问我要 token。

> **发现后端 IP**:演示时我会把 Mac IP 告诉你(或 App 里做个"服务器地址"输入框)。后端绑 `0.0.0.0:8000`,手机连同一热点即可访问。

---

## 3. 数据模型(实体 + 枚举)

### 枚举值(固定,App 端按这些做配色/文案)
- `severity`: `"info"` | `"warning"` | `"critical"`(信息/警告/严重)
- `event_type`: `"thermal_risk"`(热隐患) | `"desk_messy"`(桌面待整理) | `"device_missing"`(设备缺失) | `"estop"`(急停) | `"fault"`(故障)
- `source`: `"camera"` | `"thermal"` | `"stm32"` | `"manual"` | `"mock"`
- `verdict`(课后验收/报告结论): `"合格"` | `"需整理"` | `"存在安全隐患"`
- `acceptance_hint`(工位记录里的验收提示): `""` | `"合格"` | `"需整理"` | `"存在安全隐患"`
- `report_type`: `"post_class_acceptance"`(课后验收) | `"multi_image_synthesis"`(多图综合) | `"uncertain_followup"`(不确定追问) | `"periodic_summary"`(周期汇总)
- `actions`(建议动作,字符串数组): 取值 `"voice"` | `"recheck"` | `"aim"` | `"log"`

### 3.1 Event(安全告警事件)
```jsonc
{
  "event_id": "20260619-203000-0001",   // 唯一ID
  "timestamp": "2026-06-19T20:30:00+08:00",
  "received_at": "2026-06-19T20:30:02+08:00", // 后端收到时间
  "station_id": "desk-03",
  "source": "thermal",
  "event_type": "thermal_risk",
  "severity": "warning",
  "confidence": 0.85,                    // 0~1
  "summary": "3号工位桌面右侧疑似存在未断电电烙铁",
  "image": "20260619-203000-0001_warning.jpg", // 证据图文件名,拼 /img/{image} 取图;无图为 ""
  "action": { "robot_task": "", "voice_prompt": "", "reported_to_admin": false },
  "handled": false,                      // 管理员是否已处理
  "handled_at": null,                    // 处理时间(ISO 或 null)
  "handled_note": "",                    // 处理备注
  "brief": {                             // L2 本地认知简报(可能为 null,异步到达)
    "explanation": "3号工位桌面右侧疑似存在未断电电烙铁,当前温度较高,建议复核并提醒学生处理。",
    "confirmed_severity": "warning",     // L2 复核后的严重度(可能纠正初筛)
    "actions": ["voice", "recheck", "log"],
    "escalate_to_cloud": false
  }
}
```
> **注**:列表接口里 `brief` 可能省略(只在详情 `GET /api/events/{id}` 保证带);App 用 `confirmed_severity || severity` 显示最终严重度。

### 3.2 WorkstationRecord(工位占用记录)
```jsonc
{
  "id": 12,
  "station_id": "desk-03",
  "entered_at": 1718800000.0,            // Unix 秒
  "left_at": 1718800300.0,               // 或 null(仍在占用)
  "snapshots": ["desk-03_arrive_1718800000.jpg", "desk-03_leave_1718800300.jpg"], // 文件名数组,拼 /img/
  "note": "复核温度并提醒在场人员处理(严重度 warning)。", // 关联的L2说明,可空
  "acceptance_hint": "需整理",           // 见枚举,可空 ""
  "received_at": "2026-06-19T20:35:00+08:00"
}
```

### 3.3 Acceptance(课后桌面验收)
```jsonc
{
  "id": 5,
  "station_id": "desk-03",
  "verdict": "需整理",
  "severity": "warning",
  "problems": ["导线杂乱拖拽", "仪器设备未归位"], // 问题清单
  "report_id": 8,                        // 关联的报告id,可 null
  "received_at": "2026-06-19T21:00:00+08:00"
}
```

### 3.4 Report(巡检报告)
```jsonc
{
  "id": 8,
  "title": "课后工位验收报告",
  "report_type": "post_class_acceptance",
  "verdict": "需整理",
  "severity": "warning",
  "event_ids": ["20260619-203000-0001"],
  "body_markdown": "# 课后工位验收报告\n\n**总体结论**: 需整理...", // 完整 Markdown 正文
  "created_at": "2026-06-19T21:00:00+08:00",
  "received_at": "2026-06-19T21:00:01+08:00"
}
```
> 列表接口省略 `body_markdown`(正文较大);详情 `GET /api/reports/{id}` 才带。App 用 Markdown 渲染库显示正文。

### 3.5 Asset(物资定位)
```jsonc
{
  "id": 3,
  "name": "示波器",
  "category": "large",        // "large"=大型设备 | "small"=小型耗材
  // large 用这两个:
  "station_id": "desk-03",
  "area": "A区",
  // small 用这三个:
  "cabinet": "", "drawer": "", "box": "",
  "quantity": 1,
  "note": "Tektronix",
  "location_text": "工位 desk-03 / A区", // 后端格式化好的位置串,App 直接显示
  "updated_at": "2026-06-19T09:00:00+08:00"
}
```

---

## 4. REST API

### 4.1 安全告警(功能①)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/events` | 列表。query: `station, severity, type, since(ISO), until(ISO), handled(true/false), limit, offset`。返回 `{items:[Event(无brief)], total, limit, offset}` |
| GET | `/api/events/{event_id}` | 单条 Event(**带 brief**) |
| POST | `/api/events/{event_id}/handle` | 标记已处理。body `{"note":"已断电并提醒"}`。需 token。返回更新后的 Event |

**示例**
```bash
curl "http://192.168.1.10:8000/api/events?severity=critical&handled=false&limit=20"
curl "http://192.168.1.10:8000/api/events/20260619-203000-0001"
curl -X POST "http://192.168.1.10:8000/api/events/20260619-203000-0001/handle" \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"note":"已断电并提醒学生"}'
```

### 4.2 工位记录 + 课后验收(功能②)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/records` | 工位记录列表。query: `station, since, until, limit, offset` |
| GET | `/api/acceptance` | 验收列表。query: `station, verdict, since, limit, offset` |
| GET | `/api/stations/{station_id}` | **工位聚合**:该工位的最近记录 + 最近验收 + 近期事件,一次取齐(App 工位详情页用)。返回 `{station_id, latest_record, latest_acceptance, recent_events:[...]}` |

### 4.3 巡检报告(功能③)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/reports` | 列表(**不含 body_markdown**)。query: `type, verdict, limit, offset` |
| GET | `/api/reports/{id}` | 单份报告(**含 body_markdown**) |

### 4.4 物资定位(数据层已建,前端首期可选)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/assets` | 查询。query: `name(模糊), category(large/small), station`。返回 `{items:[Asset], total}` |
| POST | `/api/assets` | 新增(需 token) |
| PUT | `/api/assets/{id}` | 更新位置(需 token) |

### 4.5 图片
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/img/{filename}` | 取证据图/快照(二进制 jpg)。filename 来自 Event.image / WorkstationRecord.snapshots[]。例:`/img/20260619-203000-0001_warning.jpg` |

> 缩略图:首期不做服务端缩放,App 端自行约束显示尺寸。

---

## 5. 实时推送(SSE)— 功能①核心

端点:`GET /events/stream`(`Content-Type: text/event-stream`,长连接)。

后端每收到一条**新告警事件**(或事件被处理),推送一帧:
```
event: hazard
data: {"type":"event","payload": { ...Event(同3.1,可能含brief)... }}

event: handled
data: {"type":"handled","payload": {"event_id":"...","handled":true,"handled_at":"...","handled_note":"..."}}
```
- `event:` 行是 SSE 事件名(`hazard` 新告警 / `handled` 处理状态变更);`data:` 是 JSON。
- 还会周期发 `event: ping`(心跳,`data: {}`)保活,App 忽略即可。

**Web(PWA)订阅**:
```js
const es = new EventSource("/events/stream");
es.addEventListener("hazard", e => { const ev = JSON.parse(e.data).payload; showAlert(ev); });
```
**原生 App**:用各平台 SSE 客户端(iOS: 第三方 EventSource 库 / URLSession 手动按行解析;Android/Kotlin: OkHttp-EventSource);或**退化用轮询** `GET /api/events?since=<上次时间>&handled=false` 每 5~10s 拉一次(若不想接 SSE)。

---

## 6. 首期功能 → 接口映射(你 App 三屏直接照做)

| App 屏 | 拉取 | 实时 | 动作 |
|---|---|---|---|
| **① 告警** | `GET /api/events`(初始列表) | `GET /events/stream`(SSE 推新告警);critical 弹通知 | `POST /api/events/{id}/handle` |
| **② 工位/验收** | `GET /api/records`、`GET /api/acceptance`,或 `GET /api/stations/{id}` 聚合 | — | 人工查看判断(可加备注:复用 handle 或后续接口) |
| **③ 报告** | `GET /api/reports` → 点开 `GET /api/reports/{id}` | — | Markdown 渲染 |
| 图片 | 所有 `image`/`snapshots[]` → `GET /img/{filename}` | — | — |

---

## 7. 本地对接 / 联调(无机器人也能开发)

后端支持**种子数据 + 模拟实时**,你不用等机器人就能开发 App:
```bash
# 我这边(后端):
cd app/backend
python -m app.backend.seed                 # 灌入示例数据(events/records/acceptance/reports/assets + 示例图)
uvicorn app.backend.server:app --host 0.0.0.0 --port 8000
python -m app.backend.sim_feed             # (可选)定时推模拟告警,演示 SSE
```
- 起来后 `http://<Mac-IP>:8000` 即有种子数据;`GET /api/health` 自检。
- 你 App 指向这个地址即可开发全部三屏 + SSE。
- 我会把 `app/data/seed/*` 的示例数据和示例图一起提交,字段都按本文档。

---

## 8. 给 App 端的实现建议
- **服务器地址**做成可配置(输入框/扫码),别写死——演示现场 Mac IP 会变。
- **严重度配色**:critical=红、warning=橙、info=灰/蓝;`verdict`:合格=绿、需整理=橙、存在安全隐患=红。
- **离线/断连**:SSE 断了自动重连(EventSource 自带;原生需自己重连);列表接口做下拉刷新。
- **图片**懒加载 + 失败占位。
- **时间**:`timestamp`/`received_at` 是 ISO 带时区直接 parse;`entered_at/left_at` 是 Unix 秒需 ×1000 转毫秒。
- **只读优先**:首期 App 只读三屏 + 处理按钮即可覆盖竞赛演示。

---

## 9. 状态码约定
- `200` 成功;`201` 创建成功;`204` 无内容(handle 等);
- `400` 参数错;`401` 缺/错 token(写接口);`404` 资源不存在;`422` body 校验失败;`500` 服务端错。
- 错误体:`{"detail":"错误说明"}`。

---

## Changelog
- **v1 (2026-06-19)**:首版契约。events/records/acceptance/reports/assets + SSE + 图片 + handle。
  待定/后续:工位记录加备注的专用写接口、缩略图、报告 PDF 导出、鉴权细化、设备位置由机器人自动更新的写流程。

> 有任何字段需要调整(比如你 App 需要额外字段),直接跟我说,我改后端 + 更新本文档同步给你。
