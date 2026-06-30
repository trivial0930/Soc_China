# STM32 黑药丸转接板 — 引脚分配规格 + 原理图网表

> 目的:把底盘接线从面包板/杜邦固化为一块 **WeAct STM32F411CEU6 黑药丸转接板**。
> 黑药丸插中间 2×20 母座(Type-C 朝上),四轮的控制+编码器分组引出到两侧连接器:
> **左侧管 LF+LR,右侧管 RF+RR**。本文件是布板的事实源(在你的 EDA 里照此摆放/连线)。
>
> ⚠️ 旧图 `stm32_tb6612_adapter_layout.svg` 与当前固件**不同步**,勿用其引脚;以本文件为准。
> 新布局见 `stm32_tb6612_adapter_layout_v2.svg`。

## 1. 权威引脚表（源:firmware `main.c` app_motor_hw + `stm32f4xx_hal_msp.c`,本会话多次实测确认)

TIM3 PWM 通道→脚:CH1=PA6,CH2=PA7,CH3=PB0,CH4=PB1。
编码器映射含 2026-06-11 左侧交叉补偿(物理 LF 编码器接 TIM2、LR 接 TIM5)。

| 轮 | PWM | IN1 | IN2 | 编码器 A | 编码器 B | 编码器定时器 |
|---|---|---|---|---|---|---|
| **LF 左前** | PA6 | PB12 | PB13 | PA15 | PB3 | TIM2 |
| **LR 左后** | PA7 | PB14 | PB15 | PA0 | PA1 | TIM5 |
| **RF 右前** | PB1 | PB8 | PB9 | PA8 | PA9 | TIM1 |
| **RR 右后** | PB0 | PA4 | PA5 | PB6 | PB7 | TIM4 |

**保留 / 勿占用**:PA11/PA12 = USB(Type-C 通信链路)、PA13/PA14 = SWD、PC13 = 板载 LED。
**空闲可扩展**:PB10、PB11、PA10、PA2、PA3(USART2 冗余)。

所有电机/编码器脚互不冲突,且都在黑药丸 2×20 排针上可取。

## 2. 连接器引脚表（全部 2.54mm 单排排针;信号 → STM32 脚)

### J_L_CTRL — 左·电机控制(8P,→ TB6612-A 的 1P/1IN1/1IN2 与 2P/2IN1/2IN2)
| pin | 信号 | STM32 | 去向 |
|---|---|---|---|
| 1 | LF_PWM | PA6 | TB6612-A 1P (PWMA) |
| 2 | LF_IN1 | PB12 | TB6612-A 1IN1 |
| 3 | LF_IN2 | PB13 | TB6612-A 1IN2 |
| 4 | GND | GND | TB6612-A G |
| 5 | LR_PWM | PA7 | TB6612-A 2P (PWMB) |
| 6 | LR_IN1 | PB14 | TB6612-A 2IN1 |
| 7 | LR_IN2 | PB15 | TB6612-A 2IN2 |
| 8 | GND | GND | TB6612-A G |

### J_L_ENC — 左·编码器(8P,← LF/LR 霍尔编码器)
| pin | 信号 | STM32 | 去向 |
|---|---|---|---|
| 1 | LF_ENCA | PA15 | LF 电机编码 A |
| 2 | LF_ENCB | PB3 | LF 电机编码 B |
| 3 | +3V3 | 3V3 | LF 编码器 VCC |
| 4 | GND | GND | LF 编码器 GND |
| 5 | LR_ENCA | PA0 | LR 电机编码 A |
| 6 | LR_ENCB | PA1 | LR 电机编码 B |
| 7 | +3V3 | 3V3 | LR 编码器 VCC |
| 8 | GND | GND | LR 编码器 GND |

### J_R_CTRL — 右·电机控制(8P,→ TB6612-B)
| pin | 信号 | STM32 | 去向 |
|---|---|---|---|
| 1 | RF_PWM | PB1 | TB6612-B 1P (PWMA) |
| 2 | RF_IN1 | PB8 | TB6612-B 1IN1 |
| 3 | RF_IN2 | PB9 | TB6612-B 1IN2 |
| 4 | GND | GND | TB6612-B G |
| 5 | RR_PWM | PB0 | TB6612-B 2P (PWMB) |
| 6 | RR_IN1 | PA4 | TB6612-B 2IN1 |
| 7 | RR_IN2 | PA5 | TB6612-B 2IN2 |
| 8 | GND | GND | TB6612-B G |

