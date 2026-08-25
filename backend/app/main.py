"""
NOAH backend entrypoint.

FastAPI application serving:
  /tiles/{product}/{z}/{x}/{y}.png   XYZ raster tiles (multi-resolution pyramid)
  /api/products[/{id}[/times]]       satellite product catalog + time index
  /api/search                        geographic search (places + coordinates)
  /api/layers                        layer registry
  /api/admin/*                       PH administrative boundaries (GeoJSON)
  /api/inspect                       click-to-inspect analytics
  /health                            service + cache status
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

from app.api import (admin_boundaries, cyclone_forecast, cyclones,
                     earthquakes, esri_proxy, gibs_proxy, health, inspect,
                     metadata, metrics, osm_features, push, search, tiles,
                     tsunamis, volcanoes)
from app.cache.redis_cache import TileCache
from app.core.auth import AuthMiddleware
from app.core.config import settings
from app.core.ratelimit import RateLimitMiddleware, SecurityHeadersMiddleware
from app.hazards.alerts import NotificationDispatcher, load_rules
from app.hazards.channels import EmailChannel, WebhookChannel
from app.hazards.ingest import IngestWorker
from app.hazards.push import WebPushChannel
from app.hazards.providers.phivolcs import PhivolcsProvider
from app.hazards.providers.usgs import UsgsProvider
from app.hazards.base import EventBus
from app.hazards.store import EarthquakeStore
from app.services.tile_service import TileService


def parse_bbox(raw: str) -> tuple | None:
    """'minlon,minlat,maxlon,maxlat' -> tuple, or None for global."""
    if not raw or not raw.strip():
        return None
    try:
        w, s, e, n = (float(v) for v in raw.split(","))
        return (w, s, e, n)
    except ValueError:
        logger.warning("invalid EARTHQUAKE_BBOX %r; using global feed", raw)
        return None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("noah")


@asynccontextmanager
async def lifespan(application: FastAPI):
    await cache.redis._ensure()
    # --- Earthquake intelligence module ---
    if settings.EARTHQUAKE_ENABLED:
        store = EarthquakeStore(settings.EARTHQUAKE_DB_PATH)
        bus = EventBus()
        providers = [UsgsProvider(bbox=parse_bbox(settings.EARTHQUAKE_BBOX)),
                     PhivolcsProvider()]
        reference = (settings.NOAH_EQ_REF_LAT, settings.NOAH_EQ_REF_LON)
        dispatcher = NotificationDispatcher()
        dispatcher.register("dashboard", lambda payload: None)
        # Optional delivery channels (docs/earthquake/ALERTS.md)
        if settings.SMTP_HOST and settings.SMTP_TO:
            dispatcher.register("email", EmailChannel(
                settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER,
                settings.SMTP_PASSWORD, settings.SMTP_FROM, settings.SMTP_TO))
            logger.info("email alert channel enabled -> %s",
                        ", ".join(settings.SMTP_TO))
        if settings.WEBHOOK_URL:
            dispatcher.register("webhook",
                                WebhookChannel(settings.WEBHOOK_URL))
            logger.info("webhook alert channel enabled")
        if settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY:
            dispatcher.register("webpush", WebPushChannel(
                store, settings.VAPID_PRIVATE_KEY,
                settings.VAPID_PUBLIC_KEY, settings.VAPID_SUBJECT))
            logger.info("web push alert channel enabled")

        async def on_alert(decision, event):
            await dispatcher.dispatch(decision, event, bus.publish)

        worker = IngestWorker(
            providers, store, bus,
            poll_interval=settings.EARTHQUAKE_POLL_INTERVAL,
            lookback_minutes=settings.EARTHQUAKE_LOOKBACK_MINUTES,
            min_magnitude=settings.EARTHQUAKE_MIN_MAGNITUDE,
            max_depth_km=settings.EARTHQUAKE_MAX_DEPTH_KM,
            reference_point=reference,
            rules=load_rules(settings.EARTHQUAKE_ALERT_RULES_PATH),
            alert_enabled=settings.EARTHQUAKE_ALERT_ENABLED,
            backfill_days=settings.EARTHQUAKE_BACKFILL_DAYS,
            on_alert=on_alert)
        application.state.earthquakes = {
            "store": store, "bus": bus, "worker": worker,
            "reference_point": reference,
            "reference_radius_km": settings.NOAH_EQ_REF_RADIUS_KM,
            "enabled": True,
        }
        worker.start()
        logger.info("earthquake module enabled (poll every %ss)",
                    settings.EARTHQUAKE_POLL_INTERVAL)

        # Alert retention: prune hazard_alerts older than the configured
        # window, then re-check daily.
        async def retention_loop():
            while True:
                try:
                    removed = await asyncio.to_thread(
                        store.prune_alerts, settings.ALERT_RETENTION_DAYS)
                    if removed:
                        logger.info("alert retention pruned %d rows", removed)
                except Exception as exc:  # noqa: BLE001
                    logger.error("alert retention failed: %s", exc)
                await asyncio.sleep(24 * 3600)

        retention_task = asyncio.create_task(retention_loop())
    yield
    if settings.EARTHQUAKE_ENABLED and hasattr(application.state, "earthquakes"):
        retention_task.cancel()
        await application.state.earthquakes["worker"].stop()
        application.state.earthquakes["store"].close()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

# Innermost first, CORS outermost so preflights, 401s and 429s carry
# CORS headers (Starlette: last-added middleware wraps outermost).
app.add_middleware(AuthMiddleware, token=settings.AUTH_TOKEN)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, enabled=settings.RATE_LIMIT_ENABLED,
                   trusted_proxies=settings.TRUSTED_PROXIES)
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
app.include_router(earthquakes.router)
app.include_router(push.router)
app.include_router(tsunamis.router)
app.include_router(volcanoes.router)
app.include_router(health.router)
app.include_router(metrics.router)


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
