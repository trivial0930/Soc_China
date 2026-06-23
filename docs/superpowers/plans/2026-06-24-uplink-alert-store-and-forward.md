# 断网告警必达 + 板上 30 天清理 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让断网期间产生的告警(`event`/`brief`)在内存重试队列里永不丢弃、网络恢复后全部补传到后端;并给板上记录/日志类文件加 30 天自动清理。

**Architecture:** 给现有纯模块 `RetryQueue` 增加 "persistent kinds" 概念——这些 kind 失败时永不因 `max_attempts` 丢弃,只受 `max_len` 上限约束;`uplink_node` 把 `event`/`brief` 标为 persistent。后端 `event`/`brief` 已是 `ON CONFLICT(event_id)` 幂等,补传不重复。30 天清理用 systemd timer + `find -mtime +30`。

**Tech Stack:** Python 3.10(ROS2 Humble, ament_python 包)、unittest、systemd timer、bash。

## Global Constraints

- 测试运行(在仓库根 `/Users/sthefirst/Desktop/Soc_China`):`python3 -m pytest tests/test_uplink.py -v`;若无 pytest 用 `python3 -m unittest tests.test_uplink -v`。
- 代码事实源在仓库;改 `.py` 后上板部署须 `rm -rf build/inspection_manager install/inspection_manager && colcon build --packages-select inspection_manager`(ament_python 缓存坑)。
- 范围:**只**改告警(event/brief)的留存;图片、record/acceptance/report **不动**。
- `persistent_kinds` 硬编码 `{"event","brief"}`;`max_len` 默认 `2000`;`max_attempts` 保持 `5`。
- 板上 30 天清理脚本:白名单目录 + 仅 `-type f -mtime +30`;先 `-print` 验证再 `-delete`;不碰模型/配置/标定。
- 分支已在 `feat/uplink-alert-store-and-forward`。

---

### Task 1: `RetryQueue` 支持 persistent kinds + add 返回丢弃标志

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink.py`(`RetryQueue` 类,约 line 81-112)
- Test: `tests/test_uplink.py`(`RetryQueueTest` 类)

**Interfaces:**
- Produces: `RetryQueue(max_attempts=5, max_len=2000, persistent_kinds=frozenset())`;`add(kind, body) -> bool`(返回是否丢了最旧);`drain(sender) -> {"sent","requeued","dropped"}`(persistent kind 永不计入 dropped)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_uplink.py` 的 `RetryQueueTest` 类中追加:

```python
    def test_persistent_kind_never_dropped(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("event", {"a": 1})
        s = FakeSender(succeed=False)
        for _ in range(10):              # 远超 max_attempts
            res = q.drain(s)
        self.assertEqual(len(q), 1)       # 仍在队列,从未 drop
        self.assertEqual(res["dropped"], 0)

    def test_non_persistent_still_dropped(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("report", {"a": 1})
        s = FakeSender(succeed=False)
        q.drain(s)                        # attempts=1 -> requeue
        res = q.drain(s)                  # 1+1==2==max -> drop
        self.assertEqual(len(q), 0)
        self.assertEqual(res["dropped"], 1)

    def test_add_returns_true_when_oldest_dropped(self):
        q = uplink.RetryQueue(max_len=2)
        self.assertFalse(q.add("event", {"i": 0}))
        self.assertFalse(q.add("event", {"i": 1}))
        self.assertTrue(q.add("event", {"i": 2}))   # 满了,丢最旧

    def test_persistent_drains_when_sender_recovers(self):
        q = uplink.RetryQueue(max_attempts=2, persistent_kinds=frozenset({"event"}))
        q.add("event", {"a": 1})
        down = FakeSender(succeed=False)
        for _ in range(5):
            q.drain(down)                 # 断网期:一直保留
        self.assertEqual(len(q), 1)
        up = FakeSender(succeed=True)
        res = q.drain(up)                 # 恢复:发出
        self.assertEqual(res["sent"], 1)
        self.assertEqual(len(q), 0)
```

确认测试用的 `FakeSender` 支持 `succeed` 开关——查看 `tests/test_uplink.py` 顶部现有 `FakeSender` 定义;若它没有 `succeed` 参数,改成:

```python
class FakeSender:
    def __init__(self, succeed=True):
        self.succeed = succeed
        self.calls = []
    def __call__(self, kind, body):
        self.calls.append((kind, body))
        return self.succeed
```

