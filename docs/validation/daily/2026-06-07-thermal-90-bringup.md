# Thermal-90 (SenXor MI48) 上板调试记录 — 2026-06-07

热成像与 RGB 多模态融合上板验证。**Phase 1–4(路径A) 全部打通：RGB+热成像融合检测器在板上实时运行。**

## ⚠️ 板子掉线（2026-06-07 调试末尾）

融合检测器跑通并验证后，板子整机掉线（ping 100% 丢包、SSH 不通，~5 分钟未自恢复），
疑似在 摄像头+热成像+BPU 持续负载下硬挂或掉电/掉网。**只读 SSH 检查不会导致此问题。**
需**物理重启**板子。恢复步骤：

1. 给 RDK X5 断电重上电（或按复位）。等待约 20–30s 网络恢复（`ping 192.168.128.10`）。
2. 持久化配置重启后仍在（SPI1 overlay、`spidev bufsiz`），无需重做。
3. 重新拉起检测器（见下方启动命令）。检测器**未设开机自启**（故意：先确认掉线原因，避免崩溃自启循环）。
4. 若再次掉线：降低负载排查——`STREAM_FPS=1` 启动、或先 `MOCK_THERMAL=1` 只验证（排除热成像 SPI 负载），
   观察是否仍挂；也检查供电是否充足（热成像 3.3V + 摄像头 + BPU 同时工作）。

## 🟢 端到端融合已上线

- 检测器：`runtime/lab_thermal_fusion_web_detector.py`，Web 在 `http://192.168.128.10:8080/`。
- 实测日志：`INFO: plug (cold 33C)`、`INFO: wire_bundle (cold 35C)` —— RGB/YOLO 检测危险物 +
  热成像测温 + `HazardPipeline` 分级（物体类别×温度→严重度）全链路工作；左 RGB(风险框+横幅)/右 热成像伪彩 双画面。
- 热成像清理：剔除偶发 raw-0(-273℃) 死像素（<-40℃ 用有效中位数替换）+ 3×3 中值滤波；面板用 2/98 百分位归一化。
- **启动（务必按此，勿用 `pkill -f`，会偶发掐断 SSH）**：
  ```bash
  for p in $(pgrep -f "[l]ab_thermal_fusion_web_detector"); do kill -9 $p; done   # 先停旧实例
  cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
  setsid bash runtime/run_thermal_fusion_web_detector.sh </dev/null >/tmp/fusion.log 2>&1 &
  ```
  无传感器先看 UI：在上面命令前加 `MOCK_THERMAL=1`。
- **遗留（需人工/后续）**：RGB↔热成像单应仍是占位（纯缩放），物体框映射到热区是近似的，
  逐物体温度仅近似准确；需用 `rdk_x5/scripts/thermal_rgb_calibrate.py` 做一次点状热源标定（交互式，需到现场）。

## Phase 1 关键点（能读到正常热成像）

## ✅ 最终工作配置（先看这里）

读取命令（板上）：
```bash
cd /root/lab_detector_deploy
LOGLEVEL=ERROR PYTHONPATH=/root/lab_detector_deploy/thermal_detector:/root/pysenxor-master \
python3 thermal_capture_test.py --spi-bus 1 --spi-device 1 --i2c-bus 5 --cs-gpio-pin 7 \
  --frames 12 --save-png /tmp/thermal.png
```
关键点（缺一不可）：
1. **SPI1 overlay**：`/boot/overlays/dtoverlay_spi1_spidev1_x5_rdk.dtbo`，在 `config.txt` 里列于云台 overlay 之后，
   re-enable `spi@34010000`+`spidev@1` → `/dev/spidev1.1`（MOSI/MISO/SCLK 仍在物理 19/21/23）。
