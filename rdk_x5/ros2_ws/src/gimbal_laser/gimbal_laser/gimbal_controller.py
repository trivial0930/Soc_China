from __future__ import annotations

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


@dataclass
class AxisIO:
    config: AxisConfig
    sensor: AngleSensor
    motor: PhaseMotor


@dataclass(frozen=True)
class ControlConfig:
    max_duty: float = 0.1
    startup_duty: float = 0.03
    angle_deadband_deg: float = 1.0
    command_timeout_sec: float = 1.0
    proportional_gain: float = 0.01


@dataclass(frozen=True)
class GimbalStatus:
    state: GimbalState
    pan_deg: float
    tilt_deg: float
    target_pan_deg: float
    target_tilt_deg: float
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
        self.enabled = False
        self.last_command_sec: float | None = None
        self.last_pan_deg = 0.0
        self.last_tilt_deg = 0.0
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
        self.enabled = enabled
        self.last_command_sec = now_sec
        if not enabled:
            return self.stop("disabled")
        if self.state != GimbalState.FAULT:
            self.pan.motor.enable()
            self.tilt.motor.enable()
            self.state = GimbalState.ENABLED_CLOSED_LOOP
        return self.status()

    def stop(self, reason: str = "stop") -> GimbalStatus:
        self.enabled = False
        self._safe_outputs()
        if self.state != GimbalState.FAULT:
            self.state = GimbalState.IDLE
        self.fault = "" if reason in {"stop", "disabled", "operator_stop"} else reason
        return self.status()

    def step(self, now_sec: float) -> GimbalStatus:
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
            self.pan.motor.set_phase_duties(
                self._duties_for_error(self.target_pan_deg - self.last_pan_deg)
            )
            self.tilt.motor.set_phase_duties(
                self._duties_for_error(self.target_tilt_deg - self.last_tilt_deg)
            )
        else:
            self.state = GimbalState.IDLE
            self._safe_outputs()

        return self.status()

    def status(self) -> GimbalStatus:
        return GimbalStatus(
            state=self.state,
            pan_deg=self.last_pan_deg,
            tilt_deg=self.last_tilt_deg,
            target_pan_deg=self.target_pan_deg,
            target_tilt_deg=self.target_tilt_deg,
            enabled=self.enabled,
            clamped=self.last_clamped,
            fault=self.fault,
        )

    def _safe_outputs(self) -> None:
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

    def _duties_for_error(self, error_deg: float) -> tuple[float, float, float]:
        if abs(error_deg) <= self.config.angle_deadband_deg:
            return (0.0, 0.0, 0.0)

        duty = min(abs(error_deg) * self.config.proportional_gain, self.config.max_duty)
        duty = max(duty, min(self.config.startup_duty, self.config.max_duty))

        if error_deg > 0.0:
            return (duty, 0.0, 0.0)
        return (0.0, duty, 0.0)

    @staticmethod
    def _clamp(value: float, axis: AxisConfig) -> tuple[float, bool]:
        clamped = min(max(value, axis.min_deg), axis.max_deg)
        return clamped, clamped != value
