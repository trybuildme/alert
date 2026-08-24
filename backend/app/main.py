"""
AURORA-GIS backend entrypoint.

FastAPI application serving:
  /tiles/{product}/{z}/{x}/{y}.png   XYZ raster tiles (multi-resolution pyramid)
  /api/products[/{id}[/times]]       satellite product catalog + time index
  /api/search                        geographic search (places + coordinates)
  /api/layers                        layer registry
  /api/admin/*                       PH administrative boundaries (GeoJSON)
  /api/inspect                       click-to-inspect analytics
  /health                            service + cache status
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

from app.api import admin_boundaries, cyclone_forecast, cyclones, esri_proxy, health, inspect, metadata, osm_features, search, tiles
from app.cache.redis_cache import TileCache
from app.core.config import settings
from app.services.tile_service import TileService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aurora")


@asynccontextmanager
async def lifespan(application: FastAPI):
    await cache.redis._ensure()
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = TileCache()
app.state.cache = cache
app.state.tiles = TileService(cache=cache)

app.include_router(tiles.router)
app.include_router(esri_proxy.router)
app.include_router(metadata.router)
app.include_router(search.router)
app.include_router(inspect.router)
app.include_router(admin_boundaries.router)
app.include_router(cyclones.router)
app.include_router(cyclone_forecast.router)
app.include_router(osm_features.router)
app.include_router(health.router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


# Optional local static export of admin GeoJSON (dev convenience)
_data_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_data_dir):
    app.mount("/static", StaticFiles(directory=_data_dir), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