2. **GPIO 软件片选**：spidev 在本 SoC 不驱动 CS，故 `SS` 从 pin24 改接 **BOARD 7**，spidev `no_cs`，读帧时 GPIO7 全程拉低。
3. **SPI 4MHz**：31.2MHz 会因软件 CS 抖动导致位错（读出 -120℃）；4MHz 干净。
4. **MI48 片上滤波**：`enable_filter(f1,f2)`，否则原始帧噪点很大（看似随机）。
5. **bufsiz=20480**：`/etc/modprobe.d/spidev.conf` 持久化；用 `xfer3` 单次满帧读（CS 全程保持）。
6. 跳过 header CRC（`parse_header=False`）：本固件 CRC 校验误报，数据本身正确（多速率验证温度稳定）。

实测：min~20℃ / max~42℃，热图能看到人体/热物轮廓（红）与背景（蓝）。
`SENS_FACTOR 0x6b` 告警可忽略。

## 历史排查（保留用于追溯）

热成像与 RGB 多模态融合的 Phase 0–1 上板验证。最初卡在 SPI 引脚未路由 + spidev 不驱动 CS。

## 结论（先看这里）

- ✅ **I2C 完全正常**：`/dev/i2c-5` 上 `0x40` 可读出完整相机信息
  （CAMERA_ID `161301042b2b`、SN、FW `3.2.13`、MAX_FPS 25.5、fpa_shape (80,62)）。
- ✅ **DATA_READY 正常**：`get_status()` 返回 `0x12`（含 DATA_READY=0x10），芯片在出帧。
- ✅ 软件栈全部就绪并通过单测（驱动纯逻辑/融合/配置/管线，59 测试绿）；Pysenxor+crcmod 已部署。
- ❌ **SPI 读帧全 0（MISO 线无数据）**：根因是 **`/dev/spidev5.0` 这个控制器没有引脚路由**。

## 根因（device-tree / pinmux）

- 系统只有一个 spidev 节点：`spidev5.0 -> 34050000.spi`。
- `34050000.spi` 在 `pinmux-pins` 里**没有任何 claimed 引脚**（即没 mux 到 40-pin 任何脚）→ 读它当然全 0。
- 另一个 `35000000.spi` 是 **QSPI Flash**（`hsio_qspi_*`），不是 40-pin。
- 40-pin 上 SPI 能力的 pad 现状：
  - `lsio_spi2_*` pad 被 **PWM 占用**（`34140000.pwm`/`34150000.pwm`，即云台 PWM）。
  - `lsio_spi1_*` pad **未占用**（没有绑定 spidev 驱动）。
  - `lsio_spi0_*` pad 部分被 cam/gpu 占用。
- py-spidev 3.7：`xfer/xfer2` 单次上限 4096B，`xfer3` 可读满帧（已在驱动用 xfer3）——但这不是根因，根因是引脚没路由。
- `spidev bufsiz` 已临时调到 20480（`rmmod spidev && modprobe spidev bufsiz=20480`），重启会丢，需要持久化。

## 接线（按 pinmap，物理脚）

VCC→1(3.3V)、GND→6、SDA→3、SCL→5、MOSI→19、MISO→21、CLK→23、SS→24、RESET→16、READY→13。
（接线本身自洽：19/21/23/24 是同一组 SPI 的 MOSI/MISO/SCLK/CSN。问题在于这组 pad 当前没 mux 给一个能用的 spidev。）

## 根因升级（overlay 级，已定位）

`/boot/config.txt` 启用了两个 overlay：

- `dtoverlay=gimbal_pwm012_i2c1_x5_rdk`：**显式 disable 了 `spi@34010000`(SPI1) 与 `spi@34020000`(SPI2)**，
  并 enable `pwm@34140000/34150000/34160000`（PWM0/1/2）。即云台 overlay 把 40-pin 的 SPI 控制器关掉、改成 PWM。
- `dtoverlay=dtoverlay_spi5_spidev`：enable `spi@34050000`(SPI5) 为 spidev → 这就是 `spidev5.0`，
  但 SPI5 没有 pinmux 到 40-pin（dead node），所以读全 0。

**结论：热成像接的 19/21/23/24 属于 SPI1/SPI2，而它们被云台 overlay 关掉了；spidev5.0(SPI5) 又不在这些脚上。
故 40-pin 上当前没有可用 SPI。这是云台 PWM 与热成像 SPI 的外设/引脚冲突，需先决定引脚分配再改 overlay（要重启）。**

