#!/usr/bin/env python3
"""Live per-wheel velocity-PID tuning for the STM32 chassis (USB CDC).

Pushes gains over the SET_PID frame (no reflash), drives one body axis, logs
ODOM, and prints per-wheel velocity tracking (target vs measured, steady-state
error, overshoot). Tune suspended first.

Example:
  python3 pid_tune.py --kp 8 --ki 20 --vx 200 --duration 3
  python3 pid_tune.py --ff 33.3 --vx 200      # ff-only == open-loop baseline
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.protocol.rdk_stm32_uart import (  # noqa: E402
    Frame,
    FrameParser,
    FrameType,
    Mode,
    StopReason,
    encode_frame,
    pack_cmd_vel,
    pack_heartbeat,
    pack_set_mode,
    pack_set_pid,
    pack_stop,
    unpack_odom,
)

DEFAULT_PORT = "/dev/serial/by-id/usb-Soc_China_Robotics_STM32F411_Chassis_VCP_335833553034-if00"

# Chassis geometry (must match firmware app_chassis_init / MecanumDrive_Mix).
R = 0.05
L = 0.12
W = 0.10
TICKS_PER_REV = 2613.0
TWO_PI = 6.283185307179586
# Forward wheel rotation -> positive count (matches firmware APP_WHEEL_ENC_SIGN
# and RDK encoder_sign). Order LF, RF, LR, RR.
ENC_SIGN = (1, -1, 1, -1)
WHEELS = ("LF", "RF", "LR", "RR")


def target_radps(vx_mps: float, vy_mps: float, wz_radps: float):
    """Per-wheel setpoint (rad/s), identical to firmware MecanumDrive_Mix."""
    rot = -(L + W) * wz_radps
    return (
        (vx_mps + vy_mps - rot) / R,  # LF
        (vx_mps - vy_mps + rot) / R,  # RF
        (vx_mps - vy_mps - rot) / R,  # LR
        (vx_mps + vy_mps + rot) / R,  # RR
    )


def wrapped_delta(cur: int, prev: int) -> int:
    d = (int(cur) - int(prev)) & 0xFFFF
    if d >= 0x8000:
        d -= 0x10000
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--kp", type=float, default=0.0)
    ap.add_argument("--ki", type=float, default=0.0)
    ap.add_argument("--kd", type=float, default=0.0)
    ap.add_argument("--ff", type=float, default=999.0 / 30.0, help="default 33.3 == open-loop")
    ap.add_argument("--wheel", type=int, default=0xFF, help="0..3 or 255=all")
    ap.add_argument("--vx", type=int, default=0, help="mm/s")
    ap.add_argument("--vy", type=int, default=0, help="mm/s")
    ap.add_argument("--wz", type=int, default=0, help="mrad/s")
    ap.add_argument("--duration", type=float, default=3.0)
    ap.add_argument("--cmd-hz", type=float, default=20.0)
    ap.add_argument("--heartbeat-hz", type=float, default=10.0)
    args = ap.parse_args()

    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise SystemExit("pyserial required: python3 -m pip install pyserial") from exc

    ser = serial.Serial(args.port, args.baud, timeout=0.05)
    parser = FrameParser()
    seq = 0

    def send(ftype, payload):
        nonlocal seq
        ser.write(encode_frame(ftype, seq, payload))
        seq = (seq + 1) & 0xFF

    # Configure: MANUAL mode + push gains.
    send(FrameType.SET_MODE, pack_set_mode(Mode.MANUAL))
    send(FrameType.SET_PID, pack_set_pid(args.wheel, args.kp, args.ki, args.kd, args.ff))
    print(f"[pid] kp={args.kp} ki={args.ki} kd={args.kd} ff={args.ff} wheel={args.wheel}")

    tgt = target_radps(args.vx / 1000.0, args.vy / 1000.0, args.wz / 1000.0)
    print(f"[cmd] vx={args.vx} vy={args.vy} wz={args.wz}  target rad/s "
          + " ".join(f"{WHEELS[i]}={tgt[i]:+.2f}" for i in range(4)))

    samples = []  # (t, (lf,rf,lr,rr) raw)
    t0 = time.time()
    last_cmd = 0.0
    last_hb = 0.0
    cmd_dt = 1.0 / args.cmd_hz
    hb_dt = 1.0 / args.heartbeat_hz

    while time.time() - t0 < args.duration:
        now = time.time()
        if now - last_hb >= hb_dt:
            send(FrameType.HEARTBEAT, pack_heartbeat(int((now - t0) * 1000)))
            last_hb = now
        if now - last_cmd >= cmd_dt:
            send(FrameType.CMD_VEL, pack_cmd_vel(args.vx, args.vy, args.wz))
            last_cmd = now
        data = ser.read(256)
        if data:
            for fr in parser.feed(data):
                if fr.frame_type == FrameType.ODOM:
                    samples.append((time.time() - t0, unpack_odom(fr.payload)))

    # Stop.
    send(FrameType.STOP, pack_stop(StopReason.DEBUG_STOP))
    send(FrameType.SET_MODE, pack_set_mode(Mode.IDLE))
    ser.flush()
    time.sleep(0.1)
    ser.close()

    # Per-wheel velocity from consecutive ODOM samples.
    if len(samples) < 3:
        print(f"[!] only {len(samples)} ODOM samples; link issue?")
        return 1

    rad_per_tick = TWO_PI / TICKS_PER_REV
    series = {i: [] for i in range(4)}  # (t, radps)
    for k in range(1, len(samples)):
        t, cur = samples[k]
        tp, prev = samples[k - 1]
        dt = t - tp
        if dt <= 0:
            continue
        for i in range(4):
            d = wrapped_delta(cur[i], prev[i])
            v = d * ENC_SIGN[i] * rad_per_tick / dt
            series[i].append((t, v))

    print(f"\n[result] {len(samples)} ODOM samples over {args.duration:.1f}s "
          f"(~{len(samples)/args.duration:.0f} Hz)")
    print(f"{'wheel':5} {'target':>8} {'steady':>8} {'err%':>7} {'peak':>8} {'note'}")
    for i in range(4):
        vs = [v for _, v in series[i]]
        if not vs:
            continue
        n = max(1, len(vs) // 3)
        steady = sum(vs[-n:]) / n          # mean of last third
        peak = max(vs, key=abs)            # signed peak
        t_i = tgt[i]
        errpct = (abs(steady - t_i) / abs(t_i) * 100.0) if abs(t_i) > 1e-6 else 0.0
        overshoot = ""
        if abs(t_i) > 1e-6 and abs(peak) > abs(t_i) * 1.05:
            overshoot = f"overshoot {abs(peak)/abs(t_i)*100-100:.0f}%"
        print(f"{WHEELS[i]:5} {t_i:>+8.2f} {steady:>+8.2f} {errpct:>6.0f}% {peak:>+8.2f}  {overshoot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
