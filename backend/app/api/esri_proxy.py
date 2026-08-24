"""
Esri World Imagery tile proxy with placeholder detection.

Problem: ArcGIS Online tile services answer HTTP 200 with a baked-in
placeholder JPEG ("Map data not yet available.") wherever imagery does
not exist at the requested level. MapLibre cannot distinguish those from
real tiles, so users see gray text tiles at deep zoom.

Solution: proxy Esri through AURORA-GIS. Each tile is analyzed once:
  - real imagery  -> cached and served (200 image/jpeg)
  - placeholder   -> cached as EMPTY sentinel; served as 404 so MapLibre
                     drops the tile and reveals the Sentinel-2 underlay
Upstream failures also degrade to 404 (map stays clean).
"""

import io
import logging

import httpx
import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image

logger = logging.getLogger("aurora.esri")

router = APIRouter()

UPSTREAM = (
    "https://services.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

EMPTY = b"__EMPTY__"
MAX_Z = 19

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=6.0, write=6.0, pool=3.0),
            headers={"User-Agent": "AURORA-GIS/1.0 (tile proxy)"},
        )
    return _client


def is_placeholder(data: bytes) -> bool:
    """Esri placeholders are tiny, near-uniform, bright JPEGs with text."""
    if len(data) > 8192:
        return False
    try:
        img = Image.open(io.BytesIO(data)).convert("L")
    except Exception:
        return True  # undecodable payload is not usable imagery
    arr = np.asarray(img, dtype=np.float32)
    return float((arr > 185).mean()) > 0.92 and float(arr.mean()) > 185


async def fetch_esri_tile(z: int, x: int, y: int,
                          client: httpx.AsyncClient | None = None,
                          ) -> tuple[bytes | None, bool]:
    """Fetch one upstream tile -> (data|None, is_placeholder)."""
    url = UPSTREAM.format(z=z, y=y, x=x)
    use_client = client or _get_client()
    try:
        resp = await use_client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("esri upstream error z%d/%d/%d: %s", z, x, y, exc)
        return None, True
    if resp.status_code != 200 or not resp.content:
        return None, True
    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type:
        return None, True
    return resp.content, is_placeholder(resp.content)


@router.get("/tiles/esri/{z}/{x}/{y}.jpg")
async def esri_tile(z: int, x: int, y: int, request: Request):
    if z < 0 or z > MAX_Z:
        raise HTTPException(400, "zoom out of range")
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise HTTPException(404, "tile outside pyramid")

    cache = request.app.state.cache
    key = f"esri:{z}:{x}:{y}"

    cached = await cache.get(key)
    if cached == EMPTY:
        raise HTTPException(404, "no imagery at this location/level")
    if cached is not None:
        return Response(content=cached, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=604800"})

    data, placeholder = await fetch_esri_tile(z, x, y)
    if data is None or placeholder:
        await cache.set(key, EMPTY, ttl=7 * 86400)
        raise HTTPException(404, "no imagery at this location/level")

    await cache.set(key, data, ttl=30 * 86400)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=604800"})
