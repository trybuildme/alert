"""Serve pre-generated 3D buildings GeoJSON for Luzon.

GET /api/buildings  → FeatureCollection (height-filtered OSM buildings)

The data set is generated offline with scripts/generate_buildings.py.
If the file is absent the endpoint returns an honest empty collection so
the frontend layer degrades gracefully.
"""

import os
from functools import lru_cache

from fastapi import APIRouter, Response

router = APIRouter()

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "buildings_luzon.geojson"
)
_EMPTY = b'{"type":"FeatureCollection","features":[]}'


@lru_cache(maxsize=1)
def _load(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


@router.get("/api/buildings")
async def buildings() -> Response:
    if not os.path.exists(_DATA_PATH):
        return Response(
            content=_EMPTY,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    return Response(
        content=_load(_DATA_PATH),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )
