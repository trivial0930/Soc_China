from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_PWM_PIN_MAP = {
    29: ("pwmchip0", 0),
    31: ("pwmchip0", 1),
    37: ("pwmchip2", 0),
    18: ("pwmchip2", 1),
    28: ("pwmchip4", 0),
    27: ("pwmchip4", 1),
}


def clamp_duty(duty: float) -> float:
    return min(max(float(duty), 0.0), 1.0)


@dataclass
class SysfsPwmChannel:
    chip: str
    channel: int
    frequency_hz: int
    root: Path = Path("/sys/class/pwm")

    @property
    def chip_dir(self) -> Path:
        return self.root / self.chip

    @property
    def pwm_dir(self) -> Path:
        return self.chip_dir / f"pwm{self.channel}"

    @property
    def period_ns(self) -> int:
        return int(1_000_000_000 / self.frequency_hz)

    def export(self) -> None:
        if not self.pwm_dir.exists():
            (self.chip_dir / "export").write_text(str(self.channel))
        (self.pwm_dir / "period").write_text(str(self.period_ns))
        self.set_duty(0.0)
        (self.pwm_dir / "enable").write_text("1")

    def set_duty(self, duty: float) -> None:
        duty_ns = int(self.period_ns * clamp_duty(duty))
        (self.pwm_dir / "duty_cycle").write_text(str(duty_ns))

    def stop(self) -> None:
        self.set_duty(0.0)

    def disable(self) -> None:
        self.stop()
        (self.pwm_dir / "enable").write_text("0")


class PhasePwmMotor:
    def __init__(self, channels: Sequence[SysfsPwmChannel], enable_line) -> None:
        if len(channels) != 3:
            raise ValueError("A phase motor needs exactly three PWM channels")
        self.channels = list(channels)
        self.enable_line = enable_line

    def setup(self) -> None:
        self.enable_line.setup_output(initial=False)
        for channel in self.channels:
            channel.export()
            channel.stop()

    def enable(self) -> None:
        self.enable_line.enable()

    def disable(self) -> None:
        self.enable_line.disable()

    def set_phase_duties(self, duties: Sequence[float]) -> None:
        if len(duties) != 3:
            raise ValueError("Expected three phase duty values")
        for channel, duty in zip(self.channels, duties):
            channel.set_duty(duty)

    def stop(self) -> None:
        for channel in self.channels:
            channel.stop()


def pwm_channel_from_pin(pin: int, frequency_hz: int, root: Path = Path("/sys/class/pwm")):
    try:
        chip, channel = DEFAULT_PWM_PIN_MAP[int(pin)]
    except KeyError as exc:
        raise ValueError(f"No default PWM mapping for RDK X5 physical pin {pin}") from exc
    return SysfsPwmChannel(chip=chip, channel=channel, frequency_hz=frequency_hz, root=root)
