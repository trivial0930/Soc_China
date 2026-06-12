# 云台编码器零点 homing — 2026-06-12

## 背景

FOC 标定后云台已能闭环收敛,但**角度坐标系与物理朝向不一致**:`zero_deg=0` 不对应机械中心,导致 tilt 在中心读 ~-100°(超出配置范围 `[-30,45]`),pan 读 ~48°。限位钳位、后续"像素→角度"换算全都建立在一个错的零点上。homing 把零点重定到机械中心,让角度=真实物理朝向。

## 方法

1. 用户手动把云台摆到机械中心(pan 正前方、tilt 水平)。
2. 不驱动电机,直接读 AS5600 原始角(`zero_deg=0, invert=False`),多次采样取中位数。
3. 把中心原始角写入 `gimbal.yaml` 的 `pan_zero_deg` / `tilt_zero_deg`(`raw_to_degrees` 里 `reading = wrap(raw_deg - zero_deg)`,所以 `zero_deg = 中心原始角` 即可让中心归 0)。
4. 重建、用新零点复读验证中心读 ~0°。

> 重定零点只平移角度参考,不改变编码器方向与电机方向的关系,**FOC 收敛不受影响**。

## 过程中的坑

- **pan 编码器中途掉线**:摆云台时碰松了 pan 那颗 AS5600,`i2c-5` 上 `0x36` 消失(同总线的热成像 `0x40`、`0x18`、`0x68` 仍在 → 总线好的,是编码器单根线松)。用户重新接回后恢复。
- **两轴必须同一时刻一起抓**:接 pan 线时云台被碰动了 ~12°,tilt 中心原始角从首次的 -96.24° 变成 -108.28°。最终以"pan 接好后、同一姿态"下两轴一起读的值为准。
- **`colcon build --symlink-install` 在板上失败**(setuptools 报 `--editable`/`--uninstall` not recognized,且残留脏状态)。解决:`rm -rf build/gimbal_laser install/gimbal_laser` + 删除 scp 带来的 `._*` AppleDouble 文件,改用普通 `colcon build`。

## 结果

| 轴 | 中心原始角(zero_deg) | 新零点下中心复读 |
| --- | --- | --- |
| pan | **47.99°** | -0.002°(期望 0)✅ |
| tilt | **-108.28°** | -0.001°(期望 0)✅ |

- 已写入板上 `rdk_x5/ros2_ws/src/gimbal_laser/config/gimbal.yaml`,普通 `colcon build` 重建成功,install 副本已含新值。
- 现 `pan[-60,60]`、`tilt[-30,45]` 对应真实可达范围,中心=0。

## 遗留 / 下一步

1. **本地仓库未同步**:Mac 上 `Soc_China/` 内已存在的被改文件出现 "Operation not permitted"(疑似 Desktop 的 TCC/iCloud 锁),bash 子进程读写不了,Edit 工具改 `gimbal.yaml` 也 EPERM。**板上是当前可用的事实源**;本地 `gimbal.yaml`/`gimbal_controller_node.py` 的 `zero_deg` 仍是 0.0,待权限问题解决后回灌(pan 47.99 / tilt -108.28)。
2. 节点默认值 `pan_zero_deg`/`tilt_zero_deg` 仍为 0.0(launch 实际加载的是 yaml,功能不受影响,仅一致性待补)。
3. 坐标系就绪后可做:**#1 稳态误差调参** → **#3 检测→云台对准**。
