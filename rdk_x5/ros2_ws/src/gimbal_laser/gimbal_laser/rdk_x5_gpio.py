from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_GPIO_PIN_MAP = {
    11: 17,
    13: 27,
}


@dataclass
class SysfsGpioLine:
    gpio: int
    root: Path = Path("/sys/class/gpio")
    active_high: bool = True

    @property
    def gpio_dir(self) -> Path:
        return self.root / f"gpio{self.gpio}"

    def setup_output(self, initial: bool = False) -> None:
        if not self.gpio_dir.exists():
            (self.root / "export").write_text(str(self.gpio))
        (self.gpio_dir / "direction").write_text("out")
        self.write(initial)

    def write(self, enabled: bool) -> None:
        logical = enabled if self.active_high else not enabled
        (self.gpio_dir / "value").write_text("1" if logical else "0")

    def enable(self) -> None:
        self.write(True)

    def disable(self) -> None:
        self.write(False)


def gpio_line_from_pin(pin: int, root: Path = Path("/sys/class/gpio")) -> SysfsGpioLine:
    try:
        gpio = DEFAULT_GPIO_PIN_MAP[int(pin)]
    except KeyError as exc:
        raise ValueError(f"No default GPIO mapping for RDK X5 physical pin {pin}") from exc
    return SysfsGpioLine(gpio=gpio, root=root)
