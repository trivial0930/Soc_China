from __future__ import annotations

import argparse

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export trained YOLO weights.")
    parser.add_argument("--weights", default="runs/lab_supplies_public/yolo11s_640/weights/best.pt")
    parser.add_argument("--format", default="onnx", choices=["onnx", "engine", "torchscript", "openvino", "coreml"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--half", action="store_true", help="Use FP16 export when supported.")
    parser.add_argument("--dynamic", action="store_true", help="Enable dynamic axes for ONNX when supported.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = YOLO(args.weights)
    model.export(
        format=args.format,
        imgsz=args.imgsz,
        device=args.device,
        half=args.half,
        dynamic=args.dynamic,
    )


if __name__ == "__main__":
    main()
