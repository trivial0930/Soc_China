# L1.5 端侧轻认知层（Tiered Cognition）设计

日期：2026-06-17
状态：设计已确认，待写实现计划
范围：仅 RDK-independent 的软件部分（纯 Python 核心 + mock/fake + 测试）。真实小模型运行时（RDK 上 llama.cpp/BPU）为上板项，不在本 spec 实现范围。

## 背景与目标

现有三级分层（`inspection_manager`）：
- **L1** 端侧初筛：`thermal_detector` 的 YOLO + 热成像融合 → `/hazard/events`（仅 warning/critical）。
- **L2** 本地认知：`cognition_node` → `CognitionBackend.assess()` → 当前 `LocalVLMBackend` 调 **Mac 上的 Qwen2.5-VL-7B**（OpenAI 兼容，`qwen_client`）。
- **L3** 云端报告：`report_service` → Qwen3-VL-Plus（百炼）。

**问题**：L2 跑在 Mac/外部机器上 —— 机器人移动时 WiFi/热点可能断；且每条事件都走网络、延迟与成本偏高。

**目标**：在 RDK X5（8GB）本机插入一个 **L1.5 端侧轻认知层**（小 VLM，1–2B，会"看"证据图），实现：
1. **快速初判**：大量非严重事件本地秒出，不碰网络；
2. **分流**：只有"严重"或"L1.5 没把握"的才升级给 Mac 7B；
3. **离线兜底**：7B 不可达时，L1.5 顶上，机器人不瘫；
4. **纠正 L1 误报**：L1.5 看图能把纯规则挡不住的视觉误报降级（如热点其实是热咖啡）。

## 关键设计决策（已与用户确认）

- **集成方式 = 分层后端 `TieredCognitionBackend`**（实现现有 `CognitionBackend` 协议，对 `cognition_node` 完全透明）。复用最大、新代码最少、纯逻辑可单测、离板可完整开发。
- **L1.5 与 L2 是同一个 `LocalVLMBackend` 类，仅 `base_url` 不同**：L1.5 → RDK 本机小 VLM（`llama-server`/Ollama，OpenAI 兼容，localhost）；L2 → Mac 7B。零新客户端代码。
- **L1.5 看图**（小 VLM），不是只读结构化事件文本。
- **升级策略 = D（组合）**：critical 在线优先 7B、离线 L1.5 兜底；非 critical 由 L1.5 处理，只有它没把握（或自评更严重）才升 7B。
- **三档优雅降级**：deep(7B) → fast(L1.5) → rules(`MockCognitionBackend` 纯规则，永不失败)。

## 架构与组件

新增（均在 `inspection_manager/cognition.py`，复用现有抽象）：

```
TieredCognitionBackend(CognitionBackend)
├── deep : Optional[CognitionBackend]   # L2 = LocalVLMBackend(base_url → Mac 7B);可 None
├── fast : CognitionBackend             # L1.5 = LocalVLMBackend(base_url → RDK localhost 小 VLM)
├── fallback : CognitionBackend         # 纯规则,默认 MockCognitionBackend(永不失败)
└── policy : TierPolicy                 # 纯 dataclass,阈值/开关
```

- `fast`/`deep` 直接复用现成 `LocalVLMBackend` + `qwen_client`（OpenAI 兼容 + urllib 传输），无需新客户端。
- `TieredCognitionBackend.assess(request) -> CognitionResult` 实现策略 D + 三档降级。输出仍是同一个 `CognitionResult`（explanation / confirmed_severity / suggested_actions / escalate_to_cloud / confidence / reason），下游零感知。L1.5 可输出比 L1 更低的 `confirmed_severity`（纠正误报）。
- `TierPolicy`（纯 dataclass，可单测）：
  - `escalate_below_confidence: float = 0.6` — L1.5 自评置信度低于此 → 升级 deep；
  - `critical_always_deep: bool = True` — L1 报 critical 时在线优先 deep；
  - `escalate_if_fast_critical: bool = True` — L1.5 自己判成 critical（看出比 L1 更严重）→ 升级 deep 复核。

**改动面（小）：**
- `cognition.py`：加 `TieredCognitionBackend` + `TierPolicy`；
- `config.py` / `config/cognition.yaml`：加 `backend: tiered` + fast/deep 各自 `vlm_model`/`vlm_base_url` + 三个策略阈值；
- `cognition_node._build_backend`：`backend == "tiered"` 时构造 fast+deep 两个 `LocalVLMBackend`，包成 `TieredCognitionBackend`（fallback 默认 mock）；
- **不动**：`CognitionRequest`/`CognitionResult`、`actions`、`escalation` 的 gate1/gate2、L3、所有下游。

## 数据流（策略 D + 三档降级）

`assess(request)`（`event.severity` 为 L1 初筛严重度）：

