# 后端任务:低延迟遥控速度通道(teleop)

## 背景
这是巡检机器人管理系统的 FastAPI 后端(`app/backend/server.py`,SQLite,SSE,Bearer 写鉴权)。
现有 App→机器人下行是 **2 秒轮询的命令队列**(`/api/commands` + `/api/robot/commands/pending`),
适合"递检/语音播报"这类离散命令,但**延迟太大,不能用于实时遥控驾驶**。

现在要给 App 加"遥控开车 + 雷达避障"功能。RDK 端已实现:一个节点 **10Hz 轮询**后端拉"最新速度",
另一个节点把**雷达安全状态**回传后端给 App 显示。你的任务是加这条**低延迟速度通道**(与命令队列**完全分开**,不要动 `/api/commands`)。

## 要新增的端点(契约,RDK 已按此实现,字段名/类型必须一致)

### 1. `POST /api/robot/teleop` — App 设置最新速度(需 Bearer 写鉴权)
- 请求体 JSON:`{"vx": float, "vy": float, "wz": float}`(vx/vy 单位 m/s,wz rad/s)
- 行为:**只存"最新一条"**(覆盖式)+ 记录服务器接收时间戳。无需入库,模块级内存变量即可。
- 安全 clamp(收到后再夹一道):`vx,vy ∈ [-0.4, 0.4]`,`wz ∈ [-1.5, 1.5]`。
- 返回:`200 {"ok": true}`

### 2. `GET /api/robot/teleop` — RDK 拉最新速度(读,无需鉴权,和其他 GET 一致)
- 返回:`{"vx": float, "vy": float, "wz": float, "age_ms": float}`
  - `age_ms` = (now − 最近一次 POST 的时间)×1000;**从未设置过**则返回 vx=vy=wz=0 且 age_ms 给一个大值(如 1e9)。
- RDK 侧:`age_ms` 超阈值(默认 400ms)即视为失效→自动归零(deadman),所以你只要如实给 age_ms。

### 3. `POST /api/robot/teleop/status` — RDK 回传雷达安全状态(需 Bearer)
- 请求体 JSON:`{"state": str, "front_dist_m": float|null}`,state ∈ `"clear"|"slow"|"blocked"`。
- 行为:同样只存最新一条 + 时间戳(内存即可)。
- 返回:`200 {"ok": true}`

### 4. `GET /api/robot/teleop/status` — App 拉安全状态(读,无需鉴权)
- 返回:`{"state": str, "front_dist_m": float|null, "age_ms": float}`;从未上报则 `state:"unknown", front_dist_m:null, age_ms:大值`。

## 实现要点
- 用**模块级内存变量**存这两条"最新值 + 时间戳"(覆盖式,不需要 SQLite 表;掉电丢失无所谓)。FastAPI 单进程下直接全局变量即可,简单加个 dict/dataclass。
- 写端点(POST)复用现有 `require_token()` Bearer 依赖;读端点(GET)开放,与现有 `/api/events` 等一致。
- **不要改动** `/api/commands` 命令队列、ingest、SSE 等现有逻辑。
- 路由注册必须在静态文件 catch-all **之前**(见 `app/INTEGRATION.md`)。
- 时间戳用服务器单调/UTC 时间,age_ms 用毫秒浮点。

## 交付
1. 在 `app/backend/server.py` 加上述 4 个端点(+ 必要的内存 store,可放 `store.py` 或 server 内)。
2. 更新 `app/API_SPEC.md`:新增 "Teleop(低延迟遥控)" 小节,列出 4 个端点的请求/响应。
3. 加最小测试(沿用后端现有测试风格):POST teleop 后 GET 能取回且 age_ms 小;clamp 生效;status 往返。
4. 自测:`POST /api/robot/teleop {"vx":0.2,"vy":0,"wz":0}` 后立刻 `GET /api/robot/teleop` 应返回 vx≈0.2、age_ms 很小;等 1 秒再 GET,age_ms≈1000。

## 验收标准
- 4 个端点按契约工作,字段名/类型与上面**完全一致**(RDK 与 App 都按此对接)。
- 命令队列等现有功能不受影响,现有测试仍通过。
