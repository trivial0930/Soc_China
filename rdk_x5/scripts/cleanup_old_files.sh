#!/bin/bash
# 板上记录/日志类文件 30 天保留,过期自动删(与 Mac 后端 RETENTION_DAYS=30 对齐)。
# 只删超过 30 天的普通文件;白名单目录;不碰模型/配置/标定。
# 用法: cleanup_old_files.sh [--dry-run]
#
# 白名单目录说明(板上核对 2026-06-24):
#   /root/.ros/log          — ROS2 节点日志(滚动累积,ls 确认存在)
#   /tmp                    — 运行时 *.log(asr/gimbal/cognition 等,ls 确认存在)
#   /root/inspection_log    — cognition_node 写 inspection.jsonl(默认相对路径→/root/,
#                             目录已建,JSONL 尚未积累超 30 天文件)
#   /root/inspection_reports — report_service 写 *_<ts>.md(同上)
#   /root/workstation_records — workstation_record_node 写 workstation_log.jsonl
#   /root/Soc_China/logs    — uart_test frames.jsonl(find 确认 104 个 jsonl,实际存在)
#
# 不纳入(绝不触碰):模型 /root/sherpa /root/l15、配置 /root/Soc_China/rdk_x5/ros2_ws、
#   标定 gimbal.yaml、源码 /root/Soc_China/{rdk_x5,shared,stm32,app}
set -u

DAYS=30
DRY="${1:-}"

DIRS=(
  /root/.ros/log               # ROS2 节点日志(滚动累积)
  /tmp                         # *.log 运行时临时日志
  /root/inspection_log         # cognition_node inspection.jsonl
  /root/inspection_reports     # report_service *.md
  /root/workstation_records    # workstation_record_node workstation_log.jsonl
  /root/Soc_China/logs         # uart_test frames.jsonl 及其他测试日志
)

PATTERNS=( "*.log" "*.jsonl" "*.md" )

for d in "${DIRS[@]}"; do
  [ -d "$d" ] || continue
  for pat in "${PATTERNS[@]}"; do
    if [ "$DRY" = "--dry-run" ]; then
      find "$d" -type f -name "$pat" -mtime +$DAYS -print
    else
      find "$d" -type f -name "$pat" -mtime +$DAYS -delete
    fi
  done
done

echo "cleanup done (days=$DAYS, dry=${DRY:-no})"
