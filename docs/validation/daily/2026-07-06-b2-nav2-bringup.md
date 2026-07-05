# B2 Nav2 上板 bring-up 验证(部分) — 2026-07-06

实验室现场,SSH 驱动 RDK。执行 plan `docs/superpowers/plans/2026-07-06-b2-nav2-navigation.md` 的 Task 5。

## ✅ 已验证(nav 软件栈)

- **部署**:`rsync chassis_bringup → RDK` + `colcon build --packages-select chassis_bringup` 成功;`nav.launch.py` 与 `send_goal` console 脚本均装好。
- **一键起栈**:`ros2 launch chassis_bringup nav.launch.py`(transient `navstack-tmp`)把整套节点起来了:
  `/amcl /bt_navigator /controller_server /planner_server /map_server /velocity_smoother /behavior_server /ekf_filter_node /lslidar_driver_node /stm32_bridge`。
- **/scan 在流**(python 直订到);`map_server` 载入 `/root/maps/lab_map.yaml`。
- **/cmd_vel 接线正确**:发布者 = `velocity_smoother`(平滑后的 controller 输出)+ `behavior_server`(恢复行为,与跟随时间互斥),这是**标准 nav2_bringup Humble 接法**,bridge 订阅 `/cmd_vel` 拿到的正是平滑控制输出——**无需额外 remap**(plan Task 3 注释里的 remap 顾虑可去掉)。
- `map→odom` 未出现属**定位前的正常现象**(AMCL 未给初始位姿前本就没有)。

## ⛔ 被阻塞(顺延)—— STM32 黑药丸反复挂死

- 本次 bring-up 中 **STM32 空闲状态下反复挂死**(裸读串口 0 字节),今天累计挂 5–6 次。
- 后果:**/odom 不流** → EKF 无轮式里程 → 无法定位、无法发目标、无法跑动。
- **未做**(等供电修好):AMCL 定位收敛、发近目标自主到达 ≤10cm、动态避障重规划。
- **决策(用户)**:先稳住黑药丸供电,再做驱动验证。理由:黑药丸空闲都挂,若**驱动中途挂死**,PWM 定时器可能停在最后值 → 电机不受控 runaway,须物理断电才停——在这么不稳的板上跑自主导航有安全风险。

## 根因与下一步

- 根因:黑药丸 USB 供电不稳 / 功率地噪声耦合(见 [[runaway-fix-and-blackpill-hang]]、[[pcb-breakout-and-repo-path]])。这已是实地跑动的**硬阻塞**。
- 下一步:①黑药丸独立稳压供电 / 功率地粗线直连电池负极 / 换好 USB 线;②供电稳住后重跑 Task 5 Step 5–7(定位→发目标→避障);③最终 whole-branch review。
