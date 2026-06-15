# 2026-06-14 STM32 底盘链路从 USART2 迁移到原生 USB CDC(Type-C)

## 0. 起因:重启后 UART 失联,定位到 RDK 引脚硬冲突
重新接线后整车体检,发现 STM32↔RDK 的 `/dev/ttyS1` 收 0 字节(STM32 主动遥测也收不到)。
排查结论(**不是接线问题**):
- RDK **当天重启过**;在 RDK X5 上 `serial3`(=ttyS1,40-pin 8/10 脚)与 `i2c5`(热成像 MI48 0x40 + IMU 0x68,3/5 脚)**共用 SoC 同一组 pad,硬件级互斥**(srpi-config 明写 `[serial3]="i2c5"`)。重启后 pinmux 判给了 i2c5 → ttyS1 有设备节点但无物理引脚。
- 设备树里 serial3、i2c5 节点都是 `okay`,冲突发生在 pad 仲裁层;`341c0000.i2c` 抢走了 uart3 的 pad。
- 历史上 06-11 UART 与 IMU 是**分时段**用的,从未真正同时跑过,冲突一直潜伏,这次重启暴露。
- 雷达 N10 走 USB(`/dev/ttyACM0`,QinHeng CH343 `usb-1a86_USB_Single_Serial_5B8E...`),不受影响。

## 1. 方案决策:STM32 底盘链路改走 Type-C(原生 USB CDC)
要让 UART + 热成像 + IMU 三者共存(SLAM/Nav 必需),最干净的办法是把 STM32 链路移出 40-pin。
STM32F411 黑药丸的 Type-C 是**芯片自带 USB(PA11/PA12)**,加 USB CDC 虚拟串口后和雷达一样走 USB,彻底绕开 40-pin pinmux。无需额外 USB-TTL。
接法:STM32 Type-C ──(USB-A↔Type-C 数据线)── RDK 的 **USB-A 口**(host)。RDK 端枚举为 `/dev/ttyACM*`。

## 2. 固件改动(全部手工添加,未用 CubeMX 重新生成,以免冲掉手写的标定代码)
- **时钟**:`SystemClock_Config` PLLQ `4→7`,USB 时钟 = VCO 336MHz / 7 = **48MHz** 精确(SYSCLK 仍 84MHz 不变)。
- **新增 ST USB Device 库**(从 CubeF4 V1.28.3 复制,平铺进 Core/Drivers 免改 .cproject):
  - `Core/Src`:usbd_core.c、usbd_ctlreq.c、usbd_ioreq.c、usbd_cdc.c
  - `Core/Inc`:usbd_core.h、usbd_ctlreq.h、usbd_ioreq.h、usbd_def.h、usbd_cdc.h
  - `Drivers/.../Src`:stm32f4xx_hal_pcd.c、_pcd_ex.c、ll_usb.c;`Inc` 对应三个头
- **App 层(手写,F411 OTG_FS,VBUS sensing 关闭、静态内存池)**:
  - usbd_conf.c/h、usbd_desc.c/h、usbd_cdc_if.c/h、usb_device.c/h
  - VID/PID = 0x0483/0x5740(ST CDC),Linux in-box `cdc_acm` 直接识别为 ttyACM
  - **VBUS sensing = DISABLE**:无论数据线带不带 VBUS、由谁供电都能枚举
- **`stm32f4xx_hal_conf.h`**:启用 `HAL_PCD_MODULE_ENABLED`
- **`main.c`**:
  - 包含 usb_device.h / usbd_cdc_if.h;init 里调 `MX_USB_DEVICE_Init()`
  - `send_protocol_frame()`:`HAL_UART_Transmit` → `CDC_Transmit_FS`,带 5ms 有界重试(CDC 在上一包未发完时返回 USBD_BUSY;主机不在时退出不阻塞)
  - 新增 `rdk_comm_on_rx_bytes()`(强符号覆盖 cdc_if 的 __weak):逐字节喂 `rdk_parser_feed`,dispatch/comm-state 逻辑不变
  - `app_uart_start()`:不再 arm USART2 RX(链路上 USB 后 PA3 悬空,arm 会引入噪声/假 CRC 错)
