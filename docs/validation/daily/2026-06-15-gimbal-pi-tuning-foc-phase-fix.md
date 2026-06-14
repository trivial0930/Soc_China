# 云台 PI 调参 + 修复 homing 引入的 FOC 换相 bug — 2026-06-15

## 背景

`0b7da11`(2026-06-12 homing)把编码器 `zero_deg` 重定到机械中心,但**漏改了 FOC 换相的 `phase_offset`**。调 tilt 稳态误差时发现大角度/某方向会失稳、反向甩,顺藤摸瓜定位到这个 bug。本次同时:① 修 FOC 换相参考;② 把纯 P 升级为 PI 消除重力静差。

## Bug:homing 打断了 FOC 换相参考

换相公式 `electrical = current_deg·pole_pairs + phase_offset`,其中 `current_deg` 是编码器读数。

- FOC 标定(`gimbal_foc_calibrate.py`)用的是**原始角**(`zero_deg=0`)。
- homing 后控制器喂进去的是**归零角** `raw − zero_deg`。
- 于是换相被恒定偏了 `zero_deg·pole_pairs` 电角度,`phase_offset` 没补偿 → 力矩效率下降、大幅移动时方向反转 → 闭环失稳。

**修正**:`phase_offset_new = phase_offset_old + zero_deg·pole_pairs (mod 360)`

| 轴 | 旧 | 计算 | 新 |
| --- | --- | --- | --- |
| pan | 66 | +47.99×8 | **89.92** |
| tilt | 138 | +(−108.28)×7 | **100.04** |

> 教训:**任何改 `zero_deg` 的操作(homing/重标定)都必须同步补偿 `phase_offset`**,否则开环换相参考错位。

## PI 控制器(消除重力静差)

tilt 顶重力时纯 P 有 8–15° 静差(力矩 < 重力矩就停)。猛拉 kp 会让顺重力方向震荡——静差不对称只有积分能解。

- `gimbal_controller.py`:`ControlConfig` 增 `integral_gain`/`integral_limit`;`_duties_for_axis` 加积分项 + **条件积分抗饱和**(只在死区外且输出未饱和时累积,避免 slew 跑赢爬升时积分 windup 造成大过冲)。死区内保留积分偏置(顶住重力,不再一进死区就泄力)。
- 积分状态 `self._integral` 在使能/停止/fault 时清零。
- 单测:`test_integral_winds_up_then_anti_windup_plateaus` / `_does_not_accumulate_when_gain_zero` / `_resets_on_enable_and_stop`。

## 调参结果(`gimbal_tune.py` 硬件台架实测)

最终全局增益:`max_duty 0.18, proportional_gain 0.008, integral_gain 0.01, integral_limit 0.10, target_slew_rate 16`。

| 轴 | 目标 | 实测静差 |
| --- | --- | --- |
| tilt | -25 / 0 / +30 | 全 **<1°**(基线曾 -8.6 / -15) |
| pan | -40 / -20 / 0 / +20 / +40 | 全 **<1°** |

- 两轴稳态误差从最差 15° → <1°。
- pan 负方向一度反甩,实为**相机线随方位轴旋转缠紧的机械非对称负载**;用户重新理线后双向正常。

## 已落地

- 板上 `gimbal.yaml`+节点+控制器已改、`colcon build` 重建、节点烟雾测试过(IDLE/读编码器/零报错)。
- 本地回灌一致,`python3 -m unittest discover -s tests` **100 passed**。
- 新增 `rdk_x5/scripts/gimbal_tune.py`(调参台架,`--kp/--ki/--ilimit/--slew/--max-duty` 可扫,带安全 ramp-down)。

## 遗留 / 下一步

1. pan 从静止首次大幅负向移动有短暂起步反甩(收敛正确),可后续打磨。
2. 编码器接头间歇性松动(今天 pan/tilt 各掉过线),有电烙铁后建议焊死/换锁扣连接器。
3. 全局增益 pan/tilt 共用;若未来要 pan/tilt 各调,需要 per-axis ControlConfig(架构改动)。
4. 可接最初目标 **#3 检测→云台对准**(订阅 `/hazard/status` 像素 → 换算 pan/tilt → 发 `/gimbal/target_angle`);开工前需先确认相机是固定还是随云台。