### J_R_ENC — 右·编码器(8P,← RF/RR 霍尔编码器)
| pin | 信号 | STM32 | 去向 |
|---|---|---|---|
| 1 | RF_ENCA | PA8 | RF 电机编码 A |
| 2 | RF_ENCB | PA9 | RF 电机编码 B |
| 3 | +3V3 | 3V3 | RF 编码器 VCC |
| 4 | GND | GND | RF 编码器 GND |
| 5 | RR_ENCA | PB6 | RR 电机编码 A |
| 6 | RR_ENCB | PB7 | RR 电机编码 B |
| 7 | +3V3 | 3V3 | RR 编码器 VCC |
| 8 | GND | GND | RR 编码器 GND |

### J_PWR — 电机电源输入(3P)
| pin | 信号 | 说明 |
|---|---|---|
| 1 | VM+ | 12V 电机电源正(经保险丝+防反接后给两块 TB6612 的 VM) |
| 2 | GND | 电源地(与逻辑共地) |
| 3 | GND | 电源地 |

### J_SWD — 调试口(4P,引出黑药丸 SWD)
| pin | 信号 | STM32 |
|---|---|---|
| 1 | +3V3 | 3V3 |
| 2 | SWDIO | PA13 |
| 3 | SWCLK | PA14 |
| 4 | GND | GND |

**GND 计数(满足 ≥8 要求)**:J_L_CTRL ×2 + J_L_ENC ×2 + J_R_CTRL ×2 + J_R_ENC ×2 = **8 个**;再加 J_PWR ×2、J_SWD ×1、黑药丸自带多个 GND → 总计远超 8。✅

## 3. 原理图网表（net → 引脚集合,供 EDA 连线核对)

- **GND**:黑药丸所有 GND 脚 · J_L_CTRL.4 · J_L_CTRL.8 · J_L_ENC.4 · J_L_ENC.8 · J_R_CTRL.4 · J_R_CTRL.8 · J_R_ENC.4 · J_R_ENC.8 · J_PWR.2 · J_PWR.3 · J_SWD.4 · 全部 10k 下拉电阻下端 · TVS/电解负端
- **+3V3**:黑药丸 3V3 · J_L_ENC.3 · J_L_ENC.7 · J_R_ENC.3 · J_R_ENC.7 · J_SWD.1
- **VMOTOR**:J_PWR.1 →(保险丝 F1 → 防反接 → TVS/电解)→ 两块 TB6612 的 VM(板外)
- **信号网(12 条控制,各串/带 10k 下拉到 GND;8 条编码器直连不下拉)**:

| net | 黑药丸脚 | 连接器脚 | 下拉 |
|---|---|---|---|
| LF_PWM | PA6 | J_L_CTRL.1 | 10k↓ |
| LF_IN1 | PB12 | J_L_CTRL.2 | 10k↓ |
| LF_IN2 | PB13 | J_L_CTRL.3 | 10k↓ |
| LR_PWM | PA7 | J_L_CTRL.5 | 10k↓ |
| LR_IN1 | PB14 | J_L_CTRL.6 | 10k↓ |
| LR_IN2 | PB15 | J_L_CTRL.7 | 10k↓ |
| RF_PWM | PB1 | J_R_CTRL.1 | 10k↓ |
| RF_IN1 | PB8 | J_R_CTRL.2 | 10k↓ |
| RF_IN2 | PB9 | J_R_CTRL.3 | 10k↓ |
| RR_PWM | PB0 | J_R_CTRL.5 | 10k↓ |
| RR_IN1 | PA4 | J_R_CTRL.6 | 10k↓ |
| RR_IN2 | PA5 | J_R_CTRL.7 | 10k↓ |
| LF_ENCA | PA15 | J_L_ENC.1 | — |
| LF_ENCB | PB3 | J_L_ENC.2 | — |
| LR_ENCA | PA0 | J_L_ENC.5 | — |
| LR_ENCB | PA1 | J_L_ENC.6 | — |
| RF_ENCA | PA8 | J_R_ENC.1 | — |
| RF_ENCB | PA9 | J_R_ENC.2 | — |
| RR_ENCA | PB6 | J_R_ENC.5 | — |
| RR_ENCB | PB7 | J_R_ENC.6 | — |
| SWDIO | PA13 | J_SWD.2 | — |
| SWCLK | PA14 | J_SWD.3 | — |

