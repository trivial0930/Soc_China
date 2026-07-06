/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "mecanum_drive.h"
#include "rdk_stm32_uart.h"
#include "wheel_pid.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
#include <stdio.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef struct
{
  TIM_HandleTypeDef *htim;
  uint32_t channel;
  GPIO_TypeDef *in1_port;
  uint16_t in1_pin;
  GPIO_TypeDef *in2_port;
  uint16_t in2_pin;
} AppMotorHw;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define APP_STATUS_PERIOD_MS 100u
#define APP_CMD_TIMEOUT_MS 500u
#define APP_HEARTBEAT_TIMEOUT_MS 2000u
#define APP_BATTERY_MV 12000u
#define APP_FAULT_NONE 0x0000u
#define APP_FAULT_ESTOP 0x0001u
#define APP_FAULT_HEARTBEAT_TIMEOUT 0x0002u
#define APP_FAULT_CMD_TIMEOUT 0x0003u
#define APP_FAULT_CRC_ERROR_LIMIT 0x0004u
#define APP_CHASSIS_WHEEL_RADIUS_M 0.038f  /* ruler-measured 2026-07-06 (was 0.05);
   used for the cmd_vel->wheel-radps inverse kinematics. Must match the RDK odom
   wheel_radius_m in stm32_bridge.yaml or commanded vx won't equal real vx. */
#define APP_CHASSIS_HALF_LENGTH_M 0.12f
#define APP_CHASSIS_HALF_WIDTH_M 0.10f
#define APP_CHASSIS_MAX_WHEEL_RADPS 30.0f
#define APP_CHASSIS_PWM_MAX 999u
/* Closed-loop velocity PID: control step rate and encoder scale.
   ticks_per_rev = encoder_PPR*4*gear. RE-CALIBRATED 2026-07-06: hand-rolled LF
   exactly 5 turns -> 6615 ticks / 5 = 1323 (the old 2613 was a miscount, ~2x too
   big; it made the measured wheel velocity read half-real, so the loop over-drove
   ~2x and the stall threshold tripped at 2x). Matches stm32_bridge.yaml odom. */
#define APP_CTRL_PERIOD_MS 20u
#define APP_TICKS_PER_REV 1323.0f
#define APP_TWO_PI 6.28318530718f
/* EMA low-pass on measured wheel velocity: at 20ms the encoder delta is only a
   few dozen ticks, so +/-1 tick quantization is ~6% noise that the PID amplifies
   into oscillation once Ki is raised. Filtering it lets Ki close the steady-state
   error without ringing. alpha in (0,1]; smaller = smoother but more lag. */
#define APP_VEL_LPF_ALPHA 0.5f
/* Medium top speed: cap each wheel setpoint (proportional, preserves the motion
   direction). 10.5 rad/s * 0.038 m wheel = 0.4 m/s, matching the RDK vx clamp
   (max_vx_mm_s=400) so the full commanded range maps 1:1 to real speed. The robot
   does not need to be fast (per spec). */
#define APP_WHEEL_SETPOINT_MAX 10.5f
/* Encoder-stall / dropped-feedback safety: if a wheel is commanded to move but
   reads ~no motion for APP_STALL_TIMEOUT_MS, cut its output (and hold the PID
   reset) so a loose encoder cannot wind the integral up into a full-speed run. */
#define APP_STALL_SETPOINT_MIN 1.0f   /* rad/s: only guard when really commanded */
/* Relaxed 2026-06-27 after the PCB build (encoders verified, no longer the flaky
   breadboard): the old 0.4rad/s / 400ms guard false-tripped on high-load ground
   moves (esp. mecanum strafe, which starts slowly) and cut the wheels before the
   PID could push through. Now only a wheel essentially not moving (<0.15 rad/s)
   for >1.5s counts as a dropped-encoder/hard-stall. */
#define APP_STALL_MEASURED_MAX 0.15f  /* rad/s: below this counts as "not moving" */
#define APP_STALL_TIMEOUT_MS 1500u
/* Zero-command safety: when a wheel is commanded to ~stop, force its motor off and
   hold the PID reset instead of running the closed loop. A wound-up integral (e.g.
   from a mis-mapped/mis-signed encoder while driving) can otherwise keep driving the
   wheel at setpoint 0 -> runaway at rest. "Stop means stop", immune to feedback faults. */
#define APP_SETPOINT_DEADBAND 0.10f   /* rad/s: |setpoint| below this -> motor off */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim1;
TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;
TIM_HandleTypeDef htim4;
TIM_HandleTypeDef htim5;

UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
static rdk_parser_t uart_parser;
static uint8_t uart_rx_byte;
static uint8_t uart_tx_seq;
static volatile uint8_t app_mode = RDK_MODE_IDLE;
static volatile uint8_t app_estop;
static volatile uint16_t app_fault_code = APP_FAULT_NONE;
static volatile uint8_t app_last_cmd_seq;
static volatile uint8_t app_comm_state = RDK_COMM_OK;
static volatile uint32_t app_last_cmd_ms;
static volatile uint32_t app_last_heartbeat_ms;
static uint32_t app_last_status_ms;
static MecanumDrive app_chassis;
static volatile MecanumMotorCommand app_last_motor_command[MECANUM_WHEEL_COUNT];

