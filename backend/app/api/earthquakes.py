"""Earthquake REST API + SSE real-time stream.

Conventions follow the existing routers (GeoJSON FeatureCollections,
honest degradation, /health style). The SSE stream pushes:
  hazard.created    new normalized event (full feature)
  hazard.alert      fired alert decision
  provider.status   provider health transitions

DETECTED EVENTS ONLY — this API never forecasts or predicts.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings

router = APIRouter(prefix="/api/earthquakes")


def _state(request: Request) -> dict:
    return request.app.state.earthquakes


@router.get("")
@router.get("/")
async def list_earthquakes(
        request: Request,
        days: int = Query(default=None, ge=1, le=3650),
        min_magnitude: float | None = Query(default=None, alias="min_magnitude"),
        max_magnitude: float | None = Query(default=None),
        min_depth: float | None = Query(default=None),
        max_depth: float | None = Query(default=None),
        provider: str | None = Query(default=None),
        bbox: str | None = Query(default=None,
                                 description="west,south,east,north"),
        limit: int = Query(default=1000, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
) -> dict:
    st = _state(request)
    parsed_bbox = None
    if bbox:
        try:
            w, s, e, n = (float(v) for v in bbox.split(","))
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError
            parsed_bbox = (w, s, e, n)
        except ValueError:
            raise HTTPException(400, "bbox must be west,south,east,north") from None
    return st["store"].query(
        days=days if days is not None else settings.EARTHQUAKE_HISTORY_DAYS,
        min_magnitude=min_magnitude, max_magnitude=max_magnitude,
        min_depth=min_depth, max_depth=max_depth, provider=provider,
        bbox=parsed_bbox, limit=limit, offset=offset)


@router.get("/recent")
async def recent(request: Request, hours: int = Query(default=24, ge=1, le=720),
                 min_magnitude: float | None = Query(default=None)) -> dict:
    st = _state(request)
    return st["store"].query(days=max(1, hours // 24) if hours >= 24 else 1,
                             min_magnitude=min_magnitude, limit=2000)


@router.get("/nearby")
async def nearby(request: Request,
                 latitude: float = Query(..., ge=-90, le=90),
                 longitude: float = Query(..., ge=-180, le=180),
                 radius_km: float = Query(default=150, gt=0, le=3000),
                 days: int = Query(default=30, ge=1, le=3650),
                 min_magnitude: float | None = Query(default=None)) -> dict:
    return _state(request)["store"].nearby(latitude, longitude, radius_km,
                                           days=days,
                                           min_magnitude=min_magnitude)


@router.get("/region")
async def region_summary(request: Request,
                         latitude: float = Query(..., ge=-90, le=90),
                         longitude: float = Query(..., ge=-180, le=180),
                         radius_km: float = Query(default=150, gt=0, le=3000),
                         days: int = Query(default=30, ge=1, le=3650)) -> dict:
    """Historical regional activity: counts by magnitude band."""
    st = _state(request)
    near = st["store"].nearby(latitude, longitude, radius_km, days=days,
                              limit=5000)
    bands = {"light": 0, "light_strong": 0, "moderate": 0, "strong": 0,
             "major": 0}
    for f in near["features"]:
        mag = f["properties"].get("magnitude") or 0
        if mag < 3:
            bands["light"] += 1
        elif mag < 4:
            bands["light_strong"] += 1
        elif mag < 5:
            bands["moderate"] += 1
        elif mag < 6:
            bands["strong"] += 1
        else:
            bands["major"] += 1
    return {"radius_km": radius_km, "days": days, "total": len(near["features"]),
            "magnitude_bands": bands}


@router.get("/statistics")
async def statistics(request: Request) -> dict:
    st = _state(request)
    ref = st.get("reference_point")
    stats = st["store"].statistics(
        reference_point=(ref[0], ref[1]) if ref else None)
    stats["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats["disclaimer"] = ("Detected events from authoritative feeds only — "
                           "not forecasts or predictions.")
    return stats


@router.get("/alerts")
async def recent_alerts(request: Request, limit: int = Query(25, ge=1, le=200)) -> dict:
    st = _state(request)
    with st["store"]._lock:
        rows = st["store"]._conn.execute(
            "SELECT * FROM hazard_alerts ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
    return {"alerts": [dict(r) for r in rows][::-1]}


@router.get("/health")
async def health(request: Request) -> dict:
    st = _state(request)
    worker: IngestWorker = st["worker"]
    body = worker.health()
    body.update({
        "enabled": st.get("enabled", True),
        "stream_clients": st["bus"].subscriber_count,
        "providers_configured": [p.name for p in worker.providers],
        "phivolcs_note": "PHIVOLCS requires configuration of an official "
                         "machine-readable source before it can be enabled.",
    })
    return body


@router.get("/stream")
async def stream(request: Request):
    """SSE: hazard.created / hazard.alert / provider.status."""
    if not settings.EARTHQUAKE_WS_ENABLED:
        raise HTTPException(503, "real-time stream disabled by configuration")
    st = _state(request)
    queue = st["bus"].subscribe()

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {msg.get('event', 'message')}\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            st["bus"].unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# NOTE: registered LAST so literal paths (/recent, /nearby, /statistics,
# /health, /stream ...) win over the {uid} pattern.
@router.get("/{uid}")
async def event_detail(request: Request, uid: str,
                       latitude: float | None = Query(default=None),
                       longitude: float | None = Query(default=None)) -> dict:
    """Full detail for one event (`provider:provider_event_id`).

    With latitude/longitude supplied, also reports distance from that
    reference point (e.g. Aurora province)."""
    st = _state(request)
    if ":" not in uid:
        raise HTTPException(400, "uid must be provider:provider_event_id")
    provider, provider_id = uid.split(":", 1)
    row = st["store"].get_by_provider_id(provider, provider_id)
    if row is None:
        raise HTTPException(404, "event not found")
    props = row["properties"]
    if latitude is not None and longitude is not None:
        lon_c, lat_c = row["geometry"]["coordinates"]
        props["distance_from_reference_km"] = round(
            st["store"].haversine_km(latitude, longitude, lat_c, lon_c), 1)
    return {"type": "Feature", "properties": props, "geometry": row["geometry"]}
