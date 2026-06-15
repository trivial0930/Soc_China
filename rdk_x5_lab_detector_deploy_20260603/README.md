# RDK X5 Lab Detector Deployment Handoff

This package contains the verified YOLO11m lab-supplies detector artifacts prepared on macOS.

## Contents

- `weights/best.pt`: trained Ultralytics YOLO11m checkpoint.
- `weights/best.onnx`: static ONNX export, input shape `1x3x1024x1024`.
- `config/data.yaml`: original class mapping and dataset config.
- `config/lab_classes.names`: one class name per line, 74 classes.
- `results.csv`: full training metrics by epoch.
- `TRAINING_RESULT_SUMMARY_ZH.md`: training summary.
- `smoke_tests/`: local Mac smoke-test prediction images for `.pt` and `.onnx`.
- `calibration_images/`: put representative lab images here before RDK X5 INT8 conversion.

## Verified On Mac

- PyTorch/Ultralytics environment loads the trained model.
- Model reports 74 classes.
- ONNX export passes `onnx.checker.check_model`.
- PyTorch `.pt` inference runs on bundled validation mosaic.
- ONNX Runtime inference runs on bundled validation mosaic.

## RDK X5 Next Steps

1. Collect or copy 100-300 representative calibration images into `calibration_images/`.
2. Convert `weights/best.onnx` to an RDK X5 `.bin` model using the D-Robotics model conversion tools.
3. Use the RDK Model Zoo Ultralytics YOLO runtime path rather than the older YOLOv5 demo parser.
4. Test live camera FPS and accuracy on the RDK X5.

The model was trained at `imgsz=1024`. If live FPS is too low on RDK X5, train or export a smaller model/input variant later, such as YOLO11s at 640 or 768.