/* Per-wheel velocity PID closed-loop state. Setpoints are the Mix output
   (rad/s, forward-positive). Measured velocity is derived from encoder deltas;
   APP_WHEEL_ENC_SIGN makes a forward wheel rotation read positive (matches the
   RDK encoder_sign [1,-1,1,-1] for LF,RF,LR,RR). */
static WheelPid app_wheel_pid[MECANUM_WHEEL_COUNT];
static float app_wheel_setpoint_radps[MECANUM_WHEEL_COUNT];
static float app_wheel_vel_filt[MECANUM_WHEEL_COUNT];
static uint32_t app_wheel_stall_ms[MECANUM_WHEEL_COUNT];
static int16_t app_last_enc[MECANUM_WHEEL_COUNT];
static uint8_t app_have_last_enc;
static uint32_t app_last_ctrl_ms;
static const int8_t APP_WHEEL_ENC_SIGN[MECANUM_WHEEL_COUNT] = {1, -1, 1, -1};
/* RF and RR motor channels are physically swapped vs the encoders (verified
   2026-06-11 by per-wheel encoder+visual): the realized [vx,vy,wz] response of
   physical RF equals the standard RR row and vice versa. RF/RR share the same
   vx & wz signs and differ only in vy, so swapping them fixes strafe (vy) while
   leaving the verified vx (forward) and wz (CCW) untouched, and re-pairs each
   logical motor with its own encoder for closed-loop PID.
   Original (pre-swap): RF=CH3/PA4/PA5  RR=CH4/PB8/PB9. */
