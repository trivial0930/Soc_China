#!/usr/bin/env python3
"""Phase 1 self-check for the Waveshare Thermal-90 (SenXor) on RDK X5.

Reads N frames and prints min / max / centre temperature and the measured frame
rate. With ``--save-png`` it also writes a pseudo-colour image (needs numpy+cv2).

Off-board / no sensor:
    python3 thermal_capture_test.py --mock --frames 5

On the RDK (after wiring + Pysenxor install), supply the as-wired buses/pins:
    python3 thermal_capture_test.py \
        --spi-bus 0 --spi-device 0 --i2c-bus 1 --i2c-address 0x40 \
        --reset-pin <PIN> --data-ready-pin <PIN> --frames 30 --save-png thermal.png

Sanity check: point at a hand (~30-35 C) and a powered soldering iron (clearly
hotter). If the image is mirrored/upside down vs the RGB camera, pass
``--flip-vertical`` / ``--flip-horizontal`` (record the result in the calibration).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "thermal_detector"
sys.path.insert(0, str(PACKAGE_SRC))

from thermal_detector.senxor_driver import (  # noqa: E402
    MockSenxorBackend,
    ThermalCamera,
    create_pysenxor_backend,
)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mock", action="store_true", help="use a synthetic frame source (no hardware)")
    p.add_argument("--frames", type=int, default=10)
    p.add_argument("--spi-bus", type=int, default=1)       # /dev/spidev1.1 (SPI1)
    p.add_argument("--spi-device", type=int, default=1)    # CSN1 (unused with GPIO-CS)
    p.add_argument("--i2c-bus", type=int, default=5)       # /dev/i2c-5
    p.add_argument("--i2c-address", type=lambda v: int(v, 0), default=0x40)
    p.add_argument("--reset-pin", type=int, default=16)        # RDK 40-pin BOARD 16
    p.add_argument("--data-ready-pin", type=int, default=13)   # RDK 40-pin BOARD 13
    # Full frame = (80*62 + 80 header)*2 = 10080 bytes. Read it in ONE transfer so
    # CS stays asserted (needs spidev bufsiz >= this). 160 = 1 row (chunked: only
    # works with an external GPIO CS held across chunks).
    p.add_argument("--spi-xfer-size", type=int, default=10240)
    # If spidev does not assert CS on this SoC, wire SS to a GPIO-drivable BOARD pin
    # (BOARD 7 here) and pass it; the driver sets spidev no_cs and drives CS in SW.
    p.add_argument("--cs-gpio-pin", type=int, default=7)  # SS wired to BOARD 7 (SW chip-select)
    p.add_argument("--flip-vertical", action="store_true")
    p.add_argument("--flip-horizontal", action="store_true")
    p.add_argument("--save-png", type=str, default=None)
    return p.parse_args()


def frame_stats(frame):
    flat = [v for row in frame for v in row]
    h = len(frame)
    w = len(frame[0])
    center = frame[h // 2][w // 2]
    return min(flat), max(flat), center


def save_pseudocolor(frame, path):
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[skip] numpy/cv2 not available; cannot save PNG", flush=True)
        return
    arr = np.asarray(frame, dtype="float32")
    lo, hi = float(arr.min()), float(arr.max())
    norm = (arr - lo) / (hi - lo + 1e-6)
    img = (norm * 255).astype("uint8")
    colored = cv2.applyColorMap(img, cv2.COLORMAP_JET)
    colored = cv2.resize(colored, (arr.shape[1] * 8, arr.shape[0] * 8), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(path, colored)
    print(f"[saved] {path}", flush=True)


def main():
    opt = parse_args()
    if opt.mock:
        backend = MockSenxorBackend()
    else:
        backend = create_pysenxor_backend(
            spi_bus=opt.spi_bus,
            spi_device=opt.spi_device,
            i2c_bus=opt.i2c_bus,
            i2c_address=opt.i2c_address,
            reset_pin=opt.reset_pin,
            data_ready_pin=opt.data_ready_pin,
            spi_xfer_size=opt.spi_xfer_size,
            cs_gpio_pin=opt.cs_gpio_pin,
        )

    cam = ThermalCamera(
        backend=backend,
        flip_vertical=opt.flip_vertical,
        flip_horizontal=opt.flip_horizontal,
    )
    cam.init()
    last_frame = None
    started = time.time()
    try:
        for i in range(opt.frames):
            frame = cam.read_frame()
            last_frame = frame
            lo, hi, center = frame_stats(frame)
            print(f"frame {i:03d}  min={lo:6.1f}C  max={hi:6.1f}C  center={center:6.1f}C", flush=True)
    finally:
        cam.close()

    elapsed = time.time() - started
    if opt.frames and elapsed > 0:
        print(f"\n{opt.frames} frames in {elapsed:.2f}s = {opt.frames / elapsed:.1f} FPS", flush=True)
    if opt.save_png and last_frame is not None:
        save_pseudocolor(last_frame, opt.save_png)


if __name__ == "__main__":
    main()