(若现有 `FakeSender` 已是别的形态,保留其原有用法,仅补 `succeed` 默认 True 不破坏既有测试。)

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m pytest tests/test_uplink.py -v -k "persistent or add_returns"`
Expected: FAIL —— `RetryQueue.__init__() got an unexpected keyword argument 'persistent_kinds'`

- [ ] **Step 3: 改 `RetryQueue`(uplink.py)**

把 `RetryQueue` 类整体替换为:

```python
class RetryQueue:
    """Bounded FIFO of (kind, body) pending POSTs.

    Non-persistent kinds drop after max_attempts. Kinds in persistent_kinds are
    never dropped by attempt count (retried until sent) — only the max_len bound
    can evict them (oldest first). add() returns True when it evicted the oldest.
    """

    def __init__(self, max_attempts: int = 5, max_len: int = 2000,
                 persistent_kinds=frozenset()) -> None:
        self.max_attempts = max_attempts
        self.max_len = max_len
        self.persistent_kinds = frozenset(persistent_kinds)
        self._q: List[Tuple[str, Dict[str, Any], int]] = []  # (kind, body, attempts)

    def __len__(self) -> int:
        return len(self._q)

    def add(self, kind: str, body: Dict[str, Any]) -> bool:
        dropped_oldest = False
        if len(self._q) >= self.max_len:
            self._q.pop(0)
            dropped_oldest = True
        self._q.append((kind, body, 0))
        return dropped_oldest

    def drain(self, sender: Callable[[str, Dict[str, Any]], bool]) -> Dict[str, int]:
        """Try to send each queued item; requeue failures, drop the rest.
        Persistent kinds are always requeued on failure. sender(kind, body) -> True
        on success. Returns {sent, requeued, dropped}."""
        pending = self._q
        self._q = []
        sent = requeued = dropped = 0
        for kind, body, attempts in pending:
            if sender(kind, body):
                sent += 1
            elif kind in self.persistent_kinds or attempts + 1 < self.max_attempts:
                self._q.append((kind, body, attempts + 1)); requeued += 1
            else:
                dropped += 1
        return {"sent": sent, "requeued": requeued, "dropped": dropped}
```

(确认文件顶部已 `from typing import Any, Callable, Dict, List, Tuple`;若缺 `Tuple`/`List` 补上。)

- [ ] **Step 4: 跑测试确认通过(含原有用例不回归)**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m pytest tests/test_uplink.py -v`
Expected: PASS —— 新增 4 个 + 原有 `RetryQueueTest`(drain_all_success/failed_send_requeues/dropped_after_max_attempts/sender_exception/bounded_length)全绿。
注:原 `test_dropped_after_max_attempts` 仍应通过(默认 `persistent_kinds` 空,行为不变)。

- [ ] **Step 5: 提交**

```bash
cd /Users/sthefirst/Desktop/Soc_China
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink.py tests/test_uplink.py
git commit -m "feat(uplink): RetryQueue persistent kinds (alerts never dropped)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `uplink_node` 接入 persistent + max_len 参数 + 丢弃告警

**Files:**
- Modify: `rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink_node.py`(参数声明区 ~line 38-44;`_enqueue` ~line 72-75)

**Interfaces:**
- Consumes: `RetryQueue(max_attempts, max_len, persistent_kinds)` 与 `add() -> bool`(Task 1)。

- [ ] **Step 1: 加 `max_len` 参数声明**

在参数声明区(现有 `p("flush_sec", 5.0)` / `p("max_attempts", 5)` 附近)加一行:

```python
        p("max_len", 2000)
```

- [ ] **Step 2: 构造 RetryQueue 时传 persistent_kinds + max_len**

把现有(约 line 44):

```python
        self.queue = RetryQueue(max_attempts=int(gp("max_attempts").value))
```

改为:

```python
        self.queue = RetryQueue(
            max_attempts=int(gp("max_attempts").value),
            max_len=int(gp("max_len").value),
            persistent_kinds=frozenset({"event", "brief"}),
        )
```

- [ ] **Step 3: `_enqueue` 入队时,丢最旧则告警日志**

把现有 `_enqueue`(约 line 72-75):

```python
    def _enqueue(self, kind: str, body: dict, images=None) -> None:
        self._upload(images or [])
        if not self._send(kind, body):
            self.queue.add(kind, body)