static AppMotorHw app_motor_hw[MECANUM_WHEEL_COUNT] = {
  [MECANUM_WHEEL_LF] = {&htim3, TIM_CHANNEL_1, GPIOB, GPIO_PIN_12, GPIOB, GPIO_PIN_13},
  [MECANUM_WHEEL_RF] = {&htim3, TIM_CHANNEL_4, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9},
  [MECANUM_WHEEL_LR] = {&htim3, TIM_CHANNEL_2, GPIOB, GPIO_PIN_14, GPIOB, GPIO_PIN_15},
  [MECANUM_WHEEL_RR] = {&htim3, TIM_CHANNEL_3, GPIOA, GPIO_PIN_4, GPIOA, GPIO_PIN_5},
};

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM3_Init(void);
static void MX_TIM1_Init(void);
static void MX_TIM2_Init(void);
static void MX_TIM4_Init(void);
static void MX_TIM5_Init(void);
static void MX_USART2_UART_Init(void);
void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);
/* USER CODE BEGIN PFP */
static void app_encoders_start(void);
static void send_odom(void);
static void app_uart_start(void);
static void app_tick(void);
static void app_control_step(uint32_t now_ms);
static void app_update_comm_state(uint32_t now_ms);
static void dispatch_frame(const rdk_frame_t *frame);
static void send_ack(uint8_t ack_type, uint8_t ack_seq, uint8_t result);
static void send_status(void);
static HAL_StatusTypeDef send_protocol_frame(uint8_t type, const uint8_t *payload, uint8_t payload_len);
static void app_motor_output_start(void);
static void app_chassis_init(void);
static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user);
static void app_cmd_to_chassis(const rdk_cmd_vel_t *cmd);
static void app_chassis_stop(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* --- Fault forensics: figure out WHY the MCU restarted instead of guessing. ---
   g_fault_store lives in .noinit RAM (not zeroed by startup) so a HardFault record
   survives the reset. At boot we read the RCC reset flags (IWDG vs BOR-brownout vs
   NRST-pin vs POR vs SW) and any stored HardFault, then emit them as a plaintext
   "[BOOT] ..." line over CDC for the first few seconds (the RDK bridge ignores
   non-0xAA55 bytes; a raw serial read on the RDK catches it). */
typedef struct
{
  uint32_t magic;
  uint32_t cfsr, hfsr, bfar, mmfar, pc, lr, psr;
} FaultRecord;
#define APP_FAULT_MAGIC 0xDEADFA11u

__attribute__((section(".noinit"))) FaultRecord g_fault_store;  /* survives warm reset */
static uint32_t g_reset_csr;        /* RCC->CSR captured at boot */
static FaultRecord g_fault_last;    /* HardFault record from the previous life, if any */
static uint8_t g_fault_had;         /* 1 if a HardFault record was present at boot */
static uint32_t g_forensics_last_ms;

/* Called from HardFault_Handler (stm32f4xx_it.c) with the faulting stack pointer.
   Stacked frame layout: sp[0..7] = R0,R1,R2,R3,R12,LR,PC,xPSR. */
void app_hardfault_capture(uint32_t *sp)
{
  g_fault_store.cfsr  = SCB->CFSR;
  g_fault_store.hfsr  = SCB->HFSR;
  g_fault_store.bfar  = SCB->BFAR;
  g_fault_store.mmfar = SCB->MMFAR;
  g_fault_store.lr    = sp[5];
  g_fault_store.pc    = sp[6];
  g_fault_store.psr   = sp[7];
  g_fault_store.magic = APP_FAULT_MAGIC;
  NVIC_SystemReset();               /* reboot -> motor PWM off -> next boot reports it */
}

/* Read reset cause + any stored HardFault once, at boot. Call before starting IWDG. */
static void app_forensics_init(void)
{
  g_reset_csr = RCC->CSR;
  RCC->CSR |= RCC_CSR_RMVF;         /* clear reset flags so next boot is fresh */
  if (g_fault_store.magic == APP_FAULT_MAGIC)
  {
    g_fault_last = g_fault_store;
    g_fault_had = 1u;
    g_fault_store.magic = 0u;       /* consume it */
  }
}

/* Emit the plaintext forensics line over CDC (best-effort; dropped if CDC busy). */
static void app_forensics_report(void)
{
  static char line[176];
  int n = snprintf(line, sizeof(line),
      "\r\n[BOOT] CSR=%08lX%s%s%s%s%s | HF=%s CFSR=%08lX HFSR=%08lX PC=%08lX LR=%08lX\r\n",
      (unsigned long)g_reset_csr,
      (g_reset_csr & RCC_CSR_IWDGRSTF) ? " IWDG" : "",
      (g_reset_csr & RCC_CSR_BORRSTF)  ? " BOR"  : "",
      (g_reset_csr & RCC_CSR_PINRSTF)  ? " PIN"  : "",
      (g_reset_csr & RCC_CSR_PORRSTF)  ? " POR"  : "",
      (g_reset_csr & RCC_CSR_SFTRSTF)  ? " SW"   : "",
      g_fault_had ? "YES" : "no",
      (unsigned long)(g_fault_had ? g_fault_last.cfsr : 0u),
      (unsigned long)(g_fault_had ? g_fault_last.hfsr : 0u),
      (unsigned long)(g_fault_had ? g_fault_last.pc   : 0u),
      (unsigned long)(g_fault_had ? g_fault_last.lr   : 0u));
  if (n > 0)
  {
    /* The 1 Hz emit lands on the same tick as the 10 Hz telemetry (both on
       100 ms boundaries), so the CDC is busy — retry briefly until it frees so
       the line actually goes out instead of being dropped every time. */
    uint32_t start = HAL_GetTick();
    while ((CDC_Transmit_FS((uint8_t *)line, (uint16_t)n) == USBD_BUSY) &&
           ((uint32_t)(HAL_GetTick() - start) < 10u))
    {
      /* spin briefly waiting for the in-flight telemetry transfer to complete */
    }
  }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM3_Init();
  MX_TIM1_Init();
  MX_TIM2_Init();
  MX_TIM4_Init();
  MX_TIM5_Init();
  MX_USART2_UART_Init();
  MX_USB_DEVICE_Init();
  /* USER CODE BEGIN 2 */
  app_motor_output_start();
  app_encoders_start();
  app_chassis_init();
  app_uart_start();

  /* Capture the reset cause + any HardFault record BEFORE starting the watchdog. */
  app_forensics_init();

  /* Independent watchdog (IWDG): LSI-clocked, /32 prescaler, RLR=250 -> ~250 ms.
     SAFETY NET AGAINST RUNAWAY: if app_tick() ever stops kicking it (firmware
     hang / HardFault infinite-loop / stalled main loop), the MCU resets. On reset
     the motor-PWM GPIOs go inactive, so the motors STOP instead of latching the
     last commanded PWM into a runaway. app_tick worst case is ~10 ms (bounded CDC
     send), far under the timeout, so this never false-fires. Started here (write
     access via 0x5555 -> PR/RLR -> reload 0xAAAA -> start 0xCCCC); kicked each
     loop iteration below. IWDG is disabled after any reset, so DFU (BOOT0+RST)
     is unaffected. */
  IWDG->KR  = 0x5555u;   /* enable write access to PR/RLR */
  IWDG->PR  = 3u;        /* prescaler /32 (~1 kHz from LSI) */
  IWDG->RLR = 250u;      /* reload -> ~250 ms timeout */
  IWDG->KR  = 0xAAAAu;   /* reload the counter */
  IWDG->KR  = 0xCCCCu;   /* start the watchdog (cannot be stopped except by reset) */

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    IWDG->KR = 0xAAAAu;   /* kick the watchdog; a hang below stops this -> MCU reset -> motors off */
    app_tick();
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 25;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  /* PLLQ=7 -> USB clock = VCO(336MHz)/7 = 48MHz exactly (required for USB FS).
     SYSCLK is unaffected (still PLLP/4 = 84MHz). Changed from 4 when the chassis
     link moved off USART2 onto the native USB CDC (Type-C) on 2026-06-14. */
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{

  /* USER CODE BEGIN TIM3_Init 0 */

  /* USER CODE END TIM3_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM3_Init 1 */

  /* USER CODE END TIM3_Init 1 */
  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 3;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = APP_CHASSIS_PWM_MAX;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM3_Init 2 */

  /* USER CODE END TIM3_Init 2 */
  HAL_TIM_MspPostInit(&htim3);

}

/* Encoder quadrature config shared by TIM1/2/4/5 (x4 counting, input filter). */
static void app_encoder_config(TIM_Encoder_InitTypeDef *sConfig)
{
  sConfig->EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig->IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig->IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig->IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig->IC1Filter = 10;
  sConfig->IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig->IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig->IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig->IC2Filter = 10;
}

/**
  * @brief TIM1 Initialization Function (RF wheel encoder: PA8/PA9)
  */
static void MX_TIM1_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim1.Instance = TIM1;
  htim1.Init.Prescaler = 0;
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.Period = 65535;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.RepetitionCounter = 0;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  app_encoder_config(&sConfig);
  if (HAL_TIM_Encoder_Init(&htim1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim1, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function (LR wheel encoder: PA15/PB3)
  */
static void MX_TIM2_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 65535;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  app_encoder_config(&sConfig);
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM4 Initialization Function (RR wheel encoder: PB6/PB7)
  */
static void MX_TIM4_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim4.Instance = TIM4;
  htim4.Init.Prescaler = 0;
  htim4.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim4.Init.Period = 65535;
  htim4.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim4.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  app_encoder_config(&sConfig);
  if (HAL_TIM_Encoder_Init(&htim4, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim4, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM5 Initialization Function (LF wheel encoder: PA0/PA1)
  */
static void MX_TIM5_Init(void)
{
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim5.Instance = TIM5;
  htim5.Init.Prescaler = 0;
  htim5.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim5.Init.Period = 65535;
  htim5.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim5.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  app_encoder_config(&sConfig);
  if (HAL_TIM_Encoder_Init(&htim5, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim5, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4|GPIO_PIN_5, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8|GPIO_PIN_9
                          |GPIO_PIN_12|GPIO_PIN_13|GPIO_PIN_14|GPIO_PIN_15, GPIO_PIN_RESET);

  /*Configure GPIO pin : PC13 */
  GPIO_InitStruct.Pin = GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pins : PA4 PA5 (RF direction IN1/IN2) */
  GPIO_InitStruct.Pin = GPIO_PIN_4|GPIO_PIN_5;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PB8 PB9 (RR dir) PB12 PB13 (LF dir) PB14 PB15 (LR dir) */
  GPIO_InitStruct.Pin = GPIO_PIN_8|GPIO_PIN_9
                          |GPIO_PIN_12|GPIO_PIN_13|GPIO_PIN_14|GPIO_PIN_15;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
static void app_uart_start(void)
{
  uint32_t now = HAL_GetTick();

  rdk_parser_init(&uart_parser);
  app_last_cmd_ms = now;
  app_last_heartbeat_ms = now;
  app_last_status_ms = now;
  /* RX now arrives via USB CDC (CDC_Receive_FS -> rdk_comm_on_rx_bytes), which
     is event-driven and needs no arming here. USART2 RX is intentionally left
     un-armed: with the chassis link on USB, PA3 is unused and would otherwise
     float and inject noise/false CRC errors. */
  send_status();
}

static void app_tick(void)
{
  uint32_t now = HAL_GetTick();

  /* app_update_comm_state stops the chassis (zeroing setpoints + resetting the
     PIDs) on estop / heartbeat-loss / command timeout; app_control_step then
     runs the closed-loop velocity tracking at APP_CTRL_PERIOD_MS. */
  app_update_comm_state(now);
  app_control_step(now);
  if ((uint32_t)(now - app_last_status_ms) >= APP_STATUS_PERIOD_MS)
  {
    app_last_status_ms = now;
    send_status();
    send_odom();
  }
  /* Re-emit the forensics line every 5 s indefinitely (not just at boot): the
     RDK bridge ignores non-0xAA55 bytes, and the way we actually diagnose a hang
     is by raw-reading the port AFTER it happens. A one-shot boot window is missed
     if the reader connects late (USB re-enum) or the CDC's single pending slot is
     hogged by telemetry before a host drains it. Repeating forever makes the last
     reset cause catchable whenever anyone connects. */
  if ((uint32_t)(now - g_forensics_last_ms) >= 5000u)
  {
    g_forensics_last_ms = now;
    app_forensics_report();
  }
}

static void app_update_comm_state(uint32_t now_ms)
{
  if (app_estop != 0u)
  {
    app_comm_state = RDK_COMM_OK;
    app_fault_code = APP_FAULT_ESTOP;
    app_chassis_stop();
  }
  else if ((uint32_t)(now_ms - app_last_heartbeat_ms) > APP_HEARTBEAT_TIMEOUT_MS)
  {
    app_comm_state = RDK_COMM_HEARTBEAT_TIMEOUT;
    app_fault_code = APP_FAULT_HEARTBEAT_TIMEOUT;
    app_chassis_stop();
  }
  else if ((uint32_t)(now_ms - app_last_cmd_ms) > APP_CMD_TIMEOUT_MS)
  {
    app_comm_state = RDK_COMM_CMD_TIMEOUT;
    app_fault_code = APP_FAULT_CMD_TIMEOUT;
    app_chassis_stop();
  }
  else
  {
    app_comm_state = RDK_COMM_OK;
    app_fault_code = APP_FAULT_NONE;
  }
}

static void app_motor_output_start(void)
{
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4|GPIO_PIN_5, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8|GPIO_PIN_9
                          |GPIO_PIN_12|GPIO_PIN_13|GPIO_PIN_14|GPIO_PIN_15, GPIO_PIN_RESET);

  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0u);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0u);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_3, 0u);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_4, 0u);

  if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
}

static void dispatch_frame(const rdk_frame_t *frame)
{
  uint8_t result = RDK_ACK_OK;
  uint32_t uptime_ms = 0u;
  rdk_cmd_vel_t cmd;

  switch (frame->type)
  {
    case RDK_FRAME_HEARTBEAT:
      if (rdk_unpack_heartbeat(frame->payload, frame->len, &uptime_ms) == 0)
      {
        (void)uptime_ms;
        app_last_heartbeat_ms = HAL_GetTick();
      }
      else
      {
        result = RDK_ACK_LEN_ERROR;
      }
      break;

    case RDK_FRAME_CMD_VEL:
      if (rdk_unpack_cmd_vel(frame->payload, frame->len, &cmd) != 0)
      {
        result = RDK_ACK_LEN_ERROR;
      }
      else if (app_estop != 0u)
      {
        result = RDK_ACK_ESTOP_ACTIVE;
        app_chassis_stop();
      }
      else if (app_mode == RDK_MODE_IDLE)
      {
        result = RDK_ACK_MODE_NOT_ALLOWED;
        app_chassis_stop();
      }
      else
      {
        app_cmd_to_chassis(&cmd);
        app_last_cmd_ms = HAL_GetTick();
        app_last_cmd_seq = frame->seq;
      }
      break;

    case RDK_FRAME_SET_MODE:
      if (frame->len != 1u)
      {
        result = RDK_ACK_LEN_ERROR;
      }
      else if (frame->payload[0] > RDK_MODE_TEST)
      {
        result = RDK_ACK_MODE_NOT_ALLOWED;
      }
      else
      {
        app_mode = frame->payload[0];
        if (app_mode == RDK_MODE_IDLE)
        {
          app_chassis_stop();
        }
      }
      break;

    case RDK_FRAME_SET_PID:
    {
      rdk_pid_gains_t gains;
      if (rdk_unpack_set_pid(frame->payload, frame->len, &gains) != 0)
      {
        result = RDK_ACK_LEN_ERROR;
      }
      else
      {
        uint8_t w;
        for (w = 0u; w < (uint8_t)MECANUM_WHEEL_COUNT; w++)
        {
          if ((gains.wheel == 0xFFu) || (gains.wheel == w))
          {
            app_wheel_pid[w].cfg.kp = gains.kp;
            app_wheel_pid[w].cfg.ki = gains.ki;
            app_wheel_pid[w].cfg.kd = gains.kd;
            app_wheel_pid[w].cfg.ff = gains.ff;
            WheelPid_Reset(&app_wheel_pid[w]);
          }
        }
      }
      break;
    }

    case RDK_FRAME_STOP:
      if (frame->len != 1u)
      {
        result = RDK_ACK_LEN_ERROR;
      }
      else
      {
        app_mode = RDK_MODE_IDLE;
        app_last_cmd_seq = frame->seq;
        app_chassis_stop();
      }
      break;

    default:
      result = RDK_ACK_UNSUPPORTED_TYPE;
      break;
  }

  send_ack(frame->type, frame->seq, result);
}

static void app_chassis_init(void)
{
  MecanumDriveConfig cfg;

  MecanumDrive_DefaultConfig(&cfg);
  cfg.wheel_radius_m = APP_CHASSIS_WHEEL_RADIUS_M;
  cfg.half_length_m = APP_CHASSIS_HALF_LENGTH_M;
  cfg.half_width_m = APP_CHASSIS_HALF_WIDTH_M;
  cfg.max_wheel_radps = APP_CHASSIS_MAX_WHEEL_RADPS;
  cfg.pwm_max = APP_CHASSIS_PWM_MAX;
  cfg.command_timeout_ms = APP_CMD_TIMEOUT_MS;
  cfg.invert[MECANUM_WHEEL_LF] = -1;
  cfg.invert[MECANUM_WHEEL_LR] = -1;
  cfg.write_motor = app_write_motor;
  cfg.user = 0;

  (void)MecanumDrive_Init(&app_chassis, &cfg);

  /* Per-wheel velocity PID. ff = pwm_max/max_radps reproduces the open-loop
     mapping exactly when kp=ki=kd=0, so closed loop starts behaving identically
     to before and gains are raised live via SET_PID. */
  {
    WheelPidConfig pidcfg;
    uint8_t i;
    /* Tuned on hardware 2026-06-14 (suspended, with velocity LPF): tracks the
       4 rad/s setpoint to ~1-16% with no ringing. PID is default-ON (per user:
       bake the gains in). Still runtime-overridable via SET_PID. */
    pidcfg.kp = 15.0f;
    pidcfg.ki = 30.0f;
    pidcfg.kd = 0.0f;
    pidcfg.ff = (float)APP_CHASSIS_PWM_MAX / APP_CHASSIS_MAX_WHEEL_RADPS;
    pidcfg.out_min = -(float)APP_CHASSIS_PWM_MAX;
    pidcfg.out_max = (float)APP_CHASSIS_PWM_MAX;
    pidcfg.integral_min = -(float)APP_CHASSIS_PWM_MAX;
    pidcfg.integral_max = (float)APP_CHASSIS_PWM_MAX;
    for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++) {
      WheelPid_Init(&app_wheel_pid[i], &pidcfg);
      app_wheel_setpoint_radps[i] = 0.0f;
      app_wheel_vel_filt[i] = 0.0f;
    }
    app_have_last_enc = 0u;
    app_last_ctrl_ms = HAL_GetTick();
  }
}

static void app_write_motor(MecanumWheelId wheel, const MecanumMotorCommand *command, void *user)
{
  AppMotorHw *hw;

  (void)user;

  if ((wheel >= MECANUM_WHEEL_COUNT) || (command == 0))
  {
    return;
  }

  hw = &app_motor_hw[wheel];
  app_last_motor_command[wheel] = *command;

  __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, 0u);

  if ((command->dir == MECANUM_DIR_STOP) || (command->pwm == 0u))
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_RESET);
    return;
  }

  /* All four motor leads are wired with inverted polarity vs the firmware's
     IN1/IN2 convention (verified 2026-06-11: +vx drove the robot backward on
     the ground). Swapping the IN1/IN2 levels here flips every wheel's physical
     direction at the hardware-facing layer, so +vx=forward, +vy and +wz become
     consistent too, while the kinematics mix stays pure. */
  if (command->dir == MECANUM_DIR_FORWARD)
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_SET);
  }
  else
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_RESET);
  }

  __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, command->pwm);
}

