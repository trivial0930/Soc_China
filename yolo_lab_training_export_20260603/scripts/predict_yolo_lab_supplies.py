from __future__ import annotations

import argparse

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO inference on images or videos.")
    parser.add_argument("--weights", default="runs/lab_supplies_public/yolo11s_640/weights/best.pt")
    parser.add_argument("--source", default="test_images", help="Image/video path, folder, webcam id, or stream URL.")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="runs/lab_supplies_public_predict")
    parser.add_argument("--name", default="predict")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = YOLO(args.weights)
    model.predict(
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=args.device,
        project=args.project,
        name=args.name,
        save=True,
        save_txt=True,
        save_conf=True,
    )


if __name__ == "__main__":
    main()
