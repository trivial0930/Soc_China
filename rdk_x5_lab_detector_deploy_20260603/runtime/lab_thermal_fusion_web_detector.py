#!/usr/bin/env python3
"""Phase 4 (path A): live RGB + thermal *heat-source hazard* web detector.

Additive sibling of lab_mipi_web_detector.py -- the original RGB-only detector is
left untouched. This one:

* runs the existing YOLO11 hazard model on the MIPI RGB frame,
* reads a thermal frame from the Waveshare Thermal-90 (SenXor),
* fuses them with the tested thermal_detector.HazardPipeline (severity = object
  class x temperature; object-less hotspots flagged as "unknown heat source"),
* serves a side-by-side MJPEG (RGB with risk-coloured boxes + a risk banner |
  thermal pseudo-colour), and
* saves evidence frames + writes thermal_risk events (docs/protocols/event_schema.md)
  on warning/critical, throttled by a cooldown.

Run with a real sensor (buses/pins as wired -- spidev5.0 / i2c-5):
    THERMAL_DETECTOR_SRC=/path/to/ros2_ws/src/thermal_detector \
    python3 runtime/lab_thermal_fusion_web_detector.py \
      --model-path weights/hazard_yolo11s_640_nv12.bin \
      --label-file config/hazard_classes.names --classes-num 10 \
      --spi-bus 5 --spi-device 0 --i2c-bus 5 --i2c-address 0x40 \
      --reset-pin <PIN> --data-ready-pin <PIN> \
      --calib config/thermal_rgb_calib.yaml --hazard config/thermal_hazard.yaml

Test the web UI + fusion WITHOUT the sensor wired (synthetic thermal frame):
    ... same as above but add --mock-thermal (buses/pins ignored)
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from lab_mipi_web_detector import CameraReader
from lab_ultralytics_yolo11 import YoloV11

sys.path.append("/app/pydev_demo")
import utils.common_utils as common  # noqa: E402

# Make the (pure, tested) thermal_detector package importable. Point
# THERMAL_DETECTOR_SRC at ros2_ws/src/thermal_detector when running on the board.
_THERMAL_SRC = os.environ.get("THERMAL_DETECTOR_SRC")
if _THERMAL_SRC:
    sys.path.insert(0, _THERMAL_SRC)

from thermal_detector.fusion import Detection, apply_homography  # noqa: E402
from thermal_detector.hazard_pipeline import HazardPipeline  # noqa: E402
from thermal_detector.senxor_driver import (  # noqa: E402
    MockSenxorBackend,
    ThermalCamera,
    create_pysenxor_backend,
)


# Severity -> BGR colour.
SEVERITY_COLOR = {
    "critical": (0, 0, 255),
    "warning": (0, 165, 255),
    "info": (0, 200, 0),
}
ORPHAN_COLOR = (255, 0, 255)


def _color(severity):
    return SEVERITY_COLOR.get(severity, (160, 160, 160))


class FusionDetector:
    def __init__(self, opt):
        self.opt = opt
        self.labels = common.load_class_names(opt.label_file)
        self.model = YoloV11(opt)
        self.model.set_scheduling_params(priority=opt.priority, bpu_cores=opt.bpu_cores)
        common.print_model_info(self.model.model)

        self.camera = CameraReader(opt.camera_fps, opt.camera_width, opt.camera_height)

        backend = MockSenxorBackend() if opt.mock_thermal else create_pysenxor_backend(
            spi_bus=opt.spi_bus, spi_device=opt.spi_device, i2c_bus=opt.i2c_bus,
            i2c_address=opt.i2c_address, reset_pin=opt.reset_pin, data_ready_pin=opt.data_ready_pin,
            spi_xfer_size=opt.spi_xfer_size, cs_gpio_pin=opt.cs_gpio_pin,
        )
        self.thermal = ThermalCamera(
            backend=backend,
            flip_vertical=bool(opt.thermal_flip_vertical),
            flip_horizontal=bool(opt.thermal_flip_horizontal),
        )
        self._rgb_rotate = int(opt.rgb_rotate)
        self.thermal.init()

        self.pipeline = HazardPipeline.from_config(opt.hazard, opt.calib)
        self.lock = threading.Lock()
        self._last_evidence = 0.0
        os.makedirs(opt.evidence_dir, exist_ok=True)
        os.makedirs(opt.events_dir, exist_ok=True)

    def close(self):
        self.camera.close()
        try:
            self.thermal.close()
        except Exception:
            pass

    # -- rendering ------------------------------------------------------- #
    def _annotate_rgb(self, frame, result):
        for obj in result.objects:
            x1, y1, x2, y2 = (int(v) for v in obj.box)
            color = _color(obj.severity)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            temp = "" if obj.peak_c is None else f" {obj.peak_c:.0f}C"
            label = f"{obj.label} {obj.thermal_state}{temp}"
            cv2.putText(frame, label, (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        for spot in result.orphan_hotspots:
            (rx1, ry1) = apply_homography(self.pipeline.homography_thermal_to_rgb, spot.tx1, spot.ty1)
            (rx2, ry2) = apply_homography(self.pipeline.homography_thermal_to_rgb, spot.tx2, spot.ty2)
            cv2.rectangle(frame, (int(rx1), int(ry1)), (int(rx2), int(ry2)), ORPHAN_COLOR, 2)
            cv2.putText(frame, f"UNKNOWN HEAT {spot.peak_c:.0f}C", (int(rx1), max(18, int(ry1) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, ORPHAN_COLOR, 2)

        # Risk banner across the top.
        banner_color = _color(result.overall_severity)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 44), banner_color, -1)
        cv2.putText(frame, result.banner, (12, 31),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        return frame

    def _thermal_panel(self, thermal_frame, height):
        arr = np.asarray(thermal_frame, dtype="float32")
        # Percentile-based scaling so a stray hot/cold outlier doesn't flatten the
        # whole image to one colour; label shows the real min/max.
        lo = float(np.percentile(arr, 2))
        hi = float(np.percentile(arr, 98))
        norm = np.clip((arr - lo) / (hi - lo + 1e-6), 0.0, 1.0)
        colored = cv2.applyColorMap((norm * 255).astype("uint8"), cv2.COLORMAP_JET)
        width = max(1, int(height * arr.shape[1] / arr.shape[0]))
        panel = cv2.resize(colored, (width, height), interpolation=cv2.INTER_NEAREST)
        cv2.putText(panel, f"{float(arr.min()):.0f}-{float(arr.max()):.0f}C", (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return panel

    # -- evidence / events ---------------------------------------------- #
    def _maybe_save_evidence(self, composed, result):
        if result.overall_severity not in ("warning", "critical"):
            return
        now = time.time()
        if now - self._last_evidence < self.opt.evidence_cooldown:
            return
        self._last_evidence = now

        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
        img_path = os.path.join(self.opt.evidence_dir, f"{stamp}_{result.overall_severity}.jpg")
        cv2.imwrite(img_path, composed)

        confidence = max((o.score for o in result.objects), default=0.0)
        event = {
            "event_id": stamp,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
            "station_id": self.opt.station_id,
            "source": "thermal",
            "event_type": "thermal_risk",
            "severity": result.overall_severity,
            "confidence": round(float(confidence), 3),
            "summary": result.banner,
            "evidence": {"image_path": img_path, "log_path": "", "serial_output": ""},
            "action": {"robot_task": "", "voice_prompt": "", "reported_to_admin": False},
        }
        with open(os.path.join(self.opt.events_dir, f"{stamp}.json"), "w", encoding="utf-8") as fh:
            json.dump(event, fh, ensure_ascii=False, indent=2)
        print(f"[evidence] {img_path} ({result.overall_severity})", flush=True)

    # -- main step ------------------------------------------------------- #
    def detect_jpeg(self):
        started = time.time()
        with self.lock:
            # Capture RGB and thermal back-to-back (before YOLO) so the fused pair
            # is from ~the same instant. Reading thermal AFTER YOLO would offset it
            # by the inference time (~0.1-0.2s) -> visible desync on moving objects.
            frame = self.camera.read_bgr()
            if self._rgb_rotate == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self._rgb_rotate == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self._rgb_rotate == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            thermal_frame = self.thermal.read_frame()
            h, w = frame.shape[:2]
            inputs = self.model.pre_process(frame)
            outputs = self.model.forward(inputs)
            boxes, cls_ids, scores = self.model.post_process(outputs, w, h)

        # Clean the thermal frame: occasional reads return raw-0 (-273C) dead
        # pixels which wreck normalization and the hotspot baseline. Replace any
        # physically-impossible pixel (< -40C) with the median of valid pixels,
        # then a light 3x3 median filter to drop single-pixel noise (preserves
        # real hot-region peaks). medianBlur on float32 supports aperture 3/5.
        thermal_arr = np.asarray(thermal_frame, dtype=np.float32)
        valid = thermal_arr > -40.0
        if valid.any() and not valid.all():
            thermal_arr[~valid] = float(np.median(thermal_arr[valid]))
        thermal_arr = cv2.medianBlur(thermal_arr, 3)

        detections = []
        for box, cls_id, score in zip(boxes, cls_ids, scores):
            cid = int(cls_id)
            label = self.labels[cid] if cid < len(self.labels) else str(cid)
            detections.append(Detection(cid, label, float(score), tuple(float(v) for v in box)))

        result = self.pipeline.assess(detections, thermal_arr)

        annotated = self._annotate_rgb(frame, result)
        panel = self._thermal_panel(thermal_arr, annotated.shape[0])
        composed = np.hstack([annotated, panel])

        self._maybe_save_evidence(composed, result)

        ok, encoded = cv2.imencode(".jpg", composed, [int(cv2.IMWRITE_JPEG_QUALITY), self.opt.jpeg_quality])
        if not ok:
            raise RuntimeError("Failed to JPEG-encode composed frame")

        elapsed = time.time() - started
        print(f"frame {elapsed:.3f}s overall={result.overall_severity} "
              f"objects={len(result.objects)} orphans={len(result.orphan_hotspots)} | {result.banner}",
              flush=True)
        return encoded.tobytes()


def make_handler(detector):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RDK X5 Heat-Source Hazard Detector</title>
<style>html,body{margin:0;background:#101214;color:#f2f2f2;font-family:Arial}
header{padding:12px 16px;font-size:18px;font-weight:600;background:#1a1d20}
img{display:block;width:100vw;height:auto}</style></head>
<body><header>RDK X5 - RGB + Thermal heat-source hazard (left: RGB+risk, right: thermal)</header>
<img src="/stream.mjpg" alt="fusion stream"></body></html>""".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/snapshot.jpg":
                try:
                    jpeg = detector.detect_jpeg()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpeg)))
                    self.end_headers()
                    self.wfile.write(jpeg)
                except Exception as exc:
                    self.send_error(500, str(exc))
                return

            if self.path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                delay = 1.0 / max(1.0, detector.opt.stream_fps)
                while True:
                    try:
                        jpeg = detector.detect_jpeg()
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        time.sleep(delay)
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    except Exception as exc:
                        print(f"stream error: {exc}", flush=True)
                        time.sleep(0.2)
                return

            self.send_error(404)

    return Handler


