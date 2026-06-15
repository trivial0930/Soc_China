# 2026-06-11 四轮方向 / 编码器标定(TB6612-A 换新后整车联调)

环境:RDK X5 `root@192.168.128.10`(en7 直连),STM32F411 经 USART2/`/dev/ttyS1` 115200。
ST-Link 在 Mac 上(`mode=UR freq=480` 可靠连接)。

## 0. 起点
用户更换了疑似损坏的 TB6612-A、重接了 STM32↔RDK UART 与 IMU,开始整车联调。
本次目标:打通四轮电机方向 + 四编码器映射/符号,为 PID 闭环与里程标定铺路。

## 1. UART 链路 ✅
`uart_send_test.py --mode manual --vx 0`:SET_MODE/CMD_VEL/HEARTBEAT 全部 ACK=OK,
STATUS `mode=MANUAL estop=False fault=0 battery=12000mV comm=OK`,ODOM 正常回传。

## 2. 四编码器映射 ✅(修了一处对调)
逐轮手转 + `encoder_monitor.py`:
- 初测发现**物理 LF→LR 列、物理 LR→LF 列**(左侧两路在数据里对调),RF/RR 正确。
- 根因:物理 LF 编码器接在 TIM2(PA15/PB3)、物理 LR 接在 TIM5(PA0/PA1),与规范引脚图相反。
- 修:`main.c` `send_odom()` 改为 `lf=CNT(htim2)`, `lr=CNT(htim5)`(rf=htim1, rr=htim4 不变)。重刷后复验:LF→LF、RF→RF、LR→LR、RR→RR 全对。
- 四编码器手转计数均正常(LF/RF/LR/RR Δ 均达数千)。

## 3. 电机方向标定 ✅(两处修正)
悬空 + 落地驱动,用编码器符号(已知前进=LF+ RF− LR+ RR−)+ 目视判定。
- **问题 A:+vx 落地后退** → 四电机整体接反。修:`app_write_motor()` 把 FORWARD/REVERSE 的 IN1/IN2 电平对调(FORWARD 改为 IN1=RESET,IN2=SET)。重刷后 +vx 前进 ✅(目视+编码器)。
- **问题 B:+wz 转出来是 CW**(应 CCW/REP-103)。vx/vy 正常,仅 rot 项:`mecanum_drive.c` `MecanumDrive_Mix` 改 `rot = -(half_length+half_width)*wz`。bridge 正运动学同步:`mecanum_odometry.py` `wz = r/(4lw)*(w_lf - w_rf + w_lr - w_rr)`。重刷后 +wz 逆时针 ✅(目视+编码器全 −)。
- 期间一度误判为"电机左右通道对调"并改了电机表,实测发现它把 vx 又翻反、且没修好 wz → **已撤销**,电机表恢复原状(无通道置换)。
- **encoder_sign = [1,-1,1,-1]**(LF,RF,LR,RR)写入 `stm32_bridge.yaml`,已在 RDK 重新编译部署。

确认数据(悬空 vx=250,逐帧累加):LF+3335 RF−3272 LR+3359 RR−3356(四轮均匀、符号 = 前进)。

## 4. vy 横移异常 → 已定位并修复 ✅
现象:悬空 +vy 稳定复现物理"前两轮反、后两轮正"(非对角横移),落地时原地打滑/像在转。
**目视 = 编码器一致**(LF/RF 后、LR/RR 前)→ 数据可信,排除测量错误。
把三轴"每物理轮对 [vx,vy,wz] 的实际转向"列成矩阵,与标准麦轮对比:
- LF (+,−,−)=标准LF✓;LR (+,+,−)=标准LR✓
- **RF 实测 (+,−,+) = 标准 RR 行;RR 实测 (+,+,+) = 标准 RF 行** → **RF 与 RR 整行对调**。
根因:**RF↔RR 电机通道接反**(换 TB6612 重接时右侧前后电机插头接反)。因 RF/RR 在 vx、wz 上同号、只 vy 异号,**故只坏了横移、不坏 vx/wz**。
修:固件 `app_motor_hw` 把 RF↔RR 引脚对调(RF→CH4/PB8/9,RR→CH3/PA4/5;invert[] 两者均 +1,故方向行为不变,且电机-编码器重新配对)。
修后 vy 变为干净对角横移,方向为右 → 再把 mix 的 vy 全局取反(bridge odom vy 同步)使 +vy=左(REP-103)。
**最终实测:+vy 物理 LF反 RF前 LR前 RR反 = 左移 ✓。** 幅度仍不均(前~1333 vs 后~400,开环死区,PID 解决)。

