"""RDK X5 <-> STM32F411 UART protocol reference implementation.

Frame layout:
    SOF(AA 55) VER TYPE SEQ LEN PAYLOAD CRC16_LOW CRC16_HIGH

CRC range:
    VER + TYPE + SEQ + LEN + PAYLOAD
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, List, Tuple, Union


SOF = b"\xAA\x55"
PROTOCOL_VERSION = 0x01
MAX_PAYLOAD_LEN = 64
FRAME_OVERHEAD = 8

MAX_VX_MM_S = 500
MAX_VY_MM_S = 500
MAX_WZ_MRAD_S = 1500


class FrameType(IntEnum):
    HEARTBEAT = 0x01
    CMD_VEL = 0x10
    STOP = 0x11
    SET_MODE = 0x12
    STATUS = 0x81
    ODOM = 0x82
    FAULT = 0x83
    ACK = 0x84


class Mode(IntEnum):
    IDLE = 0x00
    MANUAL = 0x01
    AUTO = 0x02
    TEST = 0x03


class StopReason(IntEnum):
    NORMAL = 0x00
    USER_ESTOP = 0x01
    TASK_DONE = 0x02
    UPPER_FAULT = 0x03
    DEBUG_STOP = 0x04


class CommState(IntEnum):
    OK = 0x00
    CMD_TIMEOUT = 0x01
    HEARTBEAT_TIMEOUT = 0x02
    CRC_ERROR_LIMIT = 0x03


class AckResult(IntEnum):
    OK = 0x00
    CRC_ERROR = 0x01
    LEN_ERROR = 0x02
    UNSUPPORTED_TYPE = 0x03
    MODE_NOT_ALLOWED = 0x04
    ESTOP_ACTIVE = 0x05
    CLAMPED = 0x06


class FaultCode(IntEnum):
    NO_FAULT = 0x0000
    ESTOP_TRIGGERED = 0x0001
    HEARTBEAT_TIMEOUT = 0x0002
    CMD_TIMEOUT = 0x0003
    CRC_ERROR_LIMIT = 0x0004
    MOTOR_DRIVER_FAULT = 0x0005
    BATTERY_LOW = 0x0006


@dataclass(frozen=True)
class Frame:
    frame_type: Union[FrameType, int]
    seq: int
    payload: bytes = b""
    version: int = PROTOCOL_VERSION


@dataclass(frozen=True)
class Status:
    mode: Mode
    estop: bool
    fault_code: int
    battery_mv: int
    last_cmd_seq: int
    comm_state: CommState


@dataclass(frozen=True)
class Ack:
    ack_type: Union[FrameType, int]
    ack_seq: int
    result: AckResult


def crc16_ccitt_false(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial & 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _u8(value: int, name: str) -> int:
    if not 0 <= int(value) <= 0xFF:
        raise ValueError(f"{name} must be in 0..255, got {value}")
    return int(value)


def _u16(value: int, name: str) -> int:
    if not 0 <= int(value) <= 0xFFFF:
        raise ValueError(f"{name} must be in 0..65535, got {value}")
    return int(value)


def _u32(value: int, name: str) -> int:
    if not 0 <= int(value) <= 0xFFFFFFFF:
        raise ValueError(f"{name} must be in 0..4294967295, got {value}")
    return int(value)


def _i16(value: int, name: str) -> int:
    if not -32768 <= int(value) <= 32767:
        raise ValueError(f"{name} must fit int16, got {value}")
    return int(value)


def _require_len(payload: bytes, expected: int, name: str) -> None:
    if len(payload) != expected:
        raise ValueError(f"{name} payload must be {expected} bytes, got {len(payload)}")


def encode_frame(
    frame_type: Union[FrameType, int],
    seq: int,
    payload: bytes = b"",
    version: int = PROTOCOL_VERSION,
) -> bytes:
    if len(payload) > MAX_PAYLOAD_LEN:
        raise ValueError(f"payload length must be <= {MAX_PAYLOAD_LEN}, got {len(payload)}")

    header_and_payload = bytes(
        [
            _u8(version, "version"),
            _u8(int(frame_type), "frame_type"),
            _u8(seq, "seq"),
            len(payload),
        ]
    ) + bytes(payload)
    crc = crc16_ccitt_false(header_and_payload)
    return SOF + header_and_payload + struct.pack("<H", crc)


def decode_frame(raw: bytes) -> Frame:
    if len(raw) < FRAME_OVERHEAD:
        raise ValueError(f"frame too short: {len(raw)} bytes")
    if raw[:2] != SOF:
        raise ValueError("frame missing SOF 0xAA55")

    version, frame_type_raw, seq, length = raw[2], raw[3], raw[4], raw[5]
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version 0x{version:02X}")
    if length > MAX_PAYLOAD_LEN:
        raise ValueError(f"payload length exceeds {MAX_PAYLOAD_LEN}: {length}")
    expected_len = FRAME_OVERHEAD + length
    if len(raw) != expected_len:
        raise ValueError(f"frame length mismatch: expected {expected_len}, got {len(raw)}")

    crc_expected = struct.unpack("<H", raw[-2:])[0]
    crc_actual = crc16_ccitt_false(raw[2:-2])
    if crc_actual != crc_expected:
        raise ValueError(f"CRC mismatch: expected 0x{crc_expected:04X}, got 0x{crc_actual:04X}")

    try:
        frame_type: Union[FrameType, int] = FrameType(frame_type_raw)
    except ValueError:
        frame_type = frame_type_raw
    return Frame(frame_type=frame_type, seq=seq, payload=raw[6:-2], version=version)


class FrameParser:
    """Incremental parser that can recover after noise, partial frames, and CRC errors."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.crc_errors = 0
        self.len_errors = 0
        self.version_errors = 0

    def feed(self, data: bytes) -> List[Frame]:
        self._buffer.extend(data)
        frames: List[Frame] = []

        while True:
            sof_index = self._buffer.find(SOF)
            if sof_index < 0:
                self._keep_possible_sof_prefix()
                break
            if sof_index > 0:
                del self._buffer[:sof_index]
            if len(self._buffer) < 6:
                break

            length = self._buffer[5]
            if length > MAX_PAYLOAD_LEN:
                self.len_errors += 1
                del self._buffer[0]
                continue

            total_len = FRAME_OVERHEAD + length
            if len(self._buffer) < total_len:
                break

            candidate = bytes(self._buffer[:total_len])
            del self._buffer[:total_len]
            try:
                frames.append(decode_frame(candidate))
            except ValueError as exc:
                message = str(exc)
                if "CRC mismatch" in message:
                    self.crc_errors += 1
                elif "unsupported protocol version" in message:
                    self.version_errors += 1
                else:
                    self.len_errors += 1
        return frames

    def _keep_possible_sof_prefix(self) -> None:
        if self._buffer[-1:] == SOF[:1]:
            self._buffer[:] = SOF[:1]
        else:
            self._buffer.clear()


