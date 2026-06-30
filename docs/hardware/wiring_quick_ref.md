# 转接板接线速查卡

> STM32F411 黑药丸转接板 · 一页速查 · 详见 `pcb_breakout_pinout.md`
> 全部 2.54mm 单排;左侧=LF+LR,右侧=RF+RR;编码器供电 3V3(勿接 5V)。

```
┌──────────────── 左侧边 (LF + LR) ────────────────┐
│ J_L_CTRL → TB6612-A          J_L_ENC ← 左两轮编码 │
│  1 LF_PWM  PA6                1 LF_ENCA  PA15      │
│  2 LF_IN1  PB12               2 LF_ENCB  PB3       │
│  3 LF_IN2  PB13               3 +3V3               │
│  4 GND                        4 GND                │
│  5 LR_PWM  PA7                5 LR_ENCA  PA0        │
│  6 LR_IN1  PB14               6 LR_ENCB  PA1        │
│  7 LR_IN2  PB15               7 +3V3               │
│  8 GND                        8 GND                │
└───────────────────────────────────────────────────┘

┌──────────────── 右侧边 (RF + RR) ────────────────┐
│ J_R_CTRL → TB6612-B          J_R_ENC ← 右两轮编码 │
│  1 RF_PWM  PB1                1 RF_ENCA  PA8       │
│  2 RF_IN1  PB8                2 RF_ENCB  PA9       │
│  3 RF_IN2  PB9                3 +3V3              │
│  4 GND                        4 GND               │
│  5 RR_PWM  PB0                5 RR_ENCA  PB6       │
│  6 RR_IN1  PA4                6 RR_ENCB  PB7       │
│  7 RR_IN2  PA5                7 +3V3              │
│  8 GND                        8 GND               │
└───────────────────────────────────────────────────┘

┌─ J_PWR (电机电源) ─┐   ┌─ J_SWD (调试) ─┐   ┌─ Type-C ─┐
│ 1 VM+ (12V)         │   │ 1 +3V3          │   │ USB CDC   │
│ 2 GND               │   │ 2 SWDIO  PA13   │   │ PA11/PA12 │
│ 3 GND               │   │ 3 SWCLK  PA14   │   │ 底盘通信  │
└─ +保险丝/防反接/TVS ┘   │ 4 GND           │   └───────────┘
                          └─────────────────┘
```

## TB6612 通道对应
- **TB6612-A**:1P/1IN1/1IN2 = LF;2P/2IN1/2IN2 = LR
- **TB6612-B**:1P/1IN1/1IN2 = RF;2P/2IN1/2IN2 = RR

## 必检 5 条
1. **电源防反接**——已两次因反接烧 TB6612,VM 入口必须有保险丝+防反接。
2. **编码器供电由 TB6612 板提供(3V3,非 5V)**;本板编码器口只引 A/B 信号。
3. **控制线 10k 下拉**:必加 12 个(PA6/PA7/PB0/PB1 4 条 PWM 最关键 + 8 条 IN);预算紧至少保 4 条 PWM。防上电/复位瞬间窜车。
4. **共地**:逻辑 GND 与电机 VM 地必须连通(GND 母线 H3)。
5. 别占用 **PA11/PA12(USB)、PA13/PA14(SWD)、PC13(LED)**。

> 电阻清单(可选):编码器若为开漏才需 A/B 上拉 10k→3V3(本项目推挽,留焊盘默认不贴);PWM/IN 串 22–100Ω 限振铃为锦上添花。

## GND 计数
J_L_CTRL ×2 + J_L_ENC ×2 + J_R_CTRL ×2 + J_R_ENC ×2 = **8**(+ J_PWR ×2 + 黑药丸自带)✅

> 按本卡接线即与当前固件一致,无需改固件。若某轮方向/编码符号反,优先查接线,再考虑固件 sign。
