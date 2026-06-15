#!/usr/bin/env python3
"""Smoke-test the L2 local VLM (Qwen3-VL via Ollama) through LocalVLMBackend.

RDK-independent: run on the Mac (or the Win box) once Ollama is serving the model.
Feeds a sample hazard event (+ optional image) to the real backend and prints the
parsed cognition result, proving the prompt -> Qwen -> JSON-parse path works.

  ollama serve &                 # in another terminal
  ollama pull qwen3-vl:8b        # or qwen2.5vl:7b
  pip install openai
  python3 rdk_x5/scripts/qwen_local_smoke.py --image some.jpg

If the model tag isn't available, pass --model qwen2.5vl:7b.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "inspection_manager"
sys.path.insert(0, str(_PKG))

from inspection_manager.cognition import CognitionRequest, LocalVLMBackend  # noqa: E402
from inspection_manager.events import HazardEvent  # noqa: E402
from inspection_manager.qwen_client import ollama_vlm_client  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="qwen3-vl:8b")
    p.add_argument("--base-url", default="http://localhost:11434/v1")
    p.add_argument("--image", default="", help="optional evidence image path")
    p.add_argument("--severity", default="critical")
    p.add_argument("--station", default="desk-03")
    p.add_argument("--summary", default="CRITICAL: soldering_iron (active 145C)")
    return p.parse_args()


def main() -> None:
    opt = parse_args()
    client = ollama_vlm_client(model=opt.model, base_url=opt.base_url)
    backend = LocalVLMBackend(client=client)
    event = HazardEvent(
        event_id="smoke-1", timestamp="2026-06-15T20:30:00+08:00", station_id=opt.station,
        source="thermal", event_type="thermal_risk", severity=opt.severity,
        confidence=0.9, summary=opt.summary,
    )
    request = CognitionRequest(
        event=event, station_context="电子实验室巡检，课中", image_path=opt.image
    )
    print(f"[smoke] model={opt.model} base_url={opt.base_url} image={opt.image or '(none)'}")
    result = backend.assess(request)
    print("\n=== Qwen 本地认知结果 ===")
    print(f"  说明        : {result.explanation}")
    print(f"  确认严重度  : {result.confirmed_severity}")
    print(f"  建议动作    : {result.suggested_actions}")
    print(f"  上云        : {result.escalate_to_cloud}")
    print(f"  置信度      : {result.confidence}")


if __name__ == "__main__":
    main()
