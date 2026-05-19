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
  GPIO_TypeDef *en_port;
  uint16_t en_pin;
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
#define APP_CHASSIS_WHEEL_RADIUS_M 0.05f
#define APP_CHASSIS_HALF_LENGTH_M 0.12f
#define APP_CHASSIS_HALF_WIDTH_M 0.10f
#define APP_CHASSIS_MAX_WHEEL_RADPS 30.0f
#define APP_CHASSIS_PWM_MAX 999u

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim3;

UART_HandleTypeDef huart1;

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
static AppMotorHw app_motor_hw[MECANUM_WHEEL_COUNT] = {
  [MECANUM_WHEEL_LF] = {&htim3, TIM_CHANNEL_1, GPIOA, GPIO_PIN_0, GPIOA, GPIO_PIN_1, GPIOB, GPIO_PIN_10},
  [MECANUM_WHEEL_RF] = {&htim3, TIM_CHANNEL_3, GPIOA, GPIO_PIN_4, GPIOA, GPIO_PIN_5, GPIOB, GPIO_PIN_11},
  [MECANUM_WHEEL_LR] = {&htim3, TIM_CHANNEL_2, GPIOA, GPIO_PIN_2, GPIOA, GPIO_PIN_3, GPIOB, GPIO_PIN_10},
  [MECANUM_WHEEL_RR] = {&htim3, TIM_CHANNEL_4, GPIOB, GPIO_PIN_8, GPIOB, GPIO_PIN_9, GPIOB, GPIO_PIN_11},
};

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM3_Init(void);
static void MX_USART1_UART_Init(void);
void HAL_TIM_MspPostInit(TIM_HandleTypeDef *htim);
/* USER CODE BEGIN PFP */
static void app_uart_start(void);
static void app_tick(void);
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
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  app_motor_output_start();
  app_chassis_init();
  app_uart_start();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
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
  RCC_OscInitStruct.PLL.PLLQ = 4;
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
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

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
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3
                          |GPIO_PIN_4|GPIO_PIN_5, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8|GPIO_PIN_9|GPIO_PIN_10|GPIO_PIN_11, GPIO_PIN_RESET);

  /*Configure GPIO pin : PC13 */
  GPIO_InitStruct.Pin = GPIO_PIN_13;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pins : PA0 PA1 PA2 PA3 PA4 PA5 */
  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3
                          |GPIO_PIN_4|GPIO_PIN_5;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PB8 PB9 PB10 PB11 */
  GPIO_InitStruct.Pin = GPIO_PIN_8|GPIO_PIN_9|GPIO_PIN_10|GPIO_PIN_11;
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
  (void)HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1);
  send_status();
}

static void app_tick(void)
{
  uint32_t now = HAL_GetTick();

  MecanumDrive_UpdateTimeout(&app_chassis, now);
  app_update_comm_state(now);
  if ((uint32_t)(now - app_last_status_ms) >= APP_STATUS_PERIOD_MS)
  {
    app_last_status_ms = now;
    send_status();
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
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3
                          |GPIO_PIN_4|GPIO_PIN_5, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_8|GPIO_PIN_9, GPIO_PIN_RESET);

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

  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10|GPIO_PIN_11, GPIO_PIN_SET);
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
  cfg.write_motor = app_write_motor;
  cfg.user = 0;

  (void)MecanumDrive_Init(&app_chassis, &cfg);
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

  HAL_GPIO_WritePin(hw->en_port, hw->en_pin, GPIO_PIN_SET);

  if (command->dir == MECANUM_DIR_FORWARD)
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_RESET);
  }
  else
  {
    HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_SET);
  }

  __HAL_TIM_SET_COMPARE(hw->htim, hw->channel, command->pwm);
}

static void app_cmd_to_chassis(const rdk_cmd_vel_t *cmd)
{
  if (cmd == 0)
  {
    return;
  }

  MecanumDrive_SetVelocity(&app_chassis,
                           ((float)cmd->vx_mm_s) / 1000.0f,
                           ((float)cmd->vy_mm_s) / 1000.0f,
                           ((float)cmd->wz_mrad_s) / 1000.0f,
                           HAL_GetTick());
}

static void app_chassis_stop(void)
{
  MecanumDrive_Stop(&app_chassis);
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
  return HAL_UART_Transmit(&huart1, raw, (uint16_t)frame_len, 20u);
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

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART1)
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

    (void)HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart->Instance == USART1)
  {
    (void)HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1);
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
