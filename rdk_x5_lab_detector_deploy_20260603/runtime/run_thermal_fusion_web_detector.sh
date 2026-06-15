#!/usr/bin/env bash
# Phase 4 (path A) launcher: live RGB + thermal heat-source hazard web detector.
#
# Prereqs on the RDK:
#   1) Wire the Thermal-90 (spidev5.0 / i2c-5) and install Pysenxor.
#   2) Sync the thermal_detector package to the board and point THERMAL_DETECTOR_SRC
#      at it (it carries fusion code + config/*.yaml), e.g.:
#        scp -r rdk_x5/ros2_ws/src/thermal_detector root@RDK:/root/lab_detector_deploy/
#
# Test the web UI + fusion WITHOUT the sensor wired:  MOCK_THERMAL=1 ./run_thermal_fusion_web_detector.sh
set -euo pipefail

cd "$(dirname "$0")/.."

export THERMAL_DETECTOR_SRC="${THERMAL_DETECTOR_SRC:-/root/lab_detector_deploy/thermal_detector}"
# Pysenxor (senxor + bundled crcmod) must be importable for the thermal driver.
export PYSENXOR_SRC="${PYSENXOR_SRC:-/root/pysenxor-master}"
export PYTHONPATH="${THERMAL_DETECTOR_SRC}:${PYSENXOR_SRC}:${PYTHONPATH:-}"
CALIB="${CALIB:-$THERMAL_DETECTOR_SRC/config/thermal_rgb_calib.yaml}"
HAZARD="${HAZARD:-$THERMAL_DETECTOR_SRC/config/thermal_hazard.yaml}"

EXTRA=()
if [ "${MOCK_THERMAL:-0}" = "1" ]; then
  EXTRA+=(--mock-thermal)
fi
# RESET=BOARD 16, READY=BOARD 13 (as wired); override via env if rewired.
EXTRA+=(--reset-pin "${RESET_PIN:-16}")
EXTRA+=(--data-ready-pin "${DATA_READY_PIN:-13}")
# Orientation (both cameras mounted upside-down; thermal also mirrored vs RGB):
EXTRA+=(--rgb-rotate "${RGB_ROTATE:-180}")
EXTRA+=(--thermal-flip-vertical "${THERMAL_FLIP_V:-1}")
EXTRA+=(--thermal-flip-horizontal "${THERMAL_FLIP_H:-0}")

python3 runtime/lab_thermal_fusion_web_detector.py \
  --model-path weights/hazard_yolo11s_640_nv12.bin \
  --label-file config/hazard_classes.names \
  --classes-num 10 \
  --score-thres "${SCORE_THRES:-0.20}" \
  --nms-thres "${NMS_THRES:-0.45}" \
  --spi-bus "${SPI_BUS:-1}" \
  --spi-device "${SPI_DEVICE:-1}" \
  --i2c-bus "${I2C_BUS:-5}" \
  --i2c-address "${I2C_ADDRESS:-0x40}" \
  --cs-gpio-pin "${CS_GPIO_PIN:-7}" \
  --calib "${CALIB}" \
  --hazard "${HAZARD}" \
  --evidence-dir "${EVIDENCE_DIR:-evidence}" \
  --events-dir "${EVENTS_DIR:-events}" \
  --evidence-cooldown "${EVIDENCE_COOLDOWN:-10}" \
  --station-id "${STATION_ID:-desk-unknown}" \
  --camera-fps "${CAMERA_FPS:-30}" \
  --camera-width "${CAMERA_WIDTH:-1920}" \
  --camera-height "${CAMERA_HEIGHT:-1072}" \
  --stream-fps "${STREAM_FPS:-2}" \
  --jpeg-quality "${JPEG_QUALITY:-80}" \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8080}" \
  "${EXTRA[@]}"
