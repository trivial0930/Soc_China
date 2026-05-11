#!/usr/bin/env bash
set -euo pipefail

CAMERA_HOST="${CAMERA_HOST:-}"
CAMERA_PORT="${CAMERA_PORT:-554}"
CAMERA_URL="${CAMERA_URL:-}"

if [[ -z "${CAMERA_HOST}" && -n "${CAMERA_URL}" ]]; then
  CAMERA_HOST="$(python3 -c 'from urllib.parse import urlparse; import os; print(urlparse(os.environ["CAMERA_URL"]).hostname or "")')"
  CAMERA_PORT="$(python3 -c 'from urllib.parse import urlparse; import os; parsed = urlparse(os.environ["CAMERA_URL"]); print(parsed.port or (554 if parsed.scheme == "rtsp" else 80))')"
fi

if [[ -z "${CAMERA_HOST}" ]]; then
  echo "Usage:" >&2
  echo "  CAMERA_HOST=192.168.1.64 CAMERA_PORT=554 ./rdk_x5/scripts/check_wifi_camera.sh" >&2
  echo "  CAMERA_URL=rtsp://USER:PASSWORD@192.168.1.64:554/stream1 ./rdk_x5/scripts/check_wifi_camera.sh" >&2
  exit 2
fi

export CAMERA_HOST
export CAMERA_PORT
export CAMERA_URL

echo "[wifi-camera] RDK network"
ip -brief addr || true

echo
echo "[wifi-camera] ping ${CAMERA_HOST}"
ping -c 3 -W 2 "${CAMERA_HOST}"

echo
echo "[wifi-camera] check TCP ${CAMERA_HOST}:${CAMERA_PORT}"
python3 - <<'PY'
import os
import socket
import sys

host = os.environ["CAMERA_HOST"]
port = int(os.environ["CAMERA_PORT"])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(3)
try:
    sock.connect((host, port))
finally:
    sock.close()

print(f"[wifi-camera] TCP {host}:{port} reachable")
PY

if [[ -z "${CAMERA_URL}" ]]; then
  echo
  echo "[wifi-camera] CAMERA_URL not set, skip video frame test"
  exit 0
fi

echo
echo "[wifi-camera] open video stream"
python3 - <<'PY'
import os
import sys

import cv2

url = os.environ["CAMERA_URL"]
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"

cap = cv2.VideoCapture(url)
try:
    if not cap.isOpened():
        raise RuntimeError("cv2.VideoCapture open failed")
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError("stream opened but no frame was decoded")
    height, width = frame.shape[:2]
    print(f"[wifi-camera] decoded one frame: {width}x{height}")
finally:
    cap.release()
PY
