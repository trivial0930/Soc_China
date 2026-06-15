#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 runtime/lab_mipi_web_detector.py \
  --model-path weights/hazard_yolo11s_640_nv12.bin \
  --label-file config/hazard_classes.names \
  --classes-num 10 \
  --score-thres "${SCORE_THRES:-0.20}" \
  --nms-thres "${NMS_THRES:-0.45}" \
  --camera-fps "${CAMERA_FPS:-30}" \
  --camera-width "${CAMERA_WIDTH:-1920}" \
  --camera-height "${CAMERA_HEIGHT:-1072}" \
  --stream-fps "${STREAM_FPS:-2}" \
  --jpeg-quality "${JPEG_QUALITY:-80}" \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8080}"
