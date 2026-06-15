# YOLO 训练操作说明：expanded_all 版本

这个版本已经加入 1-5：DSEC、yolo-lab、UMP objectdetection、PHY-OG、ElectroCom61，并保留原来的 PCB/LabOS 数据。

## 数据规模

| split | images | boxes |
| --- | ---: | ---: |
| train | 8468 | 314100 |
| val | 1194 | 45706 |
| test | 605 | 20099 |

类别数：74。

## 服务器解压

```bash
unzip lab_supplies_public_yolo_expanded_all.zip
cd lab_supplies_public_yolo_expanded_all
python check_dataset.py --root .
```

## V100S 推荐训练命令

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

如果显存不够，把 `batch` 改成 4；如果还不够，把 `model` 改成 `yolo11s.pt`。

## 后台训练

```bash
tmux new -s yolo_lab_all
source /root/yolo_lab_venv/bin/activate
cd /root/lab_supplies_public_yolo_expanded_all
# 粘贴上面的训练命令
```

按 `Ctrl-b` 再按 `d` 可以退出但不停止训练。

重新进入：

```bash
tmux attach -t yolo_lab_all
```

## 监控

```bash
nvidia-smi
tail -f runs/lab_supplies_public/yolo11m_1024_expanded_all_maxdet1200/results.csv
```

重点看 `precision`、`recall`、`mAP50`、`mAP50-95`。

## 验证

```bash
python validate_yolo_lab_supplies.py \
  --weights runs/lab_supplies_public/yolo11m_1024_expanded_all_maxdet1200/weights/best.pt \
  --split val \
  --imgsz 1024 \
  --device 0 \
  --extra max_det=1200
```

## 来源注意

PHY-OG 在 Roboflow Universe 登录后可下载，但导出的 metadata 写的是 `license: Private`。如果后续要公开发布压缩包或论文附录，需要单独确认授权。
