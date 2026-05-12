#!/usr/bin/env python3
"""Send periodic HEARTBEAT/CMD_VEL frames and log STM32 responses."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, TextIO


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
    clamp_cmd_vel,
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


MODE_BY_NAME = {
    "idle": Mode.IDLE,
    "manual": Mode.MANUAL,
    "auto": Mode.AUTO,
    "test": Mode.TEST,
}


def import_serial():
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit("pyserial is required. Install with: python3 -m pip install pyserial") from exc
    return serial


def make_log_dir(root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = root / f"{stamp}_uart_test"
    path.mkdir(parents=True, exist_ok=False)
    return path


def payload_summary(frame: Frame) -> Dict[str, object]:
    summary: Dict[str, object] = {
        "type": frame.frame_type.name if isinstance(frame.frame_type, FrameType) else f"0x{frame.frame_type:02X}",
        "seq": frame.seq,
        "len": len(frame.payload),
    }
    try:
        if frame.frame_type == FrameType.ACK:
            ack = unpack_ack(frame.payload)
            summary.update(
                {
                    "ack_type": ack.ack_type.name if isinstance(ack.ack_type, FrameType) else f"0x{ack.ack_type:02X}",
                    "ack_seq": ack.ack_seq,
                    "result": ack.result.name,
                }
            )
        elif frame.frame_type == FrameType.STATUS:
            status = unpack_status(frame.payload)
            summary.update(
                {
                    "mode": status.mode.name,
                    "estop": status.estop,
                    "fault_code": status.fault_code,
                    "battery_mv": status.battery_mv,
                    "last_cmd_seq": status.last_cmd_seq,
                    "comm_state": status.comm_state.name,
                }
            )
        elif frame.frame_type == FrameType.ODOM:
            summary["delta_ticks"] = unpack_odom(frame.payload)
        elif frame.frame_type == FrameType.FAULT:
            summary["fault_code"], summary["detail"] = unpack_fault(frame.payload)
    except ValueError as exc:
        summary["decode_error"] = str(exc)
    return summary


def log_event(log_file: TextIO, direction: str, raw: bytes, frame: Frame | None = None, note: str = "") -> None:
    event: Dict[str, object] = {
        "ts": time.time(),
        "direction": direction,
        "raw_hex": raw.hex(" "),
    }
    if frame is not None:
        event.update(payload_summary(frame))
    if note:
        event["note"] = note
    log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
    log_file.flush()


def send_frame(ser, log_file: TextIO, frame_type: FrameType, seq: int, payload: bytes, corrupt: bool = False) -> None:
    raw = bytearray(encode_frame(frame_type, seq, payload))
    note = ""
    if corrupt:
        raw[-1] ^= 0xFF
        note = "crc intentionally corrupted"
    ser.write(bytes(raw))
    log_event(log_file, "tx", bytes(raw), Frame(frame_type, seq, payload), note)


def update_counters(frame: Frame, counters: Dict[str, int]) -> None:
    if frame.frame_type == FrameType.ACK:
        counters["ack"] += 1
        ack = unpack_ack(frame.payload)
        if ack.result == AckResult.OK:
            counters["ack_ok"] += 1
        else:
            counters["ack_non_ok"] += 1
    elif frame.frame_type == FrameType.STATUS:
        counters["status"] += 1
    elif frame.frame_type == FrameType.ODOM:
        counters["odom"] += 1
    elif frame.frame_type == FrameType.FAULT:
        counters["fault"] += 1


def run_dry(args) -> int:
    vx, vy, wz, clamped = clamp_cmd_vel(args.vx, args.vy, args.wz)
    frames = [
        (FrameType.SET_MODE, pack_set_mode(MODE_BY_NAME[args.mode])),
        (FrameType.HEARTBEAT, pack_heartbeat(1234)),
        (FrameType.CMD_VEL, pack_cmd_vel(vx, vy, wz)),
        (FrameType.STOP, pack_stop(StopReason.DEBUG_STOP)),
    ]
    print(f"[dry-run] command vx={vx} vy={vy} wz={wz} clamped={clamped}")
    for seq, (frame_type, payload) in enumerate(frames):
        raw = encode_frame(frame_type, seq, payload)
        decoded = frame_summary(Frame(frame_type, seq, payload))
        print(f"[dry-run] {decoded} bytes={raw.hex(' ')}")
    return 0


def run_serial(args) -> int:
    serial = import_serial()
    log_dir = make_log_dir(Path(args.log_root))
    log_path = log_dir / "frames.jsonl"
    summary_path = log_dir / "summary.json"

    vx, vy, wz, clamped = clamp_cmd_vel(args.vx, args.vy, args.wz)
    if clamped:
        print(f"[uart] command clamped to vx={vx} vy={vy} wz={wz}")

    counters = {
        "tx": 0,
        "heartbeat_tx": 0,
        "cmd_vel_tx": 0,
        "ack": 0,
        "ack_ok": 0,
        "ack_non_ok": 0,
        "status": 0,
        "odom": 0,
        "fault": 0,
    }
    parser = FrameParser()
    seq = 0
    start = time.monotonic()
    next_hb = start
    next_cmd = start
    hb_interval = 1.0 / args.heartbeat_hz
    cmd_interval = 1.0 / args.cmd_hz

    with log_path.open("w", encoding="utf-8") as log_file, serial.Serial(
        port=args.port,
        baudrate=args.baud,
        timeout=0.02,
    ) as ser:
        print(f"[uart] opened {args.port} at {args.baud}, logging to {log_dir}")
        send_frame(ser, log_file, FrameType.SET_MODE, seq, pack_set_mode(MODE_BY_NAME[args.mode]))
        counters["tx"] += 1
        seq = (seq + 1) & 0xFF

        try:
            while time.monotonic() - start < args.duration:
                now = time.monotonic()
                uptime_ms = int((now - start) * 1000)

                if now >= next_hb:
                    corrupt = args.corrupt_crc_every > 0 and counters["tx"] > 0 and counters["tx"] % args.corrupt_crc_every == 0
                    send_frame(ser, log_file, FrameType.HEARTBEAT, seq, pack_heartbeat(uptime_ms), corrupt=corrupt)
                    counters["tx"] += 1
                    counters["heartbeat_tx"] += 1
                    seq = (seq + 1) & 0xFF
                    next_hb += hb_interval

                if now >= next_cmd:
                    send_frame(ser, log_file, FrameType.CMD_VEL, seq, pack_cmd_vel(vx, vy, wz))
                    counters["tx"] += 1
                    counters["cmd_vel_tx"] += 1
                    seq = (seq + 1) & 0xFF
                    next_cmd += cmd_interval

                data = ser.read(ser.in_waiting or 1)
                if data:
                    log_event(log_file, "rx_raw", data)
                    for frame in parser.feed(data):
                        update_counters(frame, counters)
                        log_event(log_file, "rx", data, frame)
                        print(f"[rx] {payload_summary(frame)}")
        except KeyboardInterrupt:
            print("[uart] interrupted, sending STOP")
        finally:
            if not args.no_stop:
                send_frame(ser, log_file, FrameType.STOP, seq, pack_stop(StopReason.DEBUG_STOP))
                counters["tx"] += 1

    summary = {
        "port": args.port,
        "baud": args.baud,
        "duration_s": args.duration,
        "cmd": {"vx_mm_s": vx, "vy_mm_s": vy, "wz_mrad_s": wz, "clamped": clamped},
        "counters": counters,
        "parser": {
            "crc_errors": parser.crc_errors,
            "len_errors": parser.len_errors,
            "version_errors": parser.version_errors,
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Serial device, for example /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--cmd-hz", type=float, default=20.0)
    parser.add_argument("--heartbeat-hz", type=float, default=10.0)
    parser.add_argument("--mode", choices=sorted(MODE_BY_NAME), default="manual")
    parser.add_argument("--vx", type=int, default=0, help="vx in mm/s")
    parser.add_argument("--vy", type=int, default=0, help="vy in mm/s")
    parser.add_argument("--wz", type=int, default=0, help="wz in mrad/s")
    parser.add_argument("--log-root", default=str(REPO_ROOT / "logs"))
    parser.add_argument("--corrupt-crc-every", type=int, default=0, help="Intentionally corrupt every Nth TX frame")
    parser.add_argument("--no-stop", action="store_true", help="Do not send STOP on exit")
    parser.add_argument("--dry-run", action="store_true", help="Print frames without opening a serial port")
    args = parser.parse_args()

    if args.dry_run:
        return run_dry(args)
    if not args.port:
        parser.error("--port is required unless --dry-run is used")
    if args.cmd_hz <= 0 or args.heartbeat_hz <= 0:
        parser.error("--cmd-hz and --heartbeat-hz must be positive")
    return run_serial(args)


if __name__ == "__main__":
    raise SystemExit(main())
