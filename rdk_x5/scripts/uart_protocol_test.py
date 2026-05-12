#!/usr/bin/env python3
"""Local and serial smoke tests for the RDK-STM32 UART protocol."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.protocol.rdk_stm32_uart import (  # noqa: E402
    AckResult,
    Frame,
    FrameParser,
    FrameType,
    Mode,
    StopReason,
    decode_frame,
    encode_frame,
    frame_summary,
    pack_cmd_vel,
    pack_heartbeat,
    pack_set_mode,
    pack_stop,
    unpack_ack,
    unpack_fault,
    unpack_odom,
    unpack_status,
)


def import_serial():
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit("pyserial is required for --port. Install with: python3 -m pip install pyserial") from exc
    return serial


def payload_summary(frame: Frame) -> str:
    try:
        if frame.frame_type == FrameType.ACK:
            ack = unpack_ack(frame.payload)
            ack_type = ack.ack_type.name if isinstance(ack.ack_type, FrameType) else f"0x{ack.ack_type:02X}"
            return f"ACK {ack_type} seq={ack.ack_seq} result={ack.result.name}"
        if frame.frame_type == FrameType.STATUS:
            status = unpack_status(frame.payload)
            return (
                f"STATUS mode={status.mode.name} estop={int(status.estop)} "
                f"fault=0x{status.fault_code:04X} battery={status.battery_mv}mV "
                f"last_cmd_seq={status.last_cmd_seq} comm={status.comm_state.name}"
            )
        if frame.frame_type == FrameType.ODOM:
            return f"ODOM delta={unpack_odom(frame.payload)}"
        if frame.frame_type == FrameType.FAULT:
            fault_code, detail = unpack_fault(frame.payload)
            return f"FAULT code=0x{fault_code:04X} detail=0x{detail:04X}"
    except ValueError as exc:
        return f"payload decode error: {exc}"
    return frame_summary(frame)


def print_frame(prefix: str, frame: Frame) -> None:
    print(f"{prefix} {payload_summary(frame)}")


def local_self_test() -> int:
    parser = FrameParser()
    frames = []

    heartbeat = encode_frame(FrameType.HEARTBEAT, 1, pack_heartbeat(1000))
    cmd_zero = encode_frame(FrameType.CMD_VEL, 2, pack_cmd_vel(0, 0, 0))
    stop = encode_frame(FrameType.STOP, 3, pack_stop(StopReason.DEBUG_STOP))
    bad = bytearray(encode_frame(FrameType.SET_MODE, 4, pack_set_mode(Mode.TEST)))
    bad[-1] ^= 0xFF

    for chunk in (b"noise", heartbeat[:5], heartbeat[5:] + bytes(bad), cmd_zero + stop):
        frames.extend(parser.feed(chunk))

    print("[local] decoded frames:")
    for frame in frames:
        print_frame("  RX", frame)
    print(f"[local] parser crc_errors={parser.crc_errors} len_errors={parser.len_errors}")

    expected = [FrameType.HEARTBEAT, FrameType.CMD_VEL, FrameType.STOP]
    actual = [frame.frame_type for frame in frames]
    if actual != expected or parser.crc_errors != 1:
        print(f"[local] failed: expected {expected}, got {actual}")
        return 1
    print("[local] protocol self-test passed")
    return 0


def serial_probe(port: str, baud: int, duration: float) -> int:
    serial = import_serial()
    parser = FrameParser()
    seq = 0

    with serial.Serial(port=port, baudrate=baud, timeout=0.05) as ser:
        print(f"[serial] opened {port} at {baud} 8N1")
        for frame_type, payload in (
            (FrameType.SET_MODE, pack_set_mode(Mode.TEST)),
            (FrameType.HEARTBEAT, pack_heartbeat(0)),
            (FrameType.CMD_VEL, pack_cmd_vel(0, 0, 0)),
        ):
            raw = encode_frame(frame_type, seq, payload)
            ser.write(raw)
            print(f"  TX {frame_type.name} seq={seq} bytes={raw.hex(' ')}")
            seq = (seq + 1) & 0xFF

        deadline = time.monotonic() + duration
        saw_ack = False
        saw_status = False
        while time.monotonic() < deadline:
            data = ser.read(ser.in_waiting or 1)
            if not data:
                continue
            for frame in parser.feed(data):
                print_frame("  RX", frame)
                if frame.frame_type == FrameType.ACK and unpack_ack(frame.payload).result in (AckResult.OK, AckResult.CLAMPED):
                    saw_ack = True
                elif frame.frame_type == FrameType.STATUS:
                    saw_status = True

        stop_raw = encode_frame(FrameType.STOP, seq, pack_stop(StopReason.DEBUG_STOP))
        ser.write(stop_raw)
        print(f"  TX STOP seq={seq}")

    if not saw_ack:
        print("[serial] no ACK received")
        return 2
    if not saw_status:
        print("[serial] no STATUS received")
        return 3
    print(f"[serial] probe passed crc_errors={parser.crc_errors} len_errors={parser.len_errors}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial device, for example /dev/ttyUSB0 or simulator PTY")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=3.0, help="Serial receive window in seconds")
    args = parser.parse_args()

    if args.port:
        return serial_probe(args.port, args.baud, args.duration)
    return local_self_test()


if __name__ == "__main__":
    raise SystemExit(main())
