import unittest

from shared.protocol.rdk_stm32_uart import (
    Ack,
    AckResult,
    CommState,
    Frame,
    FrameParser,
    FrameType,
    Mode,
    Status,
    StopReason,
    crc16_ccitt_false,
    decode_frame,
    encode_frame,
    pack_ack,
    pack_cmd_vel,
    pack_fault,
    pack_heartbeat,
    pack_odom,
    pack_set_mode,
    pack_status,
    pack_stop,
    unpack_ack,
    unpack_cmd_vel,
    unpack_fault,
    unpack_odom,
    unpack_set_mode,
    unpack_status,
    unpack_stop,
)


class RdkStm32UartProtocolTest(unittest.TestCase):
    def test_crc16_uses_ccitt_false_reference_vector(self):
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_encode_decode_frame_round_trip(self):
        payload = pack_heartbeat(1000)

        raw = encode_frame(FrameType.HEARTBEAT, seq=7, payload=payload)
        self.assertEqual(raw[:2], b"\xAA\x55")
        self.assertEqual(raw[2:6], b"\x01\x01\x07\x04")

        frame = decode_frame(raw)
        self.assertEqual(frame, Frame(frame_type=FrameType.HEARTBEAT, seq=7, payload=payload))

    def test_stream_parser_resyncs_after_noise_and_rejects_bad_crc(self):
        good = encode_frame(FrameType.CMD_VEL, seq=8, payload=pack_cmd_vel(50, -25, 100))
        bad = bytearray(encode_frame(FrameType.STOP, seq=9, payload=pack_stop(StopReason.DEBUG_STOP)))
        bad[-1] ^= 0xFF

        parser = FrameParser()
        frames = []
        for chunk in (b"\x00junk\xAA", b"\x00", bytes(bad), good[:3], good[3:]):
            frames.extend(parser.feed(chunk))

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].frame_type, FrameType.CMD_VEL)
        self.assertEqual(unpack_cmd_vel(frames[0].payload), (50, -25, 100))
        self.assertEqual(parser.crc_errors, 1)

    def test_payload_helpers_are_little_endian_and_typed(self):
        self.assertEqual(pack_cmd_vel(-100, 25, -300), b"\x9c\xff\x19\x00\xd4\xfe")
        self.assertEqual(unpack_cmd_vel(b"\x9c\xff\x19\x00\xd4\xfe"), (-100, 25, -300))
        self.assertEqual(unpack_stop(pack_stop(StopReason.TASK_DONE)), StopReason.TASK_DONE)
        self.assertEqual(unpack_set_mode(pack_set_mode(Mode.TEST)), Mode.TEST)

        status = Status(
            mode=Mode.MANUAL,
            estop=True,
            fault_code=0x0001,
            battery_mv=12050,
            last_cmd_seq=44,
            comm_state=CommState.OK,
        )
        self.assertEqual(unpack_status(pack_status(status)), status)
        self.assertEqual(unpack_odom(pack_odom(-1, 2, -3, 4)), (-1, 2, -3, 4))
        self.assertEqual(unpack_fault(pack_fault(0x0002, 0x1234)), (0x0002, 0x1234))

        ack = Ack(ack_type=FrameType.CMD_VEL, ack_seq=8, result=AckResult.OK)
        self.assertEqual(unpack_ack(pack_ack(ack)), ack)

    def test_payload_length_errors_are_explicit(self):
        with self.assertRaises(ValueError):
            unpack_status(b"\x00")
        with self.assertRaises(ValueError):
            encode_frame(FrameType.HEARTBEAT, seq=1, payload=bytes(range(65)))


if __name__ == "__main__":
    unittest.main()
