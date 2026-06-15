# thermal_detector

RGB + 热成像多模态**热源危险检测**。把"是什么物体"（RGB/YOLO）与"有多热"
（微雪 Thermal-90 / SenXor 辐射测温）结合，判定热源危险等级。

对应计划：`~/.claude/plans/rdk-x5-lab-detector-deploy-20260603-md-iridescent-russell.md`

## 模块结构

| 文件 | 作用 | 是否依赖硬件 | 测试 |
| --- | --- | --- | --- |
| `thermal_detector/fusion.py` | 融合核心：相对热点 + 逐物体测温 + 分级（纯 stdlib） | 否 | `tests/test_thermal_fusion.py` |
| `thermal_detector/senxor_driver.py` | Thermal-90 驱动：纯解码层 + 后端抽象 | 后端依赖 | `tests/test_senxor_driver.py` |
| `thermal_detector/config_loader.py` | YAML 配置 → 融合对象 | 否（YAML 读取除外） | `tests/test_thermal_config.py` |
| `thermal_detector/hazard_pipeline.py` | 共享管线：配置 + 热帧 → 结果（A/B 路径复用） | 否 | `tests/test_hazard_pipeline.py` |
| `config/thermal_hazard.yaml` | 每类风险等级 + 温度阈值 + 热点参数（可调） | — | — |
| `config/thermal_rgb_calib.yaml` | thermal→RGB 单应矩阵（标定产物） | — | — |

跑全部纯逻辑测试（任意机器，无需 numpy/cv2/硬件）：

```bash
python3 -m unittest discover -s tests
```

## 风险判定

物体基础风险（来自危险物分类）× 热状态（cold/active/hot）→ 事件严重度
（info/warning/critical），见 `fusion.severity_for` 与 `config/thermal_hazard.yaml`：

- 高危类（电烙铁/热风枪/焊枪/裸露导线）+ 通电发热 → critical；冷态 → warning。
- 中危类（插排/插头/电源适配器）+ 过热 → critical；通电 → warning。
- 上下文类（电线/线束/焊台）+ 过热 → warning。
- **热点但无物体框** → "未知热源"告警（RGB 盲区兜底）。

温度判据"两者结合"：相对热点用于发现（`find_hotspots`），绝对 °C 用于分级。
金属低发射率会偏低读数 → 配置 `trust_absolute: false` 可只信相对热点。

## RDK 上板流程（Phase 0–5）

0. **接线**：按 `docs/hardware/pinmap.md` 的 Thermal-90 表接好，启用 SPI/I2C，
   确认 `/dev/spidevX.Y` 与 `/dev/i2c-X`，把实测脚号填回 pinmap。
1. **驱动**：装 Pysenxor（微雪 wiki 下载 `Pysenxor-master.zip` → `python setup.py install`），
   自检：
   ```bash
   python3 rdk_x5/scripts/thermal_capture_test.py \
     --spi-bus 0 --spi-device 0 --i2c-bus 1 --i2c-address 0x40 \
     --reset-pin <PIN> --data-ready-pin <PIN> --frames 30 --save-png /tmp/thermal.png
   ```
   核对：手心 ~30–35°C、通电烙铁明显更高；图像方向不对则加 `--flip-vertical/--flip-horizontal`。
   > `senxor_driver._PysenxorBackend` 中标有 `# VERIFY ON BOARD` 的调用需对照实际 Pysenxor 版本确认。
2. **标定**：
   ```bash
   python3 rdk_x5/scripts/thermal_rgb_calibrate.py --points 6 \
     --out rdk_x5/ros2_ws/src/thermal_detector/config/thermal_rgb_calib.yaml
   ```
   用点状热源在画面 ≥4 处取对应点，生成 thermal→RGB 单应矩阵。
3. **融合核心**：已完成并单测。
4. **集成（先路径 A）**：把 `HazardPipeline` 接入正在运行的
   `rdk_x5_lab_detector_deploy_20260603/runtime/lab_mipi_web_detector.py`，
   增加热帧采集 + 融合 + 双画面/风险横幅，并按 `docs/protocols/event_schema.md`
   写 `thermal_risk` 事件。之后再沉淀为路径 B 的 ROS2 节点。
5. **调参**：用真实样本调 `thermal_hazard.yaml` 阈值与热点参数，评估 FPS。

## 路径 B：ROS2 节点（已完成）

把融合沉淀为 3 个解耦的 ROS2 节点（复用同一 `HazardPipeline`），事件供 `inspection_manager` 消费：

| 节点 | 发布 |
| --- | --- |
| `thermal_detector_node` | `/thermal/temperature`(Image 32FC1) `/thermal/image_color`(bgr8) |
| `rgb_hazard_node` | `/perception/hazard_detections`(String JSON) `/perception/image_color`(bgr8) |
| `hazard_fusion_node` | `/hazard/status`(String JSON) `/hazard/events`(String JSON, `thermal_risk`) |

消息用 std_msgs/String JSON（无需自定义 msg 构建）；(de)序列化在 `ros_payloads.py`（纯函数，单测见 `tests/test_ros_payloads.py`）。

**构建并运行（RDK，单独占用 MIPI 相机+BPU，需先停 standalone web 检测器）：**
```bash
mkdir -p /root/thermal_ws/src && cp -r <repo>/rdk_x5/ros2_ws/src/thermal_detector /root/thermal_ws/src/
cd /root/thermal_ws && source /opt/ros/humble/setup.bash && colcon build --packages-select thermal_detector
source install/setup.bash && export PYSENXOR_SRC=/root/pysenxor-master
ros2 launch thermal_detector hazard_fusion.launch.py        # mock_thermal:=true 可无传感器
```
查看：`ros2 topic echo /hazard/status`、`ros2 topic echo /hazard/events`。
> 路径 B（ROS2 话题）与路径 A（:8080 网页）共用相机，二选一运行。路径 B 无网页视图，看图用 rqt/`ros2 topic`。
