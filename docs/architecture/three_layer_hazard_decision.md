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
- **待接**：`LocalVLMBackend`（本地小 VLM，注入式 client，已有 prompt 拼装 `build_prompt` 与回复解析
  `parse_vlm_result`，仅缺真实 HTTP/Ollama client）；`CloudReportBackend`（Claude 多模态，注入式 client，
  Phase C 用 `claude-api` 技能定型号/SDK + API key）。
  > 两个真实后端的"调用-解析"接线已用 fake client 单测；换真实 client 不动决策逻辑。

## 运行 / 验证（全部 RDK-independent）

- 单测：`python3 -m unittest discover -s tests`（含 `test_inspection_*`/`test_escalation`/`test_station_map`/
  `test_cognition`/`test_actions`/`test_report`/`test_inspection_pipeline`，共 157 测试全绿）。
- 离线端到端演示：`python3 rdk_x5/scripts/inspection_demo.py`（喂样例事件，打印 L1→L2→动作→L3）。
- 板上：`colcon build --packages-select inspection_manager` 后
  `ros2 launch inspection_manager inspection.launch.py`，订阅 `thermal_detector` 的 `/hazard/events`。

## 明确推迟（上板/之后）

1. **#3 检测→云台视觉伺服**：为 `AimGimbal` 填 pan/tilt（相机装在云台上 → 视觉伺服把目标转到画面中心）。
2. **真实 `LocalVLMBackend`**（本地小 VLM 部署）与 **真实 `CloudReportBackend`**（Claude 多模态 client）。
3. 动作执行器硬件实效（语音 TTS、Nav2 导航、激光指示）端到端联调。
4. 工位映射 `stations.yaml` 按真实实验室布局填写；真机调升级阈值。
