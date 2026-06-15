#!/usr/bin/env python3
"""Automatic (no-click, no-display) RGB<->thermal calibration.

Wave a *powered* heat source that the YOLO model recognises (soldering iron /
hot air gun / soldering station) slowly around the scene. For each frame this:
  * finds the strongest thermal hotspot centroid (thermal pixels), and
  * takes the highest-score RGB detection's box centre (RGB pixels),
and, when the hotspot has moved far enough from the last sample, records the
pair. After collecting enough well-spread pairs it solves a homography
(thermal -> RGB) with cv2.findHomography and writes thermal_rgb_calib.yaml.

This replaces the interactive thermal_rgb_calibrate.py for headless use.
Run with the live detector stopped (camera is single-owner).
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

from lab_mipi_web_detector import CameraReader
from lab_ultralytics_yolo11 import YoloV11

_THERMAL_SRC = os.environ.get("THERMAL_DETECTOR_SRC")
if _THERMAL_SRC:
    sys.path.insert(0, _THERMAL_SRC)
_PYSENXOR_SRC = os.environ.get("PYSENXOR_SRC")
if _PYSENXOR_SRC:
    sys.path.insert(0, _PYSENXOR_SRC)

from thermal_detector.fusion import HotspotParams, find_hotspots  # noqa: E402
from thermal_detector.senxor_driver import (  # noqa: E402
    THERMAL_HEIGHT,
    THERMAL_WIDTH,
    ThermalCamera,
    create_pysenxor_backend,
)

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model-path", default="weights/hazard_yolo11s_640_nv12.bin")
    p.add_argument("--label-file", default="config/hazard_classes.names")
    p.add_argument("--classes-num", type=int, default=10)
    p.add_argument("--score-thres", type=float, default=0.20)
    p.add_argument("--nms-thres", type=float, default=0.45)
    p.add_argument("--priority", type=int, default=0)
    p.add_argument("--bpu-cores", nargs="+", type=int, default=[0])
    p.add_argument("--camera-fps", type=int, default=30)
    p.add_argument("--camera-width", type=int, default=1920)
    p.add_argument("--camera-height", type=int, default=1072)
    p.add_argument("--spi-bus", type=int, default=1)
    p.add_argument("--spi-device", type=int, default=1)
    p.add_argument("--i2c-bus", type=int, default=5)
    p.add_argument("--i2c-address", type=lambda v: int(v, 0), default=0x40)
    p.add_argument("--reset-pin", type=int, default=16)
    p.add_argument("--data-ready-pin", type=int, default=13)
    p.add_argument("--cs-gpio-pin", type=int, default=7)
    p.add_argument("--duration", type=float, default=75.0, help="seconds to collect")
    p.add_argument("--min-points", type=int, default=6)
    p.add_argument("--min-temp", type=float, default=45.0, help="hotspot must exceed this degC")
    p.add_argument("--min-move", type=float, default=8.0, help="thermal-px the hotspot must move to log a new pair")
    p.add_argument("--out", required=True)
    return p.parse_args()


def clean_thermal(frame):
    arr = np.asarray(frame, dtype=np.float32)
    valid = arr > -40.0
    if valid.any() and not valid.all():
        arr[~valid] = float(np.median(arr[valid]))
    return cv2.medianBlur(arr, 3)


def strongest_hotspot(thermal_arr, min_temp):
    params = HotspotParams(delta_c=6.0, abs_floor_c=min_temp, min_area_px=2)
    spots = find_hotspots(thermal_arr, params, IDENTITY)  # identity -> rgb_cx/cy are thermal coords
    if not spots:
        return None
    spots.sort(key=lambda s: s.peak_c, reverse=True)
    s = spots[0]
    return (s.rgb_cx, s.rgb_cy, s.peak_c)  # thermal-pixel centroid + peak


def best_detection_center(model, labels, frame):
    h, w = frame.shape[:2]
    inputs = model.pre_process(frame)
    outputs = model.forward(inputs)
    boxes, cls_ids, scores = model.post_process(outputs, w, h)
    if len(scores) == 0:
        return None
    i = int(np.argmax(scores))
    x1, y1, x2, y2 = (float(v) for v in boxes[i])
    cid = int(cls_ids[i])
    label = labels[cid] if cid < len(labels) else str(cid)
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0, label, float(scores[i]))


def write_calib(path, H, rgb_wh, thermal_wh, n):
    rows = [[float(H[r, c]) for c in range(3)] for r in range(3)]
    lines = [
        "# RGB <-> Thermal calibration (auto, hotspot<->detection correspondences).",
        "# homography_thermal_to_rgb maps a THERMAL pixel (x,y) to its RGB pixel.",
        f"rgb_width: {rgb_wh[0]}",
        f"rgb_height: {rgb_wh[1]}",
        f"thermal_width: {thermal_wh[0]}",
        f"thermal_height: {thermal_wh[1]}",
        "calibrated: true",
        f"calibrated_at: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"calibration_method: auto_hotspot_detection ({n} pairs)",
        "homography_thermal_to_rgb:",
    ]
    for row in rows:
        lines.append(f"  - [{row[0]:.8f}, {row[1]:.8f}, {row[2]:.8f}]")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    opt = parse_args()
    sys.path.append("/app/pydev_demo")
    import utils.common_utils as common
    labels = common.load_class_names(opt.label_file)

    model = YoloV11(opt)
    model.set_scheduling_params(priority=opt.priority, bpu_cores=opt.bpu_cores)
    cam = CameraReader(opt.camera_fps, opt.camera_width, opt.camera_height)
    thermal = ThermalCamera(
        backend=create_pysenxor_backend(
            spi_bus=opt.spi_bus, spi_device=opt.spi_device, i2c_bus=opt.i2c_bus,
            i2c_address=opt.i2c_address, reset_pin=opt.reset_pin,
            data_ready_pin=opt.data_ready_pin, cs_gpio_pin=opt.cs_gpio_pin, spi_xfer_size=10240,
        )
    )
    thermal.init()

    print(f"Collecting for up to {opt.duration:.0f}s. Slowly move a POWERED, recognised heat "
          f"source (soldering iron / hot air gun) to ~{opt.min_points}+ spots across the view.", flush=True)

    pts_t, pts_r = [], []
    last = None
    started = time.time()
    while time.time() - started < opt.duration and len(pts_t) < max(opt.min_points, 8):
        rgb = cam.read_bgr()
        t_arr = clean_thermal(thermal.read_frame())
        hs = strongest_hotspot(t_arr, opt.min_temp)
        det = best_detection_center(model, labels, rgb)
        if hs and det:
            tx, ty, peak = hs
            rx, ry, label, score = det
            if last is None or ((tx - last[0]) ** 2 + (ty - last[1]) ** 2) ** 0.5 >= opt.min_move:
                pts_t.append((tx, ty))
                pts_r.append((rx, ry))
                last = (tx, ty)
                print(f"  pair {len(pts_t)}: thermal=({tx:.0f},{ty:.0f}) {peak:.0f}C  "
                      f"rgb=({rx:.0f},{ry:.0f}) [{label} {score:.2f}]", flush=True)
        time.sleep(0.05)

    cam.close()
    thermal.close()

    if len(pts_t) < 4:
        print(f"[FAIL] only {len(pts_t)} pairs; need >=4. Keeping existing calib. "
              f"Use a hotter / recognised source and move it more widely.", flush=True)
        raise SystemExit(1)

    src = np.array(pts_t, dtype="float32")
    dst = np.array(pts_r, dtype="float32")
    H, mask = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=40.0)
    if H is None:
        print("[FAIL] findHomography failed; recapture with more spread.", flush=True)
        raise SystemExit(1)
    inliers = int(mask.sum()) if mask is not None else len(pts_t)
    write_calib(opt.out, H, (opt.camera_width, opt.camera_height), (THERMAL_WIDTH, THERMAL_HEIGHT), inliers)
    print(f"[OK] wrote {opt.out} from {len(pts_t)} pairs ({inliers} inliers)\nH=\n{H}", flush=True)


if __name__ == "__main__":
    main()
