"""Volcano registry API — PHIVOLCS-monitored sites (static curated data).

GET /api/volcanoes -> GeoJSON FeatureCollection.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.data.volcanoes import ACTIVE_AS_OF, volcano_features

router = APIRouter(prefix="/api/volcanoes")


@router.get("")
async def volcanoes() -> JSONResponse:
    return JSONResponse({
        "type": "FeatureCollection",
        "features": volcano_features(),
        "source": "phivolcs-monitored-registry",
        "active_status_as_of": ACTIVE_AS_OF,
        "disclaimer": ("Static site registry of PHIVOLCS-monitored "
                       "volcanoes — NOT live alert levels. The active_now "
                       f"flag is a manual snapshot ({ACTIVE_AS_OF}); "
                       "current status only via official PHIVOLCS "
                       "channels."),
    })
