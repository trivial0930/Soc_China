# 前端任务:遥控驾驶页(虚拟摇杆 + 雷达安全状态)

## 背景
这是巡检机器人的控制 App(Flutter `app/mobile`,另有 PWA `app/web`)。现有页面:实时告警/工位/报告/操作/资产/设置。
设置页已有**后端 URL + Bearer token**(shared_preferences)。

现在加一个**"遥控"页**:用户用虚拟摇杆开车,App 把速度 ~10Hz 发给后端;后端存"最新速度",
机器人(RDK)10Hz 拉取并在本地用**雷达做避障**(前方有障碍会自动减速/停)。App 还要显示雷达安全状态。

> 安全模型:遥控走网络(可有延迟),避障在机器人本地实时跑。**App 这端的关键职责是 deadman**——
> 一旦松手/离页/断触/切后台,**立刻发零速度**,绝不能让车"卡着上一个速度"继续跑。

## 后端契约(已定,后端 agent 同步实现;字段名/类型照此对接)
- `POST /api/robot/teleop`(需 `Authorization: Bearer <token>`)
  body:`{"vx": float, "vy": float, "wz": float}`(vx/vy m/s,wz rad/s)。后端只存最新一条。
- `GET /api/robot/teleop/status`(读,无需鉴权)
  返回:`{"state": "clear"|"slow"|"blocked"|"unknown", "front_dist_m": float|null, "age_ms": float}`

## 速度范围(必须夹在此范围内,与底盘限速一致)
- 前进/后退 `vx ∈ [-0.4, 0.4]` m/s
- 转向 `wz ∈ [-1.5, 1.5]` rad/s
- 横移 `vy ∈ [-0.4, 0.4]` m/s —— **可选,默认关闭或弱**(麦轮地面横移很弱,先不主推;留开关)

## 交互设计
- **主摇杆**:上下 → vx(前进/后退),左右 → wz(左转/右转)。
- (可选)**横移开关 + 第二控件**:开启后 左右 → vy。默认关。
- **发送**:手指按住并移动时,以 **~10Hz** `POST /api/robot/teleop` 当前 {vx,vy,wz}。
- **deadman(最重要)**:松手、离开本页、App 进入后台、触摸取消 → **立即** `POST {vx:0,vy:0,wz:0}`(并停止 10Hz 循环)。
- **STOP 急停按钮**:大按钮,点一下立即发零并把摇杆归中。
- **安全状态条**:~3Hz 轮询 `GET /api/robot/teleop/status`,显示:
  - `clear` 绿色、`slow` 黄色、`blocked` 红色、`unknown`/age 过大 灰色;
  - 同时显示 `front_dist_m`(前方最近障碍距离,m;null 显示 "—")。
  - blocked 时给明显提示(如红色"前方受阻,已自动停")。

## 实现要点
- 复用设置页的 backend URL + token;写请求加 `Authorization: Bearer <token>`,Content-Type JSON。
- 10Hz 发送用定时器;注意节流与合并(只发最新值)。网络失败不阻塞 UI(忽略单次失败,继续下个 tick)。
- 沿用 App 现有架构/HTTP 封装/主题;新加一个 Tab 或入口页。
- PWA(`app/web`)如同源同理可加(可选,优先 Flutter)。
- 遵循 `app/INTEGRATION.md` 与 `app/API_SPEC.md`(契约优先)。

## 交付
1. Flutter `app/mobile`:新增"遥控"页(虚拟摇杆 + STOP + 安全状态条),接入上述两个端点。
2. 处理好所有 deadman 场景(松手/离页/后台/断触 → 发零)。
3. 加最小 widget/单测(摇杆值映射到速度范围;松手回零)。
4. 自测:连后端,推摇杆 → `GET /api/robot/teleop` 后端能看到非零;松手 → 立即变零;status 条随后端 `/api/robot/teleop/status` 变色。

## 验收标准
- 摇杆驾驶手感顺(10Hz),速度严格夹在范围内。
- **deadman 可靠**:任何中断都立即发零(这是安全底线)。
- 安全状态条正确反映 clear/slow/blocked + 距离。
