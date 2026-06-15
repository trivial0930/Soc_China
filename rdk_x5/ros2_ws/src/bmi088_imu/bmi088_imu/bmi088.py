"""BMI088 (accel + gyro) I2C driver — RDK X5, /dev/i2c-5.

IMPORTANT hardware notes (verified 2026-06-08):
- This BMI088 / RDK I2C controller does NOT support repeated-start. Every register
  access must be a SPLIT transaction: write(reg) with STOP, then read with STOP.
  (smbus2 read_byte_data / read_i2c_block_data use repeated-start and NACK here.)
- Wired DIRECT to the bare module (the RDK_IMU_CONNECTOR Ver.2.0 was defective —
  it failed to tie the gyro CSG high, so the gyro never worked through it).
  SDO1/SDO2 -> GND  => accel addr 0x18, gyro addr 0x68. CSA/CSG/SEL -> 3V3 (I2C).

Scaling functions are pure (unit-tested in tests/test_bmi088_scaling.py).
"""

from __future__ import annotations

import math

# ---- addresses / registers ----
ACC_ADDR = 0x18
GYR_ADDR = 0x68

ACC_CHIP_ID = 0x00      # -> 0x1E
ACC_DATA = 0x12         # X_LSB..Z_MSB (6 bytes)
ACC_CONF = 0x40
ACC_RANGE = 0x41
ACC_PWR_CONF = 0x7C
ACC_PWR_CTRL = 0x7D
ACC_SOFTRESET = 0x7E

GYR_CHIP_ID = 0x00      # -> 0x0F
GYR_DATA = 0x02         # RATE_X_LSB..Z_MSB (6 bytes)
GYR_RANGE = 0x0F
GYR_BANDWIDTH = 0x10

GRAVITY = 9.80665
DEG2RAD = math.pi / 180.0

# accel range register value -> +/- g
ACC_RANGE_G = {0x00: 3.0, 0x01: 6.0, 0x02: 12.0, 0x03: 24.0}
# gyro range register value -> +/- deg/s
GYR_RANGE_DPS = {0x00: 2000.0, 0x01: 1000.0, 0x02: 500.0, 0x03: 250.0, 0x04: 125.0}


def to_int16(lsb: int, msb: int) -> int:
    v = (msb << 8) | lsb
    return v - 65536 if v >= 32768 else v


def accel_ms2(raw: int, range_g: float) -> float:
    """Raw 16-bit accel -> m/s^2 for the given +/- range (g)."""
    return raw / 32768.0 * range_g * GRAVITY


def gyro_rads(raw: int, range_dps: float) -> float:
    """Raw 16-bit gyro -> rad/s for the given +/- range (deg/s)."""
    return raw / 32768.0 * range_dps * DEG2RAD


class Bmi088:
    """Thin BMI088 I2C reader using split (no-repeated-start) transactions."""

    def __init__(self, bus, acc_addr=ACC_ADDR, gyr_addr=GYR_ADDR,
                 acc_range_reg=0x01, gyr_range_reg=0x00):
        import smbus2  # noqa: F401  (kept here so the pure functions import w/o smbus2)
        self._smbus2 = smbus2
        self.bus = bus
        self.acc_addr = acc_addr
        self.gyr_addr = gyr_addr
        self.acc_range_g = ACC_RANGE_G[acc_range_reg]
        self.gyr_range_dps = GYR_RANGE_DPS[gyr_range_reg]
        self._acc_range_reg = acc_range_reg
        self._gyr_range_reg = gyr_range_reg
        self.gyro_bias = (0.0, 0.0, 0.0)  # rad/s, subtracted in read_gyro

    # ---- low level (split transactions) ----
    def _read(self, addr, reg, n=1):
        self.bus.i2c_rdwr(self._smbus2.i2c_msg.write(addr, [reg]))
        m = self._smbus2.i2c_msg.read(addr, n)
        self.bus.i2c_rdwr(m)
        return list(m)

    def _write(self, addr, reg, val):
        self.bus.i2c_rdwr(self._smbus2.i2c_msg.write(addr, [reg, val]))

    def _read_retry(self, addr, reg, n=1, tries=5):
        last = None
        for _ in range(tries):
            try:
                return self._read(addr, reg, n)
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last

    def _write_retry(self, addr, reg, val, tries=5):
        last = None
        for _ in range(tries):
            try:
                self._write(addr, reg, val)
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last

    # ---- init / ids ----
    def accel_chip_id(self):
        return self._read_retry(self.acc_addr, ACC_CHIP_ID)[0]

    def gyro_chip_id(self):
        return self._read_retry(self.gyr_addr, GYR_CHIP_ID)[0]

    def setup(self):
        """Power up accel, set ranges. Gyro is active after POR."""
        import time
        # accel out of suspend
        self._write_retry(self.acc_addr, ACC_PWR_CTRL, 0x04)
        time.sleep(0.05)
        self._write_retry(self.acc_addr, ACC_PWR_CONF, 0x00)
        time.sleep(0.05)
        self._write_retry(self.acc_addr, ACC_RANGE, self._acc_range_reg)
        self._write_retry(self.acc_addr, ACC_CONF, 0xA8)  # ODR 100Hz, normal BW
        # gyro
        self._write_retry(self.gyr_addr, GYR_RANGE, self._gyr_range_reg)
        self._write_retry(self.gyr_addr, GYR_BANDWIDTH, 0x07)  # 100 Hz ODR / 32 Hz
        time.sleep(0.05)

    # ---- data ----
    def read_accel(self):
        d = self._read_retry(self.acc_addr, ACC_DATA, 6)
        return tuple(accel_ms2(to_int16(d[i], d[i + 1]), self.acc_range_g)
                     for i in (0, 2, 4))

    def read_gyro_raw(self):
        d = self._read_retry(self.gyr_addr, GYR_DATA, 6)
        return tuple(gyro_rads(to_int16(d[i], d[i + 1]), self.gyr_range_dps)
                     for i in (0, 2, 4))

    def read_gyro(self):
        gx, gy, gz = self.read_gyro_raw()
        bx, by, bz = self.gyro_bias
        return (gx - bx, gy - by, gz - bz)

    def calibrate_gyro_bias(self, samples=200):
        """Average gyro at rest -> bias (robot MUST be stationary). Returns bias."""
        import time
        sx = sy = sz = 0.0
        n = 0
        for _ in range(samples):
            try:
                gx, gy, gz = self.read_gyro_raw()
                sx += gx; sy += gy; sz += gz; n += 1
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.005)
        if n:
            self.gyro_bias = (sx / n, sy / n, sz / n)
        return self.gyro_bias
