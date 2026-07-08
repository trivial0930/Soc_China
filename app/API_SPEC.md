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

### 3.6 Command(App→机器人 命令下行)
```jsonc
{
  "command_id": "cmd-20260620-153000-0001",
  "type": "recheck_station",            // 见命令类型表(§4.6)
  "params": { "station_id": "desk-03" },// JSON 对象,各 type 必填项不同
  "status": "queued",                   // queued|sent|done|failed|canceled
  "issued_by": "app",
  "result": "",                         // 机器人回执文本,完成前为空
  "created_at": "2026-06-20T15:30:00+08:00",
  "updated_at": "2026-06-20T15:30:01+08:00"
}
```
状态机:`queued`(已下发)→ `sent`(机器人已接收)→ `done`/`failed`(执行回执);`canceled` 取消。

---

## 4. REST API

### 4.1 安全告警(功能①)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/events` | 列表。query: `station, severity, type, since(ISO), until(ISO), handled(true/false), limit, offset`。返回 `{items:[Event(无brief)], total, limit, offset}` |
| GET | `/api/events/{event_id}` | 单条 Event(**带 brief**) |
| POST | `/api/events/{event_id}/handle` | 标记已处理。body `{"note":"已断电并提醒"}`。需 token。返回更新后的 Event |

> **数据保留**:后端会自动删除「已处理且处理时间超过 30 天」的告警(连同其 brief)。未处理的告警永不自动删除。App 端无需特殊处理,只是历史已处理告警一个月后不再返回。保留天数由后端 `APP_RETENTION_DAYS` 配置(0=不删)。

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

### 4.6 命令下行(Command API,功能④「操作」)
App 下发命令 → 入队 → 机器人轮询拉取执行 → 回执。

**App 侧**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/commands` | 下发命令。**需 token**。body `{"type":"...","params":{...},"issued_by":"app"}`。校验通过 → **201** `Command(status:queued)`;非法 type / params 缺项 → 400;缺 token → 401 |
| GET | `/api/commands` | 列表。query `status,type,since,limit,offset` → `{items:[Command],total,limit,offset}`。读接口,免 token,带 CORS |
| GET | `/api/commands/{command_id}` | 单条命令状态/回执 |

**机器人侧**(均**需 token**)
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/robot/commands/pending` | 拉取 `status=queued` 命令(`?limit=`),FIFO,**不改状态** → `{items:[Command]}` |
| POST | `/api/robot/commands/{command_id}/ack` | 确认接收 → `status=sent` |
| POST | `/api/robot/commands/{command_id}/result` | 回执。body `{"status":"done"\|"failed","result":"..."}` → 更新状态+result |

**命令类型表**（`type` / 必填 `params`）
| `type` | `params` | 含义 |
|---|---|---|
| `inspection_round` | `{}` | 发起综合巡检 |
| `recheck_station` | `{"station_id":"desk-03"}` | 到指定工位复核(Nav2) |
| `acceptance` | `{"station_id":"desk-03"}` 或 `{}`(全部) | 课后验收 |
| `find_item` | `{"asset_id":3}` 或 `{"name":"示波器"}`,`"mode":"navigate"\|"laser"`(默认 navigate) | 寻找物品:导航带路 / 激光指示 |
| `voice_prompt` | `{"text":"请整理桌面","station_id":"desk-03"?}` | 语音播报 |
| `laser_point` | `{"station_id":"desk-03"}` 或 `{"location":"元件柜2/抽屉3/盒B"}` | 激光云台指示 |
| `generate_report` | `{"report_type":"periodic_summary"}`(默认 periodic_summary) | 触发生成报告 |
| `voice_control` | `{"enabled": true \| false}` | 远程开/关机器人语音监听:`false` 停止唤醒/录音/识别(释放算力),`true` 恢复待唤醒 |
| `set_volume` | `{"level": 0-100}` | 调节机器人**播报(TTS)音量**:`0`=静音,`100`=最响。整数百分比 |
| `set_mode` | `{"mode": "mapping"\|"normal"}` | 进/出**建图模式**:`mapping` 停语音栈→起建图栈;`normal` 反之恢复语音栈 |
| `save_map` | `{"name": "<slug>"?}` | 建图时**存图**(`name` 可省,默认 `lab_map`) |

> params 校验失败 → 400 `{"detail":"..."}`。`report_type` 取值见 §3 枚举。
> `voice_control` 的 `enabled` 必须为布尔(缺失或非布尔 → 400 `{"detail":"voice_control 需要布尔 params.enabled"}`)。
> `set_volume` 的 `level` 必须为 0-100 整数(缺失/越界/非整数 → 400 `{"detail":"set_volume 需要整数 params.level (0-100)"}`)。**App 侧建议做成音量滑块**(0-100),拖动即发命令;乐观更新即可。
> `set_mode`/`save_map` 后端**不做业务校验**(合法性由 RDK 判,非法 mode 机器人回 `failed`),只入队透传;命令 `result` 的中文文案(如「已进入建图模式」「建图栈启动失败(rc=1),已停在安全态」)原样存好供 App 显示。当前模式见 §4.8。

---

### 4.7 Teleop(低延迟遥控驾驶 + 雷达避障)

实时遥控**专用低延迟通道**,与 §4.6 命令队列**完全分开**(命令队列是 2s 轮询的离散命令,不适合开车)。后端只存"最新一条"(覆盖式、内存、掉电丢失无所谓)。

