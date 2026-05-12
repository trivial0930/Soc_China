import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_C = ROOT / "stm32/firmware/stm32_motion_controller/Core/Src/main.c"


class Stm32MainUartIntegrationTest(unittest.TestCase):
    def test_main_starts_uart_rx_and_can_reply_to_rdk(self):
        source = MAIN_C.read_text(encoding="utf-8")

        required_snippets = [
            '#include "rdk_stm32_uart.h"',
            "rdk_parser_init(&uart_parser)",
            "HAL_UART_Receive_IT(&huart1, &uart_rx_byte, 1)",
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


if __name__ == "__main__":
    unittest.main()
