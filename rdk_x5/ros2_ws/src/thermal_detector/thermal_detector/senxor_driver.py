"""Waveshare Thermal-90 (Meridian MI0801 + MI48x3 / SenXor) driver for RDK X5.

Module facts (verified from the product page / datasheet):

* Resolution: 80 (H) x 62 (V), radiometric (per-pixel degrees C), +-2 C.
* FOV 90x68 deg, 25 FPS, NETD 150 mK.
* Control over **I2C** (addr 0x40, alt 0x41); thermal frame over **SPI**
  (mode 0, MSB-first, 16-bit). DATA_READY (READY) goes high when a full frame
  is available and drops once it has been read. RESET resets the MI48.

Design
------
The SPI/I2C/GPIO register dance is handled by Waveshare's official **Pysenxor**
library (install on the RDK: download ``Pysenxor-master.zip`` from the Waveshare
wiki and ``python setup.py install``). We keep that hardware coupling behind a
small ``SenxorBackend`` Protocol so:

* the pure data path (reshape / orientation / unit scaling) is unit-tested here
  on any machine, and
* ``ThermalCamera`` imports off-board (it only touches a backend you pass in).

``PysenxorBackend`` adapts the installed library. Its exact call signatures must
be confirmed against the Pysenxor version on the board during Phase 1 bring-up
(it cannot be exercised without the hardware); the spots to verify are flagged
with ``# VERIFY ON BOARD``.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import List, Optional, Protocol, Sequence


THERMAL_WIDTH = 80
THERMAL_HEIGHT = 62

# SenXor calibrated temperature frames are emitted in deci-Kelvin (0.1 K).
DECI_KELVIN_SCALE = 0.1
KELVIN_OFFSET = -273.15


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested, no hardware)
# --------------------------------------------------------------------------- #
def deci_kelvin_to_celsius(raw: float) -> float:
    """Convert a raw deci-Kelvin pixel value to degrees Celsius."""
    return raw * DECI_KELVIN_SCALE + KELVIN_OFFSET


def reshape_celsius(
    flat: Sequence[float],
    width: int,
    height: int,
    flip_vertical: bool = False,
    flip_horizontal: bool = False,
) -> List[List[float]]:
    """Reshape a flat row-major frame into a 2-D grid, applying orientation.

    ``flip_vertical`` / ``flip_horizontal`` correct the physical mounting so the
    thermal image matches the RGB image orientation (determine these once during
    calibration, Phase 2).
    """
    expected = width * height
    if len(flat) != expected:
        raise ValueError(f"Expected {expected} values for {width}x{height}, got {len(flat)}")

    rows = [[float(flat[y * width + x]) for x in range(width)] for y in range(height)]
    if flip_horizontal:
        rows = [list(reversed(row)) for row in rows]
    if flip_vertical:
        rows = list(reversed(rows))
    return rows


# --------------------------------------------------------------------------- #
# Backend abstraction
# --------------------------------------------------------------------------- #
class SenxorBackend(Protocol):
    """Minimal interface the camera needs from a hardware backend.

    Implementations return one full frame as a flat, row-major sequence of
    **degrees Celsius**, length ``width * height``.
    """

    def start_stream(self) -> None: ...

    def read_celsius_frame(self) -> Sequence[float]: ...

    def stop(self) -> None: ...


class MockSenxorBackend:
    """Off-board backend producing a synthetic frame (ambient + one hotspot).

    Lets the full RGB+thermal pipeline run on a laptop without the sensor.
    """

    def __init__(self, ambient_c: float = 24.0, hot_c: float = 120.0) -> None:
        self.ambient_c = ambient_c
        self.hot_c = hot_c
        self._started = False

    def start_stream(self) -> None:
        self._started = True

    def read_celsius_frame(self) -> Sequence[float]:
        frame = [self.ambient_c] * (THERMAL_WIDTH * THERMAL_HEIGHT)
        # A small hot square near the centre.
        for y in range(28, 34):
            for x in range(37, 43):
                frame[y * THERMAL_WIDTH + x] = self.hot_c
        return frame

    def stop(self) -> None:
        self._started = False


class _Xfer3SPI:  # pragma: no cover - requires board hardware
    """SPI frame reader for the MI48 using spidev ``xfer3``.

    py-spidev 3.7 caps ``xfer``/``xfer2`` at 4096 bytes per call, so Pysenxor's
    default 160-byte chunked read drops CS mid-frame (-> all-zero frames). ``xfer3``
    honours the kernel ``spidev bufsiz`` (raised to >= one frame), so the whole
    10080-byte frame transfers as a single CS-asserted block. Implements the same
    interface MI48 expects from ``senxor.interfaces.SPI_Interface``.
    """

    def __init__(self, spidev_obj, xfer_size: int, cs=None) -> None:
        self.device = spidev_obj
        self.xfer_size = xfer_size
        self.cs = cs  # optional software chip-select (e.g. _HobotCS), held across the read

    def open(self) -> None:
        self.device.open()

    def read(self, length_in_words: int):
        import numpy as np

        length_in_bytes = 2 * length_in_words
        if self.cs is not None:
            self.cs.assert_cs()
        try:
            response = self.device.xfer3([0] * length_in_bytes)  # one CS-held transfer
        finally:
            if self.cs is not None:
                self.cs.deassert_cs()
        buffer = np.array(response).astype("u1")
        # MI48 sends 16-bit words MSB-first -> big-endian unsigned 2-byte ints.
        return np.ndarray(shape=(len(buffer) // 2,), buffer=buffer, dtype=">u2")

    def reset_input_buffer(self) -> None:
        try:
            self.device.reset_input_buffer()
        except AttributeError:
            pass

    def reset_output_buffer(self) -> None:
        try:
            self.device.reset_output_buffer()
        except AttributeError:
            pass

    def close(self) -> None:
        self.device.close()


class _HobotCS:  # pragma: no cover - requires board hardware
    """Active-low chip-select driven by a Hobot.GPIO BOARD pin.

    Needed because spidev userspace does not assert the SPI CS on this SoC/kernel
    (a documented Pysenxor caveat). Wire the module's SS to a GPIO-drivable BOARD
    pin (BOARD 7 on this board), set spidev ``no_cs``, and hold CS low across the
    frame read.
    """

    def __init__(self, pin: int, settle_s: float = 0.0001) -> None:
        import Hobot.GPIO as GPIO  # type: ignore

        self._GPIO = GPIO
        self._pin = pin
        self._settle = settle_s
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)  # deasserted (active-low)

    def assert_cs(self) -> None:
        self._GPIO.output(self._pin, self._GPIO.LOW)
        time.sleep(self._settle)

    def deassert_cs(self) -> None:
        time.sleep(self._settle)
        self._GPIO.output(self._pin, self._GPIO.HIGH)


def _hobot_reset_pulse(pin: int, assert_s: float = 0.001, settle_s: float = 0.05) -> None:  # pragma: no cover - board
    """Active-low hardware reset of the MI48 via a Hobot.GPIO BOARD pin."""
    import Hobot.GPIO as GPIO  # type: ignore

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
    GPIO.output(pin, GPIO.LOW)
    time.sleep(assert_s)
    GPIO.output(pin, GPIO.HIGH)
    time.sleep(settle_s)


def create_pysenxor_backend(
    spi_bus: int = 1,       # SPI1 -> /dev/spidev1.1 on this RDK X5 (NOT spidev5.0)
    spi_device: int = 1,    # CSN1 (pin 24); CS is actually driven via GPIO 7
    i2c_bus: int = 5,
    i2c_address: int = 0x40,
    reset_pin: Optional[int] = None,
    data_ready_pin: Optional[int] = None,
    fps: float = 7.0,             # at 1MHz one frame read takes ~80ms; >12fps frame period < read
                                  # time -> read/write overlap -> empty frames. 7fps gives margin.
    spi_xfer_size: int = 160,
    spi_speed_hz: int = 4_000_000,  # validated clean at 4MHz once a GND flylead is twisted with
                                    # SCLK (signal-integrity fix); drop to 1-2MHz only if corrupt.
    cs_high: bool = True,
    cs_gpio_pin: Optional[int] = None,
    nuc_path: Optional[str] = "/root/thermal_nuc.npy",
) -> SenxorBackend:
    """Build a backend backed by the installed Pysenxor (``senxor``) library (RDK only).

    Verified against Pysenxor 1.4.1: ``MI48([i2c, spi])`` with
    ``I2C_Interface(SMBus(bus), addr)`` and ``SPI_Interface(SpiDev(bus, dev), xfer_size)``.
    ``MI48.read()`` returns ``(data, header)`` where ``data`` is a flat float array
    already in degrees Celsius. DATA_READY is polled via ``get_status() & DATA_READY``.

    ``data_ready_pin`` (RDK BOARD 13 as wired) is accepted for completeness; this
    backend polls STATUS instead of waiting on the pin (simpler, robust). ``reset_pin``
    (RDK BOARD 16) is pulsed once before bring-up if provided. CS polarity: the MI48
    wants CS active-high (``cs_high``); if native CE0 polarity proves wrong on the
    board, that is the first thing to revisit.
    """
    # Ensure Pysenxor is importable in-process. Some RDK libs (BPU/camera) reset
    # sys.path, dropping PYTHONPATH-based entries, so insert it explicitly here.
    import os as _os
    import sys as _sys

    for _p in (_os.environ.get("PYSENXOR_SRC"), "/root/pysenxor-master"):
        if _p and _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)

    try:
        try:
            from smbus2 import SMBus  # type: ignore
        except ImportError:  # pragma: no cover - board variance
            from smbus import SMBus  # type: ignore
        from spidev import SpiDev  # type: ignore
        from senxor.mi48 import MI48, DATA_READY  # type: ignore
        from senxor.interfaces import I2C_Interface  # type: ignore
    except ImportError as exc:  # pragma: no cover - requires board
        raise RuntimeError(
            "Pysenxor/smbus/spidev not available. On the RDK X5 install spidev + "
            "python3-smbus(2), and Pysenxor (Waveshare Pysenxor-master.zip -> "
            "`python3 setup.py install`, or add it to PYTHONPATH)."
        ) from exc

    if reset_pin is not None:
        try:
            _hobot_reset_pulse(reset_pin)
        except Exception as exc:  # pragma: no cover - board GPIO variance
            # The MI48 also soft-powers-up in its constructor, so a failed
            # hardware reset is non-fatal -- warn and continue.
            print(f"[warn] hardware reset on pin {reset_pin} skipped: {exc}", flush=True)

    i2c = I2C_Interface(SMBus(i2c_bus), i2c_address)
    spi_dev = SpiDev(spi_bus, spi_device)
    spi_dev.mode = 0
    spi_dev.max_speed_hz = spi_speed_hz
    spi_dev.bits_per_word = 8

    cs = None
    if cs_gpio_pin is not None:
        # Software chip-select on a GPIO (spidev does not assert CS on this SoC).
        try:
            spi_dev.no_cs = True
        except Exception:  # pragma: no cover - some kernels reject no_cs
            pass
        cs = _HobotCS(cs_gpio_pin)
    else:
        try:
            spi_dev.cshigh = cs_high
        except Exception:  # pragma: no cover - some kernels reject cshigh
            pass
    spi = _Xfer3SPI(spi_dev, xfer_size=spi_xfer_size, cs=cs)

    # Prevent an AttributeError crash during construction when the chip has a
    # backlog frame: MI48.error_handler -> read -> read_raw expects this class attr.
    MI48.read_raw = False

    mi48 = MI48([i2c, spi])  # __init__ runs get_camera_info() -> sets fpa_shape
    return _PysenxorBackend(mi48, DATA_READY, fps, nuc_path=nuc_path)


def _repair_bad_rows(c):  # pragma: no cover - requires numpy / board frames
    """Interpolate bad rows: the fixed row47/48 FPN plus any residual row outliers.

    After NUC subtraction most fixed-pattern noise is gone, but rows 47/48 are not
    a pure offset (true bad rows) so they leave occasional horizontal streaks.
    Replace flagged rows with a 5x1 vertical median (validated on the bench:
    removes streaks without disturbing real temperature gradients).
    """
    import numpy as np

    H, W = c.shape
    rm = np.median(c, axis=1)
    smooth = np.array([np.median(rm[max(0, i - 2):i + 3]) for i in range(H)])
    bad = np.abs(rm - smooth) > 1.5
    if H > 48:
        bad[47] = True
        bad[48] = True
    if bad.any():
        pad = np.pad(c, ((2, 2), (0, 0)), mode="edge")
        vmed = np.median(np.stack([pad[i:i + H] for i in range(5)], axis=0), axis=0).astype(np.float32)
        c = c.copy()
        c[bad] = vmed[bad]
    return c


class _PysenxorBackend:  # pragma: no cover - requires board hardware
    """Adapter over a constructed Pysenxor MI48 (verified vs Pysenxor 1.4.1).

    Reads in **single-frame** mode (``start(stream=False)`` per frame) to avoid the
    continuous-stream frame-boundary misalignment (random phase each start), and
    applies a fixed-pattern **NUC** offset (uniform-scene calibration) + known
    **bad-row** repair so the returned Celsius frame is clean: no column stripes,
    no row47/48 FPN, and no dead-pixel false hotspots (the latter previously broke
    argmax-based localisation). The NUC is per-module / mildly temperature-dependent;
    recapture (lens covered, uniform surface) if you swap modules or ambient shifts.
    """

    def __init__(self, mi48, data_ready_flag, fps: float, nuc_path: Optional[str] = None) -> None:
        self._mi48 = mi48
        self._data_ready_flag = data_ready_flag
        self._fps = fps
        self._nuc = self._load_nuc(nuc_path)

    @staticmethod
    def _load_nuc(path):
        import numpy as np

        if path:
            try:
                arr = np.load(path).astype(np.float32)
                if arr.shape == (THERMAL_HEIGHT, THERMAL_WIDTH):
                    print(f"[thermal] NUC loaded from {path}", flush=True)
                    return arr
                print(f"[warn] NUC {path} shape {arr.shape} != "
                      f"({THERMAL_HEIGHT},{THERMAL_WIDTH}); ignoring", flush=True)
            except FileNotFoundError:
                print(f"[warn] NUC {path} not found; running without NUC "
                      f"(stripes/FPN remain). Capture one with the bench tool.", flush=True)
            except Exception as exc:
                print(f"[warn] NUC load failed ({path}): {exc}; running without NUC", flush=True)
        return np.zeros((THERMAL_HEIGHT, THERMAL_WIDTH), np.float32)

    def start_stream(self) -> None:
        # Single-frame mode: each frame is triggered in read_celsius_frame(), so we
        # only configure here (no continuous stream start).
        # This MI48 firmware + Pysenxor flag a spurious header-CRC mismatch even
        # though the data is valid; disable header parsing to skip the error spam.
        try:
            self._mi48.parse_header = False
        except Exception:
            pass
        self._mi48.set_fps(self._fps)
        # Enable the MI48 on-chip filters (FW >= 2) to cut per-pixel/temporal noise,
        # as in the Pysenxor reference; otherwise the raw frame is very noisy.
        try:
            if int(self._mi48.fw_version[0]) >= 2:
                self._mi48.enable_filter(f1=True, f2=True, f3=False)
                self._mi48.set_offset_corr(0.0)
        except Exception:
            pass

    def read_celsius_frame(self) -> Sequence[float]:
        import time
        import numpy as np

        self._mi48.start(stream=False, with_header=True)  # trigger one fresh frame
        for _ in range(400):  # ~1s budget at 2.5ms poll
            if self._mi48.get_status() & self._data_ready_flag:
                break
            time.sleep(0.0025)
        data, _header = self._mi48.read()  # flat float array, already Celsius
        if data is None:
            raise RuntimeError("MI48 returned no frame (GFRA); check SPI CS / wiring")

        c = np.asarray([float(v) for v in data], np.float32).reshape(THERMAL_HEIGHT, THERMAL_WIDTH)
        c = c - self._nuc          # subtract fixed-pattern offset (stripes + per-pixel FPN)
        c = _repair_bad_rows(c)    # mend row47/48 + residual row outliers
        return [float(v) for v in c.reshape(-1)]

    def stop(self) -> None:
        try:
            self._mi48.stop(stop_timeout=0.5)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Camera
# --------------------------------------------------------------------------- #
@dataclass
class ThermalCamera:
    """Reads degrees-Celsius frames as a 2-D grid via a SenxorBackend."""

    backend: SenxorBackend
    width: int = THERMAL_WIDTH
    height: int = THERMAL_HEIGHT
    flip_vertical: bool = False
    flip_horizontal: bool = False

    def init(self) -> None:
        self.backend.start_stream()

    def read_frame(self) -> List[List[float]]:
        flat = self.backend.read_celsius_frame()
        return reshape_celsius(
            flat,
            self.width,
            self.height,
            flip_vertical=self.flip_vertical,
            flip_horizontal=self.flip_horizontal,
        )

    def close(self) -> None:
        self.backend.stop()
