"""Volcano registry API — PHIVOLCS-monitored sites (static curated data).

GET /api/volcanoes -> GeoJSON FeatureCollection.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.data.volcanoes import volcano_features

router = APIRouter(prefix="/api/volcanoes")


@router.get("")
async def volcanoes() -> JSONResponse:
    return JSONResponse({
        "type": "FeatureCollection",
        "features": volcano_features(),
        "source": "phivolcs-monitored-registry",
        "disclaimer": ("Static site registry of PHIVOLCS-monitored "
                       "volcanoes — NOT live alert levels. Current "
                       "status only via official PHIVOLCS channels."),
    })
