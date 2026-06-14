#!/usr/bin/env python3
"""Hardware tuning harness for the gimbal closed-loop controller.

Drives GimbalController directly (no ROS) so control gains can be swept from the
CLI without rebuilding. For each commanded target it steps the loop at --loop-hz
for --settle seconds and reports the steady-state error (mean over the final
--window seconds) plus peak overshoot. Use it to compare P-only vs PI tuning and
to pick proportional_gain / integral_gain / angle_deadband_deg.

Hardware setup mirrors gimbal_controller_node.py with the homed zero_deg values.
Safety: targets are clamped to axis ranges; on fault / Ctrl-C / exit the motors
ramp to neutral and disable. Run on the RDK with the gimbal free to move:

  python3 gimbal_tune.py --axis tilt --targets -20,0,20 --kp 0.005
  python3 gimbal_tune.py --axis tilt --targets -20,0,20 --kp 0.008 --ki 0.004
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "gimbal_laser"
sys.path.insert(0, str(_PKG))

from gimbal_laser.as5600 import AS5600AngleSensor, open_smbus  # noqa: E402
from gimbal_laser.gimbal_controller import (  # noqa: E402
    AxisConfig,
    AxisIO,
    ControlConfig,
    GimbalController,
    GimbalState,
)
from gimbal_laser.rdk_x5_gpio import gpio_line_from_pin  # noqa: E402
from gimbal_laser.rdk_x5_pwm import PhasePwmMotor, pwm_channel_from_pin  # noqa: E402

# Homed hardware config (FOC + zero_deg from 2026-06-12 calibration).
AXES = {
    "pan": dict(pwm_pins=[29, 31, 37], enable_pin=38, i2c_bus=5, addr=0x36,
                zero_deg=47.99, min_deg=-60.0, max_deg=60.0,
                pole_pairs=8, phase_offset_deg=89.92),
    "tilt": dict(pwm_pins=[18, 28, 27], enable_pin=40, i2c_bus=1, addr=0x36,
                 zero_deg=-108.28, min_deg=-30.0, max_deg=45.0,
                 pole_pairs=7, phase_offset_deg=100.04),
}


def build_axis(name, pwm_freq):
    c = AXES[name]
    sensor = AS5600AngleSensor(bus=open_smbus(c["i2c_bus"]), address=c["addr"],
                               zero_deg=c["zero_deg"], invert=False)
    channels = [pwm_channel_from_pin(p, pwm_freq) for p in c["pwm_pins"]]
    motor = PhasePwmMotor(channels=channels, enable_line=gpio_line_from_pin(c["enable_pin"]))
    motor.setup()
    cfg = AxisConfig(name=name, min_deg=c["min_deg"], max_deg=c["max_deg"],
                     invert=False, pole_pairs=c["pole_pairs"],
                     phase_offset_deg=c["phase_offset_deg"])
    return AxisIO(config=cfg, sensor=sensor, motor=motor)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--axis", choices=["pan", "tilt"], required=True)
    p.add_argument("--targets", default="0", help="comma list of target deg, e.g. -20,0,20")
    p.add_argument("--kp", type=float, default=0.005)
    p.add_argument("--ki", type=float, default=0.0, help="integral gain (needs PI controller)")
    p.add_argument("--deadband", type=float, default=1.0)
    p.add_argument("--max-duty", type=float, default=0.08)
    p.add_argument("--startup-duty", type=float, default=0.022)
    p.add_argument("--slew", type=float, default=32.0, help="target slew rate deg/s")
    p.add_argument("--ilimit", type=float, default=0.0, help="integral duty-contrib clamp (0=max_duty)")
    p.add_argument("--loop-hz", type=float, default=100.0)
    p.add_argument("--settle", type=float, default=4.0, help="seconds to hold each target")
    p.add_argument("--window", type=float, default=1.0, help="final seconds averaged for SS error")
    p.add_argument("--pwm-freq", type=int, default=20000)
    return p.parse_args()


def make_config(opt):
    kwargs = dict(max_duty=opt.max_duty, startup_duty=opt.startup_duty,
                  angle_deadband_deg=opt.deadband, command_timeout_sec=1e9,
                  proportional_gain=opt.kp, target_slew_rate_deg_s=opt.slew,
                  duty_slew_rate_per_sec=1.25)
    # integral_gain is only present once the PI controller is implemented
    try:
        ControlConfig(integral_gain=0.0)
        kwargs["integral_gain"] = opt.ki
        kwargs["integral_limit"] = opt.ilimit
    except TypeError:
        if opt.ki:
            print("[tune] WARNING: controller has no integral_gain; --ki ignored.")
    return ControlConfig(**kwargs)


def main():
    opt = parse_args()
    # The other axis is built too so its motor is parked (disabled) safely.
    other = "tilt" if opt.axis == "pan" else "pan"
    axis_io = build_axis(opt.axis, opt.pwm_freq)
    other_io = build_axis(other, opt.pwm_freq)
    pan_io, tilt_io = (axis_io, other_io) if opt.axis == "pan" else (other_io, axis_io)

    ctrl = GimbalController(pan=pan_io, tilt=tilt_io, config=make_config(opt))
    period = 1.0 / opt.loop_hz
    targets = [float(x) for x in opt.targets.split(",") if x.strip() != ""]

    def now():
        return time.monotonic()

    def cur():
        s = ctrl.status()
        return s.pan_deg if opt.axis == "pan" else s.tilt_deg

    print(f"[tune] axis={opt.axis} kp={opt.kp} ki={opt.ki} deadband={opt.deadband} "
          f"max_duty={opt.max_duty}")
    print(f"[tune] start angle={cur():.2f}")
    try:
        ctrl.set_enabled(True, now())
        for tgt in targets:
            # hold the OTHER axis at its current angle so it doesn't drift
            if opt.axis == "pan":
                ctrl.set_target(tgt, tilt_io.sensor.read_degrees(), now())
            else:
                ctrl.set_target(pan_io.sensor.read_degrees(), tgt, now())
            start = cur()
            t0 = now()
            samples = []
            lo = hi = start
            while now() - t0 < opt.settle:
                ctrl.last_command_sec = now()  # keep command fresh (no timeout)
                st = ctrl.step(now())
                if st.state == GimbalState.FAULT:
                    print(f"[tune] FAULT: {st.fault}")
                    raise KeyboardInterrupt
                a = cur()
                lo = min(lo, a)
                hi = max(hi, a)
                if now() - t0 >= opt.settle - opt.window:
                    samples.append(a)
                time.sleep(period)
            final = sum(samples) / len(samples) if samples else cur()
            ss_err = final - tgt
            # overshoot = how far it traveled past the target, in the move direction
            overshoot = (hi - tgt) if tgt >= start else (tgt - lo)
            print(f"  target={tgt:+7.2f}  final={final:+7.2f}  ss_err={ss_err:+6.2f}  "
                  f"overshoot={overshoot:+6.2f}  (range {lo:+.1f}..{hi:+.1f})")
    except KeyboardInterrupt:
        print("[tune] interrupted")
    finally:
        ctrl.stop("operator_stop")
        ctrl.pan.motor.disable()
        ctrl.tilt.motor.disable()
        print(f"[tune] end angle={cur():.2f}  (motors disabled)")


if __name__ == "__main__":
    main()