```

改为:

```python
    def _enqueue(self, kind: str, body: dict, images=None) -> None:
        self._upload(images or [])
        if not self._send(kind, body):
            if self.queue.add(kind, body):
                self.get_logger().warn(
                    f"uplink queue full (max_len), dropped oldest to enqueue {kind}")
```

- [ ] **Step 4: 静态检查(节点依赖 rclpy,无纯单测;靠 Task 4 集成验证)**

Run: `cd /Users/sthefirst/Desktop/Soc_China && python3 -m py_compile rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink_node.py`
Expected: 无输出(编译通过)。功能正确性由 Task 4 上板集成测试覆盖。

- [ ] **Step 5: 提交**

```bash
cd /Users/sthefirst/Desktop/Soc_China
git add rdk_x5/ros2_ws/src/inspection_manager/inspection_manager/uplink_node.py
git commit -m "feat(uplink): node marks event/brief persistent, adds max_len param

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 板上 30 天文件清理(脚本 + systemd timer)

**Files:**
- Create: `rdk_x5/scripts/cleanup_old_files.sh`(纳入仓库,便于版本管理;部署到板上 `/root/`)
- Create(板上): `/etc/systemd/system/board-cleanup.service`、`/etc/systemd/system/board-cleanup.timer`

**Interfaces:** 独立运维脚本,无代码依赖。

- [ ] **Step 1: 写清理脚本(仓库)**

创建 `rdk_x5/scripts/cleanup_old_files.sh`:

```bash
#!/bin/bash
# 板上记录/日志类文件 30 天保留,过期自动删(与 Mac 后端 RETENTION_DAYS=30 对齐)。
# 只删超过 30 天的普通文件;白名单目录;不碰模型/配置/标定。
# 用法: cleanup_old_files.sh [--dry-run]
set -u
DAYS=30
DRY="${1:-}"
# 白名单目录(实现时按板上实际路径核对增删):
DIRS=(
  /root/.ros/log                # ROS 节点日志(滚动累积)
  /tmp                          # *.log 临时日志
)
# report .md / workstation JSONL 的实际输出目录在 Step 2 核对后补入上面 DIRS。
PATTERNS=( "*.log" "*.jsonl" "*.md" )
for d in "${DIRS[@]}"; do
  [ -d "$d" ] || continue
  for pat in "${PATTERNS[@]}"; do
    if [ "$DRY" = "--dry-run" ]; then
      find "$d" -type f -name "$pat" -mtime +$DAYS -print
    else
      find "$d" -type f -name "$pat" -mtime +$DAYS -delete
    fi
  done
done
echo "cleanup done (days=$DAYS, dry=${DRY:-no})"
```

- [ ] **Step 2: 核对板上实际输出目录,补全 DIRS**

Run(板上):
```bash
ssh root@192.168.128.10 'grep -rnE "report.*\.md|\.jsonl|output|log_path|report_dir|record.*path" /root/Soc_China/rdk_x5/ros2_ws/src/inspection_manager/config/report.yaml /root/Soc_China/rdk_x5/ros2_ws/src/inspection_manager/config/*.yaml 2>/dev/null | grep -iE "dir|path|\.md|\.jsonl"'
```
把查到的 report `.md` 输出目录、workstation JSONL 目录补进脚本的 `DIRS`(若都落在 `/tmp` 或已覆盖则跳过)。

- [ ] **Step 3: 部署脚本到板上 + dry-run 验证(只打印,不删)**

```bash
scp rdk_x5/scripts/cleanup_old_files.sh root@192.168.128.10:/root/cleanup_old_files.sh
ssh root@192.168.128.10 'chmod +x /root/cleanup_old_files.sh && /root/cleanup_old_files.sh --dry-run'
```
Expected: 列出(或为空)将被删的 >30 天文件;确认**没有**模型/配置/标定文件出现在列表里。

- [ ] **Step 4: 装 systemd timer(每日触发)**

```bash
ssh root@192.168.128.10 "cat > /etc/systemd/system/board-cleanup.service" <<'EOF'
[Unit]
Description=Board file retention cleanup (30 days)
[Service]
Type=oneshot
ExecStart=/root/cleanup_old_files.sh
EOF
ssh root@192.168.128.10 "cat > /etc/systemd/system/board-cleanup.timer" <<'EOF'
[Unit]
Description=Daily board file cleanup
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
EOF
ssh root@192.168.128.10 'systemctl daemon-reload && systemctl enable --now board-cleanup.timer && systemctl list-timers board-cleanup.timer --no-pager'
```
Expected: `board-cleanup.timer` 出现在 list-timers,有下次触发时间。

