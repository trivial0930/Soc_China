# 事件结构草案

用于 RDK 本地日志、巡检报告和后续管理端展示。

```json
{
  "event_id": "20260505-0001",
  "timestamp": "2026-05-05T20:30:00+08:00",
  "station_id": "desk-03",
  "source": "camera|thermal|stm32|manual|mock",
  "event_type": "thermal_risk|desk_messy|device_missing|estop|fault",
  "severity": "info|warning|critical",
  "confidence": 0.85,
  "summary": "3号工位桌面右侧疑似存在未断电电烙铁",
  "evidence": {
    "image_path": "",
    "log_path": "",
    "serial_output": ""
  },
  "action": {
    "robot_task": "",
    "voice_prompt": "",
    "reported_to_admin": false
  }
}
```
