# RDK X5 Lab Detector Next Steps

## Current Verified State

- The RDK X5 is reachable at `192.168.128.10`.
- The deployment folder is copied to:
  `/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603`
- `weights/best.pt` and `weights/best.onnx` checksums match the Mac copies.
- The stock RDK YOLO11 sample runs successfully with:
  `/app/pydev_demo/02_detection_sample/02_ultralytics_yolo11/yolo11n_detect_bayese_640x640_nv12.bin`

## Important Model Format Finding

The Mac-exported `weights/best.onnx` is a standard Ultralytics graph:

```text
input:  images  [1, 3, 1024, 1024]
output: output0 [1, 78, 21504]
```

The RDK YOLO11 Python post-process sample expects a compiled `.bin` with six raw YOLO11 head outputs:

```text
[1, H, W, classes]
[1, H, W, 64]
```

for strides 8, 16, and 32.

For this 74-class model at 1024 input, the expected compiled output shapes should be:

```text
[1, 128, 128, 74]
[1, 128, 128, 64]
[1, 64, 64, 74]
[1, 64, 64, 64]
[1, 32, 32, 74]
[1, 32, 32, 64]
```

So the current `best.onnx` still needs the official D-Robotics Ultralytics YOLO export/mapper path before it can run on BPU.

## Files Prepared

- `runtime/lab_ultralytics_yolo11.py`: RDK-side image inference script prepared for the future lab `.bin`.
- `config/lab_classes.names`: 74-class label file.
- `weights/best.pt`: trained PyTorch model.
- `weights/best.onnx`: standard ONNX export, useful for reference/testing but not directly runnable on BPU.
- `calibration_images/`: add 100-300 representative lab images before INT8/BPU conversion.

## Future RDK Run Command

After conversion produces `weights/lab_yolo11m_1024_bayese_nv12.bin`:

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
python3 runtime/lab_ultralytics_yolo11.py \
  --model-path weights/lab_yolo11m_1024_bayese_nv12.bin \
  --test-img smoke_tests/smoke_predict_onnx/val_batch0_labels.jpg \
  --label-file config/lab_classes.names \
  --img-save-path lab_result.jpg \
  --classes-num 74 \
  --score-thres 0.25 \
  --nms-thres 0.45
```

## Remaining Blocker

This RDK image has `hbm_runtime` and `hrt_model_exec`, but it does not have the conversion tools such as `hb_mapper`, Ultralytics, Torch, ONNX, or ONNX Runtime. Use the D-Robotics OpenExplore/model-conversion environment on x86 Linux, then copy the generated `.bin` back to this folder.
