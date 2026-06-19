"""Post simulated hazard events to a running backend, for demoing live SSE/alerts
without the robot.

    python -m app.backend.sim_feed                 # every ~8s to localhost:8000
    python -m app.backend.sim_feed http://192.168.1.10:8000 5
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

SCENARIOS = [
    ("desk-03", "thermal_risk", "critical", 0.92, "检测到电烙铁,孤儿热点155℃,疑似未断电", "demo_solder.jpg"),
    ("desk-05", "desk_messy", "warning", 0.7, "桌面导线散落、仪器未归位", "demo_desk.jpg"),
    ("desk-01", "thermal_risk", "info", 0.6, "插排46℃,正常负载", ""),
    ("desk-08", "thermal_risk", "warning", 0.8, "热风枪温度偏高,注意散热", "demo_solder.jpg"),
    ("desk-02", "device_missing", "warning", 0.65, "万用表疑似不在登记位置", ""),
]


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    period = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    print(f"sim_feed -> {base} every {period}s (Ctrl-C to stop)")
    i = 0
    while True:
        st, et, sev, conf, summ, img = SCENARIOS[i % len(SCENARIOS)]
        now = datetime.now(timezone.utc).astimezone()
        eid = "sim-" + now.strftime("%H%M%S") + f"-{i:03d}"
        ev = {"event_id": eid, "timestamp": now.isoformat(timespec="seconds"), "station_id": st,
              "source": "thermal", "event_type": et, "severity": sev, "confidence": conf,
              "summary": summ, "image": img}
        try:
            post(base, "/api/ingest/event", ev)
            post(base, "/api/ingest/brief", {"event_id": eid,
                 "explanation": summ + "(端侧本地认知)", "confirmed_severity": sev,
                 "actions": ["voice", "log"], "escalate_to_cloud": sev == "critical"})
            print(f"  pushed {eid} [{sev}] {summ}")
        except Exception as e:
            print("  push failed:", e)
        i += 1
        time.sleep(period)


if __name__ == "__main__":
    main()
