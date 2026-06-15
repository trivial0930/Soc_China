#!/usr/bin/env python3
# Live MIPI camera detector for RDK X5.

import argparse
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
from hobot_vio import libsrcampy

from lab_ultralytics_yolo11 import YoloV11

sys.path.append("/app/pydev_demo")
import utils.common_utils as common
import utils.draw_utils as draw


class CameraReader:
    def __init__(self, fps, width, height):
        self.width = width
        self.height = height
        self.camera = libsrcampy.Camera()
        ret = self.camera.open_cam(0, -1, fps, [512, width], [512, height])
        if ret:
            raise RuntimeError("Failed to open MIPI camera")

    def read_bgr(self):
        raw = self.camera.get_img(2, self.width, self.height)
        if raw is None:
            raise RuntimeError("Failed to read MIPI camera frame")

        data = np.frombuffer(raw, dtype=np.uint8)
        expected = self.width * self.height * 3 // 2
        if data.size != expected:
            raise RuntimeError(
                f"Unexpected NV12 frame size: got {data.size}, expected {expected}"
            )

        nv12 = data.reshape((self.height * 3 // 2, self.width))
        return cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)

    def close(self):
        self.camera.close_cam()


class LiveDetector:
    def __init__(self, opt):
        self.opt = opt
        self.labels = common.load_class_names(opt.label_file)
        self.model = YoloV11(opt)
        self.model.set_scheduling_params(priority=opt.priority, bpu_cores=opt.bpu_cores)
        common.print_model_info(self.model.model)
        self.camera = CameraReader(opt.camera_fps, opt.camera_width, opt.camera_height)
        self.lock = threading.Lock()

    def close(self):
        self.camera.close()

    def detect_jpeg(self):
        started = time.time()
        with self.lock:
            frame = self.camera.read_bgr()
            h, w = frame.shape[:2]
            inputs = self.model.pre_process(frame)
            outputs = self.model.forward(inputs)
            boxes, cls_ids, scores = self.model.post_process(outputs, w, h)

        annotated = draw.draw_boxes(frame, boxes, cls_ids, scores, self.labels, common.rdk_colors)
        ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), self.opt.jpeg_quality])
        if not ok:
            raise RuntimeError("Failed to JPEG-encode annotated frame")

        elapsed = time.time() - started
        summary = ", ".join(
            f"{self.labels[int(cls_id)]}:{float(score):.2f}"
            for cls_id, score in zip(cls_ids, scores)
        )
        if not summary:
            summary = "none"
        print(f"frame {elapsed:.3f}s detections={len(scores)} {summary}", flush=True)
        return encoded.tobytes()


def make_handler(detector):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            print("%s - %s" % (self.address_string(), fmt % args), flush=True)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RDK X5 Lab Detector</title>
  <style>
    html, body {{ margin: 0; background: #101214; color: #f2f2f2; font-family: Arial, sans-serif; }}
    header {{ padding: 12px 16px; font-size: 18px; font-weight: 600; background: #1a1d20; }}
    img {{ display: block; width: 100vw; height: auto; }}
  </style>
</head>
<body>
  <header>RDK X5 Lab Detector - live MJPEG stream</header>
  <img src="/stream.mjpg" alt="live detection stream">
</body>
</html>
""".encode("utf-8")
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default="weights/lab_yolo11m_1024_bayese_nv12.bin")
    parser.add_argument("--label-file", default="config/lab_classes.names")
    parser.add_argument("--classes-num", type=int, default=74)
    parser.add_argument("--score-thres", type=float, default=0.15)
    parser.add_argument("--nms-thres", type=float, default=0.45)
    parser.add_argument("--priority", type=int, default=0)
    parser.add_argument("--bpu-cores", nargs="+", type=int, default=[0])
    parser.add_argument("--camera-fps", type=int, default=30)
    parser.add_argument("--camera-width", type=int, default=1920)
    parser.add_argument("--camera-height", type=int, default=1072)
    parser.add_argument("--stream-fps", type=float, default=2.0)
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


def main():
    opt = parse_args()
    if not os.path.exists(opt.model_path):
        raise FileNotFoundError(opt.model_path)
    if not os.path.exists(opt.label_file):
        raise FileNotFoundError(opt.label_file)

    detector = LiveDetector(opt)

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
