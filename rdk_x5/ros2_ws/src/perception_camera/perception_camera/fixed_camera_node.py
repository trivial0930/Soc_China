import json
import os
import time
from pathlib import Path
from typing import List, Optional, Union

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class FixedCameraNode(Node):
    def __init__(self) -> None:
        super().__init__("fixed_camera_node")

        self.declare_parameter("source_uri", "/dev/video0")
        self.declare_parameter("frame_id", "fixed_monitor_cam")
        self.declare_parameter("image_topic", "/fixed_camera/image_raw")
        self.declare_parameter("camera_info_topic", "/fixed_camera/camera_info")
        self.declare_parameter("status_topic", "/fixed_camera/status")
        self.declare_parameter("width", 1280)
        self.declare_parameter("height", 720)
        self.declare_parameter("fps", 15.0)
        self.declare_parameter("reconnect_sec", 2.0)
        self.declare_parameter("rtsp_transport", "tcp")
        self.declare_parameter("open_timeout_ms", 5000)
        self.declare_parameter("read_timeout_ms", 5000)
        self.declare_parameter("loop_file", True)
        self.declare_parameter("publish_camera_info", True)
        self.declare_parameter("snapshot_dir", "")
        self.declare_parameter("snapshot_every_n_frames", 0)

        self.source_uri = str(self.get_parameter("source_uri").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.width = int(self.get_parameter("width").value)
        self.height = int(self.get_parameter("height").value)
        self.fps = max(float(self.get_parameter("fps").value), 0.1)
        self.reconnect_sec = max(float(self.get_parameter("reconnect_sec").value), 0.5)
        self.rtsp_transport = str(self.get_parameter("rtsp_transport").value)
        self.open_timeout_ms = int(self.get_parameter("open_timeout_ms").value)
        self.read_timeout_ms = int(self.get_parameter("read_timeout_ms").value)
        self.loop_file = bool(self.get_parameter("loop_file").value)
        self.publish_camera_info = bool(self.get_parameter("publish_camera_info").value)
        self.snapshot_dir = str(self.get_parameter("snapshot_dir").value)
        self.snapshot_every_n_frames = int(self.get_parameter("snapshot_every_n_frames").value)

        image_topic = str(self.get_parameter("image_topic").value)
        camera_info_topic = str(self.get_parameter("camera_info_topic").value)
        status_topic = str(self.get_parameter("status_topic").value)

        self.image_pub = self.create_publisher(Image, image_topic, 10)
        self.camera_info_pub = self.create_publisher(CameraInfo, camera_info_topic, 10)
        self.status_pub = self.create_publisher(String, status_topic, 10)

        self.cap: Optional[cv2.VideoCapture] = None
        self.image_files: List[Path] = []
        self.image_index = 0
        self.frame_count = 0
        self.last_open_attempt = 0.0
        self.last_status = ""

        if self.snapshot_dir:
            os.makedirs(self.snapshot_dir, exist_ok=True)

        self._prepare_source()
        self.timer = self.create_timer(1.0 / self.fps, self._tick)

    def _prepare_source(self) -> None:
        path = Path(self.source_uri)

        if path.is_dir():
            self.image_files = sorted(
                item for item in path.iterdir() if item.suffix.lower() in IMAGE_SUFFIXES
            )
            if not self.image_files:
                self.get_logger().error(f"No image files found in {self.source_uri}")
            else:
                self.get_logger().info(
                    f"Loaded {len(self.image_files)} image files from {self.source_uri}"
                )
            return

        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            self.image_files = [path]
            self.get_logger().info(f"Using single image source {self.source_uri}")
            return

        self._open_video_capture(force=True)

    def _open_video_capture(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self.last_open_attempt) < self.reconnect_sec:
            return

        self.last_open_attempt = now

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        source: Union[int, str] = self._opencv_source(self.source_uri)
        self._configure_capture_options()
        cap = cv2.VideoCapture(source)

        if self.open_timeout_ms > 0 and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, float(self.open_timeout_ms))
        if self.read_timeout_ms > 0 and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, float(self.read_timeout_ms))
        if self.width > 0:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
        if self.height > 0:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
        if self.fps > 0:
            cap.set(cv2.CAP_PROP_FPS, float(self.fps))

        if not cap.isOpened():
            self._publish_status(False, "open_failed")
            cap.release()
            return

        self.cap = cap
        self._publish_status(True, "opened")
        self.get_logger().info(f"Camera source opened: {self.source_uri}")

    def _opencv_source(self, source_uri: str) -> Union[int, str]:
        if source_uri.isdigit():
            return int(source_uri)
        return source_uri

    def _configure_capture_options(self) -> None:
        if not self.source_uri.lower().startswith("rtsp://"):
            return

        options = []
        if self.rtsp_transport:
            options.extend(["rtsp_transport", self.rtsp_transport])
        if self.open_timeout_ms > 0:
            options.extend(["stimeout", str(self.open_timeout_ms * 1000)])

        if not options:
            return

        pairs = []
        for index in range(0, len(options), 2):
            pairs.append(f"{options[index]};{options[index + 1]}")

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(pairs)

    def _tick(self) -> None:
        frame = self._read_frame()
        if frame is None:
            return

        if self.width > 0 and self.height > 0:
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

        stamp = self.get_clock().now().to_msg()
        image_msg = self._frame_to_image(frame)
        image_msg.header.stamp = stamp
        image_msg.header.frame_id = self.frame_id
        self.image_pub.publish(image_msg)

        if self.publish_camera_info:
            self.camera_info_pub.publish(self._camera_info(frame, stamp))

        self.frame_count += 1
        self._maybe_save_snapshot(frame)

        if self.frame_count == 1 or self.frame_count % int(max(self.fps, 1.0) * 5.0) == 0:
            self._publish_status(True, "streaming")

    def _read_frame(self):
        if self.image_files:
            return self._read_image_source()

        if self.cap is None or not self.cap.isOpened():
            self._open_video_capture()
            return None

        ok, frame = self.cap.read()
        if ok and frame is not None:
            return frame

        if self.loop_file:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
            if ok and frame is not None:
                return frame

        self._publish_status(False, "read_failed")
        self._open_video_capture()
        return None

    def _read_image_source(self):
        if not self.image_files:
            return None

        image_path = self.image_files[self.image_index]
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            self._publish_status(False, "image_read_failed")
            return None

        self.image_index += 1
        if self.image_index >= len(self.image_files):
            self.image_index = 0 if self.loop_file else len(self.image_files) - 1

        return frame

    def _frame_to_image(self, frame) -> Image:
        height, width, channels = frame.shape
        msg = Image()
        msg.height = int(height)
        msg.width = int(width)
        msg.encoding = "bgr8"
        msg.is_bigendian = 0
        msg.step = int(width * channels)
        msg.data = frame.tobytes()
        return msg

    def _camera_info(self, frame, stamp) -> CameraInfo:
        height, width = frame.shape[:2]
        msg = CameraInfo()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.height = int(height)
        msg.width = int(width)
        return msg

    def _maybe_save_snapshot(self, frame) -> None:
        if not self.snapshot_dir or self.snapshot_every_n_frames <= 0:
            return

        if self.frame_count % self.snapshot_every_n_frames != 0:
            return

        path = Path(self.snapshot_dir) / f"fixed_camera_{self.frame_count:06d}.jpg"
        cv2.imwrite(str(path), frame)

    def _publish_status(self, ok: bool, state: str) -> None:
        status = {
            "ok": ok,
            "state": state,
            "source_uri": self.source_uri,
            "frame_id": self.frame_id,
            "frame_count": self.frame_count,
        }
        payload = json.dumps(status, ensure_ascii=True)

        if payload == self.last_status and state != "streaming":
            return

        msg = String()
        msg.data = payload
        self.status_pub.publish(msg)
        self.last_status = payload


def main(args=None) -> None:
    rclpy.init(args=args)
    node = FixedCameraNode()

    try:
        rclpy.spin(node)
    finally:
        if node.cap is not None:
            node.cap.release()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
