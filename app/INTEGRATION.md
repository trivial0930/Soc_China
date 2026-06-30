# 前后端对接清单(INTEGRATION）

> 前端(演示 PWA,`app/web/`)与后端(`app/backend/`)由两个 agent 并行开发。
> **唯一数据契约是 `app/API_SPEC.md`**;本文件只记录契约之外、需要双方对齐的**集成点**。
> 谁改了集成约定就更新这里。前端不单方面改 `API_SPEC.md`,有契约变更需求写在末尾"待后端确认"。

---

## 前端对后端的请求(请后端 agent 落实)

### 1. 同源托管静态 PWA(最关键)
生产演示时,后端 `server.py` 直接同源托管前端,使手机访问 `http://<Mac-IP>:8000/` 即得 App(契约 §2:"演示 PWA 与后端同源无需 CORS")。请在 FastAPI 里:
- `GET /` → 返回 `app/web/index.html`
- 静态挂载 `app/web/` 下的 `/css`、`/js`、`/icons`、`/manifest.json`、`/sw.js`(`Content-Type` 正确;`sw.js` 用 `application/javascript`)
- **API 路由优先于静态**:`/api/*`、`/events/*`、`/img/*` 必须先于静态 catch-all 匹配,不能被前端的 `index.html` 兜底吞掉。

> 参考:`app.mount("/", StaticFiles(directory="app/web", html=True), name="web")` 放在所有 `/api`、`/events`、`/img` 路由**之后**注册即可。

### 2. 读接口保留 CORS `*`(契约 §2 已承诺)
前端跨源开发时(PWA 跑 `:8080`,后端 `:8000`)需要 `Access-Control-Allow-Origin: *`。
- 所有 GET 读接口 + `/img/*` + **SSE `/events/stream`** 都要带 CORS 头(`CORSMiddleware` 即可覆盖)。
- 写接口(handle、assets POST/PUT)允许带 `Authorization` 头(CORS `allow_headers` 含 `Authorization`、`Content-Type`)。

### 3. 健康检查
`GET /api/health` → `{"status":"ok","version":"v1","time":"..."}`。请确保**无需 token、带 CORS**。
（注:当前前端的连接状态点实际由 **SSE 连上/断开** 驱动,不依赖此接口;health 仍建议保留供自检。）

### 4. 种子图片文件名要能被 `/img/{filename}` 取到
前端按契约示例拼图:`Event.image`、`WorkstationRecord.snapshots[]` 里的文件名直接拼 `/{base}/img/{filename}`。
- 请保证 `seed.py` 写入 DB 的 `image`/`snapshots` 文件名与 `app/data/seed/evidence/`(或运行时图片目录)里**实际文件名一致**。
- 无图时 `image` 用 `""`、`snapshots` 用 `[]`(前端按此显示占位,不会发 404 请求)。

### 5. SSE 帧格式严格按契约 §5
前端用原生 `EventSource` 订阅 `GET /events/stream`,监听三种事件名:
```
event: hazard      data: {"type":"event","payload": { …Event(同 §3.1,尽量带 brief) … }}
event: handled     data: {"type":"handled","payload": {"event_id":"…","handled":true,"handled_at":"…","handled_note":"…"}}
event: ping        data: {}
```
- `data:` 必须是**单行 JSON**(SSE 规范:`data:` 行不能含裸换行;多行会被拼接)。
- `hazard` 既用于**新告警**也用于**告警内容更新**;前端按 `payload.event_id` 去重/替换。
- `ping` 心跳建议 15~30s 一次保活;前端忽略。

### 6. 轮询降级依赖(SSE 不可用时)
前端降级用 `GET /api/events?since=<ISO>&handled=false` 每 ~7s 拉新。请确保 `since` 按 `timestamp >=` 过滤(与 store.py 现有实现一致即可)。

---

## 前端这边的约定(供后端 agent 知悉)
- 前端**只写 `app/web/*`** + 本文件;**不碰** `app/backend/*`、`app/data/*`、`API_SPEC.md`。
- 前端默认走**相对 URL**(同源);设置弹窗可填绝对地址用于跨源调试。
- 前端自带 **Mock 模式**(`app/web/js/mock.js`),后端没起也能独立开发/演示;联调时关掉。
- 写操作(handle / assets)带 `Authorization: Bearer <token>`,token 由用户在设置弹窗填入。

---

## 正式手机 App(app/mobile,Flutter)— 进展与联调

