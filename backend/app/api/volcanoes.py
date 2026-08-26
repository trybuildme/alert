"""Volcano registry API — PHIVOLCS-monitored sites (static curated data).

GET /api/volcanoes       -> GeoJSON FeatureCollection.
GET /api/volcanoes/{uid} -> single Feature + nearby seismicity summary
                            (last 7 days within 30 km, from the live
                            earthquake store when enabled). Imagery is
                            served client-side via /tiles/esri/*.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.data.volcanoes import ACTIVE_AS_OF, VOLCANOES, volcano_features
from app.hazards.volcano_assessment import build_assessment

router = APIRouter(prefix="/api/volcanoes")

_DISCLAIMER = ("Static site registry of PHIVOLCS-monitored volcanoes "
               "— NOT live alert levels. The active_now flag is a manual "
               f"snapshot ({ACTIVE_AS_OF}); current status only via "
               "official PHIVOLCS channels.")

_UIDS = {name.lower().replace(" ", "-"): i for i, (name, *_rest)
         in enumerate(VOLCANOES)}


def _lookup_index(uid: str) -> int | None:
    """Accept both the bare slug ('kanlaon') and the full feature uid
    ('phivolcs-site:kanlaon') — the frontend always sends the latter."""
    key = uid.strip().lower()
    if ":" in key:
        key = key.rsplit(":", 1)[-1]
    return _UIDS.get(key)


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


@router.get("/activity")
async def activity(request: Request) -> JSONResponse:
    """Compact per-volcano assessment summaries for the notification
    bell: one call covering all monitored sites (each site runs its own
    30 km / 7 d seismicity window). Polled by the frontend — keep it
    cheap; the underlying queries are indexed bbox reads."""
    out = []
    features = volcano_features()
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        seismicity = _seismicity_summary(request, lat, lon)
        assessment = build_assessment(props, seismicity)
        strongest = (seismicity.get("strongest") or {}) \
            if seismicity.get("available") else {}
        out.append({
            "uid": props["uid"],
            "name": props["name"],
            "latitude": lat,
            "longitude": lon,
            "active_now": bool(props.get("active_now")),
            "level": assessment["level"],
            "label": assessment["label"],
            "color": assessment["color"],
            "signals": assessment["signals"],
            "seismicity": {
                "total_7d": seismicity.get("total_7d"),
                "count_24h": seismicity.get("count_24h"),
                "strongest_uid": strongest.get("uid"),
                "strongest_magnitude": strongest.get("magnitude"),
            },
            "last_known_eruption": props.get("last_known_eruption"),
        })
    return JSONResponse({
        "generated_at": datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "assessment-synthesis",
        "disclaimer": ("Automated NOAH assessments — not official "
                       "PHIVOLCS Alert Levels."),
        "volcanoes": out,
    })


@router.get("/{uid}")
async def volcano_detail(uid: str, request: Request) -> JSONResponse:
    idx = _lookup_index(uid)
    if idx is None:
        raise HTTPException(status_code=404, detail="unknown volcano site")
    feature = volcano_features()[idx]
    lon, lat = feature["geometry"]["coordinates"]
    seismicity = _seismicity_summary(request, lat, lon)
    return JSONResponse({
        **feature,
        "active_status_as_of": ACTIVE_AS_OF,
        "disclaimer": _DISCLAIMER,
        "seismicity": seismicity,
        "assessment": build_assessment(feature["properties"], seismicity),
    })
