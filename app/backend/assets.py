"""物资定位 (asset/material location) layer — built from scratch.

Two location shapes in one table (assets), distinguished by `category`:
  large  -> name maps to station_id + area     (e.g. 示波器 -> desk-03 / A区)
  small  -> name maps to cabinet + drawer + box (e.g. 0.25W电阻 -> 元件柜2/抽屉3/盒B)

Pure stdlib (csv). Query returns API_SPEC Asset dicts with a formatted location_text.
"""

from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional


def location_text(asset: Dict[str, Any]) -> str:
    """Human-readable location string for the app to display directly."""
    if asset.get("category") == "small":
        parts = [p for p in (asset.get("cabinet"), asset.get("drawer"), asset.get("box")) if p]
        return " / ".join(parts) if parts else "未登记"
    # large
    parts = []
    if asset.get("station_id"):
        parts.append(f"工位 {asset['station_id']}")
    if asset.get("area"):
        parts.append(asset["area"])
    return " / ".join(parts) if parts else "未登记"


def _shape(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "id": row.get("id"),
        "name": row.get("name", ""),
        "category": row.get("category", ""),
        "station_id": row.get("station_id", "") or "",
        "area": row.get("area", "") or "",
        "cabinet": row.get("cabinet", "") or "",
        "drawer": row.get("drawer", "") or "",
        "box": row.get("box", "") or "",
        "quantity": int(row.get("quantity") or 0),
        "note": row.get("note", "") or "",
        "updated_at": row.get("updated_at"),
    }
    out["location_text"] = location_text(out)
    return out


def load_assets_csv(path: str) -> List[Dict[str, Any]]:
    """Read the seed CSV. Columns: name,category,station_id,area,cabinet,drawer,box,quantity,note."""
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not (r.get("name") or "").strip():
                continue
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def seed_assets(store, rows: List[Dict[str, Any]]) -> int:
    """Upsert CSV rows into the assets table; returns count inserted."""
    n = 0
    for r in rows:
        store.upsert_asset(r)
        n += 1
    return n


def query_assets(store, *, name: Optional[str] = None, category: Optional[str] = None,
                 station: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    where, args = [], []
    if name:
        where.append("name LIKE ?")
        args.append(f"%{name}%")
    if category:
        where.append("category=?")
        args.append(category)
    if station:
        where.append("station_id=?")
        args.append(station)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = store.conn.execute(f"SELECT COUNT(*) c FROM assets{clause}", args).fetchone()["c"]
    rows = store.conn.execute(
        f"SELECT * FROM assets{clause} ORDER BY category, name LIMIT ? OFFSET ?",
        args + [int(limit), int(offset)],
    ).fetchall()
    return {"items": [_shape(dict(r)) for r in rows], "total": total,
            "limit": int(limit), "offset": int(offset)}
