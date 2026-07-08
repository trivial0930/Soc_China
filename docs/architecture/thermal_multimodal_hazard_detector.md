# RDK X5 Visual + Thermal Multimodal Hazard Detector Engineering Guide

本文档记录当前 RDK X5 实验室危险源检测项目中，接入微雪 Thermal-90 Camera Module 并与现有可见光 YOLO 检测融合的工程流程。目标是形成一套可执行、可验证、可继续开发的路线，而不是只停留在概念方案。

## 1. 当前项目状态

### 1.1 已完成的可见光检测

当前 RDK X5 已经部署并验证了基于 CSI 摄像头的可见光危险源检测。

RDK 设备信息：

```text
IP: 192.168.128.10
User: root
Password: root
Web preview: http://192.168.128.10:8080/
```

RDK 侧部署目录：

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
```

Mac 侧对应目录：

```bash
/Users/sthefirst/Desktop/Soc_China/rdk_x5_lab_detector_deploy_20260603
```

当前可见光危险源模型：

```bash
weights/hazard_yolo11s_640_nv12.bin
config/hazard_classes.names
runtime/lab_mipi_web_detector.py
runtime/lab_ultralytics_yolo11.py
runtime/run_hazard_mipi_web_detector.sh
```

模型类别共 10 类：

```text
soldering_iron
soldering_station
hot_air_gun
welding_gun
power_strip
plug
power_adapter
wire
wire_bundle
exposed_wire
```

当前运行命令：

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
runtime/run_hazard_mipi_web_detector.sh
```