static void app_cmd_to_chassis(const rdk_cmd_vel_t *cmd)
{
  float wheel_radps[MECANUM_WHEEL_COUNT];
  uint8_t i;

  if (cmd == 0)
  {
    return;
  }

  /* Body twist -> per-wheel setpoints (rad/s). The closed-loop control step
     (app_control_step) tracks these with the per-wheel PID at APP_CTRL_PERIOD_MS.
     We no longer convert to PWM here (that was the open-loop path). */
  MecanumDrive_Mix(((float)cmd->vx_mm_s) / 1000.0f,
                   ((float)cmd->vy_mm_s) / 1000.0f,
                   ((float)cmd->wz_mrad_s) / 1000.0f,
                   &app_chassis.cfg,
                   wheel_radps);

  /* Medium-speed cap: scale all wheels by one factor if any exceeds the limit,
     so the motion direction is preserved (clamping wheels individually would
     distort the trajectory). */
  {
    float maxabs = 0.0f;
    float scale = 1.0f;
    for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++)
    {
      float a = (wheel_radps[i] >= 0.0f) ? wheel_radps[i] : -wheel_radps[i];
      if (a > maxabs)
      {
        maxabs = a;
      }
    }
    if (maxabs > APP_WHEEL_SETPOINT_MAX)
    {
      scale = APP_WHEEL_SETPOINT_MAX / maxabs;
    }
    for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++)
    {
      app_wheel_setpoint_radps[i] = wheel_radps[i] * scale;
    }
  }
}

