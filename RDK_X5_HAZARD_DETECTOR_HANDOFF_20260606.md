# RDK X5 Hazard Detector Handoff - 2026-06-06

This note summarizes the current state so a new Codex conversation can continue without needing the whole previous thread.

## Goal

Build a first-layer lab hazard detector on RDK X5 using the CSI camera and a web MJPEG preview. The detector should recognize potentially dangerous electrical/electronic lab objects such as soldering irons, hot air guns, power strips, plugs, adapters, wires, wire bundles, and exposed wires.

## RDK Connection

- Board: RDK X5
- SSH IP: `192.168.128.10`
- User: `root`
- Password: `root`
- Web preview URL from Mac: `http://192.168.128.10:8080/`

## Current Deployed RDK Folder

On the RDK:

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
```

On the Mac:

```bash
/Users/sthefirst/Desktop/Soc_China/rdk_x5_lab_detector_deploy_20260603
```

## Current Hazard Model

Converted model export folder on Mac:

```bash
/Users/sthefirst/Desktop/Soc_China/hazard_yolo11s_640_rdk_export
```

Important files:

```bash
/Users/sthefirst/Desktop/Soc_China/hazard_yolo11s_640_rdk_export/hazard_yolo11s_640_nv12.bin
/Users/sthefirst/Desktop/Soc_China/hazard_yolo11s_640_rdk_export/classes.txt
/Users/sthefirst/Desktop/Soc_China/hazard_yolo11s_640_rdk_export/model_info.txt
/Users/sthefirst/Desktop/Soc_China/hazard_yolo11s_640_rdk_export/conversion_notes.md
```

Deployed copies on RDK:

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/weights/hazard_yolo11s_640_nv12.bin
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/config/hazard_classes.names
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime/run_hazard_mipi_web_detector.sh
```

SHA-256 of deployed model:

```text
26ee5251048c43ae4741e0e5811531039bca640193cf2f6eb268323f0ef38e09
```

## Model Metadata

- Model name: `best_bayese_640x640_nv12`
- Runtime input: `NV12`
- Input size: `640x640`
- Class count: `10`
- RDK march: `bayes-e`
- Output format: six raw YOLO heads, class/box pairs:
  - `output0`: `[1,80,80,10]`
  - `478`: `[1,80,80,64]`
  - `492`: `[1,40,40,10]`
  - `500`: `[1,40,40,64]`
  - `514`: `[1,20,20,10]`
  - `522`: `[1,20,20,64]`

The existing runtime decoder can use this model as long as `--classes-num 10` is passed.

## Classes

```text
soldering_iron
soldering_station
hot_air_gun
welding_gun
power_strip
plug
power_adapter
wire
wire_bundle
exposed_wire
```

## Current Runtime

Main live web detector:

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime/lab_mipi_web_detector.py
```

Decoder:

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime/lab_ultralytics_yolo11.py
```

Hazard launcher:

```bash
/root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603/runtime/run_hazard_mipi_web_detector.sh
```

Launcher content:

```bash
python3 runtime/lab_mipi_web_detector.py \
  --model-path weights/hazard_yolo11s_640_nv12.bin \
  --label-file config/hazard_classes.names \
  --classes-num 10 \
  --score-thres "${SCORE_THRES:-0.20}" \
  --nms-thres "${NMS_THRES:-0.45}" \
  --camera-fps "${CAMERA_FPS:-30}" \
  --camera-width "${CAMERA_WIDTH:-1920}" \
  --camera-height "${CAMERA_HEIGHT:-1072}" \
  --stream-fps "${STREAM_FPS:-2}" \
  --jpeg-quality "${JPEG_QUALITY:-80}" \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8080}"
```

## Verified Working

The model was verified on the RDK with:

```bash
hrt_model_exec model_info --model_file weights/hazard_yolo11s_640_nv12.bin
```

The live web page responds at:

```text
http://192.168.128.10:8080/
```

The MJPEG stream was tested at:

```text
http://192.168.128.10:8080/stream.mjpg
```

Recent log showed live detections, for example:

```text
frame 0.239s detections=1 soldering_station:0.35
frame 0.157s detections=1 wire_bundle:0.62
frame 0.148s detections=0 none
frame 0.156s detections=2 wire_bundle:0.24, wire_bundle:0.20
frame 0.146s detections=1 soldering_station:0.21
```

## Useful Commands

Stop detector on RDK:

```bash
pkill -f '[l]ab_mipi_web_detector.py'
```

Start detector on RDK:

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
runtime/run_hazard_mipi_web_detector.sh
```

Start with lower threshold:

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
SCORE_THRES=0.12 runtime/run_hazard_mipi_web_detector.sh
```

Start in background and log:

```bash
cd /root/lab_detector_deploy/rdk_x5_lab_detector_deploy_20260603
nohup runtime/run_hazard_mipi_web_detector.sh >/tmp/hazard_mipi_web_detector.log 2>&1 &
```

Watch log:

```bash
tail -f /tmp/hazard_mipi_web_detector.log
```

## Recommended Next Step

Modify the live web detector into a first-layer hazard detector:

- Keep drawing bounding boxes.
- Add hazard severity mapping:
  - High risk: `soldering_iron`, `hot_air_gun`, `welding_gun`, `exposed_wire`
  - Medium risk: `power_strip`, `plug`, `power_adapter`
  - Context/risk objects: `wire`, `wire_bundle`, `soldering_station`
- Show a visible web banner such as:
  - `HIGH RISK: soldering_iron detected`
  - `MEDIUM RISK: power_strip detected`
- Save evidence frames when high-risk or medium-risk objects are detected.
- Use saved real lab frames as future validation data.

Suggested prompt for the new conversation:

```text
Continue this RDK X5 lab hazard detector project using the handoff file:
/Users/sthefirst/Desktop/Soc_China/RDK_X5_HAZARD_DETECTOR_HANDOFF_20260606.md

The current live detector already runs at http://192.168.128.10:8080/ using a converted YOLO11s 640x640 NV12 model. Please modify the runtime so it becomes a first-layer hazard detector: add severity mapping, show a web risk banner, color boxes by risk level, and save evidence frames when medium/high-risk objects are detected. Keep the current model and do not retrain.
```
