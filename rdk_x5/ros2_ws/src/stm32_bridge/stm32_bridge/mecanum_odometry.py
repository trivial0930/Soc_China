"""Pure mecanum odometry math (no ROS dependency, stdlib only).

Forward kinematics here is the exact inverse of the STM32 firmware's
`MecanumDrive_Mix` (stm32/firmware/.../mecanum_drive.c), so /odom is consistent
with how cmd_vel is mixed into wheel speeds:

    wLF = (vx - vy - rot) / r
    wRF = (vx + vy + rot) / r
    wLR = (vx + vy - rot) / r
    wRR = (vx - vy + rot) / r        rot = (L + W) * wz

Inverting:

    vx = r/4   * ( wLF + wRF + wLR + wRR)
    vy = r/4   * (-wLF + wRF + wLR - wRR)
    wz = r/(4*(L+W)) * (-wLF + wRF - wLR + wRR)

The STM32 ODOM frame carries each wheel's raw 16-bit quadrature counter
(order LF, RF, LR, RR). This module turns successive counter samples into a
body-frame increment and integrates a planar pose (x, y, theta).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

WHEELS = ("lf", "rf", "lr", "rr")


def wrapped_delta_u16(current: int, previous: int) -> int:
    """Signed delta between two unsigned-16-bit counters, wrap-safe.

    Handles the timer counter rolling over 0<->65535 in either direction,
    assuming the true delta is within +/-32767 between samples.
    """
    d = (int(current) - int(previous)) & 0xFFFF
    if d >= 0x8000:
        d -= 0x10000
    return d


def body_twist_from_wheel_rates(
    w_lf: float,
    w_rf: float,
    w_lr: float,
    w_rr: float,
    wheel_radius_m: float,
    half_length_m: float,
    half_width_m: float,
) -> Tuple[float, float, float]:
    """Forward kinematics: 4 wheel angular rates (rad/s) -> (vx, vy, wz).

    Exact inverse of the firmware mix. Units: rad/s in, (m/s, m/s, rad/s) out.
    The same relation holds for *increments* (rad in -> m, m, rad out).
    """
    r = wheel_radius_m
    lw = half_length_m + half_width_m
    vx = r / 4.0 * (w_lf + w_rf + w_lr + w_rr)
    # vy term negated to match the firmware mix's negated vy sign (2026-06-11),
    # so +vy = LEFT (REP-103) on both the command and odometry sides.
    vy = r / 4.0 * (w_lf - w_rf - w_lr + w_rr)
    # wz term negated to match the firmware mix's negated rot sign (2026-06-11);
    # this keeps +wz = CCW (REP-103) on both the command and odometry sides.
    wz = r / (4.0 * lw) * (w_lf - w_rf + w_lr - w_rr)
    return vx, vy, wz


@dataclass
class MecanumOdometryConfig:
    wheel_radius_m: float = 0.05
    half_length_m: float = 0.12
    half_width_m: float = 0.10
    # Encoder counts per *wheel* revolution = encoder_PPR * 4 (x4 mode) * gear_ratio.
    # Calibrated 2026-06-08 (hand-roll RF 6 turns -> 15679/6 = 2613, ~+/-2-3%).
    ticks_per_rev: float = 2613.0
    # Per-wheel sign so a forward wheel rotation yields a positive count.
    # Order LF, RF, LR, RR. Calibrate on hardware (RF/RR measured +1 on 2026-06-08).
    encoder_sign: Tuple[int, int, int, int] = (1, 1, 1, 1)


@dataclass
class OdometryState:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0


@dataclass
class MecanumOdometry:
    config: MecanumOdometryConfig = field(default_factory=MecanumOdometryConfig)
    state: OdometryState = field(default_factory=OdometryState)
    _last_ticks: List[int] = field(default_factory=list)
    _have_last: bool = False

    def reset(self) -> None:
        self.state = OdometryState()
        self._have_last = False
        self._last_ticks = []

    def resync(self) -> None:
        """Drop the tick baseline WITHOUT touching the accumulated pose.

        Use after the STM32 re-enumerates (e.g. a watchdog reset zeroed its
        encoder counters): the next update() re-latches the baseline instead of
        integrating a bogus wrap delta, so x/y/theta stay continuous.
        """
        self._have_last = False
        self._last_ticks = []

    def update(
        self,
        ticks_lf: int,
        ticks_rf: int,
        ticks_lr: int,
        ticks_rr: int,
        dt_s: float,
    ) -> OdometryState:
        """Integrate one ODOM sample of raw 16-bit wheel counters over dt_s.

        First call only latches the baseline (no motion). Returns current state.
        """
        ticks = [int(ticks_lf), int(ticks_rf), int(ticks_lr), int(ticks_rr)]
        if not self._have_last:
            self._last_ticks = ticks
            self._have_last = True
            return self.state

        signs = self.config.encoder_sign
        deltas = [
            signs[i] * wrapped_delta_u16(ticks[i], self._last_ticks[i])
            for i in range(4)
        ]
        self._last_ticks = ticks

        # tick delta -> wheel angular displacement (rad)
        rad_per_tick = 2.0 * math.pi / self.config.ticks_per_rev
        dth = [d * rad_per_tick for d in deltas]  # LF, RF, LR, RR

        # body-frame increments (same forward kinematics on displacements)
        dbx, dby, dtheta = body_twist_from_wheel_rates(
            dth[0], dth[1], dth[2], dth[3],
            self.config.wheel_radius_m,
            self.config.half_length_m,
            self.config.half_width_m,
        )

        # integrate into world frame using mid-point heading for accuracy
        th_mid = self.state.theta + dtheta / 2.0
        cos_t = math.cos(th_mid)
        sin_t = math.sin(th_mid)
        self.state.x += dbx * cos_t - dby * sin_t
        self.state.y += dbx * sin_t + dby * cos_t
        self.state.theta = _wrap_angle(self.state.theta + dtheta)

        if dt_s > 0.0:
            self.state.vx = dbx / dt_s
            self.state.vy = dby / dt_s
            self.state.wz = dtheta / dt_s
        return self.state


def _wrap_angle(a: float) -> float:
    """Wrap to (-pi, pi]."""
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    if a <= -math.pi:
        a += 2.0 * math.pi
    return a