static void app_chassis_stop(void)
{
  uint8_t i;
  for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++)
  {
    app_wheel_setpoint_radps[i] = 0.0f;
    WheelPid_Reset(&app_wheel_pid[i]);
  }
  MecanumDrive_Stop(&app_chassis);
}

/* int16 quadrature counter wrap-safe delta (handles 0<->65535 rollover). */
static int16_t app_wrapped_delta_u16(uint16_t now, uint16_t prev)
{
  return (int16_t)(uint16_t)(now - prev);
}

/* Fixed-rate closed-loop velocity control. Reads each wheel's encoder delta,
   converts to rad/s (forward-positive), runs the per-wheel PID against the
   stored setpoint, and writes PWM+direction. When not actively commanded
   (estop / IDLE / command timed out) it forces motors off and holds the PIDs
   reset, so a stalled/dropped encoder can never wind up into a runaway. */
static void app_control_step(uint32_t now_ms)
{
  uint32_t dt_ms;
  float dt;
  float rad_per_tick;
  uint16_t raw[MECANUM_WHEEL_COUNT];
  uint8_t active;
  uint8_t i;

  dt_ms = (uint32_t)(now_ms - app_last_ctrl_ms);
  if (dt_ms < APP_CTRL_PERIOD_MS)
  {
    return;
  }
  app_last_ctrl_ms = now_ms;
  dt = (float)dt_ms / 1000.0f;

  /* Same encoder->wheel mapping as send_odom. Re-mapped 2026-07-06 after a hot-glued
     rewire: per-wheel hand-spin showed physical LF's encoder now lands on TIM5 and
     physical LR on TIM2 (the left pair swapped vs the old wiring), so LF<-TIM5 and
     LR<-TIM2. RF<-TIM1, RR<-TIM4 unchanged. Signs {+1,-1,+1,-1} already correct. */
  raw[MECANUM_WHEEL_LF] = (uint16_t)__HAL_TIM_GET_COUNTER(&htim5);
  raw[MECANUM_WHEEL_RF] = (uint16_t)__HAL_TIM_GET_COUNTER(&htim1);
  raw[MECANUM_WHEEL_LR] = (uint16_t)__HAL_TIM_GET_COUNTER(&htim2);
  raw[MECANUM_WHEEL_RR] = (uint16_t)__HAL_TIM_GET_COUNTER(&htim4);

  if (app_have_last_enc == 0u)
  {
    for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++)
    {
      app_last_enc[i] = (int16_t)raw[i];
    }
    app_have_last_enc = 1u;
    return; /* need a baseline before the first velocity estimate */
  }

  active = (uint8_t)((app_estop == 0u) &&
                     (app_mode != RDK_MODE_IDLE) &&
                     ((uint32_t)(now_ms - app_last_cmd_ms) < APP_CMD_TIMEOUT_MS));

  rad_per_tick = APP_TWO_PI / APP_TICKS_PER_REV;

  for (i = 0u; i < (uint8_t)MECANUM_WHEEL_COUNT; i++)
  {
    int16_t d = app_wrapped_delta_u16(raw[i], (uint16_t)app_last_enc[i]);
    float measured;
    float out;
    MecanumMotorCommand cmd;

    app_last_enc[i] = (int16_t)raw[i];

    if (active == 0u)
    {
      WheelPid_Reset(&app_wheel_pid[i]);
      app_wheel_vel_filt[i] = 0.0f;
      app_wheel_stall_ms[i] = 0u;
      cmd.pwm = 0u;
      cmd.dir = MECANUM_DIR_STOP;
      app_write_motor((MecanumWheelId)i, &cmd, 0);
      continue;
    }

    /* Zero-command guard: commanded to ~stop -> force motor off + hold PID reset,
       so a wound-up integral (e.g. from a bad encoder while driving) can never keep
       the wheel running at setpoint 0. Coasts to a stop, immune to feedback faults. */
    {
      float sp = app_wheel_setpoint_radps[i];
      float sp_abs = (sp >= 0.0f) ? sp : -sp;
      if (sp_abs < APP_SETPOINT_DEADBAND)
      {
        WheelPid_Reset(&app_wheel_pid[i]);
        app_wheel_vel_filt[i] = 0.0f;
        app_wheel_stall_ms[i] = 0u;
        cmd.pwm = 0u;
        cmd.dir = MECANUM_DIR_STOP;
        app_write_motor((MecanumWheelId)i, &cmd, 0);
        continue;
      }
    }

    measured = (float)d * (float)APP_WHEEL_ENC_SIGN[i] * rad_per_tick / dt;
    /* EMA low-pass to suppress encoder-quantization noise before the PID. */
    app_wheel_vel_filt[i] += APP_VEL_LPF_ALPHA * (measured - app_wheel_vel_filt[i]);
    measured = app_wheel_vel_filt[i];

    /* Encoder-stall / dropped-feedback guard: commanded to move but no motion
       seen -> count time; past the timeout, cut this wheel so its PID integral
       can't wind up into a full-speed runaway on a loose encoder. */
    {
      float sp_abs = (app_wheel_setpoint_radps[i] >= 0.0f)
                     ? app_wheel_setpoint_radps[i] : -app_wheel_setpoint_radps[i];
      float meas_abs = (measured >= 0.0f) ? measured : -measured;
      if ((sp_abs > APP_STALL_SETPOINT_MIN) && (meas_abs < APP_STALL_MEASURED_MAX))
      {
        app_wheel_stall_ms[i] += dt_ms;
      }
      else
      {
        app_wheel_stall_ms[i] = 0u;
      }
      if (app_wheel_stall_ms[i] >= APP_STALL_TIMEOUT_MS)
      {
        WheelPid_Reset(&app_wheel_pid[i]);
        cmd.pwm = 0u;
        cmd.dir = MECANUM_DIR_STOP;
        app_write_motor((MecanumWheelId)i, &cmd, 0);
        continue;
      }
    }

    out = WheelPid_Update(&app_wheel_pid[i],
                          app_wheel_setpoint_radps[i], measured, dt);

    {
      float mag = (out >= 0.0f) ? out : -out;
      int8_t invert = (app_chassis.cfg.invert[i] < 0) ? -1 : 1;
      int8_t dir_sign = (out >= 0.0f) ? 1 : -1;
      uint16_t pwm;

      if (mag > (float)app_chassis.cfg.pwm_max)
      {
        mag = (float)app_chassis.cfg.pwm_max;
      }
      pwm = (uint16_t)(mag + 0.5f);
      if (pwm < app_chassis.cfg.pwm_deadband)
      {
        pwm = 0u;
      }
      cmd.pwm = pwm;
      if (pwm == 0u)
      {
        cmd.dir = MECANUM_DIR_STOP;
      }
      else if ((dir_sign * invert) > 0)
      {
        cmd.dir = MECANUM_DIR_FORWARD;
      }
      else
      {
        cmd.dir = MECANUM_DIR_REVERSE;
      }
      app_write_motor((MecanumWheelId)i, &cmd, 0);
    }
  }
}