- **`stm32f4xx_it.c/.h`**:新增 `OTG_FS_IRQHandler` → `HAL_PCD_IRQHandler(&hpcd_USB_OTG_FS)`(startup 向量表已有弱符号,强覆盖)

协议层 `rdk_stm32_uart.c/h` **一行未动**(纯编解码/CRC,不碰硬件)。

## 3. 构建 / 烧录
- STM32CubeIDE headless cleanBuild Debug:**0 errors, 0 warnings**;text 42812 / data 348 / bss 5548。
- ST-Link(mode=UR freq=480)烧录 + 校验通过,MCU 已复位运行。

## 4. 供电注意(连接前确认)
Type-C 会从 RDK USB-A 引入 5V。两选一,固件 VBUS sensing 已关,两种都兼容:
- 接 Type-C 后让 STM32 仅由 USB 供电(断开底盘那路);或
- 用切掉 VBUS 的数据线,STM32 继续吃底盘电。
**别让底盘 5V 与 USB 5V 同时顶在一起。**

## 5. 连接 + 链路验证(已完成 ✅)
1. Type-C → RDK USB-A,枚举为 `/dev/ttyACM1` = `usb-Soc_China_Robotics_STM32F411_Chassis_VCP_335833553034-if00`(VID/PID 0483:5740,产品串 "STM32F411 Chassis VCP")。雷达是 ttyACM0(1a86 CH343)。
2. `stm32_bridge.yaml` 的 `port` 改为该 by-id 固定名(本地 + RDK,clean colcon 重编;注意 colcon 会缓存 config,改 yaml 后要 `rm -rf build/install/stm32_bridge` 再 build 才会刷新)。
3. 链路实测:`uart_send_test` tx182 / **ack181 全 OK**,STATUS+ODOM 各 60,crc/len/version 错误全 0;bridge 节点 `/stm32/status` 和 `/odom` 稳定 **10Hz**。

## 6. 换板后三轴方向 + 编码器复验(已完成 ✅)
重接电机/编码器期间反复松线(LF 编码器、左侧编码器供电、RR 编码器、LR/RR 电机轮番接触不良),且**一块 TB6612 被电源反接打坏**(LR 通道死、换通道判别确认"故障跟电机走→实为该板通道损坏",换新板后恢复)。最终架空逐轴实测(净增量,原始符号):
- **+vx 前进**:LF+ RF− LR+ RR− ✅(与 06-11 基准一致)
- **+vy 左移**:LF− RF− LR+(RR 开环死区未动)✅
- **+wz 逆时针**:LF− RF− LR− RR−(四轮全负)✅
- 四电机全转、四编码器全读、电机在原位(诊断对调已还原,固件未改)。

## 7. 教训
- **TB6612 无防反接**:电源正负反接会打坏通道(本会话第二次因反接换板;上次是 TB6612-A 整板坏)。接电源前必用万用表确认 VM 极性。
- **杜邦直插极不可靠**:本会话松动七八次,每次现象不同(时好时坏=松动,一致死=烧毁——可据此区分)。**上 PID 前必须加固**(热熔胶/连体壳/补焊)。
- **换通道判别法**:把可疑电机换到已知好的通道,故障跟电机走=电机/线问题,跟通道走=板/通道问题。

## 8. 待办(下一步)
1. **#8 加固接线**(强烈建议先做)——电机/编码器杜邦头热熔胶点固或换连体壳/XH。
2. **#5 落地 ≤20cm** 实测 +vx/+vy/+wz 真实运动方向(最终验收)+ 精修 ticks_per_rev。
3. **#6 PID 闭环**——解决开环死区(尤其 vy 后轮弱)/四轮不均。
   - 注意:40-pin 的 i2c5(热成像+IMU)现在不再被 UART 抢,可与底盘链路共存。
