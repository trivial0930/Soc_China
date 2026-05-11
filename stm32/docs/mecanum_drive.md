# 麦轮底盘驱动说明

本驱动对应 `docs/hardware/pinmap.md` 中的四路 MDDS20 接线：

| 轮位 | 接口 | 说明 |
| --- | --- | --- |
| LF | PWM1/DIR1 | 左前轮 |
| RF | PWM2/DIR2 | 右前轮 |
| LR | PWM3/DIR3 | 左后轮 |
| RR | PWM4/DIR4 | 右后轮 |

## 坐标约定

- `vx_mps > 0`：车体前进。
- `vy_mps > 0`：车体向左平移。
- `wz_radps > 0`：车体逆时针旋转。
- 速度单位与 `docs/protocols/rdk_stm32_uart.md` 中 `CMD_VEL` 草案保持一致，推荐 RDK 下发 `m/s` 和 `rad/s`。

四轮顺序固定为 `LF, RF, LR, RR`。如果实车某个轮子方向相反，只改 `MecanumDriveConfig.invert[]`，不要改运动学公式。

## CubeMX 集成步骤

1. 在 CubeMX 中为四个电机配置 4 路 PWM 和 4 路 DIR GPIO。
2. 把 `Core/Inc/mecanum_drive.h` 加入头文件路径，把 `Core/Src/mecanum_drive.c` 加入工程编译。
3. 初始化后启动四路 PWM。
4. 在 UART `CMD_VEL` 解析成功后调用 `MecanumDrive_SetVelocity()`。
5. 在主循环或 1 ms 定时任务里调用 `MecanumDrive_UpdateTimeout()`，控制帧超时后自动停车。

## 回调示例

下面示例只展示接线方式，实际 `TIM` 通道和 GPIO 名称以 CubeMX 生成代码为准。

```c
#include "mecanum_drive.h"
#include "tim.h"
#include "gpio.h"

typedef struct
{
    TIM_HandleTypeDef *htim;
    uint32_t channel;
    GPIO_TypeDef *dir_port;
    uint16_t dir_pin;
} MotorHw;

static MotorHw motor_hw[MECANUM_WHEEL_COUNT] = {
    {&htim1, TIM_CHANNEL_1, LF_DIR_GPIO_Port, LF_DIR_Pin},
    {&htim1, TIM_CHANNEL_2, RF_DIR_GPIO_Port, RF_DIR_Pin},
    {&htim1, TIM_CHANNEL_3, LR_DIR_GPIO_Port, LR_DIR_Pin},
    {&htim1, TIM_CHANNEL_4, RR_DIR_GPIO_Port, RR_DIR_Pin},
};

static void WriteMotor(MecanumWheelId wheel,
                       const MecanumMotorCommand *command,
                       void *user)
{
    MotorHw *hw = &((MotorHw *)user)[wheel];

    HAL_GPIO_WritePin(hw->dir_port,
                      hw->dir_pin,
                      (command->dir == MECANUM_DIR_FORWARD) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, command->pwm);
}

static MecanumDrive chassis;

void Chassis_Init(void)
{
    MecanumDriveConfig cfg;

    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_3);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_4);

    MecanumDrive_DefaultConfig(&cfg);
    cfg.wheel_radius_m = 0.05f;
    cfg.half_length_m = 0.12f;
    cfg.half_width_m = 0.10f;
    cfg.max_wheel_radps = 30.0f;
    cfg.pwm_max = 999U;
    cfg.command_timeout_ms = 2000U;
    cfg.write_motor = WriteMotor;
    cfg.user = motor_hw;

    cfg.invert[MECANUM_WHEEL_LF] = 1;
    cfg.invert[MECANUM_WHEEL_RF] = 1;
    cfg.invert[MECANUM_WHEEL_LR] = 1;
    cfg.invert[MECANUM_WHEEL_RR] = 1;

    (void)MecanumDrive_Init(&chassis, &cfg);
}

void Chassis_OnCmdVel(float vx_mps, float vy_mps, float wz_radps)
{
    MecanumDrive_SetVelocity(&chassis, vx_mps, vy_mps, wz_radps, HAL_GetTick());
}

void Chassis_Task1ms(void)
{
    MecanumDrive_UpdateTimeout(&chassis, HAL_GetTick());
}
```

## 空载验证顺序

1. 架空底盘，主电池和 RDK/STM32 共地后再上电。
2. 单独下发 `vx > 0, vy = 0, wz = 0`，四轮应表现为前进。
3. 单独下发 `vy > 0`，底盘应向左平移。
4. 单独下发 `wz > 0`，底盘应逆时针旋转。
5. 哪个轮子方向不一致，只调整对应 `invert[]`。
6. 停止发送控制帧，确认 2 s 内进入安全停车。
