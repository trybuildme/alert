"""
Live NASA GIBS proxy for Himawari-9 AHI layers (requirement: real feed).

GIBS serves pre-rendered EPSG:3857 WMTS tiles with a 10-minute time
dimension over a rolling ~23-day window:

    https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/
        {Time}/{TileMatrixSet}/{z}/{y}/{x}.png

Three honest modes per tile:

    live     real GIBS bytes, cached (frames are immutable)
    gap      GIBS answered 404 (housekeeping window / frame not produced)
             -> transparent PNG, never synthetic filler
    fallback GIBS unreachable -> synthetic generator keeps the app usable,
             flagged via X-Alert-Source so the client can disclose it

Time strings use the same %Y-%m-%dT%H:%M:%SZ stamps as the internal time
index; the /api/products/{id}/times endpoint already emits that grid.
"""

import io
import logging
from datetime import datetime, timedelta, timezone

import httpx
import numpy as np
from PIL import Image

from app.services.tile_service import PRODUCTS, TILE_SIZE, TileService

logger = logging.getLogger("alert.gibs")

GIBS_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"

# product id -> GIBS request parameters + offline fallback product
GIBS_PRODUCTS = {
    "himawari-clean-ir": {
        "layer": "Himawari_AHI_Band13_Clean_Infrared",
        "tms": "GoogleMapsCompatible_Level6",
        "max_zoom": 6,
        "format": "png",
        "fallback": "infrared",
    },
    "himawari-air-mass": {
        "layer": "Himawari_AHI_Air_Mass",
        "tms": "GoogleMapsCompatible_Level6",
        "max_zoom": 6,
        "format": "png",
        "fallback": "water-vapor",
    },
    "himawari-visible-red": {
        "layer": "Himawari_AHI_Band3_Red_Visible_1km",
        "tms": "GoogleMapsCompatible_Level7",
        "max_zoom": 7,
        "format": "png",
        "fallback": "true-color",
    },
    "modis-true-color": {
        "layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "tms": "GoogleMapsCompatible_Level9",
        "max_zoom": 9,
        "format": "jpg",
        "fallback": None,
    },
}

_client: httpx.AsyncClient | None = None

# --------------------------------------------------------------------------
# Windy-style enhanced IR palette (clean infrared only)
#
# GIBS Clean IR ships grayscale: bright = cold cloud top, dark = warm
# surface. The LUT below remaps that intensity the way Windy/NOAA enhanced
# IR does — near-black surface, white decks, then yellow→orange→red→violet
# for progressively colder tops. Qualitative by design: GIBS pre-renders
# its own normalization, so exact Kelvin values are not recoverable.
# --------------------------------------------------------------------------

ENHANCED_IR_STOPS = [
    (0.00, (10, 12, 24)),      # warm surface: near-black navy
    (0.40, (22, 28, 48)),      # land/ocean haze
    (0.55, (58, 66, 92)),      # low cloud, grey-blue
    (0.68, (128, 136, 150)),   # mid cloud grey
    (0.78, (225, 230, 238)),   # bright deck
    (0.84, (255, 255, 255)),   # deep cloud pure white
    (0.89, (255, 232, 120)),   # cold tops: pale yellow
    (0.93, (255, 140, 50)),    # orange
    (0.96, (235, 50, 80)),     # red
    (0.985, (180, 40, 200)),   # magenta
    (1.00, (110, 20, 160)),    # deepest/coldest violet
]

_ENHANCED_IR_LUT: np.ndarray | None = None


def enhanced_ir_lut() -> np.ndarray:
    """256x3 uint8 lookup table mapping grayscale intensity -> RGB."""
    global _ENHANCED_IR_LUT
    if _ENHANCED_IR_LUT is None:
        from app.services.tile_service import _palette
        idx = np.linspace(0.0, 1.0, 256)
        _ENHANCED_IR_LUT = _palette(idx.astype(np.float32), ENHANCED_IR_STOPS).reshape(256, 3)
    return _ENHANCED_IR_LUT


def apply_enhanced_ir(png_bytes: bytes) -> bytes:
    """Recolor a grayscale IR tile through the enhanced-IR LUT.

    GIBS normalizes each rendered frame independently, so a fixed curve
    under-flares on quiet scenes. A robust per-tile contrast stretch
    (p1–p99.5 -> full range) before the LUT restores the Windy-style pop;
    near-uniform tiles skip the stretch so they keep their natural tone.
    """
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    lum = np.asarray(img, dtype=np.float32).mean(axis=2)
    lo, hi = np.percentile(lum, [1.0, 99.5])
    if hi - lo >= 10.0:
        lum = (lum - lo) * (255.0 / (hi - lo))
    idx = np.clip(lum, 0, 255).astype(np.uint8)
    rgb = enhanced_ir_lut()[idx]
    alpha = np.full(idx.shape, 255, dtype=np.uint8)
    out = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"User-Agent": "ALERT/1.0 (live Himawari tile proxy)"},
            follow_redirects=True,
        )
    return _client


def _transparent_png() -> bytes:
    img = Image.fromarray(np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8), "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


TRANSPARENT_PNG = _transparent_png()