static HAL_StatusTypeDef send_protocol_frame(uint8_t type, const uint8_t *payload, uint8_t payload_len)
{
  uint8_t raw[RDK_MAX_FRAME_LEN];
  int frame_len = rdk_encode_frame(type, uart_tx_seq, payload, payload_len, raw, sizeof(raw));

  if (frame_len <= 0)
  {
    return HAL_ERROR;
  }

  uart_tx_seq = (uint8_t)(uart_tx_seq + 1u);

  /* Chassis link now runs over the native USB CDC (Type-C), not USART2.
     CDC_Transmit_FS returns USBD_BUSY while the previous IN packet is still
     in flight; retry briefly so back-to-back frames (STATUS+ODOM) don't drop.
     If the host is absent it returns BUSY/FAIL and we give up after the budget
     (no blocking when unplugged). */
  uint32_t start = HAL_GetTick();
  uint8_t rc;
  do
  {
    rc = CDC_Transmit_FS(raw, (uint16_t)frame_len);
    if (rc == USBD_OK)
    {
      return HAL_OK;
    }
  } while ((rc == USBD_BUSY) && ((uint32_t)(HAL_GetTick() - start) < 5u));

  return HAL_ERROR;
}

static void send_ack(uint8_t ack_type, uint8_t ack_seq, uint8_t result)
{
  uint8_t payload[3];
  rdk_ack_t ack = {
    .ack_type = ack_type,
    .ack_seq = ack_seq,
    .result = result,
  };

  rdk_pack_ack(payload, &ack);
  (void)send_protocol_frame(RDK_FRAME_ACK, payload, sizeof(payload));
}