> 由前端 agent 开发,独立工程 `app/mobile/`(Flutter 3.44 / Dart 3.12)。**不改 app/web、app/backend**。
> 技术栈:Flutter 跨平台(本机出 Android;iOS 待装 Xcode 的机器)。状态管理 ChangeNotifier(无 provider)。依赖:http、shared_preferences、intl、flutter_markdown。

**已实现(覆盖首期三屏 + 物资)**
- ① 实时告警:`GET /api/events` 初始列表 + `GET /events/stream` SSE(手动解析 event/data 帧,hazard/handled,ping 忽略)+ 指数退避重连 + **断线轮询降级**(`?since=&handled=false`);严重度配色;证据图 `/img/{filename}`(懒加载+占位);**critical 实时横幅 + 震动**;处理 `POST /api/events/{id}/handle`(带 `Authorization: Bearer`,token 可空)。
- ② 工位/验收:`/api/records`、`/api/acceptance` 双段 + `/api/stations/{id}` 聚合详情;快照画廊、verdict 徽章、问题清单。
- ③ 报告:`/api/reports` → `/api/reports/{id}`,flutter_markdown 渲染 `body_markdown`;report_type 中文化。
- ④ 物资:`/api/assets?name=&category=`,显示 `location_text`。
- ⑤ 历史(纯客户端,后端无需配合):已处理告警从「告警」移入「历史」单行紧凑列表(时间·严重度·内容省略号);单击看详情,长按可**删除(本地隐藏)**或**标记为未处理(移回告警)**;`handled_at` 超 **30 天**自动不显示。删除/移回的 id 用 shared_preferences 持久化,**仅 App 内隐藏,后端数据不动**(API_SPEC 无删除/反处理接口,无需新增)。
- 设置页:**服务器地址 + token 可配置**(shared_preferences 持久化),health 自检;地址自动补 `http://`、去尾斜杠。
- `finalSeverity = brief.confirmed_severity || severity`(§3.1 注),筛选/角标/通知全局统一。
- Android:已开 `INTERNET` 权限 + `usesCleartextTraffic`(后端为 http://,否则连不上)。

**已对运行中的后端联调验证(localhost:8000)**
- [x] `/api/health` → `{status,version,time}`,带 CORS `*`
- [x] `/api/events`(列表无 brief)、`/api/events/{id}`(含 brief,可 null)字段与模型逐一对齐
- [x] `/api/reports`(列表无 body_markdown)、`/api/assets`(含 location_text)、`/api/records`(entered_at unix float / left_at null)对齐
- [x] SSE `text/event-stream`,`event: ping`/`data: {}` 帧解析正确(hazard/handled 同构)
- [x] 读接口 CORS `access-control-allow-origin: *`(跨源开发 OK)
- [x] 写接口当前开放(未设 APP_INGEST_TOKEN,handle 无需 token;App 配了 token 也会带)
- [x] `flutter analyze` 零问题;`flutter test` 6/6 通过
- [x] **Android debug APK 构建成功** → `app/mobile/build/app/outputs/flutter-apk/app-debug.apk`(143MB,debug 全 ABI)
- [ ] 真机/模拟器实跑连后端(可选,下一步):`adb install` 后设置页填 `http://10.0.2.2:8000`(模拟器访问宿主)

**国内网络构建要点(Soc_China 在墙内,已踩平)**
- `dl.google.com` 被墙 → Gradle/Maven 依赖改走阿里云镜像(已写入 `app/mobile/android/settings.gradle.kts`,**随工程提交**)。
- NDK/CMake 是 **Android SDK 组件**,sdkmanager 仍从 `dl.google.com` 拉,镜像覆盖不到 → 走 **Clash 代理 127.0.0.1:7897**(Java 工具不读 env 代理,需 `~/.gradle/gradle.properties` 写 `systemProp.*.proxy*`;sdkmanager 需 JDK17+,用 Android Studio JBR21 + `JAVA_TOOL_OPTIONS` 代理)。
- 已装:NDK `28.2.13676358` + CMake `3.22.1`。这些是**本机环境配置**(`~/.gradle`、Android SDK),不入库。

> 提示:Mac IP 实测会变(192.168.128.100 → 192.168.5.41),App 地址可配置正为此;模拟器连本机后端用 `http://10.0.2.2:8000`。

## 待后端确认(契约外需求,如有则在此登记)
- **【命令下行通道 / Command API】** App 已新增「操作」Tab,需要把用户操作(发起巡检/到点复核/课后验收/寻找物品导航·激光/语音提醒/激光指示/生成报告)下发给机器人。当前系统纯单向(只上行无下行),需后端新增命令队列 + `POST /api/commands` + `GET /api/commands[/{id}]` + 机器人轮询通道(`GET /api/robot/commands/pending`、`POST .../{id}/ack|result`),机器人 agent 加命令接收节点。**完整任务说明见 [`BACKEND_PROMPT_command_api.md`](BACKEND_PROMPT_command_api.md)**。前端已按该契约实现(`command_client.dart`),后端未实现时 App 收 404 会优雅提示"待支持",不阻塞。
- (其余)正式 App 其它功能完全按 API_SPEC v1 即可,无需契约新增字段。

---

## 前端只读审查发现(2026-06-19,交前端 agent 评估修复)

> 已逐条对照 `API_SPEC.md` 与现有 `app/web/*` 源码核对,剔除误报。按优先级排序。
> 整体评价:四屏 + SSE + Markdown + SW + manifest 完整,架构(IIFE 全局 `API`/`Alerts`…、同源相对 URL)自洽可用。以下为可改进项,非阻塞。

### P1 — 契约符合性(建议修)
- [ ] **handle 写接口缺 `Authorization: Bearer`**。`js/alerts.js → handle()` 调 `API.post('/api/events/{id}/handle')`,但 `js/api.js` 的 `post()` 不带任何鉴权头;契约 §4.1 标明 handle **需 token**。若后端对写接口校验 token,会 401。建议:`post()` 增加可选 `Authorization` 头 + 一处 token 输入/存储(localStorage 即可)。
  - 关联:若演示阶段后端对写接口放开(不校验),则暂不影响,但上线前必补。

### P2 — 一致性 / 健壮性(可选)
- [ ] **L2 `confirmed_severity` 在筛选/角标/通知处漏读 `brief`**。`card()` 用 `e.confirmed_severity || e.brief?.confirmed_severity || e.severity`(✓);但 `matches()`、`updateBadge()`、`onLive()` 只用 `e.confirmed_severity || e.severity` —— 而 Event **顶层并无 `confirmed_severity`**(它在 `brief` 内,§3.1),故这几处实际只吃 `severity`,拿不到 L2 纠正后的严重度。建议抽一个 `finalSev(e)=e.brief?.confirmed_severity || e.severity` 统一调用(注意:列表接口 §4 不带 brief,SSE hazard 可能带 brief —— 带时才有纠正值)。
- [ ] **顶层 `e.confirmed_severity` 是契约外字段**:多处 `e.confirmed_severity || …` 的首项恒为 `undefined`(死分支),清理或统一到 `finalSev()` 即可。

### P3 — 体验 / 收尾(锦上添花)
- [ ] **服务器地址不可配置**:`js/api.js` `base=""` 仅同源。符合"同源托管"决策、演示够用;若将来要原生 App / 跨源调试,需加可配置地址(§8 建议项)。
- [ ] **SSE 无显式轮询降级**:现依赖 `EventSource` 自带重连(可接受);§5 提到可退化为 `GET /api/events?since=&handled=false` 轮询,弱网演示可考虑补。
- [ ] **`report_type` 直显英文枚举**(如 `post_class_acceptance`):`js/reports.js` 列表直接渲染原值,建议映射中文(课后验收/多图综合/不确定追问/周期汇总)。
- [ ] **Service Worker 未缓存 icons**:`service-worker.js` 的 `ASSETS` 缺 `icons/*`,离线时图标可能丢(壳本身可离线,影响小)。
- [ ] **SW 的 `/api//img//events/` 前缀判断为绝对路径**:仅在后端**根路径**托管时成立(当前决策即根路径,OK);若改为子路径托管需同步调整。

> 以上均为前端侧改进,**后端 agent 不需处理**;列在此处仅为同步可见。前端 agent 认领后可逐条勾掉。

## 联调检查表
- [ ] `GET /` 返回 PWA,`/css /js /icons` 可加载
- [ ] `/api/health` 带 CORS、无需 token,前端状态点变绿
- [ ] 三屏数据:`/api/events`、`/api/records`、`/api/acceptance`、`/api/stations/{id}`、`/api/reports`(+`/{id}`)、`/api/assets`
- [ ] `/img/{filename}` 能取到种子证据图
- [ ] SSE `hazard` 新告警实时进列表,`critical` 触发横幅;`handled` 更新状态
- [ ] handle 写接口带 token 成功(401 提示符合预期)
