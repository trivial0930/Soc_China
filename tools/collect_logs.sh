#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="logs/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

git rev-parse HEAD > "$OUT_DIR/commit.txt" 2>/dev/null || true
uname -a > "$OUT_DIR/uname.txt"

echo "[logs] collected basic logs into $OUT_DIR"
