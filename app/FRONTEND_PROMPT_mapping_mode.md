# 前端 Prompt:建图模式开关 + 存图(app/mobile Flutter)

给前端 agent。目标:在 App 里加一个「建图模式」开关,打开后机器人自动腾资源 + 起建图栈,关闭后恢复语音栈;建图中露出遥控摇杆 + 一键存图。

## 链路(后端已就绪)
- 进/退建图:`POST /api/robot/commands`(Bearer)body `{"type":"set_mode","params":{"mode":"mapping"|"normal"}}`。
- 存图:`POST /api/robot/commands` body `{"type":"save_map","params":{"name":"<slug>"}}`(name 可省,默认 lab_map)。
- 看真实模式:`GET /api/robot/mode` → `{"mode":"normal|switching|mapping|mapping_error","age_ms":N}`。
- 命令执行结果:沿用现有命令结果拉取(status done/failed + result 中文文案),用来弹 toast。

## UI / 行为

### 建图模式开关(放设置页或遥控页顶部)
- 开关状态**以 `GET /api/robot/mode` 回报的真实 mode 为准**,不是开关的本地位置。轮询 `GET /api/robot/mode`(~2s)刷新。
- ON → 发 `set_mode:mapping`;OFF → 发 `set_mode:normal`。
- 模式态展示:
  - `normal`:开关关、正常。
  - `switching`:开关禁用 + 转圈「切换中…」(切换要十几秒,起建图栈+校验)。
  - `mapping`:开关开、绿色「建图中」。
  - `mapping_error`:红色错误条「进入建图失败,已停在安全态」+【重试】(再发 mapping)/【退出】(发 normal 恢复语音)两个按钮。
  - `age_ms` 过大(>~6s 没更新):灰显「机器人离线」,开关禁用。

### 建图中(mode==mapping)
- 露出**遥控页摇杆**(复用现有 teleop 遥控控件 + 安全状态条)开车绕图。
- 一个【存图】按钮:点击弹输入框填地图名(默认 `lab_map`,只允许字母数字/下划线/连字符,机器人侧也会净化),发 `save_map`;按结果弹 toast(「已存图:xxx」/「存图失败」)。

### 通用
- 所有写请求带 Bearer token(沿用现有鉴权)。
- 命令是幂等的:已在目标模式再发无害;若请求的模式和回报 mode 持续不一致(超过若干秒),可自动重发一次。
- 切换/存图的成功失败文案直接用命令 result 里的中文。

## 约束
- 不要在前端做模式合法性判断或本地推断 mode;一切以 RDK 回报为准。
- 建图模式是临时态:App 重启/重连后按 `GET /api/robot/mode` 还原当前真实状态(不要假设是 normal)。
- 别在 normal 模式下显示存图按钮(存图仅建图模式有效,机器人侧也会拒)。

## 验收
- 开关 ON → 显示 switching → 十几秒后变 mapping;摇杆可用、能开车。
- 存图 → toast 成功、机器人侧 `~/maps/<name>.pgm|.yaml` 生成。
- 开关 OFF → switching → normal,语音恢复。
- 拔网/机器人离线 → age 变大 → 开关灰显「离线」。
- 进建图失败 → 红色 mapping_error + 重试/退出可用。
