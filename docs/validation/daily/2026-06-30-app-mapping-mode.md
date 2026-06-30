# 2026-06-30 App 建图模式 上板集成验证

环境:RDK X5(`root@192.168.128.10`),分支 `feat/chassis-bringup-stack`。
SDD 实现 Task 1–7 完成(host 单测全过),本日做 Task 6 上板集成验证。

## 部署
rsync 3 个 py(mode_switch / command_receiver / command_receiver_node)+ 3 个脚本到 `/root/Soc_China`,`colcon build --packages-select inspection_manager`(8s 通过)。

## 上板发现并修复的 2 个真机 bug
1. **`set -u` 与 ROS setup.bash 冲突**:脚本 `set -u` 后 `source /opt/ros/humble/setup.bash` 触发 `AMENT_TRACE_SETUP_FILES: unbound variable` → 整脚本 exit 1。修:`set -u` 移到 source ROS 之后(3 个脚本)。
2. **on.sh 校验用错节点名**:用了 launch 动作名 `async_slam_toolbox_node / stm32_bridge_node / ekf_node`,但 `ros2 node list` 返回 ROS 节点名 → 永远校验失败。修:改为 `slam_toolbox / stm32_bridge / ekf_filter_node`(`lslidar_driver_node` 不变)。
(commit `3b257b19`)

## 验证结果
- **mapping_mode_on.sh ✅** `ON_EXIT=0`「mapping stack up after 1s」:
  - 重负载子集全停(llama-server / voice_node / asr_node / cognition_node)✅
  - **命令通道三件全在**(uplink / command_receiver / acceptance)——核心安全属性 ✅
  - 建图栈 4 节点齐:`lslidar_driver_node / slam_toolbox / stm32_bridge / ekf_filter_node` ✅
  - llama 释放 ~3GB 内存(avail 3271→6277,跨多次切换)✅
- **mapping_mode_off.sh ✅**(两次)`OFF_EXIT=0`「normal stack restored」:建图栈干净清除(串口释放、stm32_bridge 无残留)、重负载全恢复、命令通道全程在 ✅
- **ModeController 上板冒烟 ✅**:`current_mode=normal`、正常模式 `save_map` 被拒「仅建图模式可存图」、非法 mode 被拒「非法模式:banana」——Python→脚本这层真机接通。
- **save_map ⏳ 顺延**:静止 + 刚起 slam 时 map_saver_cli 与 slam_toolbox/save_map 服务**都失败且无文件**;slam 日志明示 "Cannot save map, no map yet received on topic /map"。根因:车全程静止 → 扫描不过 slam 最小位移阈值 → 从不发布 /map。**非脚本 bug**(命令标准、服务存在);真实建图(开车绕)时 /map 会持续发布,save_map 即可用。**存图最终验证顺延到实地建图(#24)**。

## 未做(明确)
- 完整 App→后端命令队列→command_receiver(新代码)→ModeController→脚本 的活体端到端:command_receiver 仍是开机旧代码(已 colcon build 但未重启该常驻节点)。各环节分别已验(脚本上板过、ModeController 上板冒烟过、dispatch+wiring host 测+py_compile+review 过),仅"活体 command_receiver 调用"这一缝未连跑。可在 App 接好后顺带验。
- save_map 真图验证(#24 实地建图时)。

## 坑/备注
- Mac↔RDK SSH 本轮反复抖动(长连接 ~40s 会被中途掐断),改用"detached 后台脚本写日志 + 短连接轮询"才稳。
- 验证用的临时 wrapper/log 已清理;RDK 收尾回到正常模式(语音栈在跑)。

关联:`docs/superpowers/specs/2026-06-30-app-mapping-mode-design.md`、`docs/superpowers/plans/2026-06-30-app-mapping-mode.md`、`docs/ops/lab_mapping_procedure.md`。
