"""Elevation profiles along drawn lines — real DEM, proxied.

Source: Open-Meteo Elevation API (https://open-meteo.com/en/docs/elevation)
backed by Copernicus DEM GLO-90 (~90 m posting). Free, no API key,
up to 100 coordinates per request. ALERT samples the drawn line into
<= 100 evenly-spaced points client-side, then asks for all of them in
one upstream call.

Honesty contract: this is REAL elevation data (unlike the simulated
terrain basemap shading). Resolution is ~90 m — fine relief detail
(e.g., a 10 m berm) will not appear.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("alert.elevation")

UPSTREAM = "https://api.open-meteo.com/v1/elevation"
MAX_POINTS = 100            # upstream hard limit per request
_cache: dict[tuple, dict] = {}
CACHE_MAX_ENTRIES = 256

router = APIRouter(prefix="/api/elevation")

_client = httpx.AsyncClient(timeout=15)


def parse_coords(raw: str) -> list[tuple[float, float]]:
    """'lat,lon|lat,lon|...' -> [(lat, lon), ...]; raises on garbage."""
    coords: list[tuple[float, float]] = []
    for pair in raw.split("|"):
        parts = pair.split(",")
        if len(parts) != 2:
            raise ValueError(f"expected 'lat,lon', got '{pair}'")
        lat, lon = float(parts[0]), float(parts[1])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"coordinate out of range: {pair}")
        coords.append((lat, lon))
    return coords


async def fetch_elevations(coords: list[tuple[float, float]]) -> list[float]:
    """One upstream call (caller guarantees <= MAX_POINTS)."""
    lats = ",".join(f"{lat:.6f}" for lat, _ in coords)
    lons = ",".join(f"{lon:.6f}" for _, lon in coords)
    resp = await _client.get(UPSTREAM, params={"latitude": lats,
                                               "longitude": lons})
    resp.raise_for_status()
    elevations = resp.json().get("elevation")
    if not isinstance(elevations, list) or len(elevations) != len(coords):
        raise ValueError("upstream returned unexpected payload")
    return [float(e) if e is not None else 0.0 for e in elevations]


@router.get("/profile")
async def profile(
    coords: str = Query(
        ..., description="Sampled points along the line: 'lat,lon|lat,lon|…'",
        max_length=4096),
) -> JSONResponse:
    try:
        points = parse_coords(coords)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not 2 <= len(points) <= MAX_POINTS:
        raise HTTPException(
            status_code=400,
            detail=f"need between 2 and {MAX_POINTS} sampled points")

    # Cache key rounded to ~11 m so tiny re-samples hit.
    key = tuple((round(lat, 4), round(lon, 4)) for lat, lon in points)
    cached = _cache.get(key)
    if cached is not None:
        return JSONResponse({**cached, "cached": True})

    try:
        elevations = await fetch_elevations(points)
    except Exception as exc:  # noqa: BLE001 — degrade honestly
        logger.warning("elevation upstream failed: %s: %s",
                       type(exc).__name__, exc or "(no message)")
        raise HTTPException(
            status_code=502,
            detail="elevation source unavailable") from exc

    body = {
        "points": [{"lat": lat, "lon": lon} for lat, lon in points],
        "elevations_m": elevations,
        "count": len(elevations),
        "cached": False,
        "source": "open-meteo-copernicus-dem-glo-90",
        "resolution_m": 90,
        "disclaimer": ("Real Copernicus DEM elevations at ~90 m posting "
                       "via Open-Meteo — fine terrain detail below that "
                       "scale will not resolve."),
    }
    if len(_cache) >= CACHE_MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))     # FIFO trim
    _cache[key] = body
    return JSONResponse(body)