## 进展：SPI1 已启用（overlay 修复，无需改线）

板子是 **RDK X5 V1.0**，其引脚表里 **SPI1 = BOARD 19/21/23（MOSI/MISO/SCLK）+ 24=SPI1_CSN1** ——
正好就是热成像现有接线，**无需改线**。已做：
- 新 overlay `/boot/overlays/dtoverlay_spi1_spidev1_x5_rdk.dtbo`（re-enable `spi@34010000` + `spidev@1`，
  禁用 bmi08a@1/bmi08g@0），在 `config.txt` 里列在云台 overlay 之后覆盖其 disable。
- `/etc/modprobe.d/spidev.conf` = `options spidev bufsiz=20480`（持久化，重启后 20480）。
- 重启后：`/dev/spidev1.1`(`34010000.spi`, CSN1=pin24) 出现；pinctrl 确认 SPI1 已 mux 到 19/21/23/24；
  云台 PWM(pwmchip0/2/4/6) 与 i2c 不受影响。
- 备份：`/boot/config.txt.bak-thermal-spi1-20260607`。

**仍未解决**：即便 SPI1 已正确 mux 到引脚，`spidev1.1` 的 MISO 原始读取仍**全 0**（xfer2/xfer3/readbytes 都是 0）。
I2C 完好（能读相机信息）、SPI 已 mux、DATA_READY 正常 → 嫌疑收窄到：**(a) MISO(pin21) 接触不良/接错**，
或 **(b) spidev 用户态在本 SoC 上不驱动 CS**（Pysenxor 官方明确警告新内核如此，需用 GPIO 当 CS）。
本板 Hobot.GPIO 仅 BOARD 7 可驱动 → 若是 (b)，把 SS 从 pin24 改接 BOARD 7 + spidev `no_cs` + GPIO7 软件片选。

## 待解决：在 40-pin 启用一个真正路由到 19/21/23/24 的 SPI

需要板级配置（device-tree overlay / RDK 配置工具，类似 `srpi-config` 的 Enable SPI），让物理 19/21/23/24 这组
SPI pad mux 到一个 SPI 控制器并暴露为 spidev 节点。要点：

1. **启用 40-pin SPI overlay**：用 RDK X5 的配置工具/设备树开启 SPI，生成对应 spidev（很可能**不是** `spidev5.0`）。
2. **解决与云台 PWM 的冲突**：`lsio_spi2_*` pad 现被云台 PWM 占用。若热成像 SPI 与云台 PWM 抢同一组 pad，二者不能共存。
   方案：把热成像 SPI 放到未占用的 `lsio_spi1_*` 那组对应的物理脚（需相应改接线），或重新分配云台 PWM 脚位。
   → 这是一次**引脚分配的取舍**，需要结合云台现有占用（见 `gimbal.yaml` / `gimbal_control_flow.md`）统一规划。
3. 启用后用 `thermal_capture_test.py --spi-bus <新> --spi-device <新>` 重测；正常应看到手心~30℃、烙铁高温。

## 备选：GPIO 软件片选（若 native CS 仍不可用）

Pysenxor 官方示例在新内核上用普通 GPIO 当 CS（不是 SPI 原生 CE）。本板实测 Hobot.GPIO **仅 BOARD 7 可驱动**
（其余多被占用/未映射）。若启用 SPI 后 CS 仍无效，可：SS 改接 BOARD 7，spidev 设 `no_cs`，读帧时用 GPIO7
全程拉低（active-low）。驱动已预留 `xfer3` 单次满帧读法，便于此扩展。

## 已部署到板上的内容

- `/root/pysenxor-master`（Pysenxor 1.4.1 + 内置 `crcmod` 纯 python 包）
- `/root/lab_detector_deploy/thermal_detector`（融合/驱动包）
- 运行需 `PYTHONPATH=/root/lab_detector_deploy/thermal_detector:/root/pysenxor-master`

## SSH/供电备注

- 公钥已装，免密 SSH 可用（`root@192.168.128.10`）。
- VCC 接 3.3V 供电充足（I2C 枚举正常），**无需改 5V**。
