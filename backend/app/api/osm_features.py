"""Real OSM road and waterway geometry via the Overpass API.

Replaces the dead tiles.openstreetmap.fr vector source. Whole-country
extraction measured at ~800 MB of raw JSON, so geometry is fetched per
VIEWPORT: the client sends its current bounds, the server clamps the
span, snaps it to a shared grid so panning reuses cached answers, and
disk-caches each result for 7 days. Two road tiers keep payloads sane:
major (motorway..secondary) from z6, minor (tertiary/unclassified/track)
only from z13. Degrades honestly to an empty FeatureCollection when
Overpass is unreachable.
"""

import json
import os
import time
from pathlib import Path

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api")

_client: httpx.AsyncClient | None = None

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_TTL_SECONDS = 7 * 86400

# Grid snap (degrees): identical rounded viewports share cache entries
_SNAP = 0.05
# Max viewport span per request class (degrees)
_MAX_SPAN = {"major": 2.0, "minor": 0.6, "water": 0.6, "places": 3.0}

_ROAD_CLASSES = {
    "major": "motorway|trunk|primary|secondary",
    "minor": "tertiary|unclassified|track",
}
_WATER_CLASSES = "river|stream|canal|drain"
_PLACE_CLASSES = ("city", "town", "village", "borough", "suburb", "quarter",
                  "neighbourhood")

_CACHE_DIR = Path(os.environ.get(
    "NOAH_OSM_CACHE_DIR", "/tmp/opencode/noah-osm-cache"))


def _parse_bbox(raw: str | None, max_span: float) -> tuple[float, float, float, float] | None:
    """Parse 'west,south,east,north'; clamp span; snap outward to grid."""
    if not raw:
        return None
    try:
        w, s, e, n = (float(v) for v in raw.split(","))
    except ValueError:
        return None
    w = max(-180.0, w)
    e = min(180.0, e)
    s = max(-85.0, s)
    n = min(85.0, n)
    if not (w < e and s < n):
        return None
    cx, cy = (w + e) / 2, (s + n) / 2
    half = min(max(e - w, n - s), max_span) / 2
    # Snap center AND span outward to the grid so nearby viewports
    # collapse onto one cache entry (span must quantize too, else two
    # almost-equal windows produce different edge coordinates).
    half = max(round(half / _SNAP) * _SNAP, _SNAP)
    cx = round(cx / _SNAP) * _SNAP
    cy = round(cy / _SNAP) * _SNAP
    return (cx - half, cy - half, cx + half, cy + half)


def _query(regex: str, bbox: tuple[float, float, float, float]) -> str:
    # bbox arrives as (west, south, east, north); Overpass QL wants
    # (south, west, north, east)
    w, s, e, n = bbox
    filt = f'["highway"~"^({regex})$"]'
    return f"[out:json][timeout:90];way{filt}({s},{w},{n},{e});out geom;"


