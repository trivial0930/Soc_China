import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "stm32/firmware/stm32_motion_controller/Core/Src/main.c"
HAL_CONF_H = ROOT / "stm32/firmware/stm32_motion_controller/Core/Inc/stm32f4xx_hal_conf.h"
HAL_TIM_C = ROOT / "stm32/firmware/stm32_motion_controller/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c"
IOC = ROOT / "stm32/firmware/stm32_motion_controller/stm32_motion_controller.ioc"


class Stm32MainUartIntegrationTest(unittest.TestCase):
    def test_main_starts_uart_rx_and_can_reply_to_rdk(self):
        source = MAIN_C.read_text(encoding="utf-8")

        required_snippets = [
            '#include "rdk_stm32_uart.h"',
            '#include "mecanum_drive.h"',
            "rdk_parser_init(&uart_parser)",
            "HAL_UART_Receive_IT(&huart2, &uart_rx_byte, 1)",
            "static MecanumDrive app_chassis",
            "app_chassis_init()",
            # Closed-loop velocity PID (2026-06-14): CMD_VEL -> Mix -> per-wheel
            # setpoints, tracked by WheelPid in the fixed-rate app_control_step.
            "MecanumDrive_Mix(",
            "app_control_step(now)",
            "WheelPid_Update(",
            "RDK_FRAME_SET_PID",
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
        ioc = IOC.read_text(encoding="utf-8")

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
            "GPIO_PIN_8|GPIO_PIN_9",
        ]

        for snippet in required_main_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source)

        self.assertIn("#define HAL_TIM_MODULE_ENABLED", hal_conf)
        self.assertTrue(HAL_TIM_C.exists(), "HAL TIM driver source must be present for CubeIDE build")

        forbidden_main_snippets = [
            "en_port",
            "en_pin",
            "GPIO_PIN_10|GPIO_PIN_11",
            "HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10",
            "HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11",
        ]

        for snippet in forbidden_main_snippets:
            with self.subTest(forbidden_snippet=snippet):
                self.assertNotIn(snippet, source)

        self.assertNotIn("PB10.Signal=GPIO_Output", ioc)
        self.assertNotIn("PB11.Signal=GPIO_Output", ioc)

    def test_main_inverts_left_wheels_for_current_motor_wiring(self):
        source = MAIN_C.read_text(encoding="utf-8")

        required_snippets = [
            "cfg.invert[MECANUM_WHEEL_LF] = -1;",
            "cfg.invert[MECANUM_WHEEL_LR] = -1;",
        ]

        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source)

    def test_main_uses_usart2_and_relocated_dir_pins_for_encoder_room(self):
        """RDK link moved to USART2 (PA2/PA3); LF/LR direction pins relocated to
        PB12-PB15 so PA0/PA1 (TIM5), PA2/PA3 (USART2) free up for encoders."""
        source = MAIN_C.read_text(encoding="utf-8")
        msp = (ROOT / "stm32/firmware/stm32_motion_controller/Core/Src/stm32f4xx_hal_msp.c").read_text(encoding="utf-8")

        required = [
            "huart2.Instance = USART2;",
            "MX_USART2_UART_Init();",
            # LF direction -> PB12/PB13, LR direction -> PB14/PB15
            "[MECANUM_WHEEL_LF] = {&htim3, TIM_CHANNEL_1, GPIOB, GPIO_PIN_12, GPIOB, GPIO_PIN_13}",
            "[MECANUM_WHEEL_LR] = {&htim3, TIM_CHANNEL_2, GPIOB, GPIO_PIN_14, GPIOB, GPIO_PIN_15}",
        ]
        for snippet in required:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, source)

        # USART2 must be mux'd to PA2/PA3 with AF7
        self.assertIn("GPIO_PIN_2|GPIO_PIN_3", msp)
        self.assertIn("GPIO_AF7_USART2", msp)

        # The old USART1/PA9-PA10 RDK link must be gone (those pins now feed encoders)
        self.assertNotIn("USART1", source)
        self.assertNotIn("huart1", source)


if __name__ == "__main__":
    unittest.main()
