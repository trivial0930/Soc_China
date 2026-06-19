"""Backend config — paths and env-overridable settings."""

from __future__ import annotations

import os

# app/ root (parent of backend/)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
SEED_DIR = os.path.join(DATA_DIR, "seed")
RUNTIME_DIR = os.path.join(DATA_DIR, "runtime")
WEB_DIR = os.path.join(APP_DIR, "web")
ASSETS_CSV = os.path.join(DATA_DIR, "assets", "assets_seed.csv")

DB_PATH = os.environ.get("APP_DB", os.path.join(RUNTIME_DIR, "app.db"))

# Image lookup order: runtime (uploaded by uplink) first, then seed (demo images).
IMAGE_DIRS = [os.path.join(RUNTIME_DIR, "evidence"), os.path.join(SEED_DIR, "evidence")]

HOST = os.environ.get("APP_HOST", "0.0.0.0")
PORT = int(os.environ.get("APP_PORT", "8000"))

# Bearer token required on write/ingest endpoints. Empty -> writes open (dev only).
INGEST_TOKEN = os.environ.get("APP_INGEST_TOKEN", "")

VERSION = "v1"


def ensure_dirs() -> None:
    for d in (RUNTIME_DIR, os.path.join(RUNTIME_DIR, "evidence")):
        os.makedirs(d, exist_ok=True)
