# Expanded All YOLO Dataset for Electronic Lab Supplies

This package merges the previous public electronic-lab dataset with the five additional datasets requested by the user.

## Included Sources

| source | version | license shown by source | contribution |
| --- | --- | --- | --- |
| LibreYOLO/printed-circuit-board | current HF snapshot | CC BY 4.0 | dense PCB components |
| LibreYOLO/circuit-elements | current HF snapshot | CC BY 4.0 | additional dense PCB components |
| smerkd/labos-segmentation | current GitHub snapshot | MIT | lab object boxes converted from COCO to YOLO |
| ElectroCom61 | v2 | CC BY 4.0 | electronics components and modules |
| fauzan/yolo-lab-ugfjs | Roboflow v3 | Public Domain | Arduino, Raspberry Pi, multimeter, oscilloscope, function generator |
| myspace-natcf/dsec-object-detection | Roboflow v1 | CC BY 4.0 | breadboard, function generator, oscilloscope, trainer, component box |
| universiti-malaysia-pahang-qcvas/objectdetection-ngxjp | Roboflow v5 | Public Domain | DC power supply, digital trainer, function generator, multimeter, oscilloscope |
| dkphy/phy-og | Roboflow v1 | Private | physics/electronics lab instruments |

Note: `dkphy/phy-og` was publicly reachable through Roboflow Universe after login, but its exported metadata reports `license: Private`. Keep that in mind before redistribution.

## Dataset Size

| split | images | boxes |
| --- | ---: | ---: |
| train | 8468 | 314100 |
| val | 1194 | 45706 |
| test | 605 | 20099 |

Total: 10267 images and 374005 boxes.

## Classes

This dataset has 74 merged classes. Important new instrument classes include:

```text
function_generator, multimeter, oscilloscope, power_supply, digital_trainer,
lab_breadboard_trainer, power_strip, component_box, raspberry_pi, bnc_cable,
probe, wire, transformer_device, variable_transformer, ammeter, voltmeter,
stopwatch, resistance_box, capacitor_box, bulb_socket, bulb,
electronic_balance, electroscope, experiment_apparatus, timer, galvanometer,
lamp, calorimeter, magnet, amplifier, polarizer, rheostat, screwdriver,
solenoid, tesla_coil, teslameter, electronics_kit, vacuum_pump
```

The original PCB and electronics classes are preserved:

```text
battery, button, buzzer, capacitor, clock, connector, diode, display,
ferrite_bead, fuse, heatsink, ic_chip, inductor, jumper, led, pad, pin,
potentiometer, resistor, switch, test_point, transformer, transistor,
unknown_component, vortex_mixer, centrifuge_tube, tube_cap, tube_rack,
arduino_board, breadboard, sensor_module, electronic_module, motor,
relay_module, ic_socket, keypad
```

## Training

Use the scripts included in this directory. A V100S starting command:

```bash
python train_yolo_lab_supplies.py \
  --model yolo11m.pt \
  --epochs 220 \
  --imgsz 1024 \
  --batch 6 \
  --device 0 \
  --workers 8 \
  --patience 70 \
  --name yolo11m_1024_expanded_all_maxdet1200 \
  --optimizer AdamW \
  --lr0 0.0012 \
  --lrf 0.01 \
  --weight-decay 0.0005 \
  --warmup-epochs 5 \
  --close-mosaic 40 \
  --mosaic 0.7 \
  --mixup 0.05 \
  --copy-paste 0.05 \
  --translate 0.1 \
  --scale 0.4 \
  --extra max_det=1200 \
  --extra save_period=20
```

Keep `max_det=1200`; dense PCB images contain many small objects, and the default YOLO validation cap can suppress recall.
