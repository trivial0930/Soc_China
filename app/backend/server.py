"""FastAPI app — thin HTTP/SSE adapter over the pure store/ingest/assets/push layers.

Implements app/API_SPEC.md v1. Run:
    uvicorn app.backend.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.backend import assets as assets_mod
from app.backend import config, images, ingest
from app.backend import push as push_mod
from app.backend import store as store_mod

config.ensure_dirs()
STORE = store_mod.Store(config.DB_PATH)
BROKER = push_mod.Broker()

app = FastAPI(title="Lab Inspection Management API", version=config.VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- auth (writes)
def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not config.INGEST_TOKEN:
        return  # writes open in dev
    if authorization != f"Bearer {config.INGEST_TOKEN}":
        raise HTTPException(status_code=401, detail="missing or invalid token")


def _qbool(v: Optional[str]) -> Optional[bool]:
    if v is None:
        return None
    return v.lower() in ("1", "true", "yes")


# ------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    return {"status": "ok", "version": config.VERSION, "time": store_mod.now_iso()}


# ------------------------------------------------------------------- events
@app.get("/api/events")
def list_events(station: Optional[str] = None, severity: Optional[str] = None,
                type: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None,
                handled: Optional[str] = None, limit: int = 50, offset: int = 0):
    return STORE.list_events(station=station, severity=severity, type=type, since=since,
                             until=until, handled=_qbool(handled), limit=limit, offset=offset)


@app.get("/api/events/{event_id}")
def get_event(event_id: str):
    e = STORE.get_event(event_id)
    if not e:
        raise HTTPException(404, "event not found")
    return e


@app.post("/api/events/{event_id}/handle")
async def handle_event(event_id: str, body: dict, _=Depends(require_token)):
    e = STORE.handle_event(event_id, str(body.get("note", "")))
    if not e:
        raise HTTPException(404, "event not found")
    BROKER.publish("handled", {"type": "handled", "payload": {
        "event_id": event_id, "handled": True, "handled_at": e["handled_at"],
        "handled_note": e["handled_note"]}})
    return e


# ---------------------------------------------------- records / acceptance / station
@app.get("/api/records")
def list_records(station: Optional[str] = None, since: Optional[str] = None,
                 until: Optional[str] = None, limit: int = 50, offset: int = 0):
    return STORE.list_records(station=station, since=since, until=until, limit=limit, offset=offset)


@app.get("/api/acceptance")
def list_acceptance(station: Optional[str] = None, verdict: Optional[str] = None,
                    since: Optional[str] = None, limit: int = 50, offset: int = 0):
    return STORE.list_acceptance(station=station, verdict=verdict, since=since, limit=limit, offset=offset)


@app.get("/api/stations/{station_id}")
def station_summary(station_id: str):
    return STORE.station_summary(station_id)


# ------------------------------------------------------------------- reports
@app.get("/api/reports")
def list_reports(type: Optional[str] = None, verdict: Optional[str] = None,
                 limit: int = 50, offset: int = 0):
    return STORE.list_reports(type=type, verdict=verdict, limit=limit, offset=offset)


@app.get("/api/reports/{report_id}")
def get_report(report_id: int):
    r = STORE.get_report(report_id)
    if not r:
        raise HTTPException(404, "report not found")
    return r


# -------------------------------------------------------------------- assets
@app.get("/api/assets")
def list_assets(name: Optional[str] = None, category: Optional[str] = None,
                station: Optional[str] = None, limit: int = 50, offset: int = 0):
    return assets_mod.query_assets(STORE, name=name, category=category, station=station,
                                   limit=limit, offset=offset)


@app.post("/api/assets")
def create_asset(body: dict, _=Depends(require_token)):
    aid = STORE.upsert_asset({k: v for k, v in body.items() if k != "id"})
    return assets_mod.query_assets(STORE, name=body.get("name"))["items"][0] if aid else {}


@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, body: dict, _=Depends(require_token)):
    body = dict(body)
    body["id"] = asset_id
    STORE.upsert_asset(body)
    return JSONResponse({"id": asset_id, "updated": True})


# --------------------------------------------------------------------- images
@app.get("/img/{filename}")
def get_image(filename: str):
    out = images.resolve(filename, config.IMAGE_DIRS)
    if not out:
        raise HTTPException(404, "image not found")
    data, ctype = out
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "max-age=3600"})


# -------------------------------------------------------------- SSE real-time
@app.get("/events/stream")
async def stream(request: Request):
    q = BROKER.subscribe()

    async def gen():
        try:
            yield push_mod.sse_format("ping", {})  # open the stream immediately
            while True:
                if await request.is_disconnected():
                    break
                try:
                    name, data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield push_mod.sse_format(name, data)
                except asyncio.TimeoutError:
                    yield push_mod.sse_format("ping", {})  # heartbeat
        finally:
            BROKER.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------- ingest (uplink)
@app.post("/api/ingest/event")
def ingest_event(raw: dict, _=Depends(require_token)):
    e = ingest.normalize_event(raw)
    STORE.upsert_event(e)
    full = STORE.get_event(e["event_id"])
    BROKER.publish("hazard", {"type": "event", "payload": full})
    return {"ok": True, "event_id": e["event_id"]}


@app.post("/api/ingest/brief")
def ingest_brief(raw: dict, _=Depends(require_token)):
    b = ingest.normalize_brief(raw)
    STORE.upsert_brief(b)
    # If the event exists, re-push it (now enriched with the brief).
    full = STORE.get_event(b["event_id"])
    if full:
        BROKER.publish("hazard", {"type": "event", "payload": full})
    return {"ok": True, "event_id": b["event_id"]}


@app.post("/api/ingest/record")
def ingest_record(raw: dict, _=Depends(require_token)):
    rid = STORE.insert_record(ingest.normalize_record(raw))
    return {"ok": True, "id": rid}


@app.post("/api/ingest/acceptance")
def ingest_acceptance(raw: dict, _=Depends(require_token)):
    aid = STORE.insert_acceptance(ingest.normalize_acceptance(raw))
    return {"ok": True, "id": aid}


@app.post("/api/ingest/report")
def ingest_report(raw: dict, _=Depends(require_token)):
    rid = STORE.insert_report(ingest.normalize_report(raw))
    return {"ok": True, "id": rid}


@app.post("/api/ingest/image")
async def ingest_image(file: UploadFile, _=Depends(require_token)):
    name = images.safe_name(file.filename or "")
    if not name:
        raise HTTPException(400, "bad filename")
    dest = os.path.join(config.RUNTIME_DIR, "evidence", name)
    with open(dest, "wb") as fh:
        fh.write(await file.read())
    return {"ok": True, "filename": name}


# ------------------------------------------------ static PWA (mounted last)
if os.path.isdir(config.WEB_DIR):
    app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