def pack_heartbeat(uptime_ms: int) -> bytes:
    return struct.pack("<I", _u32(uptime_ms, "uptime_ms"))


def unpack_heartbeat(payload: bytes) -> int:
    _require_len(payload, 4, "HEARTBEAT")
    return struct.unpack("<I", payload)[0]


def pack_cmd_vel(vx_mm_s: int, vy_mm_s: int, wz_mrad_s: int) -> bytes:
    return struct.pack(
        "<hhh",
        _i16(vx_mm_s, "vx_mm_s"),
        _i16(vy_mm_s, "vy_mm_s"),
        _i16(wz_mrad_s, "wz_mrad_s"),
    )


def unpack_cmd_vel(payload: bytes) -> Tuple[int, int, int]:
    _require_len(payload, 6, "CMD_VEL")
    return struct.unpack("<hhh", payload)


def clamp_cmd_vel(vx_mm_s: int, vy_mm_s: int, wz_mrad_s: int) -> Tuple[int, int, int, bool]:
    clipped_vx = max(-MAX_VX_MM_S, min(MAX_VX_MM_S, int(vx_mm_s)))
    clipped_vy = max(-MAX_VY_MM_S, min(MAX_VY_MM_S, int(vy_mm_s)))
    clipped_wz = max(-MAX_WZ_MRAD_S, min(MAX_WZ_MRAD_S, int(wz_mrad_s)))
    clamped = (clipped_vx, clipped_vy, clipped_wz) != (int(vx_mm_s), int(vy_mm_s), int(wz_mrad_s))
    return clipped_vx, clipped_vy, clipped_wz, clamped


