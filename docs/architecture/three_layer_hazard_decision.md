# 三级分层危险决策架构

落地设计文档 `docs/source/基于RDK X5的电子实验室巡检管理系统与多模态大模型分层协同优化 (1).docx`
第三节第 3 点"基于分层认知处理的巡检信息分析机制"。目标：紧急事件本地快速响应，普通事件本地完成
说明与记录，只有复杂/周期性事件才上云，控制成本与延迟。

## 三层职责与代码归属

| 层 | 职责 | 包 / 模块 | 状态 |
| --- | --- | --- | --- |
| **L1 端侧快速初筛** | YOLO + 热成像阈值 + 规则 → 结构化事件，过滤正常画面 | `thermal_detector`（`fusion.py`/`hazard_pipeline.py`/`hazard_fusion_node.py`），发 `/hazard/events`、`/hazard/status` | 已建 |
| **L2 本地理解 + 处置建议** | 事件 + 截图 + 工位上下文 → 简要说明 + 建议动作；多数普通异常就地处置 | `inspection_manager`：`cognition.py`/`actions.py`/`station_map.py`/`escalation.py` + `cognition_node` | 本计划已建（mock 后端；真实本地 VLM 待接） |
| **L3 按需云端分析** | 聚合多事件/多图 → 结构化报告（课后验收/周期/不确定追问） | `inspection_manager`：`report.py` + `report_service` | 本计划已建（mock 后端；真实 Claude 客户端待接） |

L1 与 L2/L3 解耦：L1 在 `thermal_detector`，决策聚合层在新包 `inspection_manager`。

## 层间契约

- **事件**：`docs/protocols/event_schema.md`。L1 在 `/hazard/events`（std_msgs/String JSON，已节流为
  warning/critical）发出；`inspection_manager/events.py` 的 `parse_event()` 解析为 `HazardEvent`，
  其中 **`action` 块**（`robot_task`/`voice_prompt`/`reported_to_admin`）由 L2 回填。
- **L2 输出**：`/inspection/brief`（说明 + 回填后的事件 + 动作 + 是否上云）。
- **L2→L3**：`/inspection/escalate`（升级的 brief），由 `report_service` 缓冲。
- **报告**：`/inspection/report`（结构化简报元信息 + 落盘路径）。

## 升级网关（`escalation.py`，纯函数）

- **Gate 1（L1→L2）**：`should_cognize(event)` —— severity ≥ 门限 且 confidence ≥ 门限才进认知层。
- **Gate 2（L2→L3）**：`should_escalate_to_cloud(confidence, needs_report)` —— **不按 severity 自动上云**
  （紧急事件本地快速处置）；仅在「需要报告/周期/多图」(`needs_report`) 或「本地不确定」(confidence 低) 时上云。

## 动作路由（`actions.py` → 执行器）

`route_actions()` 把 L2 的建议动作映射为具体命令：
- `VoicePrompt` → `/inspection/voice`（TTS 执行器，板上）
- `RobotRecheck(station)` → 经 `station_map` 反查 waypoint → Nav2 `followWaypoints`（`chassis_bringup`）
- `AimGimbal(station)` → `/gimbal/target_angle`（Vector3）——**pan/tilt 由 #3 检测→云台视觉伺服填入**
- `LogRecord` → 巡检日志

## 可插拔后端

`CognitionBackend` / `ReportBackend` 协议 + 工厂（`make_backend` / `make_report_backend`）：
- **现在**：`MockCognitionBackend`、`MockReportBackend`（规则/模板，确定性、可单测、可演示）。
- **真实后端（选型 = 通义千问 Qwen，L2/L3 同源）**，client 已写好(`qwen_client.py`，注入式 transport，
  用 fake transport 全单测,仅差 API key / Ollama 运行时):
  - **L2 本地** `LocalVLMBackend` ← `ollama_vlm_client("qwen3-vl:8b")`（本地 Qwen3-VL，Ollama，OpenAI 兼容）。
  - **L3 云端** `CloudReportBackend` ← `qwen_cloud_client(model="qwen3-vl-plus")`（阿里云百炼 DashScope，
    OpenAI 兼容；API key 走环境变量 `DASHSCOPE_API_KEY`）。
  > 两个真实后端的"调用-解析"接线已用 fake transport 单测；换真实 client 不动决策逻辑。
  > `cognition_node`/`report_service` 在 config `backend: local_vlm`/`cloud` 时自动构造对应 Qwen client。

## 运行 / 验证（全部 RDK-independent）

- 单测：`python3 -m unittest discover -s tests`（含 `test_inspection_*`/`test_escalation`/`test_station_map`/
  `test_cognition`/`test_actions`/`test_report`/`test_inspection_pipeline`，共 157 测试全绿）。
- 离线端到端演示：`python3 rdk_x5/scripts/inspection_demo.py`（喂样例事件，打印 L1→L2→动作→L3）。
- 板上：`colcon build --packages-select inspection_manager` 后
  `ros2 launch inspection_manager inspection.launch.py`，订阅 `thermal_detector` 的 `/hazard/events`。

## 已离板写好 / 明确推迟

**已离板写好（上板只剩接线/调参/给 key）**：
- **#3 检测→云台视觉伺服**：`gimbal_laser/visual_servo.py`（IBVS 控制律，纯函数，单测）+
  `gimbal_aim_node`（订阅 `/hazard/status` → `pick_target` → `servo_step` → 发 `/gimbal/target_angle`，
  enable 门控）+ `config/visual_servo.yaml`。上板只需:确认 FOV、标定 `invert_pan/tilt` 符号、调 `gain/deadband`。
- **Qwen client**：`inspection_manager/qwen_client.py`（L2 Ollama + L3 百炼，OpenAI 兼容，注入式 transport）。

**仍须上板/之后**：
1. 给 L2/L3 接真实运行时：本地 Ollama 跑 `qwen3-vl:8b`；百炼 `DASHSCOPE_API_KEY`。
2. 动作执行器硬件实效（语音 TTS、Nav2 导航、激光指示）端到端联调。
3. 工位映射 `stations.yaml` 按真实实验室布局填写；真机调升级阈值与伺服增益。
