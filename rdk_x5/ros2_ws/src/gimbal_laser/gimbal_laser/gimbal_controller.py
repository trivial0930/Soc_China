from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence


class GimbalState(str, Enum):
    BOOT = "BOOT"
    IDLE = "IDLE"
    ENABLED_CLOSED_LOOP = "ENABLED_CLOSED_LOOP"
    FAULT = "FAULT"


class AngleSensor(Protocol):
    def read_degrees(self) -> float:
        ...


class PhaseMotor(Protocol):
    def disable(self) -> None:
        ...

    def enable(self) -> None:
        ...

    def set_phase_duties(self, duties: Sequence[float]) -> None:
        ...

    def stop(self) -> None:
        ...


@dataclass(frozen=True)
class AxisConfig:
    name: str
    min_deg: float
    max_deg: float
    invert: bool = False
    pole_pairs: int = 7
    phase_offset_deg: float = 0.0


@dataclass
class AxisIO:
    config: AxisConfig
    sensor: AngleSensor
    motor: PhaseMotor


@dataclass(frozen=True)
class ControlConfig:
    max_duty: float = 0.08
    startup_duty: float = 0.022
    angle_deadband_deg: float = 1.0
    command_timeout_sec: float = 1.0
    proportional_gain: float = 0.005
    integral_gain: float = 0.0
    integral_limit: float = 0.0
    target_slew_rate_deg_s: float = 32.0
    duty_slew_rate_per_sec: float = 1.25


@dataclass(frozen=True)
class GimbalStatus:
    state: GimbalState
    pan_deg: float
    tilt_deg: float
    target_pan_deg: float
    target_tilt_deg: float
    commanded_pan_deg: float
    commanded_tilt_deg: float
    enabled: bool
    clamped: bool = False
    fault: str = ""

    def as_dict(self) -> dict:
        return {
            "state": self.state.value,
            "pan_deg": self.pan_deg,
            "tilt_deg": self.tilt_deg,
            "target_pan_deg": self.target_pan_deg,
            "target_tilt_deg": self.target_tilt_deg,
            "commanded_pan_deg": self.commanded_pan_deg,
            "commanded_tilt_deg": self.commanded_tilt_deg,
            "enabled": self.enabled,
            "clamped": self.clamped,
            "fault": self.fault,
        }


