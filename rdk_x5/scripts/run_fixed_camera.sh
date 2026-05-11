#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$(cd "${SCRIPT_DIR}/../ros2_ws" && pwd)"

SOURCE_TYPE="${SOURCE_TYPE:-opencv}"
SOURCE_URI="${SOURCE_URI:-/dev/video0}"
WIDTH="${WIDTH:-1280}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-15}"
USB_PIXEL_FORMAT="${USB_PIXEL_FORMAT:-mjpeg}"
MIPI_VIDEO_DEVICE="${MIPI_VIDEO_DEVICE:-}"

if [[ -f /opt/tros/humble/setup.bash ]]; then
  source /opt/tros/humble/setup.bash
elif [[ -f /opt/tros/setup.bash ]]; then
  source /opt/tros/setup.bash
else
  echo "[camera] Cannot find tros.b setup.bash under /opt/tros" >&2
  exit 1
fi

if [[ -f "${WS_DIR}/install/setup.bash" ]]; then
  source "${WS_DIR}/install/setup.bash"
else
  echo "[camera] Workspace is not built yet. Run:" >&2
  echo "  cd ${WS_DIR}" >&2
  echo "  colcon build --symlink-install --packages-select perception_camera" >&2
  exit 1
fi

echo "[camera] source_type=${SOURCE_TYPE}"
echo "[camera] source_uri=${SOURCE_URI}"
echo "[camera] size=${WIDTH}x${HEIGHT} fps=${FPS}"

ros2 launch perception_camera fixed_camera.launch.py \
  source_type:="${SOURCE_TYPE}" \
  source_uri:="${SOURCE_URI}" \
  width:="${WIDTH}" \
  height:="${HEIGHT}" \
  fps:="${FPS}" \
  usb_pixel_format:="${USB_PIXEL_FORMAT}" \
  mipi_video_device:="${MIPI_VIDEO_DEVICE}"
