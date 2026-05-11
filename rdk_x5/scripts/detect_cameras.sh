#!/usr/bin/env bash
set -euo pipefail

echo "[camera] video devices"
if compgen -G "/dev/video*" >/dev/null; then
  for dev in /dev/video*; do
    echo "  - ${dev}"
  done
else
  echo "  no /dev/video* devices found"
fi

if command -v v4l2-ctl >/dev/null 2>&1; then
  echo
  echo "[camera] v4l2 devices"
  v4l2-ctl --list-devices || true

  if compgen -G "/dev/video*" >/dev/null; then
    for dev in /dev/video*; do
      echo
      echo "[camera] formats for ${dev}"
      v4l2-ctl --device="${dev}" --list-formats-ext || true
    done
  fi
else
  echo
  echo "[camera] v4l2-ctl not found, install with: sudo apt install -y v4l-utils"
fi

echo
echo "[camera] network summary"
ip -brief addr || true