class GimbalController:
    def __init__(self, pan: AxisIO, tilt: AxisIO, config: ControlConfig | None = None) -> None:
        self.pan = pan
        self.tilt = tilt
        self.config = config or ControlConfig()
        self.state = GimbalState.BOOT
        self.target_pan_deg = 0.0
        self.target_tilt_deg = 0.0
        self.commanded_pan_deg = 0.0
        self.commanded_tilt_deg = 0.0
        self.enabled = False
        self.last_command_sec: float | None = None
        self.last_step_sec: float | None = None
        self.last_pan_deg = 0.0
        self.last_tilt_deg = 0.0
        self._last_pan_duties = (0.5, 0.5, 0.5)
        self._last_tilt_duties = (0.5, 0.5, 0.5)
        self._integral = {"pan": 0.0, "tilt": 0.0}
        self.last_clamped = False
        self.fault = ""
        self._safe_outputs()

    def set_target(self, pan_deg: float, tilt_deg: float, now_sec: float) -> GimbalStatus:
        self.target_pan_deg, pan_clamped = self._clamp(pan_deg, self.pan.config)
        self.target_tilt_deg, tilt_clamped = self._clamp(tilt_deg, self.tilt.config)
        self.last_clamped = pan_clamped or tilt_clamped
        self.last_command_sec = now_sec
        return self.status()

    def set_enabled(self, enabled: bool, now_sec: float) -> GimbalStatus:
        was_enabled = self.enabled
        self.enabled = enabled
        self.last_command_sec = now_sec
        if not enabled:
            return self.stop("disabled")
        if self.state != GimbalState.FAULT:
            if not was_enabled:
                self.commanded_pan_deg = self.last_pan_deg
                self.commanded_tilt_deg = self.last_tilt_deg
                self._last_pan_duties = (0.5, 0.5, 0.5)
                self._last_tilt_duties = (0.5, 0.5, 0.5)
                self._integral = {"pan": 0.0, "tilt": 0.0}
            self.pan.motor.enable()
            self.tilt.motor.enable()
            self.state = GimbalState.ENABLED_CLOSED_LOOP
        return self.status()

    def stop(self, reason: str = "stop") -> GimbalStatus:
        self.enabled = False
        self._safe_outputs()
        recoverable_stop = reason in {"stop", "disabled", "operator_stop"}
        if recoverable_stop or self.state != GimbalState.FAULT:
            self.state = GimbalState.IDLE
        self.fault = "" if recoverable_stop else reason
        return self.status()

    def step(self, now_sec: float) -> GimbalStatus:
        dt = self._step_dt(now_sec)
        if self.state == GimbalState.FAULT:
            self._safe_outputs()
            return self.status()

        try:
            self.last_pan_deg = self.pan.sensor.read_degrees()
            self.last_tilt_deg = self.tilt.sensor.read_degrees()
        except OSError as exc:
            return self._fault(f"i2c_read_failed:{exc}")

        if self.enabled and self._command_timed_out(now_sec):
            return self._fault("command_timeout")

        if self.enabled:
            self.state = GimbalState.ENABLED_CLOSED_LOOP
            self.pan.motor.enable()
            self.tilt.motor.enable()
            self.commanded_pan_deg = self._advance_angle(
                self.commanded_pan_deg, self.target_pan_deg, dt
            )
            self.commanded_tilt_deg = self._advance_angle(
                self.commanded_tilt_deg, self.target_tilt_deg, dt
            )
            self._last_pan_duties = self._slew_duties(
                self._last_pan_duties,
                self._duties_for_axis(self.pan, self.commanded_pan_deg, dt),
                dt,
            )
            self._last_tilt_duties = self._slew_duties(
                self._last_tilt_duties,
                self._duties_for_axis(self.tilt, self.commanded_tilt_deg, dt),
                dt,
            )
            self.pan.motor.set_phase_duties(self._last_pan_duties)
            self.tilt.motor.set_phase_duties(self._last_tilt_duties)
        else:
            self.state = GimbalState.IDLE
            self.commanded_pan_deg = self.last_pan_deg
            self.commanded_tilt_deg = self.last_tilt_deg
            self._safe_outputs()

        return self.status()

    def status(self) -> GimbalStatus:
        return GimbalStatus(
            state=self.state,
            pan_deg=self.last_pan_deg,
            tilt_deg=self.last_tilt_deg,
            target_pan_deg=self.target_pan_deg,
            target_tilt_deg=self.target_tilt_deg,
            commanded_pan_deg=self.commanded_pan_deg,
            commanded_tilt_deg=self.commanded_tilt_deg,
            enabled=self.enabled,
            clamped=self.last_clamped,
            fault=self.fault,
        )

    def _safe_outputs(self) -> None:
        self._last_pan_duties = (0.5, 0.5, 0.5)
        self._last_tilt_duties = (0.5, 0.5, 0.5)
        self._integral = {"pan": 0.0, "tilt": 0.0}
        self.pan.motor.stop()
        self.tilt.motor.stop()
        self.pan.motor.disable()
        self.tilt.motor.disable()

    def _fault(self, reason: str) -> GimbalStatus:
        self.enabled = False
        self.state = GimbalState.FAULT
        self.fault = reason
        self._safe_outputs()
        return self.status()

    def _command_timed_out(self, now_sec: float) -> bool:
        if self.last_command_sec is None:
            return True
        return (now_sec - self.last_command_sec) > self.config.command_timeout_sec

    def _step_dt(self, now_sec: float) -> float:
        if self.last_step_sec is None:
            self.last_step_sec = now_sec
            return 0.0
        dt = max(now_sec - self.last_step_sec, 0.0)
        self.last_step_sec = now_sec
        return min(dt, 0.1)

    def _advance_angle(self, current_deg: float, target_deg: float, dt: float) -> float:
        max_step = max(self.config.target_slew_rate_deg_s, 0.0) * max(dt, 0.0)
        delta = self._angle_error(current_deg, target_deg)
        if max_step <= 0.0 or abs(delta) <= max_step:
            return target_deg
        return self._wrap_signed_degrees(
            current_deg + max_step * (1.0 if delta > 0.0 else -1.0)
        )

    def _slew_duties(
        self,
        previous: tuple[float, float, float],
        target: tuple[float, float, float],
        dt: float,
    ) -> tuple[float, float, float]:
        max_step = max(self.config.duty_slew_rate_per_sec, 0.0) * max(dt, 0.0)
        if max_step <= 0.0:
            return previous
        return tuple(
            self._advance_scalar(old, new, max_step) for old, new in zip(previous, target)
        )

    def _duties_for_axis(
        self, axis: AxisIO, target_deg: float, dt: float = 0.0
    ) -> tuple[float, float, float]:
        name = axis.config.name
        current_deg = self.last_pan_deg if name == "pan" else self.last_tilt_deg
        error_deg = self._angle_error(current_deg, target_deg)
        if axis.config.invert:
            error_deg *= -1.0

        in_deadband = abs(error_deg) <= self.config.angle_deadband_deg

        p_term = 0.0 if in_deadband else error_deg * self.config.proportional_gain

        # Integral term (PI) with conditional-integration anti-windup: accumulate only
        # outside the deadband AND only while the command is not saturated, so a slew
        # that outruns the axis cannot wind the integral up into a large overshoot.
        ki = self.config.integral_gain
        integral = self._integral.get(name, 0.0)
        saturated = abs(p_term + ki * integral) >= self.config.max_duty
        if ki > 0.0 and dt > 0.0 and not in_deadband and not saturated:
            integral += error_deg * dt
            ilimit = self.config.integral_limit or self.config.max_duty
            max_integral = ilimit / ki
            integral = min(max(integral, -max_integral), max_integral)
            self._integral[name] = integral
        i_term = ki * integral

        signed_modulation = min(
            max(p_term + i_term, -self.config.max_duty),
            self.config.max_duty,
        )

        if in_deadband:
            # Hold only the integral (e.g. gravity) bias; no stiction kick here.
            if abs(signed_modulation) < 1e-6:
                return (0.5, 0.5, 0.5)
        else:
            if abs(signed_modulation) < self.config.startup_duty:
                ramp_window = max(self.config.angle_deadband_deg * 4.0, 1.0)
                ramp = min(
                    (abs(error_deg) - self.config.angle_deadband_deg) / ramp_window, 1.0
                )
                minimum = self.config.startup_duty * max(ramp, 0.0)
                signed_modulation = math.copysign(
                    max(abs(signed_modulation), minimum),
                    signed_modulation,
                )

        electrical_rad = math.radians(
            current_deg * axis.config.pole_pairs + axis.config.phase_offset_deg
        )
        torque_rad = electrical_rad + math.pi / 2.0
        phases = (0.0, -2.0 * math.pi / 3.0, 2.0 * math.pi / 3.0)
        return tuple(
            min(max(0.5 + signed_modulation * math.sin(torque_rad + phase), 0.0), 1.0)
            for phase in phases
        )

    @staticmethod
    def _clamp(value: float, axis: AxisConfig) -> tuple[float, bool]:
        clamped = min(max(value, axis.min_deg), axis.max_deg)
        return clamped, clamped != value

    @staticmethod
    def _advance_scalar(current: float, target: float, max_step: float) -> float:
        delta = target - current
        if abs(delta) <= max_step:
            return target
        return current + max_step * (1.0 if delta > 0.0 else -1.0)

    @staticmethod
    def _angle_error(current_deg: float, target_deg: float) -> float:
        return GimbalController._wrap_signed_degrees(target_deg - current_deg)

    @staticmethod
    def _wrap_signed_degrees(angle: float) -> float:
        wrapped = (angle + 180.0) % 360.0 - 180.0
        if wrapped == -180.0 and angle > 0.0:
            return 180.0
        return wrapped