App 摇杆 10Hz `POST` 最新速度;RDK 一个节点 10Hz `GET` 拉速度驱动底盘(`age_ms` 超阈值即 deadman 归零),另一节点 `POST` 雷达安全状态;App `GET` 安全状态做 UI 显示。

| 方法 | 路径 | 鉴权 | 请求体 | 响应 |
|---|---|---|---|---|
| `POST` | `/api/robot/teleop` | Bearer | `{"vx":float,"vy":float,"wz":float}` | `{"ok":true}` |
| `GET` | `/api/robot/teleop` | 无 | — | `{"vx":float,"vy":float,"wz":float,"age_ms":float}` |
| `POST` | `/api/robot/teleop/status` | Bearer | `{"state":"clear"\|"slow"\|"blocked","front_dist_m":float\|null}` | `{"ok":true}` |
| `GET` | `/api/robot/teleop/status` | 无 | — | `{"state":str,"front_dist_m":float\|null,"age_ms":float}` |

- `vx,vy` 单位 m/s,`wz` rad/s。后端**收到后再 clamp 一道**:`vx,vy ∈ [-0.4,0.4]`、`wz ∈ [-1.5,1.5]`。
- `age_ms` = (now − 最近一次 POST)×1000。**从未设置**:`GET teleop` 返回 `vx=vy=wz=0` 且 `age_ms` 为大值(`1e9`);`GET teleop/status` 返回 `state:"unknown", front_dist_m:null, age_ms` 大值。
- **App 侧**:虚拟摇杆 → 10Hz `POST /api/robot/teleop`;轮询 `GET /api/robot/teleop/status` 显示避障状态(clear/slow/blocked + 前向距离),松手即发 `{0,0,0}` 停车。

---

### 4.8 机器人模式(建图模式状态)

进/出建图模式靠 §4.6 的 `set_mode`/`save_map` 命令;这里是**当前真实模式的心跳**——**事实源是 RDK 上报的 mode**,后端只存最新一条 + 接收时间戳(覆盖式、内存),不推断。

| 方法 | 路径 | 鉴权 | 请求体 | 响应 |
|---|---|---|---|---|
| `POST` | `/api/robot/mode` | Bearer(RDK 调) | `{"mode": str}` | `{"ok":true}` |
| `GET` | `/api/robot/mode` | 无(App 读) | — | `{"mode": str, "age_ms": float}` |

- `mode` 取值:`normal`(正常,语音在跑)、`switching`(切换中)、`mapping`(建图中)、`mapping_error`(进建图失败、已停在安全态);**从未上报**则 `mode:"unknown"` 且 `age_ms` 大值(`1e9`)。
- `age_ms` = (now − 最近一次 POST)×1000。RDK 每 ~2s 上报一次;**App 超过 ~6s 没更新即视为机器人离线**。
- **App 侧**:轮询 `GET /api/robot/mode` 显示当前模式 + 离线提示;建图开关发 `set_mode` 命令(乐观更新,真实状态以 mode 心跳为准),建图中显示「存图」按钮发 `save_map`。

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
- 命令状态变更也会推 `event: command`(`data:{"type":"command","payload":Command}`),App 可订阅实时看回执,或退化轮询 `GET /api/commands`。
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
- **v1.5 (2026-06-24)**:**建图模式**。命令类型表新增 `set_mode`(mapping/normal)、`save_map`(存图)——后端只白名单透传、不做业务校验(RDK 判合法性)。新增模式心跳端点 `POST/GET /api/robot/mode`(§4.8,RDK 上报真实 mode + age_ms,App 据此显示当前模式/离线)。
- **v1.4 (2026-06-24)**:新增 **Teleop 低延迟遥控通道**(§4.7):`POST/GET /api/robot/teleop`(速度,App↔RDK,最新值覆盖式+age_ms+后端 clamp)、`POST/GET /api/robot/teleop/status`(雷达安全状态)。与命令队列分开、内存存储,不动 `/api/commands`。
- **v1.3 (2026-06-24)**:命令类型表新增 `set_volume`(`params.level` 0-100 整数,调机器人 TTS 播报音量)。复用现有命令通道;机器人侧:command_receiver 把 level 写 `/root/.tts_volume`,常驻 TTS 服务读取并作为播放增益(USB 音响无 ALSA 音量控件,故走软件增益)。**App 侧待加音量滑块。**
- **v1.2 (2026-06-21)**:命令类型表新增 `voice_control`(`params.enabled` 布尔,App 远程开/关机器人端侧语音监听)。复用现有命令通道,不新增端点;机器人侧由 asr_node 响应开关。
- **v1.1 (2026-06-20)**:新增命令下行通道(功能④「操作」)。`Command` 实体(§3.6)+ App 侧 `POST/GET /api/commands(/{id})` + 机器人侧 `GET /api/robot/commands/pending`、`POST .../ack`、`POST .../result`(§4.6)+ SSE `event: command`。后端另加「已处理告警 / 报告超 30 天自动删除」(`APP_RETENTION_DAYS`,默认30)。
- **v1 (2026-06-19)**:首版契约。events/records/acceptance/reports/assets + SSE + 图片 + handle。
  待定/后续:工位记录加备注的专用写接口、缩略图、报告 PDF 导出、鉴权细化、设备位置由机器人自动更新的写流程。

> 有任何字段需要调整(比如你 App 需要额外字段),直接跟我说,我改后端 + 更新本文档同步给你。
