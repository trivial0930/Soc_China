import errno
import unittest
from unittest.mock import patch

from shared.protocol.rdk_stm32_uart import CommState, FrameType, Mode, Status, pack_status
from sim.stm32_simulator.serial_simulator import send_frame


class Stm32SimulatorTest(unittest.TestCase):
    def test_send_frame_reports_pty_backpressure_without_crashing(self):
        status = Status(
            mode=Mode.IDLE,
            estop=False,
            fault_code=0,
            battery_mv=12000,
            last_cmd_seq=0,
            comm_state=CommState.OK,
        )

        def blocked_write(fd, data):
            raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable")

        with patch("sim.stm32_simulator.serial_simulator.os.write", blocked_write):
            self.assertFalse(send_frame(1, FrameType.STATUS, 0, pack_status(status)))


if __name__ == "__main__":
    unittest.main()
