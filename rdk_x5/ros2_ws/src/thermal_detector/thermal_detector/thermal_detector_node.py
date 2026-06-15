#!/usr/bin/env python3
"""ROS2 node that owns the Waveshare Thermal-90 sensor and publishes frames.

Publishes:
  /thermal/temperature  (sensor_msgs/Image, encoding "32FC1", 80x62) -- per-pixel degC
  /thermal/image_color  (sensor_msgs/Image, encoding "bgr8")        -- pseudo-colour for viz

Defaults match the verified RDK X5 wiring (SPI1 spidev1.1, GPIO chip-select on
BOARD 7, I2C bus 5 @ 0x40). Set parameter mock_thermal:=true to run without the
sensor (synthetic frame).
"""

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from .senxor_driver import (
    THERMAL_HEIGHT,
    THERMAL_WIDTH,
    MockSenxorBackend,
    ThermalCamera,
    create_pysenxor_backend,
)


class ThermalDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("thermal_detector_node")
        p = self.declare_parameter
        p("mock_thermal", False)
        p("spi_bus", 1)
        p("spi_device", 1)
        p("i2c_bus", 5)
        p("i2c_address", 0x40)
        p("reset_pin", 16)
        p("data_ready_pin", 13)
        p("cs_gpio_pin", 7)
        p("fps", 10.0)
        p("publish_rate", 5.0)
        p("frame_id", "thermal_90")
        p("temperature_topic", "/thermal/temperature")
        p("color_topic", "/thermal/image_color")

        gp = self.get_parameter
        self.frame_id = str(gp("frame_id").value)

        if bool(gp("mock_thermal").value):
            backend = MockSenxorBackend()
            self.get_logger().warn("thermal: using MOCK backend (synthetic frame)")
        else:
            backend = create_pysenxor_backend(
                spi_bus=int(gp("spi_bus").value),
                spi_device=int(gp("spi_device").value),
                i2c_bus=int(gp("i2c_bus").value),
                i2c_address=int(gp("i2c_address").value),
                reset_pin=int(gp("reset_pin").value),
                data_ready_pin=int(gp("data_ready_pin").value),
                cs_gpio_pin=int(gp("cs_gpio_pin").value),
                fps=float(gp("fps").value),
                spi_xfer_size=10240,
            )
        self.cam = ThermalCamera(backend=backend)
        self.cam.init()

        self.temp_pub = self.create_publisher(Image, str(gp("temperature_topic").value), 5)
        self.color_pub = self.create_publisher(Image, str(gp("color_topic").value), 5)
        self.timer = self.create_timer(1.0 / max(1.0, float(gp("publish_rate").value)), self._tick)
        self.get_logger().info("thermal_detector_node up")

    def _clean(self, frame):
        arr = np.asarray(frame, dtype=np.float32)
        valid = arr > -40.0
        if valid.any() and not valid.all():
            arr[~valid] = float(np.median(arr[valid]))
        return cv2.medianBlur(arr, 3)

    def _tick(self) -> None:
        try:
            arr = self._clean(self.cam.read_frame())
        except Exception as exc:  # keep the node alive on a transient read error
            self.get_logger().warn(f"thermal read failed: {exc}")
            return
        stamp = self.get_clock().now().to_msg()

        temp = Image()
        temp.header.stamp = stamp
        temp.header.frame_id = self.frame_id
        temp.height, temp.width = arr.shape
        temp.encoding = "32FC1"
        temp.is_bigendian = 0
        temp.step = int(arr.shape[1] * 4)
        temp.data = arr.astype(np.float32).tobytes()
        self.temp_pub.publish(temp)

        lo, hi = float(np.percentile(arr, 2)), float(np.percentile(arr, 98))
        norm = np.clip((arr - lo) / (hi - lo + 1e-6), 0.0, 1.0)
        color = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
        img = Image()
        img.header.stamp = stamp
        img.header.frame_id = self.frame_id
        img.height, img.width = color.shape[:2]
        img.encoding = "bgr8"
        img.is_bigendian = 0
        img.step = int(color.shape[1] * 3)
        img.data = color.tobytes()
        self.color_pub.publish(img)

    def destroy_node(self) -> None:
        try:
            self.cam.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThermalDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
