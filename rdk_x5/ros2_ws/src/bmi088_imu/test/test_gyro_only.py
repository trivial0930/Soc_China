"""Gyro-only fallback for the BMI088 driver (dead/absent accel).

Runs on a host with no smbus2 and no hardware: we inject a fake ``smbus2``
module and a fake I2C bus that can mark the accel address dead (raises OSError
on every transaction, like the RDK accel does when it drops offline). Verifies
that probe/setup/read all degrade to gyro-only instead of crashing.
"""

import sys
import types

import pytest


# --- fake smbus2 (split-transaction i2c_rdwr, like the real driver uses) ---
class _FakeMsg:
    def __init__(self, addr, data=None, length=0, is_write=False):
        self.addr = addr
        self.data = list(data) if data else []
        self.length = length
        self.is_write = is_write
        self._out = []

    def __iter__(self):
        return iter(self._out)


class _FakeI2cMsg:
    @staticmethod
    def write(addr, data):
        return _FakeMsg(addr, data=data, is_write=True)

    @staticmethod
    def read(addr, n):
        return _FakeMsg(addr, length=n, is_write=False)


class FakeBus:
    """Split-transaction I2C: write(reg) then read(n). Dead addrs raise."""

    def __init__(self, dead_addrs=(), regmap=None):
        self.dead = set(dead_addrs)
        self.regmap = dict(regmap or {})
        self._pending_reg = {}

    def i2c_rdwr(self, *msgs):
        for m in msgs:
            if m.addr in self.dead:
                raise OSError(121, "Remote I/O error")
            if m.is_write:
                self._pending_reg[m.addr] = m.data[0]
                if len(m.data) >= 2:  # reg + value write
                    self.regmap[(m.addr, m.data[0])] = m.data[1]
            else:
                reg = self._pending_reg.get(m.addr, 0)
                m._out = [self.regmap.get((m.addr, reg + i), 0)
                          for i in range(m.length)]


@pytest.fixture(autouse=True)
def _fake_smbus2(monkeypatch):
    fake = types.ModuleType("smbus2")
    fake.i2c_msg = _FakeI2cMsg
    fake.SMBus = lambda n: FakeBus()
    monkeypatch.setitem(sys.modules, "smbus2", fake)
    yield


def _import_driver():
    # import after smbus2 is faked so the in-__init__ import resolves
    from bmi088_imu.bmi088 import Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID
    return Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID


def _live_gyro_regmap(gyr_addr, gid=0x0F):
    # gyro CHIP_ID + a nonzero Z rate at GYR_DATA(0x02)..0x07
    return {
        (gyr_addr, 0x00): gid,
        (gyr_addr, 0x06): 0x00, (gyr_addr, 0x07): 0x04,  # Z raw = 0x0400
    }


def test_probe_accel_false_when_dead():
    Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID = _import_driver()
    bus = FakeBus(dead_addrs=[ACC_ADDR], regmap=_live_gyro_regmap(GYR_ADDR))
    imu = Bmi088(bus)
    assert imu.probe_accel() is False          # dead accel -> False, no raise
    assert imu.gyro_chip_id() == GYR_ID        # gyro still answers


def test_probe_accel_true_when_present():
    Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID = _import_driver()
    rm = _live_gyro_regmap(GYR_ADDR)
    rm[(ACC_ADDR, 0x00)] = ACC_ID
    imu = Bmi088(FakeBus(regmap=rm))
    assert imu.probe_accel() is True


def test_setup_gyro_only_never_touches_dead_accel():
    Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID = _import_driver()
    bus = FakeBus(dead_addrs=[ACC_ADDR], regmap=_live_gyro_regmap(GYR_ADDR))
    imu = Bmi088(bus)
    imu.setup_gyro()                # must not raise despite dead accel
    gx, gy, gz = imu.read_gyro()    # gyro readable
    assert gz != 0.0


def test_setup_accel_raises_on_dead_accel():
    # setup_accel must only be called when probe_accel() is True; on a dead
    # accel it raises (that's why the node guards it behind the probe).
    Bmi088, ACC_ADDR, GYR_ADDR, ACC_ID, GYR_ID = _import_driver()
    bus = FakeBus(dead_addrs=[ACC_ADDR], regmap=_live_gyro_regmap(GYR_ADDR))
    imu = Bmi088(bus)
    with pytest.raises(OSError):
        imu.setup_accel()