> USB(PA11/PA12)走黑药丸自带 Type-C,不上转接板连接器。

## 4. 电阻清单 / BOM / 布板注意

### 电阻清单（2026-06-18 定稿）
**A. 必加 — 控制线 10kΩ 下拉到 GND（共 12 个）**
| 类别 | 引脚 | 数量 | 作用 |
|---|---|---|---|
| PWM(最关键) | PA6, PA7, PB0, PB1 | 4 | PWM=低→电机停;MCU 未驱动/复位/掉线时电机绝不乱转 |
| IN1/IN2 | PB12, PB13, PB14, PB15, PB8, PB9, PA4, PA5 | 8 | 定默认方向(PWM 已拉低则次要) |

> 预算紧至少保 4 个 PWM 下拉;本板既然要做,12 个全上最稳。复位/上电瞬间防窜车的**关键安全项**。

**B. 可选(留焊盘、默认不贴)— 编码器 A/B 上拉 10kΩ 到 3V3(4 或 8 个)**
- 仅当霍尔编码器为**开漏输出**才需要。本项目编码器面包板裸接即可计数 → 推挽输出,**默认不贴**。
- 留焊盘以防换开漏编码器或信号发飘:涉及 PA15, PB3, PA0, PA1, PA8, PA9, PB6, PB7。

**C. 可选(抗干扰)**:PWM/IN 串 22–100Ω 限振铃;编码线串 100Ω + 对地 1nF RC 低通。走线短可不加。

**D. 本板不加**(黑药丸自带):SWD、BOOT0、PC13 LED、USB。

### BOM / 布板
- **U17**:2×20 母排座(2.54mm),供 WeAct 黑药丸 v2.0+ 插接;Type-C 朝板外缘。
- **连接器(本规格)**:J_L_CTRL / J_L_ENC / J_R_CTRL / J_R_ENC = 4× 8P;J_PWR = 3P;J_SWD = 4P。
  - **实际原理图(2026-06-18 嘉立创 EDA)采用等价的另一种分组**:每轮一个 **5P**(PWM,IN1,IN2,ENCA,ENCB)+ 一个 **8P 全 GND 母线(H3)**;引脚→网络分配与本文件完全一致(已逐脚核对)。
- **电源前端**:F1 保险丝 + 防反接(P-MOS/肖特基)+ TVS + 大电解(≥470µF)在 VM 入口(**本项目已两次因反接烧 TB6612,务必加防反接**)。注:VM 与编码器供电由 TB6612 板提供,本转接板可不含电源段。
- **工艺**:双层板,底层 GND 覆铜;PWM/IN 线尽量短、远离编码器线;可留测试点 + M3 安装孔。
- **编码器供电**:由 **TB6612 板**给(3V3,非 5V);本转接板的编码器连接器只引 A/B 信号,VCC/GND 走 TB6612/GND 母线。

## 5. 与固件的对应关系
- 控制脚顺序与固件 `app_motor_hw`(main.c)一一对应;固件方向/通道已含 RF↔RR、左编码器交叉的补偿,**按本表接线即与当前固件一致,无需再改固件**。
- 编码器极性:固件 `APP_WHEEL_ENC_SIGN = {1,-1,1,-1}`(LF,RF,LR,RR,前进为正)与 RDK `encoder_sign=[1,-1,1,-1]` 一致;若实测某轮符号反,优先在接线/固件 sign 处理,不改本表脚位。
- 通信:底盘链路走黑药丸 Type-C(USB CDC),与本转接板连接器无关。
