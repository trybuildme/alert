"""Flood Monitoring API.

All endpoints are health-tier (no auth, no rate limit) matching
ALERT's other public read surfaces — the module exposes no write path;
observations arrive exclusively through the authenticated server-side
ingest worker.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.flood.stations import registry as station_registry

router = APIRouter(prefix="/api/flood")


def _state(request: Request) -> dict:
    state = getattr(request.app.state, "flood", None)
    if not state or not state.get("enabled"):
        raise HTTPException(status_code=503, detail="flood module disabled")
    return state


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _station_feature(station: dict, latest_by_station: dict,
                     assessment_by_station: dict) -> dict:
    sid = station["id"]
    latest = latest_by_station.get(sid)
    assessment = assessment_by_station.get(sid)
    props = {
        "uid": sid,
        "name": station["name"],
        "kind": station["kind"],
        "river_basin": station.get("river_basin"),
        "provider": station.get("provider", "none"),
        "level": (assessment or {}).get("level", "NORMAL"),
        "recommended_action": (assessment or {}).get("recommended_action"),
        # Latest measurement + trend context for the popup.
        "latest": {
            "metric": latest["metric"],
            "value": latest["value"],
            "observed_at": latest["observed_at"],
            "quality": latest["quality"],
            "source": latest["source"],
        } if latest else None,
        "data_status": ("live" if latest else "offline-awaiting-feed"
                        if station.get("provider") == "none"
                        else "awaiting-data"),
    }
    if latest:
        props["latest"]["age_minutes"] = max(0, int(
            (datetime.now(timezone.utc)
             - datetime.strptime(latest["observed_at"],
                                 "%Y-%m-%dT%H:%M:%SZ").replace(
                                     tzinfo=timezone.utc)).total_seconds()
            / 60))
        # Flat convenience fields for the map's data-driven styling.
        if latest["metric"] == "rainfall_mm_h":
            props["mmh"] = latest["value"]
            props["mmhLabel"] = f"{latest['value']:g}"
    return {
        "type": "Feature",
        "id": sid,
        "properties": props,
        "geometry": {"type": "Point",
                     "coordinates": [station["longitude"],
                                     station["latitude"]]},
    }


@router.get("/stations")
async def stations(request: Request,
                   kind: str | None = Query(default=None)) -> dict:
    """GeoJSON FeatureCollection of monitoring stations with live status."""
    st = _state(request)
    store = st["store"]
    store.upsert_stations(station_registry())
    features = []
    latest_map: dict[str, dict] = {}
    assessments = st.get("assessments") or {}
    for s in store.stations(kind):
        metrics = [store.latest_observation(s["id"], m)
                   for m in ("rainfall_mm_h", "rainfall_mm_3h",
                             "rainfall_mm_24h", "water_level_m")]
        fresh = [o for o in metrics if o]
        if fresh:
            latest_map[s["id"]] = max(fresh, key=lambda o: o["observed_at"])
        features.append(_station_feature(s, latest_map, assessments))
    return {
        "type": "FeatureCollection",
        "features": features,
        "source": "alert-flood-monitoring",
        "generated_at": _iso_now(),
        "disclaimer": (
            "Rainfall values are REAL model data via Open-Meteo + RainViewer. "
            "Water-level gauges report offline until an authorized "
            "PAGASA/DENR feed exists — no values are fabricated."),
    }


@router.get("/observations/{station_id}")
async def observations(request: Request, station_id: str,
                       metric: str | None = Query(default=None),
                       hours: int = Query(default=48, ge=1, le=720)) -> dict:
    st = _state(request)
    store = st["store"]
    station = store.get_station(station_id)
    if not station:
        raise HTTPException(status_code=404, detail="unknown station")
    metrics = ([metric] if metric
               else ["rainfall_mm_h", "rainfall_mm_3h", "rainfall_mm_24h",
                     "water_level_m"])
    out = {}
    for m in metrics:
        series = store.timeseries(station_id, m, hours=hours)
        if series:
            out[m] = series
    return {
        "station": {k: station[k] for k in
                    ("id", "name", "kind", "latitude", "longitude",
                     "river_basin", "provider")},
        "series": out,
        "hours": hours,
        "generated_at": _iso_now(),
    }


@router.get("/status")
async def status(request: Request) -> dict:
    """Dashboard summary: per-station current level + active alerts."""
    st = _state(request)
    store = st["store"]
    store.upsert_stations(station_registry())
    alerts = store.active_alerts()
    by_station: dict[str, str] = {}
    for a in alerts:
        prev = by_station.get(a["station_id"])
        order = ["NORMAL", "ADVISORY", "WATCH", "WARNING", "CRITICAL"]
        if prev is None or order.index(a["level"]) > order.index(prev):
            by_station[a["station_id"]] = a["level"]
    stations_out = []
    for s in store.stations():
        stations_out.append({
            **{k: s[k] for k in ("id", "name", "kind", "river_basin",
                                 "provider")},
            "level": by_station.get(s["id"], "NORMAL"),
        })
    counts: dict[str, int] = {lvl: 0 for lvl in
                              ["NORMAL", "ADVISORY", "WATCH",
                               "WARNING", "CRITICAL"]}
    for s in stations_out:
        counts[s["level"]] += 1
    return {
        "levels": counts,
        "stations": stations_out,
        "active_alerts": [
            {k: a[k] for k in ("id", "station_id", "level", "reason",
                               "measurement", "threshold", "basis",
                               "source", "recommended_action",
                               "created_at")}
            for a in alerts],
        "worker_health": st["worker"].health() if st.get("worker") else None,
        "generated_at": _iso_now(),
        "basis_note": ("Levels are ALERT's automated classification of "
                       "OBSERVED rainfall data — forecasts and official "
                       "PAGASA warnings are separate things."),
    }


@router.get("/alerts")
async def alerts(request: Request,
                 limit: int = Query(default=50, ge=1, le=200)) -> dict:
    st = _state(request)
    recent = st["store"].recent_alerts(limit=limit)
    return {
        "alerts": [{k: a[k] for k in
                    ("id", "station_id", "level", "reason", "measurement",
                     "threshold", "basis", "source", "recommended_action",
                     "created_at", "resolved_at")} for a in recent],
        "active_count": len(st["store"].active_alerts()),
    }


@router.get("/stream")
async def flood_stream(request: Request):
    """SSE endpoint for real-time flood updates.

    Pushes new observations and alerts as they arrive from the
    real-time ingest worker.
    """
    st = _state(request)
    event_queue = st.get("event_queue")
    if not event_queue:
        raise HTTPException(status_code=503,
                            detail="real-time stream not available")

    async def event_generator():
        # Send initial heartbeat
        yield f"data: {json.dumps({'type': 'connected', 'timestamp': _iso_now()})}\n\n"

        while True:
            try:
                # Wait for new event with timeout for heartbeat
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=30.0
                    )
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': _iso_now()})}\n\n"
            except asyncio.CancelledError:
                break
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