def _to_featurecollection(data: dict, prop_key: str) -> dict:
    features = []
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if not geom or len(geom) < 2:
            continue
        tags = el.get("tags", {})
        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in geom]
        features.append({
            "type": "Feature",
            "properties": {
                "osm_id": el.get("id"),
                "class": tags.get(prop_key, ""),
                "name": tags.get("name", ""),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })
    return {"type": "FeatureCollection", "features": features,
            "source": "osm-overpass"}


def _load_cached(key: str) -> dict | None:
    path = _CACHE_DIR / f"{key}.json"
    try:
        if time.time() - path.stat().st_mtime < _TTL_SECONDS:
            return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _store_cache(key: str, payload: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (_CACHE_DIR / f"{key}.json").write_text(json.dumps(payload))
    except OSError:
        pass


async def _fetch_overpass(query: str) -> dict | None:
    global _client
    try:
        if _client is None or _client.is_closed:
            # Explicit UA required: overpass-api.de answers 406 to the
            # bare python-httpx default agent.
            _client = httpx.AsyncClient(
                timeout=120,
                headers={"User-Agent": "ALERT/1.0 (local hazard dashboard)"})
        resp = await _client.post(_OVERPASS_URL, content=query,
                                  headers={"Content-Type": "text/plain"})
        # Overpass rate-limits bursts of viewport fetches (429); back
        # off briefly instead of degrading to an empty map. A page load
        # can fire several place/road requests at once.
        import asyncio
        for wait_s in (2.0, 6.0):
            if resp.status_code != 429:
                break
            retry_after = resp.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else wait_s
            await asyncio.sleep(min(delay, 10.0))
            resp = await _client.post(_OVERPASS_URL, content=query,
                                      headers={"Content-Type": "text/plain"})
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def _get_features(kind: str, prop_key: str, regex: str,
                        bbox_raw: str | None, max_span: float) -> dict:
    empty = {"type": "FeatureCollection", "features": [],
             "source": "unavailable"}
    bbox = _parse_bbox(bbox_raw, max_span)
    if bbox is None:
        return {**empty, "error": "missing-or-invalid-bbox"}
    key = f"{kind}_{bbox[0]:.2f}_{bbox[1]:.2f}_{bbox[2]:.2f}_{bbox[3]:.2f}"
    cached = _load_cached(key)
    if cached is not None:
        return cached
    data = await _fetch_overpass(_query(regex, bbox))
    if data is None:
        return empty
    payload = _to_featurecollection(data, prop_key)
    _store_cache(key, payload)
    return payload


@router.get("/roads")
async def roads(bbox: str | None = None, tier: str = "major") -> dict:
    """Major (default) or minor OSM roads within the given viewport."""
    regex = _ROAD_CLASSES.get(tier)
    if regex is None:
        return {"type": "FeatureCollection", "features": [],
                "source": "unavailable", "error": "unknown-tier"}
    return await _get_features(f"roads_{tier}", "highway", regex, bbox,
                               _MAX_SPAN[tier])


@router.get("/waterways")
async def waterways(bbox: str | None = None) -> dict:
    """Rivers, streams, canals, drains within the given viewport."""
    return await _get_features("waterways", "waterway", _WATER_CLASSES,
                               bbox, _MAX_SPAN["water"])


async def _get_places(bbox_raw: str | None) -> dict:
    """OSM settlement nodes (city/town/village/...) for place labels."""
    empty = {"type": "FeatureCollection", "features": [],
             "source": "unavailable"}
    bbox = _parse_bbox(bbox_raw, _MAX_SPAN["places"])
    if bbox is None:
        return {**empty, "error": "missing-or-invalid-bbox"}
    w, s, e, n = bbox
    key = f"places_{w:.2f}_{s:.2f}_{e:.2f}_{n:.2f}"
    cached = _load_cached(key)
    if cached is not None:
        return cached
    cls = "|".join(_PLACE_CLASSES)
    query = (f"[out:json][timeout:90];"
             f'node["place"~"^({cls})$"]({s},{w},{n},{e});out;')
    data = await _fetch_overpass(query)
    if data is None:
        return empty
    features = []
    for el in data.get("elements", []):
        lat, lon = el.get("lat"), el.get("lon")
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        if tags.get("place") not in _PLACE_CLASSES or not name:
            continue
        if lat is None or lon is None:
            continue
        pop = tags.get("population")
        features.append({
            "type": "Feature",
            "properties": {
                "osm_id": el.get("id"),
                "class": tags.get("place", ""),
                "name": name,
                "population": int(pop) if pop and pop.isdigit() else None,
                # Capital markers rank above ordinary cities on Google Maps
                "capital": tags.get("place") == "city"
                           and tags.get("capital", "") == "yes",
            },
            "geometry": {"type": "Point",
                         "coordinates": [round(lon, 6), round(lat, 6)]},
        })
    payload = {"type": "FeatureCollection", "features": features,
               "source": "osm-overpass"}
    _store_cache(key, payload)
    return payload


@router.get("/places")
async def places(bbox: str | None = None) -> dict:
    """Named OSM settlements (cities, towns, villages, districts)
    within the given viewport — the raw material for map labels."""
    return await _get_places(bbox)
