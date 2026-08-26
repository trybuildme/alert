"""Volcano registry API — PHIVOLCS-monitored sites (static curated data).

GET /api/volcanoes       -> GeoJSON FeatureCollection.
GET /api/volcanoes/{uid} -> single Feature + nearby seismicity summary
                            (last 7 days within 30 km, from the live
                            earthquake store when enabled). Imagery is
                            served client-side via /tiles/esri/*.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.data.volcanoes import ACTIVE_AS_OF, VOLCANOES, volcano_features

router = APIRouter(prefix="/api/volcanoes")

_DISCLAIMER = ("Static site registry of PHIVOLCS-monitored volcanoes "
               "— NOT live alert levels. The active_now flag is a manual "
               f"snapshot ({ACTIVE_AS_OF}); current status only via "
               "official PHIVOLCS channels.")

_UIDS = {name.lower().replace(" ", "-"): i for i, (name, *_rest)
         in enumerate(VOLCANOES)}


@router.get("")
async def volcanoes() -> JSONResponse:
    return JSONResponse({
        "type": "FeatureCollection",
        "features": volcano_features(),
        "source": "phivolcs-monitored-registry",
        "active_status_as_of": ACTIVE_AS_OF,
        "disclaimer": _DISCLAIMER,
    })


def _seismicity_summary(request: Request, lat: float, lon: float) -> dict:
    """Best-effort: earthquake module disabled or store down -> empty."""
    eq = getattr(request.app.state, "earthquakes", None)
    store = eq.get("store") if eq else None
    if store is None:
        return {"available": False}
    try:
        near = store.nearby(lat, lon, radius_km=30, days=7, limit=500)
    except Exception:  # noqa: BLE001 — detail popup must not 500 on feed hiccups
        return {"available": False}
    feats = near["features"]
    # Re-sort by time (nearby() returns distance order).
    feats.sort(key=lambda f: f["properties"]["origin_time"], reverse=True)
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    def _ts(f: dict) -> datetime:
        raw = f["properties"]["origin_time"]
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))

    count_24h = sum(1 for f in feats if _ts(f) >= cutoff)
    strongest = max(feats, key=lambda f: f["properties"].get("magnitude") or 0,
                    default=None)
    return {
        "available": True,
        "radius_km": 30,
        "days": 7,
        "total_7d": len(feats),
        "count_24h": count_24h,
        "strongest": (strongest["properties"] if strongest else None),
    }


@router.get("/{uid}")
async def volcano_detail(uid: str, request: Request) -> JSONResponse:
    idx = _UIDS.get(uid)
    if idx is None:
        raise HTTPException(status_code=404, detail="unknown volcano site")
    feature = volcano_features()[idx]
    lon, lat = feature["geometry"]["coordinates"]
    return JSONResponse({
        **feature,
        "active_status_as_of": ACTIVE_AS_OF,
        "disclaimer": _DISCLAIMER,
        "seismicity": _seismicity_summary(request, lat, lon),
    })
