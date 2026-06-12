#!/usr/bin/env python3
"""Open-loop FOC alignment calibration for one gimbal axis.

The closed-loop controller (gimbal_controller.py) drives a sinusoidal 3-phase
vector and assumes the rotor electrical angle is ``current_deg*pole_pairs +
phase_offset_deg`` with a fixed (+) direction. If pole_pairs / phase_offset /
commutation-direction are wrong, closed-loop diverges (the gimbal only swings).

This tool finds them safely WITHOUT closed-loop: it applies a STATIC voltage
vector at a chosen electrical angle, the rotor magnetically aligns to it and
HOLDS (no runaway), and we read the AS5600 mechanical angle. Sweeping the applied
electrical angle and recording the mechanical angle gives:

  * commutation direction (+1 / -1): does mech increase as applied elec increases
  * pole_pairs: |delta_elec / delta_mech| over the sweep
  * phase_offset_deg: so that controller's electrical estimate matches reality

A safety window aborts and ramps the drive down if the encoder leaves
[mech_min, mech_max]. Keep amp low; run with the motor able to move freely.

Run on the RDK (source the gimbal ws first so gimbal_laser imports):
  python3 gimbal_foc_calibrate.py --axis pan
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(_PKG))

from gimbal_laser.as5600 import AS5600AngleSensor, open_smbus  # noqa: E402
from gimbal_laser.rdk_x5_gpio import gpio_line_from_pin  # noqa: E402
from gimbal_laser.rdk_x5_pwm import PhasePwmMotor, pwm_channel_from_pin  # noqa: E402

AXES = {
    "pan": {"pwm_pins": [29, 31, 37], "enable_pin": 38, "i2c_bus": 5, "addr": 0x36},
    "tilt": {"pwm_pins": [18, 28, 27], "enable_pin": 40, "i2c_bus": 1, "addr": 0x36},
}
_PHASES = (0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0)


def vector_duties(angle_deg: float, amp: float):
    a = math.radians(angle_deg)
    return tuple(min(max(0.5 + amp * math.sin(a + p), 0.0), 1.0) for p in _PHASES)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--axis", choices=["pan", "tilt"], default="pan")
    p.add_argument("--amp", type=float, default=0.10, help="vector modulation (holding strength)")
    p.add_argument("--step-deg", type=float, default=20.0, help="electrical-angle step")
    p.add_argument("--sweep-deg", type=float, default=360.0, help="total electrical sweep")
    p.add_argument("--settle-sec", type=float, default=0.6)
    p.add_argument("--pwm-freq", type=int, default=20000)
    p.add_argument("--mech-margin", type=float, default=55.0,
                   help="abort if mech moves more than this (deg) from the start")
    return p.parse_args()


def main():
    opt = parse_args()
    cfg = AXES[opt.axis]
    sensor = AS5600AngleSensor(bus=open_smbus(cfg["i2c_bus"]), address=cfg["addr"])
    channels = [pwm_channel_from_pin(pin, opt.pwm_freq) for pin in cfg["pwm_pins"]]
    motor = PhasePwmMotor(channels=channels, enable_line=gpio_line_from_pin(cfg["enable_pin"]))
    motor.setup()

    start_mech = sensor.read_degrees()
    print(f"[cal] axis={opt.axis} start_mech={start_mech:.2f} deg  amp={opt.amp}")
    samples = []  # (applied_elec_deg, mech_deg)

    def ramp_down():
        for k in range(10, -1, -1):
            motor.set_phase_duties(vector_duties(samples[-1][0] if samples else 0.0, opt.amp * k / 10.0))
            time.sleep(0.03)
        motor.stop()
        motor.disable()

    try:
        motor.enable()
        # initial alignment to electrical 0 (rotor snaps & holds)
        motor.set_phase_duties(vector_duties(0.0, opt.amp))
        time.sleep(max(opt.settle_sec, 1.0))

        applied = 0.0
        while applied <= opt.sweep_deg + 1e-6:
            motor.set_phase_duties(vector_duties(applied, opt.amp))
            time.sleep(opt.settle_sec)
            mech = sensor.read_degrees()
            samples.append((applied, mech))
            print(f"  applied_elec={applied:6.1f}  mech={mech:8.3f}")
            if abs(mech - start_mech) > opt.mech_margin:
                print(f"[cal] ABORT: mech moved > {opt.mech_margin} deg from start; ramping down.")
                ramp_down()
                break
            applied += opt.step_deg
        else:
            ramp_down()
    except KeyboardInterrupt:
        ramp_down()
    finally:
        motor.stop()
        motor.disable()

    if len(samples) < 3:
        print("[cal] not enough samples to fit.")
        return

    # Fit applied_elec = direction*pole_pairs*mech + C  (unwrap mech)
    elec = [s[0] for s in samples]
    mech = _unwrap([s[1] for s in samples])
    n = len(elec)
    mean_e = sum(elec) / n
    mean_m = sum(mech) / n
    cov = sum((mech[i] - mean_m) * (elec[i] - mean_e) for i in range(n))
    var = sum((mech[i] - mean_m) ** 2 for i in range(n))
    if abs(var) < 1e-6:
        print("[cal] rotor did not move enough; increase --amp.")
        return
    slope = cov / var                      # elec deg per mech deg = direction*pole_pairs
    intercept = mean_e - slope * mean_m    # C
    direction = 1 if slope > 0 else -1
    pole_pairs_est = abs(slope)

    print("\n=== 标定结果 ===")
    print(f"  斜率(电度/机度) = {slope:.3f}")
    print(f"  换相方向 commutation_direction = {direction}")
    print(f"  极对数估计 pole_pairs ≈ {pole_pairs_est:.2f}  (取最近整数: {round(pole_pairs_est)})")
    pp = round(pole_pairs_est)
    # controller: electrical = current_deg*pole_pairs + phase_offset, fixed (+) dir.
    # We need electrical(mech) == true applied. true = direction*pp*mech + C.
    # If direction==+1: phase_offset = C (mod 360).
    # If direction==-1: controller can't express it with + dir -> need commutation_direction param.
    phase_off = intercept % 360.0
    print(f"  phase_offset_deg ≈ {phase_off:.1f}  (电角度, 取模360)")
    if direction < 0:
        print("  注意: 换相方向为 -1, 控制器当前公式是 + 方向 -> 需要给控制器加 commutation_direction 参数(或用负 pole_pairs)。")


def _unwrap(vals):
    out = [vals[0]]
    for v in vals[1:]:
        prev = out[-1]
        d = v - prev
        while d > 180.0:
            d -= 360.0
        while d < -180.0:
            d += 360.0
        out.append(prev + d)
    return out


if __name__ == "__main__":
    main()
