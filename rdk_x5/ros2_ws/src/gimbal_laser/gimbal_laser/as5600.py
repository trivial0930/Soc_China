from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


AS5600_ADDRESS = 0x36
AS5600_RAW_ANGLE_REGISTER = 0x0C
AS5600_RESOLUTION = 4096


class I2CBus(Protocol):
    def read_i2c_block_data(self, address: int, register: int, length: int):
        ...


def wrap_signed_degrees(angle: float) -> float:
    wrapped = (angle + 180.0) % 360.0 - 180.0
    if wrapped == -180.0 and angle > 0:
        return 180.0
    return wrapped


def raw_to_degrees(raw: int, zero_deg: float = 0.0, invert: bool = False) -> float:
    raw &= 0x0FFF
    degrees = raw * 360.0 / AS5600_RESOLUTION
    if invert:
        degrees = -degrees
    return wrap_signed_degrees(degrees - zero_deg)


@dataclass
class AS5600AngleSensor:
    bus: I2CBus
    address: int = AS5600_ADDRESS
    zero_deg: float = 0.0
    invert: bool = False

    def read_raw(self) -> int:
        high, low = self.bus.read_i2c_block_data(
            self.address,
            AS5600_RAW_ANGLE_REGISTER,
            2,
        )
        return ((int(high) & 0x0F) << 8) | int(low)

    def read_degrees(self) -> float:
        return raw_to_degrees(self.read_raw(), zero_deg=self.zero_deg, invert=self.invert)


def open_smbus(bus_id: int):
    try:
        from smbus2 import SMBus
    except ImportError as exc:
        raise RuntimeError("Install smbus2 on RDK before reading AS5600 sensors") from exc
    return SMBus(bus_id)
