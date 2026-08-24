"""
Geographic search: local PH admin index + global Nominatim geocoding.

Coordinate queries ("14.6, 120.9") short-circuit. Place queries merge
curated local entries (ranked first) with OpenStreetMap Nominatim
results, each carrying a viewport-fitted zoom for fly-to. Nominatim
responses are cached and failures degrade gracefully to local-only.
"""

import logging
import math
import re

import httpx
from fastapi import APIRouter, Query, Request

from app.data.ph_admin import search_index

logger = logging.getLogger("noah.search")

router = APIRouter(prefix="/api")

_COORD_RE = re.compile(
    r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)

NOMINATIM = "https://nominatim.openstreetmap.org/search"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, connect=3.0),
            headers={"User-Agent": "NOAH/1.0 (geographic search)"},
        )
    return _client


def zoom_for_bbox(south: float, north: float, west: float, east: float) -> int:
    """Zoom level that fits the bbox in a typical viewport."""
    dlat = max(abs(north - south), 0.002)
    dlon = max(abs(east - west), 0.002)
    span = max(dlat, dlon)
    return min(17, max(2, round(math.log2(360.0 / span) - 1)))


_TYPE_ZOOM = {
    "country": 5, "state": 7, "region": 7, "county": 9, "island": 8,
    "city": 12, "municipality": 12, "town": 13, "village": 14,
    "suburb": 14, "neighbourhood": 15, "quarter": 15, "borough": 13,
}


async def nominatim_search(q: str, limit: int, request: Request) -> list[dict]:
    cache = request.app.state.cache
    key = f"geocode:{q.lower()}:{limit}"
    cached = await cache.get(key)
    if cached is not None:
        import json
        try:
            return json.loads(cached)
        except ValueError:
            pass

    try:
        resp = await _get_client().get(NOMINATIM, params={
            "q": q, "format": "jsonv2", "limit": limit,
            "addressdetails": 0,
        })
        if resp.status_code != 200:
            return []
        raw = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("nominatim unavailable: %s", exc)
        return []

    results: list[dict] = []
    for r in raw:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (KeyError, ValueError):
            continue
        bbox = r.get("boundingbox")
        if bbox and len(bbox) == 4:
            try:
                s, n, w, e = map(float, bbox)
                zoom = zoom_for_bbox(s, n, w, e)
            except ValueError:
                zoom = _TYPE_ZOOM.get(r.get("type", ""), 14)
        else:
            zoom = _TYPE_ZOOM.get(r.get("type", ""), 14)

        display = r.get("display_name", "")
        parts = [p.strip() for p in display.split(",")]
        results.append({
            "name": parts[0] if parts else display,
            "level": r.get("type") or "place",
            "parent": ", ".join(parts[1:3]) if len(parts) > 1 else None,
            "lat": round(lat, 6), "lon": round(lon, 6),
            "zoom": zoom,
        })

    import json as _json
    await cache.set(key, _json.dumps(results).encode(), ttl=86400)
    return results


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=120),
                 limit: int = Query(default=12, ge=1, le=50),
                 request: Request = None):
    q = q.strip()

    coord = _COORD_RE.match(q)
    if coord:
        lat, lon = float(coord.group(1)), float(coord.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return {"results": [{
                "name": f"{lat:.5f}, {lon:.5f}",
                "level": "coordinates",
                "parent": None,
                "lat": lat, "lon": lon, "zoom": 14,
            }]}

    # Local curated index first
    ql = q.lower()
    scored = []
    for entry in search_index():
        name = entry["name"].lower()
        if ql == name:
            score = 100
        elif name.startswith(ql):
            score = 80
        elif ql in name:
            score = 50
        else:
            parent = (entry.get("parent") or "").lower()
            score = 30 if ql in parent else 0
        if score:
            scored.append((score, dict(entry, source="local")))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1]["name"])))
    local_results = [e for _, e in scored[:limit]]

    remaining = max(1, limit - len(local_results))
    remote = await nominatim_search(q, remaining, request)

    merged: list[dict] = []
    seen: set[tuple] = set()
    for entry in local_results + remote:
        key_id = (entry["name"].lower(), round(entry["lat"], 2), round(entry["lon"], 2))
        if key_id in seen:
            continue
        seen.add(key_id)
        merged.append(entry)
    return {"results": merged[:limit]}