def _to_png(data: bytes) -> bytes:
    """Normalize any upstream raster (JPEG etc.) to PNG."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# Cached payloads carry a one-byte mode prefix so provenance survives
# round-trips through the cache ("L" live, "G" gap).
_MODE_LIVE = b"L"
_MODE_GAP = b"G"

# A 404 at the newest frame is often transient ingest lag, so it is
# cached only briefly; older frames are immutable and gaps there are
# cached for a full hour.
GAP_TTL_NEWEST_S = 180
GAP_TTL_ARCHIVED_S = 3600

# How many publication steps to walk back when the newest frame 404s.
NEWEST_FRAME_RETRIES = 3


def _tile_url(cfg: dict, stamp: str, z: int, x: int, y: int) -> str:
    return (f"{GIBS_BASE}/{cfg['layer']}/default/{stamp}/"
            f"{cfg['tms']}/{z}/{y}/{x}.{cfg['format']}")


def _shift_stamp(stamp: str, minutes: int) -> str | None:
    """Return `stamp` shifted by `minutes`, or None for date-only stamps."""
    try:
        dt = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    out = dt.replace(tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return out.strftime("%Y-%m-%dT%H:%M:%SZ")


async def get_gibs_tile(product_id: str, z: int, x: int, y: int,
                        time_str: str | None, cache,
                        palette: str | None = None) -> tuple[bytes, str]:
    """Fetch one live GIBS tile.

    Returns (bytes, source) with source in {"live", "gap", "fallback"}.
    palette="windy" applies the enhanced-IR LUT (clean infrared only);
    recolored tiles are cached under their own key so palettes never mix.
    """
    cfg = GIBS_PRODUCTS[product_id]
    if z > cfg["max_zoom"]:
        # Beyond the GIBS tile matrix: client-side over-zoom territory.
        return TRANSPARENT_PNG, "gap"
    enhance = palette == "windy" and product_id == "himawari-clean-ir"
    meta = PRODUCTS.get(product_id, {})
    step = int(meta.get("temporal_step_minutes", 10))
    newest = False
    if time_str:
        stamp = time_str
    else:
        lag = int(meta.get("publication_lag_minutes", 0))
        hours = 0.17 if step < 1440 else float(step) / 60.0
        stamp = TileService.available_times(product_id, hours=hours,
                                            step_min=step, lag_min=lag)[0]
        newest = True
    key = f"gibs:{product_id}:{stamp}:{z}:{x}:{y}"
    if enhance:
        key += ":windy"
    if cache is not None:
        cached = await cache.get(key)
        if cached is not None:
            if cached[:1] == _MODE_LIVE:
                return cached[1:], "live"
            return TRANSPARENT_PNG, "gap"

    async def _store(target: str, data: bytes) -> bytes:
        """Normalize + optionally recolor, then cache under the target frame."""
        if cfg["format"] != "png":
            data = _to_png(data)
        if enhance:
            data = apply_enhanced_ir(data)
        if cache is not None:
            ck = f"gibs:{product_id}:{target}:{z}:{x}:{y}"
            if enhance:
                ck += ":windy"
            await cache.set(ck, _MODE_LIVE + data, ttl=3 * 86400)
        return data

    try:
        resp = await _get_client().get(_tile_url(cfg, stamp, z, x, y))
    except httpx.HTTPError as exc:
        logger.warning("gibs unreachable (%s): %s", product_id, exc)
        fallback = await TileService(cache=None).get_tile(
            cfg["fallback"], z, x, y, time_str)
        if fallback is not None:
            data = apply_enhanced_ir(fallback) if enhance else fallback
            return data, "fallback"
        return TRANSPARENT_PNG, "gap"

    if resp.status_code == 200:
        return await _store(stamp, resp.content), "live"

    if resp.status_code == 404 and newest and step < 1440:
        # Fresh frames ingest level-by-level: top-zoom tiles can serve
        # 200 while parent levels still answer 404 for several minutes.
        # Walk back a few publication steps before declaring an honest
        # gap so a just-published frame does not render as holes.
        back = stamp
        for _ in range(NEWEST_FRAME_RETRIES):
            back = _shift_stamp(back, -step)
            if back is None:
                break
            try:
                older = await _get_client().get(_tile_url(cfg, back, z, x, y))
            except httpx.HTTPError:
                break
            if older.status_code == 200:
                data = await _store(back, older.content)
                # Also satisfy the originally requested key so concurrent
                # requests during ingest lag do not repeat the walk-back.
                if cache is not None:
                    await cache.set(key, _MODE_LIVE + data, ttl=3 * 86400)
                return data, "live"
            if older.status_code != 404:
                break

    if resp.status_code == 404:
        # Frame genuinely absent from the GIBS index (scan gap): honest blank.
        ttl = GAP_TTL_NEWEST_S if newest else GAP_TTL_ARCHIVED_S
        if cache is not None:
            await cache.set(key, _MODE_GAP, ttl=ttl)
        return TRANSPARENT_PNG, "gap"

    logger.warning("gibs http %s for %s", resp.status_code,
                   _tile_url(cfg, stamp, z, x, y))
    fallback = await TileService(cache=None).get_tile(cfg["fallback"], z, x, y, time_str)
    if fallback is not None:
        return fallback, "fallback"
    return TRANSPARENT_PNG, "gap"
