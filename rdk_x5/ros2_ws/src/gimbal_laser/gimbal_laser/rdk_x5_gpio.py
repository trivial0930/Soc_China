from __future__ import annotations

from dataclasses import dataclass


class _NoopGpio:
    BOARD = "BOARD"
    OUT = "OUT"
    HIGH = 1
    LOW = 0

    def setwarnings(self, enabled: bool) -> None:
        pass

    def setmode(self, mode) -> None:
        pass

    def setup(self, pin: int, mode, initial=0) -> None:
        pass

    def output(self, pin: int, value: int) -> None:
        pass

    def cleanup(self, pin: int | None = None) -> None:
        pass


def load_hobot_gpio():
    try:
        import Hobot.GPIO as GPIO
    except ImportError:
        GPIO = _NoopGpio()
    return GPIO


@dataclass
class HobotGpioLine:
    pin: int
    active_high: bool = True
    gpio_module = None

    def __post_init__(self) -> None:
        if self.gpio_module is None:
            self.gpio_module = load_hobot_gpio()

    def setup_output(self, initial: bool = False) -> None:
        self.gpio_module.setwarnings(False)
        self.gpio_module.setmode(self.gpio_module.BOARD)
        initial_value = self._logical_value(initial)
        self.gpio_module.setup(self.pin, self.gpio_module.OUT, initial=initial_value)

    def write(self, enabled: bool) -> None:
        self.gpio_module.output(self.pin, self._logical_value(enabled))

    def enable(self) -> None:
        self.write(True)

    def disable(self) -> None:
        self.write(False)

    def cleanup(self) -> None:
        self.gpio_module.cleanup(self.pin)

    def _logical_value(self, enabled: bool) -> int:
        logical = enabled if self.active_high else not enabled
        return self.gpio_module.HIGH if logical else self.gpio_module.LOW


def gpio_line_from_pin(pin: int) -> HobotGpioLine:
    return HobotGpioLine(pin=int(pin))
