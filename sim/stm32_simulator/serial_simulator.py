#!/usr/bin/env python3
"""Pseudo-terminal STM32 simulator for RDK UART development."""

from __future__ import annotations

import argparse
import os
import pty
import select
import sys
import time
import tty
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.protocol.rdk_stm32_uart import (  # noqa: E402
    Ack,
    AckResult,
    CommState,
    FaultCode,
    Frame,
    FrameParser,
    FrameType,
    Mode,
    Status,
    StopReason,
    clamp_cmd_vel,
    encode_frame,
    frame_summary,
    pack_ack,
    pack_fault,
    pack_odom,
    pack_status,
    unpack_cmd_vel,
    unpack_set_mode,
    unpack_stop,
)


class SimState:
    def __init__(self, battery_mv: int, estop_after: float) -> None:
        self.mode = Mode.IDLE
        self.estop = False
        self.fault_code = FaultCode.NO_FAULT
        self.battery_mv = battery_mv
        self.last_cmd_seq = 0
        self.comm_state = CommState.OK
        self.vx_mm_s = 0
        self.vy_mm_s = 0
        self.wz_mrad_s = 0
        self.last_cmd_time = time.monotonic()
        self.last_heartbeat_time = time.monotonic()
        self.start_time = time.monotonic()
        self.estop_after = estop_after

    def tick(self) -> None:
        now = time.monotonic()
        if self.estop_after > 0 and now - self.start_time >= self.estop_after:
            self.estop = True
        if self.estop:
            self.comm_state = CommState.OK
            self.fault_code = FaultCode.ESTOP_TRIGGERED
            self.vx_mm_s = 0
            self.vy_mm_s = 0
            self.wz_mrad_s = 0
            return
        if now - self.last_heartbeat_time > 2.0:
            self.comm_state = CommState.HEARTBEAT_TIMEOUT
            self.fault_code = FaultCode.HEARTBEAT_TIMEOUT
            self.vx_mm_s = 0
            self.vy_mm_s = 0
            self.wz_mrad_s = 0
        elif now - self.last_cmd_time > 0.5:
            self.comm_state = CommState.CMD_TIMEOUT
            self.fault_code = FaultCode.CMD_TIMEOUT
            self.vx_mm_s = 0
            self.vy_mm_s = 0
            self.wz_mrad_s = 0
        else:
            self.comm_state = CommState.OK
            self.fault_code = FaultCode.NO_FAULT

    def status(self) -> Status:
        return Status(
            mode=self.mode,
            estop=self.estop,
            fault_code=int(self.fault_code),
            battery_mv=self.battery_mv,
            last_cmd_seq=self.last_cmd_seq,
            comm_state=self.comm_state,
        )

    def odom_payload(self) -> bytes:
        delta = int(self.vx_mm_s / 20)
        return pack_odom(delta, delta, delta, delta)


def send_frame(master_fd: int, frame_type: FrameType, seq: int, payload: bytes, bad_crc: bool = False) -> bool:
    raw = bytearray(encode_frame(frame_type, seq, payload))
    if bad_crc:
        raw[-1] ^= 0xFF
    try:
        os.write(master_fd, bytes(raw))
    except BlockingIOError:
        return False
    return True


def ack_payload(frame: Frame, result: AckResult) -> bytes:
    return pack_ack(Ack(ack_type=frame.frame_type, ack_seq=frame.seq, result=result))


def handle_frame(master_fd: int, frame: Frame, state: SimState, seq_out: int) -> int:
    print(f"[sim rx] {frame_summary(frame)}", flush=True)
    result = AckResult.OK

    try:
        if frame.frame_type == FrameType.HEARTBEAT:
            state.last_heartbeat_time = time.monotonic()
        elif frame.frame_type == FrameType.CMD_VEL:
            vx, vy, wz = unpack_cmd_vel(frame.payload)
            vx, vy, wz, clamped = clamp_cmd_vel(vx, vy, wz)
            result = AckResult.CLAMPED if clamped else AckResult.OK
            if state.estop:
                result = AckResult.ESTOP_ACTIVE
            else:
                state.vx_mm_s = vx
                state.vy_mm_s = vy
                state.wz_mrad_s = wz
                state.last_cmd_seq = frame.seq
                state.last_cmd_time = time.monotonic()
        elif frame.frame_type == FrameType.SET_MODE:
            state.mode = unpack_set_mode(frame.payload)
        elif frame.frame_type == FrameType.STOP:
            _ = unpack_stop(frame.payload)
            state.vx_mm_s = 0
            state.vy_mm_s = 0
            state.wz_mrad_s = 0
            state.mode = Mode.IDLE
            state.last_cmd_seq = frame.seq
        else:
            result = AckResult.UNSUPPORTED_TYPE
    except ValueError:
        result = AckResult.LEN_ERROR

    if send_frame(master_fd, FrameType.ACK, seq_out, ack_payload(frame, result)):
        print(f"[sim tx] ACK {frame.frame_type} seq={frame.seq} result={result.name}", flush=True)
        return (seq_out + 1) & 0xFF
    return seq_out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--battery-mv", type=int, default=12000)
    parser.add_argument("--duration", type=float, default=0.0, help="0 means run forever")
    parser.add_argument("--status-hz", type=float, default=10.0)
    parser.add_argument("--odom-hz", type=float, default=10.0)
    parser.add_argument("--estop-after", type=float, default=0.0, help="Trigger simulated estop after N seconds")
    parser.add_argument("--bad-crc-every", type=int, default=0, help="Corrupt every Nth periodic outgoing frame")
    args = parser.parse_args()

    master_fd, slave_fd = pty.openpty()
    tty.setraw(master_fd)
    tty.setraw(slave_fd)
    os.set_blocking(master_fd, False)
    slave_name = os.ttyname(slave_fd)
    print(f"[sim] connect RDK script to: {slave_name}", flush=True)

    parser_state = FrameParser()
    state = SimState(args.battery_mv, args.estop_after)
    seq_out = 0
    periodic_count = 0
    next_status = time.monotonic()
    next_odom = time.monotonic()
    deadline = None if args.duration <= 0 else time.monotonic() + args.duration

    try:
        while deadline is None or time.monotonic() < deadline:
            state.tick()
            readable, _, _ = select.select([master_fd], [], [], 0.02)
            if readable:
                try:
                    data = os.read(master_fd, 4096)
                except BlockingIOError:
                    data = b""
                for frame in parser_state.feed(data):
                    seq_out = handle_frame(master_fd, frame, state, seq_out)

            now = time.monotonic()
            if now >= next_status:
                periodic_count += 1
                bad_crc = args.bad_crc_every > 0 and periodic_count % args.bad_crc_every == 0
                if send_frame(master_fd, FrameType.STATUS, seq_out, pack_status(state.status()), bad_crc=bad_crc):
                    print(f"[sim tx] STATUS seq={seq_out} comm={state.comm_state.name}", flush=True)
                    seq_out = (seq_out + 1) & 0xFF
                next_status += 1.0 / args.status_hz

            if now >= next_odom:
                periodic_count += 1
                bad_crc = args.bad_crc_every > 0 and periodic_count % args.bad_crc_every == 0
                if send_frame(master_fd, FrameType.ODOM, seq_out, state.odom_payload(), bad_crc=bad_crc):
                    seq_out = (seq_out + 1) & 0xFF
                next_odom += 1.0 / args.odom_hz
    except KeyboardInterrupt:
        print("[sim] stopped", flush=True)
    finally:
        os.close(master_fd)
        os.close(slave_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
