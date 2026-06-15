# YOLO 电子实验室用品检测模型训练结果

训练已完成：220/220 epoch

## 推荐模型

使用 `weights/best.pt`。该权重按 YOLO fitness 选择，主要参考 mAP50-95。

## 关键指标

| 项目 | Epoch | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| 最后一轮 | 220 | 0.85838 | 0.75875 | 0.81689 | 0.61518 |
| best.pt / best fitness | 204 | 0.80249 | 0.79290 | 0.81777 | 0.61534 |
| 最高 mAP50 | 212 | 0.85678 | 0.75925 | 0.81837 | 0.61427 |
| 最高 mAP50-95 | 204 | 0.80249 | 0.79290 | 0.81777 | 0.61534 |
| 最高 Precision | 131 | 0.86264 | 0.73175 | 0.81134 | 0.60717 |
| 最高 Recall | 198 | 0.79992 | 0.79305 | 0.81704 | 0.61452 |

## 远程原始目录

`/root/lab_supplies_public_yolo_expanded_all/runs/detect/runs/lab_supplies_public/yolo11m_1024_expanded_all_maxdet1200`