def pack_stop(reason: Union[StopReason, int]) -> bytes:
    return struct.pack("<B", _u8(int(reason), "reason"))


def unpack_stop(payload: bytes) -> StopReason:
    _require_len(payload, 1, "STOP")
    return StopReason(payload[0])


def pack_set_mode(mode: Union[Mode, int]) -> bytes:
    return struct.pack("<B", _u8(int(mode), "mode"))


def unpack_set_mode(payload: bytes) -> Mode:
    _require_len(payload, 1, "SET_MODE")
    return Mode(payload[0])


def pack_status(status: Status) -> bytes:
    return struct.pack(
        "<BBHHBB",
        _u8(int(status.mode), "mode"),
        1 if status.estop else 0,
        _u16(status.fault_code, "fault_code"),
        _u16(status.battery_mv, "battery_mv"),
        _u8(status.last_cmd_seq, "last_cmd_seq"),
        _u8(int(status.comm_state), "comm_state"),
    )


def unpack_status(payload: bytes) -> Status:
    _require_len(payload, 8, "STATUS")
    mode, estop, fault_code, battery_mv, last_cmd_seq, comm_state = struct.unpack("<BBHHBB", payload)
    return Status(
        mode=Mode(mode),
        estop=bool(estop),
        fault_code=fault_code,
        battery_mv=battery_mv,
        last_cmd_seq=last_cmd_seq,
        comm_state=CommState(comm_state),
    )


def pack_odom(delta_lf: int, delta_rf: int, delta_lr: int, delta_rr: int) -> bytes:
    return struct.pack(
        "<hhhh",
        _i16(delta_lf, "delta_lf"),
        _i16(delta_rf, "delta_rf"),
        _i16(delta_lr, "delta_lr"),
        _i16(delta_rr, "delta_rr"),
    )


def unpack_odom(payload: bytes) -> Tuple[int, int, int, int]:
    _require_len(payload, 8, "ODOM")
    return struct.unpack("<hhhh", payload)


def pack_fault(fault_code: int, detail: int) -> bytes:
    return struct.pack("<HH", _u16(fault_code, "fault_code"), _u16(detail, "detail"))


def unpack_fault(payload: bytes) -> Tuple[int, int]:
    _require_len(payload, 4, "FAULT")
    return struct.unpack("<HH", payload)


def pack_ack(ack: Ack) -> bytes:
    return struct.pack(
        "<BBB",
        _u8(int(ack.ack_type), "ack_type"),
        _u8(ack.ack_seq, "ack_seq"),
        _u8(int(ack.result), "result"),
    )


def unpack_ack(payload: bytes) -> Ack:
    _require_len(payload, 3, "ACK")
    ack_type_raw, ack_seq, result = struct.unpack("<BBB", payload)
    try:
        ack_type: Union[FrameType, int] = FrameType(ack_type_raw)
    except ValueError:
        ack_type = ack_type_raw
    return Ack(ack_type=ack_type, ack_seq=ack_seq, result=AckResult(result))


def next_seq(seq: int) -> int:
    return (int(seq) + 1) & 0xFF


def frame_summary(frame: Frame) -> str:
    frame_type = frame.frame_type.name if isinstance(frame.frame_type, FrameType) else f"0x{frame.frame_type:02X}"
    payload = " ".join(f"{byte:02X}" for byte in frame.payload)
    return f"type={frame_type} seq={frame.seq} len={len(frame.payload)} payload=[{payload}]"


def iter_encoded_frames(frames: Iterable[Frame]) -> Iterable[bytes]:
    for frame in frames:
        yield encode_frame(frame.frame_type, frame.seq, frame.payload, frame.version)