static void send_status(void)
{
  uint8_t payload[8];
  rdk_status_t status = {
    .mode = app_mode,
    .estop = app_estop,
    .fault_code = app_fault_code,
    .battery_mv = APP_BATTERY_MV,
    .last_cmd_seq = app_last_cmd_seq,
    .comm_state = app_comm_state,
  };

  rdk_pack_status(payload, &status);
  (void)send_protocol_frame(RDK_FRAME_STATUS, payload, sizeof(payload));
}

static void app_encoders_start(void)
{
  (void)HAL_TIM_Encoder_Start(&htim1, TIM_CHANNEL_ALL);
  (void)HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
  (void)HAL_TIM_Encoder_Start(&htim4, TIM_CHANNEL_ALL);
  (void)HAL_TIM_Encoder_Start(&htim5, TIM_CHANNEL_ALL);
}

static void send_odom(void)
{
  /* Raw 16-bit quadrature counter per wheel (x4 counts). Order: LF, RF, LR, RR.
     Physical wiring re-verified 2026-07-06 by per-wheel hand-spin after a hot-glued
     rewire: the left pair swapped again -- physical LF now lands on TIM5(PA0/PA1)
     and physical LR on TIM2(PA15/PB3). We therefore read LF<-TIM5 and LR<-TIM2 so
     the ODOM payload is canonical (LF,RF,LR,RR). RF=TIM1(PA8/PA9) RR=TIM4(PB6/PB7) OK.
     Must stay in sync with the identical mapping in app_control_step. */
  uint8_t payload[8];
  int16_t lf = (int16_t)__HAL_TIM_GET_COUNTER(&htim5);
  int16_t rf = (int16_t)__HAL_TIM_GET_COUNTER(&htim1);
  int16_t lr = (int16_t)__HAL_TIM_GET_COUNTER(&htim2);
  int16_t rr = (int16_t)__HAL_TIM_GET_COUNTER(&htim4);

  rdk_pack_odom(payload, lf, rf, lr, rr);
  (void)send_protocol_frame(RDK_FRAME_ODOM, payload, sizeof(payload));
}

