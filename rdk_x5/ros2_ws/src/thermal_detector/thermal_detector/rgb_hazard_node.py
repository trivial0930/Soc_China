#!/usr/bin/env python3
"""ROS2 node: MIPI RGB camera + BPU YOLO11 -> hazard detections.

Publishes:
  /perception/hazard_detections (std_msgs/String, JSON)   -- detections (ros_payloads format)
  /perception/image_color       (sensor_msgs/Image, bgr8) -- optional, for evidence/viz

Reuses the BPU YOLO wrapper (lab_ultralytics_yolo11.YoloV11) and MIPI reader
(lab_mipi_web_detector.CameraReader) from the deploy runtime via `runtime_src`.

NOTE: the MIPI camera + BPU are single-owner -- run this OR the standalone
lab_thermal_fusion_web_detector.py, not both at once.
"""

import sys
import types

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .fusion import Detection
from .ros_payloads import encode_detections


class RgbHazardNode(Node):
    def __init__(self) -> None:
        super().__init__("rgb_hazard_node")
        p = self.declare_parameter
        p("runtime_src", "/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime")
        p("model_path", "/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/weights/hazard_yolo11s_640_nv12.bin")
        p("label_file", "/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/config/hazard_classes.names")
        p("classes_num", 10)
        p("score_thres", 0.20)
        p("nms_thres", 0.45)
        p("priority", 0)
        p("bpu_cores", [0])
        p("camera_fps", 30)
        p("camera_width", 1920)
        p("camera_height", 1072)
        p("publish_rate", 5.0)
        p("publish_color", True)
        p("detections_topic", "/perception/hazard_detections")
        p("color_topic", "/perception/image_color")
        p("frame_id", "mipi_rgb")
        gp = self.get_parameter

        sys.path.insert(0, str(gp("runtime_src").value))
        sys.path.append("/app/pydev_demo")
        from lab_mipi_web_detector import CameraReader  # noqa: E402
        from lab_ultralytics_yolo11 import YoloV11  # noqa: E402
        import utils.common_utils as common  # noqa: E402

        opt = types.SimpleNamespace(
            model_path=str(gp("model_path").value),
            score_thres=float(gp("score_thres").value),
            nms_thres=float(gp("nms_thres").value),
            classes_num=int(gp("classes_num").value),
        )
        self.model = YoloV11(opt)
        self.model.set_scheduling_params(
            priority=int(gp("priority").value),
            bpu_cores=[int(c) for c in gp("bpu_cores").value],
        )
        self.labels = common.load_class_names(str(gp("label_file").value))
        self.camera = CameraReader(
            int(gp("camera_fps").value), int(gp("camera_width").value), int(gp("camera_height").value)
        )
        self.publish_color = bool(gp("publish_color").value)
        self.frame_id = str(gp("frame_id").value)

        self.det_pub = self.create_publisher(String, str(gp("detections_topic").value), 10)
        self.color_pub = self.create_publisher(Image, str(gp("color_topic").value), 2)
        self.timer = self.create_timer(1.0 / max(1.0, float(gp("publish_rate").value)), self._tick)
        self.get_logger().info("rgb_hazard_node up")

    def _tick(self) -> None:
        try:
            frame = self.camera.read_bgr()
        except Exception as exc:
            self.get_logger().warn(f"camera read failed: {exc}")
            return
        h, w = frame.shape[:2]
        inputs = self.model.pre_process(frame)
        outputs = self.model.forward(inputs)
        boxes, cls_ids, scores = self.model.post_process(outputs, w, h)

        detections = []
        for box, cls_id, score in zip(boxes, cls_ids, scores):
            cid = int(cls_id)
            label = self.labels[cid] if cid < len(self.labels) else str(cid)
            detections.append(Detection(cid, label, float(score), tuple(float(v) for v in box)))

        now = self.get_clock().now()
        msg = String()
        msg.data = encode_detections(detections, now.nanoseconds * 1e-9)
        self.det_pub.publish(msg)

        if self.publish_color:
            img = Image()
            img.header.stamp = now.to_msg()
            img.header.frame_id = self.frame_id
            img.height, img.width = int(h), int(w)
            img.encoding = "bgr8"
            img.is_bigendian = 0
            img.step = int(w * 3)
            img.data = frame.tobytes()
            self.color_pub.publish(img)

    def destroy_node(self) -> None:
        try:
            self.camera.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RgbHazardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
