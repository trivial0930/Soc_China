#!/usr/bin/env python3
"""Phase 2: calibrate the RGB <-> Thermal homography for the co-mounted cameras.

Because a thermal camera cannot see a printed checkerboard, we use a small moving
**point heat source** (soldering-iron tip, hot resistor, incandescent bulb) as the
shared landmark. Place it at >=4 spots spanning the field of view; for each spot
click its location in the RGB image and in the thermal image. We then solve a
homography (thermal pixel -> RGB pixel) with cv2.findHomography and write it to
config/thermal_rgb_calib.yaml.

Run on the RDK (needs the live MIPI camera + the wired Thermal-90):
    python3 thermal_rgb_calibrate.py --points 6 --out <repo>/rdk_x5/ros2_ws/src/thermal_detector/config/thermal_rgb_calib.yaml

Notes
-----
* Keep the heat source > ~0.5 m away to keep parallax negligible (the static
  homography assumes a roughly planar far scene; see the plan's caveats).
* The thermal frame is auto-located as the hottest pixel each capture, so you only
  need to click the RGB location; press SPACE to capture a pair, U to undo, Q when
  you have enough (>=4).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "thermal_detector"
sys.path.insert(0, str(PACKAGE_SRC))

from thermal_detector.senxor_driver import (  # noqa: E402
    THERMAL_HEIGHT,
    THERMAL_WIDTH,
    ThermalCamera,
    create_pysenxor_backend,
)

# Reuse the project's MIPI reader from the running detector.
DEPLOY_RUNTIME = Path("/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime")
if DEPLOY_RUNTIME.exists():
    sys.path.insert(0, str(DEPLOY_RUNTIME))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--points", type=int, default=6, help="number of correspondences to collect (>=4)")
    p.add_argument("--out", type=str, required=True, help="output thermal_rgb_calib.yaml path")
    p.add_argument("--camera-width", type=int, default=1920)
    p.add_argument("--camera-height", type=int, default=1072)
    p.add_argument("--camera-fps", type=int, default=30)
    # thermal bus/pins (as wired)
    p.add_argument("--spi-bus", type=int, default=5)       # /dev/spidev5.0
    p.add_argument("--spi-device", type=int, default=0)
    p.add_argument("--i2c-bus", type=int, default=5)       # /dev/i2c-5
    p.add_argument("--i2c-address", type=lambda v: int(v, 0), default=0x40)
    p.add_argument("--reset-pin", type=int, default=16)        # RDK 40-pin BOARD 16
    p.add_argument("--data-ready-pin", type=int, default=13)   # RDK 40-pin BOARD 13
    p.add_argument("--flip-vertical", action="store_true")
    p.add_argument("--flip-horizontal", action="store_true")
    return p.parse_args()


def hottest_pixel(frame):
    arr = np.asarray(frame, dtype="float32")
    y, x = np.unravel_index(int(np.argmax(arr)), arr.shape)
    return float(x), float(y), float(arr[y, x])


def open_mipi(width, height, fps):
    from lab_mipi_web_detector import CameraReader  # provided by the deploy runtime

    return CameraReader(fps, width, height)


def write_calib_yaml(path, H, rgb_wh, thermal_wh):
    rows = [[float(H[r, c]) for c in range(3)] for r in range(3)]
    lines = [
        "# RGB <-> Thermal spatial calibration (Phase 2).",
        "# homography_thermal_to_rgb maps a THERMAL pixel (x,y) to its RGB pixel.",
        f"rgb_width: {rgb_wh[0]}",
        f"rgb_height: {rgb_wh[1]}",
        f"thermal_width: {thermal_wh[0]}",
        f"thermal_height: {thermal_wh[1]}",
        "calibrated: true",
        f"calibrated_at: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        "homography_thermal_to_rgb:",
    ]
    for row in rows:
        lines.append(f"  - [{row[0]:.8f}, {row[1]:.8f}, {row[2]:.8f}]")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    opt = parse_args()
    thermal = ThermalCamera(
        backend=create_pysenxor_backend(
            spi_bus=opt.spi_bus, spi_device=opt.spi_device, i2c_bus=opt.i2c_bus,
            i2c_address=opt.i2c_address, reset_pin=opt.reset_pin, data_ready_pin=opt.data_ready_pin,
        ),
        flip_vertical=opt.flip_vertical,
        flip_horizontal=opt.flip_horizontal,
    )
    thermal.init()
    cam = open_mipi(opt.camera_width, opt.camera_height, opt.camera_fps)

    rgb_pts = []
    thermal_pts = []
    click = {"xy": None}

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            click["xy"] = (float(x), float(y))

    cv2.namedWindow("rgb")
    cv2.setMouseCallback("rgb", on_mouse)
    print("Click the heat source in the RGB window, then press SPACE to capture. "
          "U=undo, Q=finish (need >=4).", flush=True)

    while True:
        rgb = cam.read_bgr()
        frame = thermal.read_frame()
        tx, ty, tmax = hottest_pixel(frame)

        disp = rgb.copy()
        for (rx, ry) in rgb_pts:
            cv2.circle(disp, (int(rx), int(ry)), 6, (0, 255, 0), 2)
        if click["xy"] is not None:
            cv2.circle(disp, (int(click["xy"][0]), int(click["xy"][1])), 6, (0, 0, 255), 2)
        cv2.putText(disp, f"pairs={len(rgb_pts)}/{opt.points}  thermal_max={tmax:.1f}C @({int(tx)},{int(ty)})",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.imshow("rgb", disp)

        key = cv2.waitKey(30) & 0xFF
        if key == ord(" ") and click["xy"] is not None:
            rgb_pts.append(click["xy"])
            thermal_pts.append((tx, ty))
            print(f"captured pair {len(rgb_pts)}: rgb={click['xy']} thermal=({tx:.0f},{ty:.0f}) {tmax:.1f}C", flush=True)
            click["xy"] = None
        elif key == ord("u") and rgb_pts:
            rgb_pts.pop()
            thermal_pts.pop()
            print(f"undo -> {len(rgb_pts)} pairs", flush=True)
        elif key == ord("q"):
            break

    cam.close()
    thermal.close()
    cv2.destroyAllWindows()

    if len(rgb_pts) < 4:
        raise SystemExit(f"Need at least 4 correspondences, got {len(rgb_pts)}")

    src = np.array(thermal_pts, dtype="float32")  # thermal pixels
    dst = np.array(rgb_pts, dtype="float32")      # rgb pixels
    H, _mask = cv2.findHomography(src, dst, method=0)
    if H is None:
        raise SystemExit("findHomography failed; recapture with more spread-out points")

    write_calib_yaml(opt.out, H, (opt.camera_width, opt.camera_height), (THERMAL_WIDTH, THERMAL_HEIGHT))
    print(f"[saved] {opt.out}\nH=\n{H}", flush=True)


if __name__ == "__main__":
    main()