```
① event.severity == "critical" 且 policy.critical_always_deep 且 deep 存在:
     r = try_deep(request)                 # 调 deep;捕获超时/连接错误 → None
     若 r 非 None → 返回 r                   # 7B 结果
     否则 → 返回 fast.assess(request),reason="L2离线→L1.5兜底"
            (若 fast 也抛 → fallback,reason="L2/L1.5均不可用→规则")

② 否则(非 critical):
     f = run_fast(request)                 # fast.assess;若抛异常 → fallback 结果(reason 标注),直接返回
     uncertain = f.confidence < policy.escalate_below_confidence
                 OR (policy.escalate_if_fast_critical 且 f.confirmed_severity == "critical")
     若 deep 存在 且 uncertain:
          r = try_deep(request)
          若 r 非 None → 返回 r              # 7B 复核结果
          否则 → 返回 f,reason="不确定但L2离线→L1.5"
     否则 → 返回 f                          # L1.5 本地搞定,不耗网
```

辅助：
- `try_deep(request)`：`try: return deep.assess(request) except (超时/连接错误等网络异常): return None`。"离线判定"即此 try/except；不引入心跳（`qwen_client` 的 urllib 已有 `timeout_s`）。
- `run_fast(request)`：`try: return fast.assess(request) except Exception: return fallback.assess(request)`（带 reason 标注）。

关键性质：
- **断网不瘫**：任何走 deep 的分支，deep 网络异常都被接住 → 退 fast；fast 再抛 → 退 rules。
- **省网+快**：非 critical 且 L1.5 有把握的事件根本不碰网络，本地秒出。

## 错误处理

- deep 网络异常（超时/连不上）→ 降 fast；
- fast 异常（RDK 模型没起/崩）→ 降 fallback（规则 mock）；
- **任何情况下都返回一个 `CognitionResult`**，机器人永不"无结论"；
- 每次降级在 `reason` 标注（如 `"L2离线→L1.5兜底"`），便于排查与演示。
- 异常捕获只针对预期的网络/后端错误，避免吞掉编程 bug（捕获范围在实现时收窄到具体异常类型 + 通用兜底分层）。

## 测试（纯单测,注入 fake 后端,零模型、完全离板）

`tests/test_tiered_cognition.py`：用 fake `CognitionBackend`（可配置返回值/抛异常/记录是否被调用）注入 fast/deep/fallback，断言"谁被调、返回了谁、reason 对不对"：
- `TierPolicy` 默认值与字段；
- critical + deep 在线 → deep 被调、返回 deep；deep **未**被调时 fast 不应被多余调用；
- critical + deep 离线 → fast 兜底；
- 非 critical + fast 有把握(高 confidence) → 只调 fast，deep **不**被调；
- 非 critical + fast 没把握(低 confidence) + deep 在线 → deep 被调；
- 非 critical + fast 没把握 + deep 离线 → 返回 fast 结果；
- `escalate_if_fast_critical`：fast 判 critical → deep 被调；
- fast 抛异常 → fallback 被调、有结论；
- deep 与 fast 都不可用 → fallback。
约 10 个测试。沿用仓库测试范式（`unittest`、`sys.path.insert(PACKAGE_SRC)`、不依赖 numpy/rclpy/模型）。

另：离线演示脚本（仿 `inspection_demo.py`）用 fake/mock 后端跑通三档降级，打印每条事件走了哪档 + reason，证明无硬件下端到端可演示。

## 离板/上板分界

**现在做（无 RDK，纯软件，本 spec 范围）：**
- `TieredCognitionBackend` + `TierPolicy`；
- `config.py`/`cognition.yaml` 的 `tiered` 后端选项与阈值；
- `cognition_node._build_backend` 接线；
- `tests/test_tiered_cognition.py`（~10）；
- 离线降级演示脚本。

**以后做（有 RDK，不在本 spec）：**
- RDK 上用 `llama-server`（llama.cpp，OpenAI 兼容）起本机小 VLM；fast `base_url` 指 localhost；
- 选 + 量化实际小 VLM（先 CPU/llama.cpp 摸可行性与速度，后评估 BPU/OpenExplorer）；
- 真机实测调 `escalate_below_confidence` 等阈值。
- **唯一上板依赖 = L1.5 小模型运行时**。

## 明确不做（YAGNI）

- 不动 L3、actions、gate1/gate2、CognitionRequest/Result 结构；
- 不引入额外的心跳/健康检查（靠调用 try/except 判离线）；
- 不在本 spec 选定具体小 VLM 型号（留到上板实测）；
- 语音交互是独立的下一阶段功能，不在本 spec。

## 验证

1. `python3 -m unittest discover -s tests` 全绿（含新增 ~10 个 tiered 测试，现有不回归）。
2. 离线降级演示脚本：喂样例事件，打印每条走了 deep/fast/rules 哪档 + reason，覆盖在线/离线/有把握/没把握各分支。
