# 云台 FOC 标定 — 2026-06-12

## 背景

云台之前"经过测试能转动"，但实际**只会来回摆动、从不收敛到目标**。诊断发现：闭环位置控制从未真正工作，根因是 **FOC 换相参数从未标定**——`gimbal.yaml` 里 `pole_pairs=7、phase_offset_deg=0` 都是错的（占位值）。换相不对齐 → 力矩方向错乱 → 一使能就冲向限位（`invert` 正反都修不了）。

接线已确认无松动、无接错（用户核对），所以不是接线问题，就是标定缺失。

## 方法

新增开环对齐标定工具 `rdk_x5/scripts/gimbal_foc_calibrate.py`：
- 给电机施加**静止**电压矢量（转子磁吸对齐到该电角度并保持，不会跑飞——比闭环安全）；
- 扫描施加的电角度 0→360°，每步读 AS5600 机械角；
- 线性拟合 `applied_elec = 方向·pole_pairs·mech + C`，得出换相方向 / 极对数 / phase_offset；
- 带安全窗口（编码器超界自动 ramp-down）。

## 结果（闭环实测验证）

| 轴 | pole_pairs | phase_offset_deg | 方向 | 闭环表现 |
| --- | --- | --- | --- | --- |
| pan | **8**（原 7） | **66**（原 0） | +1 | 收敛，稳态误差 ~3-7° |
| tilt | **7** | **138**（原 0） | +1 | 收敛，稳态误差 ~10-19°（重力影响） |

- pan：目标 25/55/40 → 停在 32/50/43，**转过去并稳住，不再跑飞**。
- tilt：目标 -90/-60/-100 → 停在 -100/-79/-102，同样收敛（往上抬欠到位是重力，P 控制无重力补偿）。

注：开环法对 pole_pairs 受齿槽效应影响有噪声（pan 端点法 ~8.6、tilt ~7），但取整后的值经**闭环实测确认够用**（能收敛）。

## 已保存

- `rdk_x5/ros2_ws/src/gimbal_laser/config/gimbal.yaml`：pan_pole_pairs=8 / pan_phase_offset_deg=66 / tilt_phase_offset_deg=138。
- `gimbal_controller_node.py` 默认值同步更新。
- 板上 `colcon build gimbal_laser` 已重建。

## 遗留（云台后续 TODO）

1. **稳态误差调参**：P-only 控制器有 3-19° 静差。可调 `proportional_gain`/`angle_deadband_deg`，或加积分项 / tilt 重力前馈。
2. **编码器零点 homing**：当前 `zero_deg=0` 不对应机械中心（实测 pan~27°、tilt~-100°，tilt 已超出配置范围 [-30,45]）。需把云台摆到机械中心读编码器、写入 `zero_deg`，让角度范围有意义。
3. 之后即可接入 **检测→云台对准**（订阅 `/hazard/status` 的危险物像素位置 → 换算 pan/tilt → 发 `/gimbal/target_angle`）。