def parse_args():
    p = argparse.ArgumentParser()
    # RGB model (same as the running detector)
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
    # thermal sensor (as wired: spidev5.0 / i2c-5)
    p.add_argument("--mock-thermal", action="store_true", help="use a synthetic thermal frame (no sensor)")
    p.add_argument("--spi-bus", type=int, default=1)           # /dev/spidev1.1 (SPI1)
    p.add_argument("--spi-device", type=int, default=1)        # CSN1 (unused with GPIO-CS)
    p.add_argument("--i2c-bus", type=int, default=5)
    p.add_argument("--i2c-address", type=lambda v: int(v, 0), default=0x40)
    p.add_argument("--reset-pin", type=int, default=16)        # RDK 40-pin BOARD 16
    p.add_argument("--data-ready-pin", type=int, default=13)   # RDK 40-pin BOARD 13
    p.add_argument("--cs-gpio-pin", type=int, default=7)       # SW chip-select: SS -> BOARD 7
    p.add_argument("--spi-xfer-size", type=int, default=10240)
    # Orientation: both cameras need 180deg to be upright; after that they are
    # horizontal mirrors of each other, so flip ONE extra (the thermal) to align.
    # RGB: 180deg rotation. Thermal: vertical flip only (= 180deg + horizontal flip).
    p.add_argument("--rgb-rotate", type=int, default=180, choices=[0, 90, 180, 270])
    p.add_argument("--thermal-flip-vertical", type=int, default=1)
    p.add_argument("--thermal-flip-horizontal", type=int, default=0)
    # fusion config
    p.add_argument("--calib", default="config/thermal_rgb_calib.yaml")
    p.add_argument("--hazard", default="config/thermal_hazard.yaml")
    # output
    p.add_argument("--evidence-dir", default="evidence")
    p.add_argument("--events-dir", default="events")
    p.add_argument("--evidence-cooldown", type=float, default=10.0)
    p.add_argument("--station-id", default=os.environ.get("STATION_ID", "desk-unknown"))
    p.add_argument("--stream-fps", type=float, default=2.0)
    p.add_argument("--jpeg-quality", type=int, default=80)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    return p.parse_args()


def main():
    opt = parse_args()
    for path in (opt.model_path, opt.label_file, opt.calib, opt.hazard):
        if not os.path.exists(path):
            raise FileNotFoundError(path)

    detector = FusionDetector(opt)

    def shutdown(_sig, _frame):
        detector.close()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    server = ThreadingHTTPServer((opt.host, opt.port), make_handler(detector))
    print(f"Open http://{opt.host}:{opt.port}/ from your browser", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