## 5. 工具/方法
- ODOM 增量必须**逐帧累加**回绕安全差值;只取首末两帧在快速悬空旋转时会因 16-bit 回绕误判符号。
- 低速(vx≤100 / 任意 vy)开环会**死区堵转**且各轮不均;需闭环 PID。

## 6. 硬件可靠性问题(继续前需加固)
反复架空/落地搬动期间接连松线:RR 编码器线(2 次)、ST-Link SWD(`DEV_CONNECT_ERR`,重插 + `freq=480` 恢复)、Mac↔RDK 网线(en7 inactive)。**上 PID / 落地标定前应先理线、加固、必要处补焊。**

## 7. IMU 复通 ✅(当日晚些时候完成)
当天搬动把 IMU 多根线弄掉,一度整条 i2c-5 全空。排查/修复序列(有教学价值):
1. **总线全空** → 缺 **SEL(协议选择)线**:SEL 低/悬空 = 整个模块进 SPI 模式、I2C 上隐身。SEL→3V3 后陀螺 0x68 回归。
2. **CSA 已 3.3V 但 0x18 仍不见** → **BMI088 加速度计 SPI 锁存坑**:带电状态下 CSB1/CSA 出现上升沿(热插线)会把加速度计锁进 SPI,直到断电复位。修:线全部固定后,拔 VDD 5 秒重插。
3. 重插 VDD 时把 SDI/SCK 带掉 → 重插。
最终:0x18+0x68 在线,芯片 ID 0x1E/0x0F,|accel|=9.70,陀螺静止≈0;
`bringup.launch.py use_imu:=true` 全链路:/imu 100Hz、/odometry/filtered 30Hz、odom→base_link TF 稳定(qz=0.004 恒定)。陀螺零偏标定正常 (-0.0002,-0.0017,-0.0015)。
**9 线清单(直连裸模块)**:VDD/CSA/CSG/**SEL**→3V3(共 4 根!)、GND/SDO1/SDO2→GND(3 根)、SDI→物理3脚、SCK→物理5脚。
万用表核对:上述 3V3 组全≈3.3V、SDO1/SDO2=0V;**物理 2 脚是 5V 别碰**(BMI088 上限 3.6V)。

## 8. 测试
`python3 -m unittest discover -s tests` → **97 passed**(含为 wz 符号翻转更新的 `test_mecanum_odometry.py`)。

## 9. 待办(下次)
1. 加固接线(尤其编码器/RR、ST-Link、网线)——反复搬动易松。
2. `wheel_pid` 接入 `mecanum_drive` + 整定 FF+PID(落地、闭环)——解决开环死区/四轮不均,横移才干净。
3. 落地 ≤20cm vx/vy/wz 里程标定,精修 `ticks_per_rev`。
4. ~~IMU 陀螺 0x68 复通~~ ✅ 已完成(见第 7 节)。
5. 之后:手控建图(slam_toolbox)→ 存图 → Nav2(MPPI omni)。

## 10. 最终固件方向配置(本次收敛结果)
- 电机表:LF=CH1/PB12-13,**RF=CH4/PB8-9**,LR=CH2/PB14-15,**RR=CH3/PA4-5**(RF/RR 已对调)。
- `app_write_motor`:FORWARD = IN1=RESET,IN2=SET(全局翻转)。
- `MecanumDrive_Mix`:`rot = -(L+W)*wz`;vy 四项取反。invert[] = {LF:-1, RF:+1, LR:-1, RR:+1}。
- `send_odom`:lf=CNT(htim2), rf=CNT(htim1), lr=CNT(htim5), rr=CNT(htim4)。
- bridge:`encoder_sign=[1,-1,1,-1]`;odom vy、wz 项均取反以匹配固件。
- 结果:+vx 前进、+vy 左移、+wz 逆时针,全部 REP-103 正确。