- [ ] **Step 5: 提交(脚本入库)**

```bash
cd /Users/sthefirst/Desktop/Soc_China
git add rdk_x5/scripts/cleanup_old_files.sh
git commit -m "feat(ops): board-side 30-day file retention cleanup (script + timer)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 上板端到端集成验证(断网模拟)

**Files:** 无(部署 + 验证)

**Interfaces:** 验证 Task 1+2 在真机上端到端正确。

- [ ] **Step 1: 部署改动到板上(重建包)**

```bash
cd /Users/sthefirst/Desktop/Soc_China
# 同步改动到板上(按你的同步方式,如 git pull 或 scp uplink.py/uplink_node.py)
ssh root@192.168.128.10 'cd /root/Soc_China/rdk_x5/ros2_ws && rm -rf build/inspection_manager install/inspection_manager && source /opt/ros/humble/setup.bash && colcon build --packages-select inspection_manager 2>&1 | tail -3'
ssh root@192.168.128.10 'bash /root/start_cmd_nodes.sh; sleep 3; ps -ef | grep "lib/inspection_manager/uplink_node" | grep -v grep | wc -l'
```
Expected: colcon build 成功;uplink_node 进程数=1。

- [ ] **Step 2: 模拟断网 —— 停 Mac 后端**

在 Mac:`lsof -tiTCP:8000 -sTCP:LISTEN | xargs kill`(记下,验证后要重启)。
确认板上 uplink 连不上:`ssh root@192.168.128.10 'tail -5 /tmp/uplink.log'` 应出现 POST 失败 warn。

- [ ] **Step 3: 断网期发若干告警,等超过旧的丢弃窗口(>30s)**

```bash
ssh root@192.168.128.10 'source /opt/ros/humble/setup.bash; source /root/Soc_China/rdk_x5/ros2_ws/install/setup.bash; timeout 12 ros2 run inspection_manager sim_hazard_publisher 2>&1 | grep published'
# 等 40s,确认告警没被丢(persistent)
sleep 40
ssh root@192.168.128.10 'grep -c "flush" /tmp/uplink.log; tail -3 /tmp/uplink.log'
```
Expected: uplink 持续 requeue,日志无 "dropped" 告警类(persistent 不丢)。

- [ ] **Step 4: 恢复网络 —— 重启 Mac 后端,验证补传**

```bash
# Mac: 重启后端
cd /Users/sthefirst/Desktop/Soc_China
APP_INGEST_TOKEN=$(cat ~/.app_ingest_token) nohup ~/.venvs/inspection/bin/uvicorn app.backend.server:app --host 0.0.0.0 --port 8000 > ~/backend.log 2>&1 &
sleep 8
# 板上 uplink 下次 flush(5s)应补传;等 15s 后查后端是否收到断网期的 event
sleep 15
curl -s -m5 http://localhost:8000/api/events 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('events 条数:', d.get('total', len(d) if isinstance(d,list) else '?'))"
```
Expected: 断网期间 sim 发的 event 出现在后端(`total` 增加),证明补传成功、未丢。

- [ ] **Step 5: 提交验证记录(可选)**

将验证结果记入 `docs/validation/daily/2026-06-24-uplink-store-and-forward.md`(若该目录惯例存在),`git add` + commit。否则跳过。

---

## Self-Review

**Spec 覆盖:** ① persistent event/brief 不丢 → Task 1。② uplink_node 接线 + max_len + 丢弃日志 → Task 2。③ 后端幂等 → 无需改(已具备),Task 4 验证补传不重复(可在 Step 4 加查重)。④ 30 天清理 → Task 3。⑤ 测试用例(persistent 不 drop/非 persistent drop/max_len 溢出/混合) → Task 1 Step 1。全覆盖。

**Placeholder 扫描:** Task 3 Step 1 脚本里"report .md/JSONL 目录在 Step 2 核对后补入"是**有意的核对步骤**(Step 2 显式执行),非占位。其余无 TBD/TODO。

**类型一致:** `RetryQueue(max_attempts, max_len, persistent_kinds)` 与 `add()->bool` 在 Task 1 定义、Task 2 一致使用;`drain` 返回 `{sent,requeued,dropped}` 不变。一致。
