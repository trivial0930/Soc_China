# 2026-06-27 PCB 真机验线 + App 遥控 + 雷达反应式避障(A 阶段)

环境:RDK X5(`root@192.168.128.10`),STM32 经 USB CDC(`/dev/serial/by-id/...Chassis_VCP...`)。
仓库路径注意:**Desktop 那份被 macOS TCC 拦(EPERM),改用 `~/projects/Soc_China`**(含全部改动)。

## 1. PCB 转接板真机验线 ✅
新做的黑药丸转接板首装,逐项验并修了初装接线错:
- **右侧两电机线反** → 对调修;**左侧两电机线反** → 对调修;过程中还排掉右侧控制线接错、卡轮、黑药丸供电不稳致 USB 掉。
- 验法:开环 ff-only(`pid_tune --kp 0 --ki 0`)逐侧驱动看编码器符号 + 目视转向;架空逐轴。
- **最终(架空)**:+vx 四轮全正匹配;+vy LF+ RF− LR− RR+;+wz LF+ RF− LR+ RR− —— 四轮×三轴全对,接线 100% 正确(与固件一致)。
- 落地:**前进/旋转正常**;横移弱(滚子+地面摩擦,清滚子后右侧能动,临界堵转——非缺陷,光滑地面即可)。
- 教训:一侧一次通电时,黑药丸要**独立稳定供电**(别跟板电一起切,否则 USB CDC 掉、全断);掉线/卡轮/反复重启严重拖慢联调。

## 2. App 遥控 + 雷达本地安全层(反应式避障 A 阶段)✅
设计见 `docs/superpowers/specs/2026-06-27-app-teleop-lidar-safety-design.md`(brainstorming 流程产出)。

**链路**:App 摇杆(~10Hz)→`POST /api/robot/teleop`→后端存最新→RDK `teleop_receiver` 10Hz `GET`→`/cmd_vel_teleop`→`lidar_safety` 门控→`/cmd_vel`→stm32_bridge→车;安全状态 `/safety/status`→回传后端→App 显示。

**RDK 新包 `teleop_safety`**(`rdk_x5/ros2_ws/src/teleop_safety`):
- `gate.py` 纯门控逻辑(host 单测 `tests/test_teleop_gate.py` **11/11**):
  按平移方向 heading 取扇区最近障碍;`<0.30m` 砍平移、`<0.60m` 线性减速、旋转 wz 恒透传、deadman 0.5s。
- **near_masks 近场自遮挡屏蔽**(关键修复):雷达正后方 30cm 内是车体(实测),`near_masks=[180,45,0.30]` → 后方 <30cm 丢弃(车体)、**≥30cm 仍避障**;解决"倒退被自身线缆永久挡死"。
- `lidar_safety_node`(纯 ROS)、`teleop_receiver_node`(网络,urllib 轮询)、launch、config。
- **后端/前端由另两个 agent 实现**(prompt:`app/BACKEND_PROMPT_teleop.md`、`app/FRONTEND_PROMPT_teleop.md`):后端加 `POST/GET /api/robot/teleop` + `/status`(低延迟,与 2s 命令队列分开);前端加遥控页(虚拟摇杆+STOP+状态条+deadman)。

**联调实测(架空)**:全链路通——curl/App 灌速度→`/cmd_vel` 跟随;前进遇障减速/停;倒退车体屏蔽、30cm 外避障;旋转放行;deadman 停发即 0;**App 摇杆遥控成功**。
- 坑:中途"摇杆突然失效"= 后端 age 6.5s,**App 停发**(前端 10Hz 循环挂了),机器人端无恙——若复发交前端修(POST 失败不中断循环)。

## 3. 三重 deadman / 安全
前端松手发 0 → 后端 age_ms → RDK staleness/cmd_timeout → stm32_bridge 0.5s 超时。雷达避障纯本地,网络延迟/断不影响安全。

## 4. 待办
1. **黑药丸独立稳压供电**(根治反复失联;#8 加固一并)。
2. 后方 `near_masks` 角度/距离按实际线缆微调(现 ±45°/30cm)。
3. **B 阶段**:slam_toolbox 建图→存图→Nav2(AMCL+MPPI omni)自主导航。
4. 横移在光滑硬地面复验。