后台运行命令：

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
nohup runtime/run_hazard_mipi_web_detector.sh >/tmp/hazard_mipi_web_detector.log 2>&1 &
```

查看日志：

```bash
tail -f /tmp/hazard_mipi_web_detector.log
```

### 1.2 多模态扩展目标

后续需要把 Thermal-90 热成像数据与当前 YOLO 可见光检测融合，用于识别可能的热源危险。

典型危险包括：

- 电烙铁、热风枪、焊枪等高温工具。
- 插排、电源适配器、插头异常发热。
- 导线、线束、裸线局部异常发热。
- YOLO 未识别到具体物体，但热成像中存在明显高温区域。

## 2. Thermal-90 硬件说明

### 2.1 模块接口

微雪 Thermal-90 Camera Module 使用：

- I2C：配置寄存器、设备控制。
- SPI：读取热成像数据。
- GPIO：RESET 和 READY。
- VCC/GND：供电。

模块引脚：

```text
RESET
READY
SDA
SCL
SS
CLK
MISO
MOSI
GND
VCC
```

模块 I2C 地址：

```text
0x40 或 0x41
```

当前实测地址：

```text
0x40
```

### 2.2 实测接线（已跑通，2026-06-07/12 更新）

> ⚠️ 本节已更新为**实际跑通方案**。早期草案里 `SS→24 / spidev5.0` 那条路不通（spidev 在本 SoC 不驱动 CS、且 spidev5.0 没路由到 40PIN），已废弃。最终方案：**SS 接物理脚 7 做 GPIO 软件片选，走 SPI1/`/dev/spidev1.1`**。

当前项目中云台已经占用了部分 RDK X5 40PIN 引脚，因此 Thermal-90 不能照树莓派默认接线方式接，尤其不能把 READY 接到物理 18 脚。

当前需要避开的云台占用：

```text
PWM pins: 29, 31, 37, 18, 28, 27
Enable pins: 38, 40
Gimbal I2C buses: 5, 1
```

实测接线：

| Thermal-90 引脚 | RDK X5 40PIN | 说明 |
| --- | ---: | --- |
| VCC | 1 | 3.3V（实测足够，i2cdetect 能枚举到 0x40） |
| GND | 6 | 共地 |
| SDA | 3 | I2C SDA，`/dev/i2c-5`，地址 0x40 |
| SCL | 5 | I2C SCL，`/dev/i2c-5` |
| MOSI | 19 | SPI1 MOSI |
| MISO | 21 | SPI1 MISO |
| CLK | 23 | SPI1 SCLK |
| **SS** | **7** | **GPIO 软件片选**（不是 24！spidev 不驱动 native CS） |
| RESET | 16 | GPIO，模块复位（Hobot.GPIO 导不出，驱动已容错走软上电） |
| READY | 13 | GPIO，数据就绪（驱动改用轮询 STATUS，不依赖此脚） |

关键软件配置：

- 自定义 overlay `dtoverlay_spi1_spidev1_x5_rdk`（列在云台 overlay 之后，re-enable SPI1）→ `/dev/spidev1.1`。
- `spidev bufsiz=20480`（`/etc/modprobe.d/spidev.conf` 持久化），整帧用 `xfer3` 单次读。
- SPI 速率 **1MHz**（杜邦走线在 >1MHz 偏 marginal），传感器 fps 7，开 MI48 片上滤波，剔除 -273℃ 死像素。
- 运行参数：`--spi-bus 1 --spi-device 1 --i2c-bus 5 --cs-gpio-pin 7`。

注意事项：

- RDK X5 IO 是 3.3V 逻辑，优先使用 3.3V 给 Thermal-90 供电。
- 不要把任何信号线拉到 5V。
- 接线前关闭 RDK 电源，接线完成后再上电。
- I2C 是总线，可以多设备共享；但需要确认地址不冲突。
- 当前 Thermal-90 地址 `0x40`，AS5600 编码器常见地址 `0x36`，地址不冲突。

## 3. 当前诊断结果

### 3.1 RDK 连接正常

Mac 到 RDK SSH 已验证可用：

```bash
ssh -i .tmp/rdk_codex_key root@192.168.128.10 'hostname; uname -a'
```

实测输出说明 RDK 在线：

```text
ubuntu
Linux ubuntu 6.1.83 ... aarch64
```

### 3.2 I2C 已经确认通

原先执行：

```bash
i2cdetect -y -r 1
```

没有扫到设备，是因为扫错了 bus。

实际应扫描所有 I2C bus：

```bash
i2cdetect -l
for b in /dev/i2c-*; do
  n=${b##*-}
  echo "===== i2c-$n ====="
  i2cdetect -y -r "$n"
done
```

当前实测 Thermal-90 出现在：

```text
/dev/i2c-5
address 0x40
```

关键输出：

```text
----- i2c-5 -----
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

结论：

```text
Thermal-90 的 I2C 供电、SDA、SCL 至少已经工作。
```

### 3.3 SPI 尚未暴露为 spidev

当前执行：

```bash
ls -l /dev/spidev*
```

输出：

```text
ls: cannot access '/dev/spidev*': No such file or directory
```

执行：

```bash
modprobe spidev
ls -l /dev/spidev*
```

仍然没有 `/dev/spidev*`。

进一步检查 sysfs：

```bash
find /sys/bus/spi/devices -maxdepth 2 -type l -o -type d | sort
```

实测存在：

```text
/sys/bus/spi/devices/spi5.0
/sys/bus/spi/devices/spi7.0
```

其中：

```text
spi7.0: 已绑定 spi-nand，不要动
spi5.0: 当前设备树 modalias 是 spi:tcan4x5x，没有绑定 spidev
```

关键检查命令：

```bash
for d in /sys/bus/spi/devices/spi*; do
  echo "----- $d -----"
  cat "$d/modalias" 2>/dev/null || true
  [ -e "$d/driver" ] && readlink "$d/driver" || echo "driver: <none>"
done
```

当前结论：

```text
SPI 物理线暂时不能仅凭 /dev/spidev* 判断。
根因是 RDK 设备树没有把 SPI5 CS0 暴露为 spidev。
```

### 3.4 当前启动 overlay

当前 `/boot/config.txt` 内容：

```text
dtoverlay=gimbal_pwm012_i2c1_x5_rdk
```

这说明当前只加载了云台相关 overlay。

RDK 上已有现成 SPI5 spidev overlay：

```bash
/boot/overlays/dtoverlay_spi5_spidev.dtbo
/boot/overlays/dtoverlay_spi5_spidev.dts
```

其 dts 内容指向：

```text
/soc/a55_apb0/spi@34050000
```

也就是当前看到的 `spi5.0`。

## 4. 下一步硬件总线打通流程

> ⚠️ **本节（4.x）已作废**：当时设想用 `dtoverlay_spi5_spidev` + `spidev5.0`，实测该控制器没路由到 40PIN，行不通。
> 最终用的是 SPI1（`dtoverlay_spi1_spidev1_x5_rdk` + `/dev/spidev1.1`）+ GPIO 软件片选。
> 以下 4.x 内容仅作历史排查记录保留。

### 4.1 启用 SPI5 spidev overlay

在 RDK 上执行：

```bash
cp /boot/config.txt /boot/config.txt.bak-thermal-$(date +%Y%m%d-%H%M%S)
printf '\ndtoverlay=dtoverlay_spi5_spidev\n' >> /boot/config.txt
sync
reboot
```

重启后验证：

```bash
i2cdetect -y -r 5
ls -l /dev/spidev*
```

预期结果：

```text
i2c-5 能看到 0x40
/dev/spidev5.0 或类似 SPI5 spidev 节点出现
```

如果 `/dev/spidev*` 仍然不存在，检查：

```bash
cat /boot/config.txt
dmesg | grep -Ei 'spi|spidev|overlay|dtoverlay' | tail -120
find /sys/bus/spi/devices -maxdepth 2 -type l -o -type d | sort
```

### 4.2 验证 overlay 是否影响云台

因为当前云台使用了 `gimbal_pwm012_i2c1_x5_rdk` overlay，而 Thermal-90 需要增加 `dtoverlay_spi5_spidev`，重启后必须验证云台相关接口仍然存在。

检查 PWM：

```bash
ls -l /sys/class/pwm
```

检查 I2C：

```bash
i2cdetect -l
```

重点确认：

- `/dev/i2c-5` 仍存在。
- `/dev/i2c-1` 仍存在。
- Thermal-90 `0x40` 仍在 `/dev/i2c-5`。
- 不要动 `spi7.0`，它绑定的是系统 SPI NAND。

### 4.3 如果 SPI overlay 与云台 overlay 冲突

如果增加 `dtoverlay_spi5_spidev` 后导致云台 PWM 或 I2C 异常，先恢复：

```bash
cp /boot/config.txt.bak-thermal-YYYYMMDD-HHMMSS /boot/config.txt
sync
reboot
```

然后采用更保守方案：

1. 保留 `gimbal_pwm012_i2c1_x5_rdk`。
2. 新建一个只修改 `spi5` 的 Thermal-90 overlay。
3. 明确禁用 base dts 中 `tcan4x5x@0`，再添加 `spidev@0`。

目标是只影响：

```text
/soc/a55_apb0/spi@34050000
```

不要修改：

```text
spi7.0
云台 PWM 使用的 spi@34010000 / spi@34020000 相关复用
```

## 5. Thermal-90 软件接入路线

### 5.1 第一阶段：独立热成像探测脚本

先不要直接改现有 YOLO live detector。应先写一个最小热成像测试脚本，只验证 Thermal-90 能稳定读数据。

建议新增：

```bash
rdk_x5_lab_detector_deploy_20260603/runtime/thermal90_probe.py
```

功能：

- 打开 `/dev/i2c-5`，访问地址 `0x40`。
- 打开 `/dev/spidev5.0` 或实际 spidev 节点。
- 通过 I2C 初始化 Thermal-90。
- 通过 SPI 读取一帧热数据。
- 输出最高温、最低温、平均温。
- 保存热图伪彩色图片。

建议命令：

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
python3 runtime/thermal90_probe.py \
  --i2c-bus 5 \
  --i2c-address 0x40 \
  --spi-dev /dev/spidev5.0 \
  --save-path thermal_probe.jpg
```

验收标准：

```text
能连续读取 100 帧。
最高温/最低温数值随手靠近或热源靠近而变化。
能保存一张非空 thermal_probe.jpg。
```

### 5.2 第二阶段：热源热点检测

在独立热图数据稳定后，新增热点检测逻辑。

建议输出结构：

```json
{
  "timestamp": 0.0,
  "frame_id": 123,
  "ambient_temp_c": 28.5,
  "max_temp_c": 68.2,
  "hotspots": [
    {
      "bbox_thermal": [12, 8, 30, 25],
      "max_temp_c": 68.2,
      "mean_temp_c": 55.4,
      "area_px": 210,
      "level": "HIGH"
    }
  ]
}
```

初始规则建议：

| 条件 | 等级 |
| --- | --- |
| `max_temp_c >= 70` | HIGH |
| `max_temp_c >= 55` | MEDIUM |
| `max_temp_c >= ambient + 20` | MEDIUM |
| `max_temp_c >= ambient + 12` | LOW |

需要根据现场实测调整，尤其注意热成像模块自身温漂和环境温度变化。

### 5.3 第三阶段：可见光与热图配准

Thermal-90 和 CSI 摄像头视角不同，必须做坐标映射。

最低可行方案：

1. 固定两个摄像头相对位置。
2. 用电烙铁或热源在画面多个位置采样。
3. 保存 RGB 图和 thermal 图。
4. 人工标注对应点。
5. 估计单应性矩阵或仿射矩阵。
6. 保存到配置文件。

建议配置文件：

```bash
rdk_x5_lab_detector_deploy_20260603/config/thermal_alignment.yaml
```

示例：

```yaml
thermal_to_rgb:
  method: homography
  matrix:
    - [1.0, 0.0, 0.0]
    - [0.0, 1.0, 0.0]
    - [0.0, 0.0, 1.0]
rgb_size: [1920, 1072]
thermal_size: [90, 90]
```

验收标准：

```text
热源热点框映射到可见光画面后，能落在真实热源附近。
误差先控制在可见光画面 5%-10% 范围内即可，后续再细化。
```

### 5.4 第四阶段：与现有 live detector 融合

核心文件：

```bash
rdk_x5_lab_detector_deploy_20260603/runtime/lab_mipi_web_detector.py
```

建议不要把所有逻辑都塞进这个文件，而是拆出模块：

```bash
runtime/thermal90_reader.py
runtime/thermal_hotspot.py
runtime/multimodal_fusion.py
runtime/evidence_store.py
```

职责：

| 文件 | 职责 |
| --- | --- |
| `thermal90_reader.py` | Thermal-90 I2C/SPI 初始化与帧读取 |
| `thermal_hotspot.py` | 温度矩阵到热点框、温度统计、风险等级 |
| `multimodal_fusion.py` | YOLO 检测框和热源框融合 |
| `evidence_store.py` | 保存 RGB、thermal、fused、JSON 证据 |
| `lab_mipi_web_detector.py` | 主循环、网页服务、MJPEG 输出 |

融合规则初版：

| 可见光结果 | 热成像结果 | 输出风险 |
| --- | --- | --- |
| `soldering_iron` + 高温 | 有重叠热点 | HIGH |
| `hot_air_gun` + 高温 | 有重叠热点 | HIGH |
| `welding_gun` + 高温 | 有重叠热点 | HIGH |
| `exposed_wire` + 热点 | 有重叠热点 | HIGH |
| `power_strip` + 异常发热 | 有重叠热点 | MEDIUM/HIGH |
| `plug` + 异常发热 | 有重叠热点 | MEDIUM/HIGH |
| `power_adapter` + 异常发热 | 有重叠热点 | MEDIUM/HIGH |
| `wire_bundle` + 异常发热 | 有重叠热点 | HIGH |
| YOLO 未识别 + 明显热点 | 独立热点 | UNKNOWN_HOTSPOT |
| YOLO 识别危险物但无高温 | 无热点 | VISUAL_RISK |

## 6. 网页与证据保存

### 6.1 网页展示目标

现有网页：

```text
http://192.168.128.10:8080/
```

需要增加：

- 顶部风险横幅。
- 当前最高温度。
- 当前风险等级。
- 可见光检测框。
- 热源热点框。
- 融合后的风险说明。

建议颜色：

| 风险 | 颜色 |
| --- | --- |
| HIGH | 红色 |
| MEDIUM | 橙色 |
| LOW | 黄色 |
| UNKNOWN_HOTSPOT | 紫色 |
| 普通 YOLO 目标 | 蓝色或绿色 |

### 6.2 证据帧保存

检测到 MEDIUM 或 HIGH 时保存证据。

建议目录：

```bash
rdk_x5_lab_detector_deploy_20260603/evidence/
```

单次事件建议保存：

```text
20260607_153000_HIGH_rgb.jpg
20260607_153000_HIGH_thermal.jpg
20260607_153000_HIGH_fused.jpg
20260607_153000_HIGH_event.json
```

JSON 示例：

```json
{
  "timestamp": "2026-06-07T15:30:00+08:00",
  "risk_level": "HIGH",
  "reason": "soldering_iron overlaps high-temperature hotspot",
  "max_temp_c": 73.4,
  "visual_detections": [
    {
      "label": "soldering_iron",
      "score": 0.72,
      "bbox_rgb": [320, 240, 500, 430]
    }
  ],
  "thermal_hotspots": [
    {
      "bbox_thermal": [20, 18, 35, 31],
      "bbox_rgb": [330, 245, 510, 420],
      "max_temp_c": 73.4,
      "level": "HIGH"
    }
  ]
}
```

### 6.3 证据保存限流

避免每秒保存大量图片。

建议规则：

```text
同一风险等级每 5 秒最多保存 1 次。
HIGH 风险可以立即保存。
MEDIUM 风险需要连续出现 2-3 帧后保存。
```

## 7. 测试与验收流程

### 7.1 总线验收

命令：

```bash
i2cdetect -y -r 5
ls -l /dev/spidev*
```

通过标准：

```text
i2c-5 出现 0x40。
出现 SPI5 对应 spidev 节点。
```

### 7.2 Thermal-90 单模态验收

命令：

```bash
python3 runtime/thermal90_probe.py \
  --i2c-bus 5 \
  --i2c-address 0x40 \
  --spi-dev /dev/spidev5.0 \
  --save-path thermal_probe.jpg
```

通过标准：

```text
能连续读取帧。
温度随热源变化。
保存的热图非空。
```

### 7.3 多模态融合验收

测试物品：

- 电烙铁。
- 热风枪。
- 插排。
- 电源适配器。
- 普通导线。
- 线束。
- 裸线模拟件。
- 无热源普通背景。

测试记录内容：

```text
测试时间
测试物品
热源状态
可见光检测结果
热成像最高温
融合风险等级
是否保存证据
误报/漏报说明
截图或证据文件路径
```

通过标准：

```text
高温电烙铁、热风枪、焊枪能稳定标为 HIGH。
正常冷态插排/适配器不应频繁误报 HIGH。
异常高温插排/适配器至少标为 MEDIUM。
未知热源能以 UNKNOWN_HOTSPOT 提示。
网页预览和证据保存同时可用。
```

## 8. 当前待办清单

### 8.1 立即要做（已全部完成 ✅，2026-06）

- [x] 启用 SPI（实际用 `dtoverlay_spi1_spidev1_x5_rdk` 而非 spi5）。
- [x] 验证 `/dev/i2c-5` 上有 `0x40`。
- [x] `/dev/spidev1.1` 出现。
- [x] 确认不影响云台 PWM/I2C（pwmchip0/2/4/6 存活）。
- [x] 热成像单模态读帧 + RGB/热成像融合 Web/ROS2 节点均已跑通。

### 8.2 短期开发

- [ ] 新增 Thermal-90 最小探测脚本。
- [ ] 确认 Thermal-90 的 Python 初始化流程和 SPI 数据格式。
- [ ] 保存第一张热成像伪彩色图。
- [ ] 实现热点检测和温度阈值规则。
- [ ] 保存热源事件 JSON。

### 8.3 中期融合

- [ ] 固定 Thermal-90 与 CSI 摄像头的机械位置。
- [ ] 采集 RGB/thermal 对齐样本。
- [ ] 生成 `config/thermal_alignment.yaml`。
- [ ] 把热源框映射到 RGB 画面。
- [ ] 实现 YOLO 框与热点框融合。
- [ ] 修改网页显示风险横幅和温度信息。
- [ ] 实现中/高风险证据保存。

### 8.4 后期优化

- [ ] 做现场多物品测试。
- [ ] 调整温度阈值和持续帧数。
- [ ] 降低误报。
- [ ] 加入离线回放测试。
- [ ] 整理答辩演示流程和测试视频。

## 9. 风险点与处理建议

### 9.1 SPI overlay 与云台 overlay 冲突

风险：

```text
两个 overlay 同时修改 40PIN 复用，可能影响云台或 SPI。
```

处理：

```text
每次修改 /boot/config.txt 前备份。
重启后同时验证 Thermal-90 和云台。
如果冲突，创建专用 overlay，只启用 spi5 spidev。
```

### 9.2 I2C bus 被多个进程同时访问

风险：

```text
云台编码器和 Thermal-90 均使用 I2C，若进程高频访问同一 bus，可能造成延迟或冲突。
```

处理：

```text
确认实际 bus 分布。
Thermal-90 使用 /dev/i2c-5。
云台 AS5600 若也使用 i2c-5，需要控制访问频率或迁移其中一个设备。
```

### 9.3 热成像与可见光视角不一致

风险：

```text
热源热点框映射到 RGB 画面后位置偏移。
```

处理：

```text
固定机械结构。
做至少 6-10 个点的标定。
先接受粗配准，再逐步优化。
```

### 9.4 温度阈值误报

风险：

```text
环境温度变化、反光、热源残留会导致误报。
```

处理：

```text
不要只用绝对温度。
同时使用 ambient delta、热点面积、持续帧数、YOLO 类别融合。
```

## 10. 推荐执行顺序

严格按下面顺序推进：

1. 先打通 I2C 和 SPI。
2. 再做 Thermal-90 单模态读帧。
3. 再做温度统计和热点检测。
4. 再做 RGB/thermal 配准。
5. 再做多模态融合规则。
6. 再接入现有网页。
7. 最后做证据保存和现场验证。

不要在 SPI 未出现 `/dev/spidev*` 前开始写复杂融合逻辑。当前最关键的工程阻塞点是：

```text
启用 SPI5 spidev 并验证 Thermal-90 SPI 数据读取。
```

