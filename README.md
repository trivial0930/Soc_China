# RDK X5-Based Mobile Intelligent Steward for Electronics Labs with Cloud–Edge–Device Tiered AI Collaboration

[中文](README_cn.md) | **English**

A mobile intelligent inspection robot system for coordinated "people–equipment–environment" management in university electronics laboratories. Entry for the National College Student Embedded Chip and System Design Competition, Chip Application Track (D-Robotics theme).

## Overview

University electronics labs are dense with equipment and wiring: soldering irons, hot-air guns, and power strips carry risks of localized overheating and being left powered on. Manual inspection is constrained by experience, time, and workload, while equipment lookup, workstation records, and after-class inspection are typically disconnected from each other.

This project builds a mobile intelligent lab steward around the D-Robotics **RDK X5** (8× Cortex-A55 + 10 TOPS BPU). Without replacing the instructor's final judgment, it organizes **safety patrol, mobile perception, teaching assistance, and process archiving** into a traceable task loop:

- **Safety loop**: scheduled plans, preset workstation routes, or App tasks drive the robot to autonomously reach target positions. A two-axis gimbal performs close-range RGB–thermal capture and risk grading, alerts via voice, laser pointer, and App; after remediation the robot re-checks and archives the event.
- **Teaching loop**: records workstation state before class, supports equipment/consumable location queries during class (App / voice / laser pointing), and checks tool return, scattered wires, flammable leftovers, and power state against per-workstation templates after class.

## System Composition

| Part | Solution |
| --- | --- |
| Edge computer | RDK X5 8GB — BPU vision inference, navigation, voice, task and event management |
| Motion controller | STM32F411CEU6 — 50 Hz four-wheel independent PID, encoder capture, command/heartbeat timeout stop, USB CDC link |
| Chassis | 2× TB6612FNG + 4× 520 geared motors with encoders + mecanum wheels (omnidirectional), custom breakout PCB |
| Environment sensing | LSLIDAR N10 2D lidar; BMI088 IMU (gyro yaw fused with wheel odometry via EKF; accelerometer failure auto-degrades to gyro-only) |
| Vision / thermal | MIPI RGB camera (120° FOV) + Waveshare Thermal-90 thermal module, co-mounted on a two-axis FOC gimbal (2804 BLDC + AS5600 + SimpleFOC) |
| Voice interaction | Noise-canceling microphone + USB speaker; fully offline KWS wake word / VAD / SenseVoice ASR / TTS |
| Onboard network | GL.iNet MT300N-V2 travel router fixed on the robot: wired to the RDK, bridging site Wi-Fi/hotspot for App access and data uplink |
| Management side | FastAPI + SQLite + SSE backend, Flutter mobile App (plus a PWA sharing the same API contract) |

Software runs on Ubuntu 22.04 + ROS 2 Humble / TogetheROS.Bot; mapping with slam_toolbox, localization and navigation with AMCL + Nav2 (MPPI omnidirectional controller).

## Key Innovations

1. **Object-level RGB–thermal fusion**: YOLO11s on the BPU detects 10 hazardous object classes; RGB bounding boxes are spatially associated with the Thermal-90 temperature matrix via mirror/rotation/3×3 affine calibration, grading risk from "object class + hotspot position + temperature + duration" — upgrading "found a hot spot" to "identified a hazardous object". Significant hotspots that match no known object are reported as "unidentified heat source" for human review, preventing missed alarms.
2. **Complexity-driven four-tier cloud–edge–device cognition**: L1 on-device BPU real-time detection → L1.5 on-device lightweight semantic re-check → L2 LAN multimodal understanding (Qwen2.5-VL) → L3 cloud analysis on demand. Normal data is filtered locally; only complex events escalate, uploading a cropped, de-identified minimal evidence package. Any tier timing out or going offline falls back to local rule templates; large models only return structured suggestions and can never drive the chassis or close events.
3. **Multi-level safety and self-recovery chain across App → RDK → STM32**: the App sends zero velocity on release/page-leave; the RDK bridge zeroes the target after 0.5 s without commands; the STM32 stops on 0.5 s command / 2 s heartbeat timeouts; an independent hardware watchdog (IWDG, ~250 ms) force-resets and shuts off PWM if the firmware hangs. Reset causes and HardFault context are written to .noinit memory for forensics on next boot; after a USB CDC drop the bridge auto-reconnects, resends the mode, and re-anchors odometry — "guarantee stopping first, then pursue intelligence".
4. **Traceable event loop keyed by event_id**: a discover–verify–handle–recheck–archive state machine, separated from the robot task state machine. During network outages critical alerts enter an unlimited-retry queue and are idempotently re-uploaded by event_id after recovery — zero loss, no duplicates. Voice, App, and autonomous patrol entry points reuse one CommandExecutor for consistent behavior.

## Field-Verified Performance (repeated real-lab validation)

| Metric | Result |
| --- | --- |
| BPU hazard detection | YOLO11s @ 640 input, ~3–4 FPS; independent validation mAP50 = 0.5183 (primary YOLO11m model mAP50 = 0.8178) |
| RGB–thermal calibration | ~10 px reprojection error in the central region |
| Voice real-time factor | KWS RTF ≈ 0.19, ASR RTF ≈ 0.3, TTS short-command response ~0.5 s (resident model) |
| L2 edge understanding | Qwen2.5-VL 7B warm call ~1.4 s |
| Mapping | ~17.4 m × 10.3 m lab, loop-closure residual ~27 cm |
| Autonomous navigation | AMCL + Nav2 goal reached SUCCEEDED, repeatedly verified |
| Offline retransmission | 45 s network-outage fault injection: 0 critical events dropped, full re-upload on recovery |
| Link self-healing | odometry recovers ~2–3 s after forced USB CDC re-enumeration, no pose jump |
| Regression tests | 426 tests all passing (backend API / safety gating / voice intent / patrol pipeline / mapping mode / retransmission) |

## Repository Layout

```text
app/        Management backend (FastAPI/SQLite/SSE), Flutter mobile App, demo PWA
docs/       Architecture design, hardware wiring, operation manuals, protocols
rdk_x5/     RDK X5-side ROS 2 workspace (perception/decision/voice/navigation), scripts, maps
stm32/      STM32 firmware (mecanum drive, encoders, velocity PID, USB CDC, IWDG watchdog)
shared/     Protocols and event schemas shared between RDK and STM32
sim/        STM32 simulator and sample data for hardware-free development
tests/      Host-side unit tests
tools/      Setup, testing, and log-collection scripts
```

Model training and deployment artifacts: `yolo_lab_training_export_20260603/` (YOLO training scripts and configs), `rdk_x5_lab_detector_deploy_20260603/` (RDK-side detector runtime).

## Quick Start

- Backend + App: see `app/README.md` and `app/API_SPEC.md`.
- RDK-side ROS 2 workspace: see `rdk_x5/README.md`.
- STM32 firmware: see `stm32/README.md`.
- Mapping and navigation operations: see `docs/ops/lab_mapping_procedure.md`, `docs/ops/lab_nav_procedure.md`.

Run tests:

```bash
python -m pytest tests/
```

## Safety and Scope Statement

- The system is positioned as an **assistant** for lab managers; high-risk conclusions require human confirmation. It does not replace professional electrical inspection or safety accountability.
- Large models only output structured suggestions and have no authority to control the chassis or close events.
- Deployments must set the `APP_INGEST_TOKEN` write-auth token and stay within a controlled LAN; no ports are exposed to the public internet.
- Any real-machine test involving motors, the main battery, or chassis motion must be supervised on site.
