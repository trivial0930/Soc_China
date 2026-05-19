import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "stm32/firmware/stm32_motion_controller/Core/Src/main.c"
HAL_CONF_H = ROOT / "stm32/firmware/stm32_motion_controller/Core/Inc/stm32f4xx_hal_conf.h"
HAL_TIM_C = ROOT / "stm32/firmware/stm32_motion_controller/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c"


class Stm32MainUartIntegrationTest(unittest.TestCase):
    def test_main_starts_uart_rx_and_can_reply_to_rdk(self):
        source = MAIN_C.read_text(encoding="utf-8")

        required_snippets = [
            '#include "rdk_stm32_uart.h"',
            '#include "mecanum_drive.h"',
            "rdk_parser_init(&uart_parser)",
            "HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1)",
            "static MecanumDrive app_chassis",
            "app_chassis_init()",
            "MecanumDrive_SetVelocity(&app_chassis,",
            "MecanumDrive_UpdateTimeout(&app_chassis, now)",
            "MecanumDrive_Stop(&app_chassis)",
            "app_cmd_to_chassis(&cmd)",
            "app_write_motor",
            "void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)",
            "rdk_parser_feed(&uart_parser, uart_rx_byte, &frame)",
            "send_ack(frame->type, frame->seq,",
            "send_status",
            "RDK_FRAME_STATUS",
            "RDK_FRAME_ACK",
        ]

        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source)

    def test_main_drives_tb6612_outputs_with_tim3_pwm_and_gpio(self):
        source = MAIN_C.read_text(encoding="utf-8")
        hal_conf = HAL_CONF_H.read_text(encoding="utf-8")

        required_main_snippets = [
            "TIM_HandleTypeDef htim3",
            "static AppMotorHw app_motor_hw[MECANUM_WHEEL_COUNT]",
            "MX_TIM3_Init()",
            "HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1)",
            "HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2)",
            "HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_3)",
            "HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_4)",
            "__HAL_TIM_SET_COMPARE(hw->htim, hw->channel, command->pwm)",
            "__HAL_TIM_SET_COMPARE(hw->htim, hw->channel, 0u)",
            "HAL_GPIO_WritePin(hw->in1_port, hw->in1_pin, GPIO_PIN_SET)",
            "HAL_GPIO_WritePin(hw->in2_port, hw->in2_pin, GPIO_PIN_SET)",
            "GPIO_PIN_10|GPIO_PIN_11",
            "GPIO_PIN_8|GPIO_PIN_9",
        ]

        for snippet in required_main_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source)

        self.assertIn("#define HAL_TIM_MODULE_ENABLED", hal_conf)
        self.assertTrue(HAL_TIM_C.exists(), "HAL TIM driver source must be present for CubeIDE build")


if __name__ == "__main__":
    unittest.main()