/* Chassis link RX path. Called from the USB CDC interface (usbd_cdc_if.c,
   CDC_Receive_FS) for every received packet -- strong override of the __weak
   stub there. Feeds each byte into the same rdk protocol parser the old USART2
   RX interrupt used, so dispatch_frame / comm-state logic is unchanged. */
void rdk_comm_on_rx_bytes(const uint8_t *data, uint32_t len)
{
  rdk_frame_t frame;
  uint32_t i;

  for (i = 0u; i < len; i++)
  {
    rdk_parse_result_t result = rdk_parser_feed(&uart_parser, data[i], &frame);

    if (result == RDK_PARSE_FRAME_READY)
    {
      dispatch_frame(&frame);
    }
    else if (result == RDK_PARSE_CRC_ERROR)
    {
      app_comm_state = RDK_COMM_CRC_ERROR_LIMIT;
      app_fault_code = APP_FAULT_CRC_ERROR_LIMIT;
    }
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART2)
  {
    rdk_frame_t frame;
    rdk_parse_result_t result = rdk_parser_feed(&uart_parser, uart_rx_byte, &frame);

    if (result == RDK_PARSE_FRAME_READY)
    {
      dispatch_frame(&frame);
    }
    else if (result == RDK_PARSE_CRC_ERROR)
    {
      app_comm_state = RDK_COMM_CRC_ERROR_LIMIT;
      app_fault_code = APP_FAULT_CRC_ERROR_LIMIT;
    }

    (void)HAL_UART_Receive_IT(&huart2, &uart_rx_byte, 1);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART2)
  {
    (void)HAL_UART_Receive_IT(&huart2, &uart_rx_byte, 1);
  }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
