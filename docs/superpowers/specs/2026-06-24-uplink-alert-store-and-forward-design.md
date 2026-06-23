# 设计:断网告警必达(uplink persistent retry)+ 板上 30 天文件清理

> 日期:2026-06-24
> 状态:设计已评审通过,待写实现计划
> 相关代码:`rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink.py`、`uplink_node.py`;后端 `app/backend/store.py`、`ingest.py`

## 1. 背景与问题

机器人巡检时若与 Mac 后端断网,板上 `uplink_node` 通过 `RetryQueue` 上报的数据会受限于重试上限而丢失:

- `RetryQueue` 默认 `max_attempts=5`,`uplink_node` 每 `flush_sec=5.0` 秒 drain 一次 → **断网约 25 秒后,告警被丢弃且永不补传**。
- 队列为内存结构,`max_len=500`,超出丢最旧。

后果:机器人在断网期间照常自主巡检、照常检测到危险,但这些**告警(event/brief)话题流过即逝**,传不出去就永久消失;网络恢复后 App 也看不到断网期内发生的告警。

## 2. 目标与非目标

### 目标
- 断网期间产生的**告警(`event` + `brief`,纯文本)**全部留存,网络恢复后**自动全部补传**到后端,App 能完整看到。
- 实现轻量:利用现有 `RetryQueue`,不引入落盘/数据库。

### 非目标(明确排除)
- **不补传告警证据图片**:当前图片上传失败即跳过,维持现状(用户决策 A,仅文本告警)。
- **不保 `record`/`acceptance`/`report`**:断网场景下这三类根本不会产生——`workstation_record_node` 当前未自启(record 不产生);`acceptance`/`report` 靠 App 命令触发,断网时命令通道同时中断,无从触发;且各有本地兜底(JSONL / `.md`)。维持原"尽力上报"。
- **不做落盘持久化**:前提是"断网期间板子不重启/不断电"(用户确认),内存队列足够。

## 3. 现状(代码事实)

- `uplink.py: RetryQueue`(约 line 81-112):`__init__(max_attempts=5, max_len=500)`;`drain` 中失败项 `attempts+1 < max_attempts` 才 requeue,否则 drop。
- `uplink_node.py`:`_enqueue(kind, body, images)` 先 `_upload(images)`(失败仅 debug 跳过、**不重试**),再 `_send`,失败入 `queue.add`;`_flush` 每 5s drain。告警来自 `_on_event`("event") 与 `_on_brief`("brief")。
- 后端幂等:`store.py: upsert_event` / `upsert_brief` 均为 `INSERT ... ON CONFLICT(event_id) DO UPDATE` → **重传同一 event_id 不产生重复**。(注:`record`/`acceptance`/`report` 为无幂等键的 `INSERT`,但本设计不补传它们,无影响。)

## 4. 设计

### 4.1 `RetryQueue` 加 "persistent kinds"(`uplink.py`)

新增构造参数 `persistent_kinds`(集合)。属于 persistent 的 kind 发送失败时**永不因 `max_attempts` 被丢弃**,一直 requeue 到发送成功:

```python
class RetryQueue:
    def __init__(self, max_attempts=5, max_len=2000, persistent_kinds=frozenset()):
        self.max_attempts = max_attempts
        self.max_len = max_len
        self.persistent_kinds = frozenset(persistent_kinds)
        self._q = []

    def add(self, kind, body):
        dropped_oldest = False
        if len(self._q) >= self.max_len:
            self._q.pop(0)        # 丢最旧
            dropped_oldest = True
        self._q.append((kind, body, 0))
        return dropped_oldest      # 调用方据此打 warn 日志

    def drain(self, sender):
        pending = self._q
        self._q = []
        sent = requeued = dropped = 0
        for kind, body, attempts in pending:
            if sender(kind, body):
                sent += 1
            elif kind in self.persistent_kinds or attempts + 1 < self.max_attempts:
                self._q.append((kind, body, attempts + 1))
                requeued += 1
            else:
                dropped += 1
        return {"sent": sent, "requeued": requeued, "dropped": dropped}
```

关键单行:`elif kind in self.persistent_kinds or attempts + 1 < self.max_attempts` —— persistent kind 走前半永远成立 → 永不 drop。

### 4.2 `uplink_node` 接线

```python
self.queue = RetryQueue(
    max_attempts=int(gp("max_attempts").value),       # 仍 5,管非告警
    max_len=int(gp("max_len").value),                 # 新参数,默认 2000
    persistent_kinds=frozenset({"event", "brief"}),   # 告警必达
)
```

- 新增 ROS 参数 `max_len`(默认 2000)。
- `add` 返回 `dropped_oldest=True` 时打 `warn`(仅断网极久才触发)。
- 其余逻辑全不动(图片仍跳过、其他 kind 仍尽力)。

### 4.3 配置
- `persistent_kinds` 硬编码 `{"event","brief"}`(YAGNI,不做成可配)。
- `max_len=2000`(可配):告警 body 数百字节,2000 条仅几 MB;不重启,内存撑得住。
- `max_attempts=5`(不变)。

### 4.4 数据流
断网 → `event`/`brief` 入队(persistent)→ 每 5s `flush` 失败但**不丢** → 网络恢复 → `flush` 成功移除 → 后端 `upsert_event`/`upsert_brief` 幂等写入 → App 同步看到。补传按 FIFO 顺序,后端按 `event_id` 幂等去重,App 按时间戳展示。

### 4.5 错误处理
- 重复:后端 `event`/`brief` 已 `ON CONFLICT(event_id)` 幂等,补传不重复。
- 队列满 `max_len`:丢最旧 + `warn` 日志(断网极久才触发)。
- "断网不重启"前提成立 → 内存不丢,无需落盘。

## 5. 测试

`RetryQueue` 是纯模块、已有单测。新增/更新用例:
1. persistent kind 失败多次(远超 `max_attempts`)**不 drop**,始终在队列;
2. 非 persistent kind 到 `max_attempts` 后 **drop**;
3. `sender` 成功的项被移除,失败的 requeue;
4. `max_len` 溢出时 `add` 丢最旧并返回 `dropped_oldest=True`;
5. 混合队列(告警 + 非告警):断网久了非告警被 drop、告警全保留。

## 6. 附:板上 30 天文件清理(同一 spec,实现时一并做)

板上记录/日志类文件目前无清理,长期累积。补一个与 Mac 后端 `RETENTION_DAYS=30` 对齐的清理:

- 新增 `systemd` timer(每日触发)+ service,跑清理脚本对板上文件执行 `find <dir> -type f -mtime +30 -delete`。
- 清理目标(**实现时核对确切路径**):report `.md` 输出目录、`workstation_record` 的 JSONL 日志、旧 `/tmp/*.log`。
- 仅删超过 30 天的文件;不碰模型/配置/标定(`gimbal.yaml` 等)。

## 7. 实现注意 / 风险

- `RetryQueue` 改了 `drain`/`add` 签名(`add` 增返回值),需同步更新现有单测与调用点。
- `max_len=2000` 是经验值;若实测告警频率高、单次断网极长,可调大(纯内存,代价是 RAM)。
- 30 天清理脚本务必**白名单目录 + 仅 `-mtime +30` + 仅 `-type f`**,避免误删;先 `find ... -print` 验证再加 `-delete`。
- 本设计依赖"断网不重启"前提;若将来需扛重启,再考虑落盘(超出本 spec 范围)。
