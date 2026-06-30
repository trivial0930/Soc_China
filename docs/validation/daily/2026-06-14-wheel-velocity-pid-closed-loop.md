# 2026-06-14 四轮速度 PID 闭环(接入 + 整定 + 烧入默认)

承接 USB CDC 迁移与三轴方向验收(见同日 `…-stm32-usb-cdc-migration.md`)。本次把已存在但未接线的 `wheel_pid` 模块接入控制环并整定。

## 1. 固件改动(main.c 为主;wheel_pid.c / mecanum_drive.c Mix 未动)
- **闭环结构**:CMD_VEL → `MecanumDrive_Mix` → 每轮 setpoint(rad/s)存全局;新增 **50Hz `app_control_step`**(`APP_CTRL_PERIOD_MS=20`)读编码器增量算 rad/s、跑 `WheelPid_Update` → PWM+方向 `app_write_motor`。开环 `SetWheelSpeeds/SetVelocity` 路径弃用(保留、host 测试仍覆盖)。
- **测速**:编码器映射同 send_odom(LF←TIM2,RF←TIM1,LR←TIM5,RR←TIM4);wrapped int16 增量 × `APP_WHEEL_ENC_SIGN={1,-1,1,-1}`(前进为正)× 2π/2613 / dt。
- **测速低通**:`APP_VEL_LPF_ALPHA=0.5` EMA。**关键**——20ms 编码器量化噪声(±1 tick≈6%)被 PID 放大,Ki 一大就震荡;加滤波后才能把 Ki 提上去收稳态。
- **运行时调参**:新增 `RDK_FRAME_SET_PID=0x13`(payload: wheel u8 + kp/ki/kd/ff 4×LE-f32 = 17B,wheel=0xFF 全轮);`dispatch_frame` 应用并 reset。Python 侧 `shared/protocol` 加 `pack_set_pid`,新脚本 `rdk_x5/scripts/pid_tune.py`(推增益→驱动→算每轮 rad/s→打印目标/稳态/误差/超调)。
- **安全(PID 默认常开,面包板期间必须)**:
  - 非激活(estop/IDLE/命令超时)→ 强制各轮 STOP + reset PID + 清滤波/stall。
  - **编码器掉线保护**:命令了(|sp|>1)但测不到转(|meas|<0.4)持续 >400ms → 切断该轮 + reset,防止反馈丢失时积分饱和冲满速。
  - **中速限幅**:每轮 setpoint 比例缩放到 ≤ `APP_WHEEL_SETPOINT_MAX=8.0 rad/s`(0.4 m/s),保方向。

## 2. 整定(架空,USB CDC 链路,vx=200→目标 4 rad/s)
- ff-only(ff=33.3=pwm_max/max_radps,gains=0)≡ 开环:稳态 ~1.8(欠 50%,证明需要闭环)。
- 无滤波:Kp=30 稳但欠 30%+超调;Ki=30 震荡;Ki=60 发散。→ 定位噪声天花板,加测速 LPF。
- 有滤波:**Kp=15 Ki=30** → 稳态 LF/LR ~1-2%、RF/RR ~16%,收敛无发散(超调 60-80% 瞬态);四轮齐平。
- **烧入默认(app_chassis_init):Kp=15, Ki=30, Kd=0, ff=33.3**(用户选 A:常开)。仍可 SET_PID 覆盖。
- 验证(不推增益、纯驱动确认默认生效):四轮净转 LF+5442/RF+5024/LR+5375/RR+5204(折前进为正全正),彼此差 ~8%,无 stall 误触发。

## 3. 状态 / 待办
- 207 host 测试全过;固件 0 error 烧录校验通过。
- **待办**:① 落地 ≤20cm 验 PID 下直行/横移是否比开环干净 + 精修 ticks_per_rev;② PCB 到货后正式接线(面包板期间 PID 常开+掉线保护是兜底);③ 之后 SLAM/Nav2。
- 注意:面包板期间编码器仍偶发掉线;掉线保护会让该轮停转(不是 bug,是保护)。
