"""Proxy AWS Terrain Tiles (Terrarium format) for 3D terrain rendering.

The frontend requests /tiles/terrain/{z}/{x}/{y}.png — we fetch from
AWS S3 and relay with cache headers. CORS is handled by the app-wide
middleware; adding it here would duplicate the header.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Response

router = APIRouter()

AWS_TERRAIN = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
NATIVE_MAX_ZOOM = 14
MAX_REQUEST_ZOOM = 22
_client = httpx.AsyncClient(timeout=10, follow_redirects=True)


@router.get("/tiles/terrain/{z}/{x}/{y}.png")
async def terrain_tile(z: int, x: int, y: int) -> Response:
    if not 0 <= z <= MAX_REQUEST_ZOOM:
        raise HTTPException(400, "zoom out of range")
    # Overzoom: clamp to native max and scale x/y to parent tile
    if z > NATIVE_MAX_ZOOM:
        shift = z - NATIVE_MAX_ZOOM
        z, x, y = NATIVE_MAX_ZOOM, x >> shift, y >> shift
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise HTTPException(404, "tile outside pyramid")

    url = f"{AWS_TERRAIN}/{z}/{x}/{y}.png"
    resp = await _client.get(url)
    if resp.status_code == 404:
        raise HTTPException(404, "upstream tile unavailable")
    if resp.status_code != 200:
        raise HTTPException(502, "upstream tile unavailable")

    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
