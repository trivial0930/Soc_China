#!/usr/bin/env python3
"""实时编码器监视器 (在 RDK X5 上运行)。

读 STM32 经 /dev/ttyS1 回传的 ODOM 帧 (4 路正交编码器 16-bit 计数, 顺序 LF,RF,LR,RR)，
打印相对初值的变化。手转某个轮子, 对应列的数字明显变化 = 该轮 A/B 接对、映射正确。
正转/反转对应 +/-。无需电机上电, 安全。

用法:
  python3 encoder_monitor.py                 # 监视 30s
  python3 encoder_monitor.py --duration 60
"""

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.protocol.rdk_stm32_uart import FrameParser, FrameType, unpack_odom  # noqa: E402


def import_serial():
    try:
        import serial  # type: ignore
        return serial
    except ImportError as exc:
        raise SystemExit("需要 pyserial: python3 -m pip install pyserial") from exc


def wrapped_delta(cur, base):
    """16-bit 有符号计数的环绕安全差值。"""
    d = (cur - base) & 0xFFFF
    if d >= 0x8000:
        d -= 0x10000
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyS1")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--duration", type=float, default=30.0)
    args = ap.parse_args()

    serial = import_serial()
    parser = FrameParser()
    base = None
    last_print = None
    n_odom = 0

    with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
        print(f"[encoder] 监视 {args.port} @ {args.baud}, {args.duration:.0f}s")
        print("说明: 手转某轮 -> 对应列变化(正转/反转=+/-)。LF RF LR RR")
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            data = ser.read(ser.in_waiting or 1)
            if not data:
                continue
            for frame in parser.feed(data):
                if frame.frame_type != FrameType.ODOM:
                    continue
                n_odom += 1
                vals = unpack_odom(frame.payload)  # (lf, rf, lr, rr)
                if base is None:
                    base = list(vals)
                    print(f"[基准] LF={vals[0]} RF={vals[1]} LR={vals[2]} RR={vals[3]}")
                    continue
                rel = [wrapped_delta(v, b) for v, b in zip(vals, base)]
                if rel != last_print:
                    t = time.strftime("%H:%M:%S")
                    print(f"{t}  LF={rel[0]:+7d}  RF={rel[1]:+7d}  LR={rel[2]:+7d}  RR={rel[3]:+7d}")
                    last_print = rel

    print(f"[encoder] 结束, 收到 {n_odom} 个 ODOM 帧。", end="")
    if n_odom == 0:
        print(" ⚠️ 没收到 ODOM —— 检查固件是否在发 ODOM / 串口是否对。")
    else:
        print(" 各列有变化的轮子说明编码器接对。")
    return 0 if n_odom else 1


if __name__ == "__main__":
    raise SystemExit(main())
