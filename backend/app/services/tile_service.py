"""
AURORA-GIS multi-resolution raster tile service.

Architecture (requirement #2/#14):

    Satellite Raster (Himawari-style products, synthetic here)
        -> Tile pyramid (XYZ / GoogleMapsCompatible scheme, EPSG:3857)
            -> /tiles/{product}/{z}/{x}/{y}.png
                -> Browser requests ONLY visible tiles

Each product declares its NATIVE spatial resolution and therefore the
maximum zoom level at which real information exists (GIBS convention:
1 km -> z8, 2 km -> z7, 250 m -> z9). Beyond that the client over-zooms;
the frontend displays a "beyond native resolution" warning (#10/#11).

Georeferencing (#12/#13): tiles are generated directly in Web Mercator
(EPSG:3857) tile space using global lattice noise keyed by world pixel
coordinates, so features stay anchored to the same geographic location
at every zoom level. A geostationary source (Himawari) would be
reprojected to EPSG:3857 upstream; see README "Reprojection pipeline".
"""

import hashlib
import io
import math
from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import Image

TILE_SIZE = 256


# --------------------------------------------------------------------------
# Deterministic global value-noise field (seamless across tile borders)
# --------------------------------------------------------------------------

def _lattice_grid(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """Vectorized integer hash over lattice coordinate arrays -> [0,1)."""
    h = (ix * 374761393 + iy * 668265263 + seed * 1013904223) & 0xFFFFFFFF
    h ^= h >> np.int64(13)
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> np.int64(16)
    return ((h & 0xFFFFFF).astype(np.float32)) / float(0xFFFFFF)


def value_noise(px: np.ndarray, py: np.ndarray, cell: int, seed: int) -> np.ndarray:
    """Bilinearly-interpolated value noise sampled at world pixel coords."""
    ix = px // cell
    iy = py // cell
    fx = (px - ix * cell).astype(np.float32) / cell
    fy = (py - iy * cell).astype(np.float32) / cell

    v00 = _lattice_grid(ix, iy, seed)
    v10 = _lattice_grid(ix + 1, iy, seed)
    v01 = _lattice_grid(ix, iy + 1, seed)
    v11 = _lattice_grid(ix + 1, iy + 1, seed)

    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    top = v00 + (v10 - v00) * sx
    bottom = v01 + (v11 - v01) * sx
    return top + (bottom - top) * sy


def fractal_noise(px: np.ndarray, py: np.ndarray, seed: int, octaves: int,
                  base_cell: int = 128) -> np.ndarray:
    """Fractal (fBm) noise; more octaves reveal finer detail at higher zoom."""
    total = np.zeros_like(px, dtype=np.float32)
    amplitude = 1.0
    norm = 0.0
    cell = base_cell
    for _ in range(octaves):
        total += value_noise(px, py, cell, seed) * amplitude
        norm += amplitude
        amplitude *= 0.55
        cell = max(2, cell // 2)
    return total / norm


def _seed_for(*parts) -> int:
    digest = hashlib.sha1(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _world_pixel_grids(z: int, x: int, y: int, drift_px: int = 0, size: int = TILE_SIZE):
    step = TILE_SIZE // size
    xs = x * TILE_SIZE + np.arange(0, TILE_SIZE, step, dtype=np.int64)[None, :]
    ys = y * TILE_SIZE + np.arange(0, TILE_SIZE, step, dtype=np.int64)[:, None] - drift_px
    return np.broadcast_to(xs, (size, size)), np.broadcast_to(ys, (size, size))


def _palette(field: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Map normalized field [0,1] through color stops -> (256,256,3) uint8."""
    out = np.zeros((*field.shape, 3), dtype=np.float32)
    positions = [p for p, _ in stops]
    colors = np.array([c for _, c in stops], dtype=np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(field, positions, colors[:, ch])
    return out.astype(np.uint8)


# Tropical easterly flow: cloud systems translate westward ~1.5 world-px
# per 10-min step at native resolution (~1 km/step at z8), matching the
# pace of real Himawari loops. Layers drift at slightly different speeds
# so consecutive frames evolve organically instead of sliding rigidly.
DRIFT_PX_PER_STEP = 1.5


def _advect(tmin: int) -> int:
    return int(round(tmin * DRIFT_PX_PER_STEP))


def _cloud_field(px, py, seed, tmin):
    """Coherent cloud cover field advected westward over time.

    Three scales: large masses (100-400 km systems) dominate so shapes read
    as weather; mid-level bands and fine wisps ride on slightly different
    advection speeds, producing believable frame-to-frame evolution.
    """
    dx = _advect(tmin)
    masses = fractal_noise(px - dx, py, seed, 3, base_cell=192)
    bands = fractal_noise(px - int(round(dx * 1.12)), py, seed ^ 0xB4D5, 2, base_cell=64)
    wisps = fractal_noise(px - int(round(dx * 0.92)), py, seed ^ 0xDE7A, 2, base_cell=24)
    f = np.clip(masses * 0.55 + bands * 0.28 + wisps * 0.22 - 0.06, 0, 1)
    return f * f * (3 - 2 * f)  # smoothstep: defined cloud edges


# --------------------------------------------------------------------------
# Product generators
# --------------------------------------------------------------------------

def _upsample(field: np.ndarray) -> np.ndarray:
    """Bilinear upscale of a half-res field back to full tile size."""
    if field.shape[0] == TILE_SIZE:
        return field
    im = Image.fromarray(field)
    return np.asarray(im.resize((TILE_SIZE, TILE_SIZE), Image.BILINEAR))


def _gen_true_color(z, x, y, tmin):
    px, py = _world_pixel_grids(z, x, y, size=128)
    octaves = min(6, z + 2)
    landmass = fractal_noise(px, py, 777001, min(4, octaves))
    terrain = fractal_noise(px, py, 777002, octaves)
    clouds = _cloud_field(px, py, 777003, tmin)

    ocean = terrain < 0.34 + (landmass - 0.5) * 0.12

    veg = _palette(np.clip(terrain * 1.2, 0, 1), [
        (0.00, (48, 110, 52)), (0.35, (74, 142, 66)), (0.55, (118, 158, 84)),
        (0.72, (168, 168, 108)), (0.88, (176, 152, 116)), (1.00, (198, 186, 160)),
    ])
    sea = _palette(np.clip((terrain - 0.1) * 1.6, 0, 1), [
        (0.00, (8, 24, 62)), (0.45, (14, 48, 102)), (0.80, (24, 82, 138)), (1.00, (46, 118, 168)),
    ])
    rgb = np.where(ocean[..., None], sea, veg)

    cloud_rgb = _palette(clouds, [
        (0.47, (200, 208, 216)), (0.55, (232, 236, 240)), (0.65, (255, 255, 255)),
    ])
    cmask = np.clip((clouds - 0.47) * 3.0, 0, 1)[..., None]
    rgb = (rgb * (1 - cmask) + cloud_rgb * cmask).astype(np.uint8)
    return _upsample(rgb), 255


def _gen_infrared(z, x, y, tmin):
    px, py = _world_pixel_grids(z, x, y, size=128)
    octaves = min(5, z + 2)
    clouds = _cloud_field(px, py, 888001, tmin)
    temps = fractal_noise(px, py, 888002, octaves)
    field = np.clip(clouds * 0.8 + temps * 0.25, 0, 1)
    rgb = _palette(field, [
        (0.00, (20, 20, 60)), (0.35, (70, 30, 110)), (0.55, (170, 60, 60)),
        (0.75, (235, 130, 40)), (0.90, (250, 220, 120)), (1.00, (255, 255, 255)),
    ])
    return _upsample(rgb), 255


def _gen_water_vapor(z, x, y, tmin):
    px, py = _world_pixel_grids(z, x, y, size=128)
    octaves = min(5, z + 2)
    dx = _advect(tmin)
    pxs = px - dx
    moisture = fractal_noise(pxs, py, 999001, octaves)
    streams = fractal_noise(pxs // 2, py * 2, 999002, max(2, octaves - 1))
    field = np.clip(moisture * 0.7 + streams * 0.4, 0, 1)
    rgb = _palette(field, [
        (0.00, (86, 20, 20)), (0.30, (150, 60, 30)), (0.50, (40, 70, 140)),
        (0.72, (30, 130, 200)), (0.90, (120, 200, 240)), (1.00, (230, 248, 255)),
    ])
    return _upsample(rgb), 255


def _gen_cloud_temp(z, x, y, tmin):
    px, py = _world_pixel_grids(z, x, y, size=128)
    octaves = min(5, z + 2)
    clouds = _cloud_field(px, py, 101001, tmin)
    height = fractal_noise(px, py, 101002, octaves)
    field = np.clip(clouds * height * 1.6, 0, 1)
    rgb = _palette(field, [
        (0.00, (255, 255, 255)), (0.25, (185, 225, 250)), (0.50, (90, 160, 230)),
        (0.72, (40, 80, 190)), (0.90, (30, 30, 140)), (1.00, (60, 10, 100)),
    ])
    return _upsample(rgb), 255


def _gen_elevation(z, x, y, tmin):
    px, py = _world_pixel_grids(z, x, y, size=128)
    octaves = min(7, z + 3)
    elev = fractal_noise(px, py, 202001, octaves)
    # Hillshade: gradient toward NW light
    dy, dx = np.gradient(elev)
    shade = np.clip(0.5 + (dx * -6.0 + dy * -6.0), 0, 1)
    field = np.clip(elev * 0.55 + shade * 0.45, 0, 1)
    rgb = _palette(field, [
        (0.00, (20, 44, 82)), (0.35, (58, 110, 74)), (0.55, (148, 148, 96)),
        (0.75, (172, 132, 92)), (0.90, (222, 222, 222)), (1.00, (255, 255, 255)),
    ])
    return _upsample(rgb), 255


GENERATORS = {
    "true-color": _gen_true_color,
    "infrared": _gen_infrared,
    "water-vapor": _gen_water_vapor,
    "cloud-temp": _gen_cloud_temp,
    "elevation": _gen_elevation,
}


# --------------------------------------------------------------------------
# Product registry (native resolution -> max native zoom, GIBS convention)
# --------------------------------------------------------------------------

PRODUCTS = {
    # ---- Live NASA GIBS feeds (proxied, real data) ----
    "modis-true-color": {
        "name": "True Color · Live",
        "satellite": "NASA Terra MODIS",
        "sensor": "Corrected reflectance (B1/4/3, 250 m)",
        "source": "gibs",
        "gibs_layer": "MODIS_Terra_CorrectedReflectance_TrueColor",
        "native_resolution_km": 0.25,
        "max_native_zoom": 9,
        "temporal_resolution": "daily",
        "temporal_step_minutes": 1440,
        "publication_lag_minutes": 360,
        "projection_source": "Polar-orbiting swath mosaic via GIBS",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": -180.0, "south": -85.0, "east": 180.0, "north": 85.0},
        "bands": ["red", "green", "blue"],
        "legend": {"description": "Real daily sunlight reflectance composite (clouds obscure the surface)", "stops": ["ocean", "vegetation", "bare soil", "cloud"]},
        "time_dependent": True,
    },
    "himawari-clean-ir": {
        "name": "Clean Infrared · Live",
        "satellite": "Himawari-9",
        "sensor": "AHI B13 (10.4 um)",
        "source": "gibs",
        "gibs_layer": "Himawari_AHI_Band13_Clean_Infrared",
        "native_resolution_km": 2.0,
        "max_native_zoom": 6,
        "temporal_resolution": "10 minutes",
        "publication_lag_minutes": 40,
        "projection_source": "Geostationary (Himawari FSD) via GIBS",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["brightness_temperature"],
        "legend": {"description": "Real cloud-top temperature (cold = bright)", "stops": ["warm surface", "mid cloud", "cold tops"]},
        "time_dependent": True,
    },
    "himawari-air-mass": {
        "name": "Air Mass · Live",
        "satellite": "Himawari-9",
        "sensor": "AHI RGB composite (6.2/7.3/9.7/10.4/12.4 um)",
        "source": "gibs",
        "gibs_layer": "Himawari_AHI_Air_Mass",
        "native_resolution_km": 2.0,
        "max_native_zoom": 6,
        "temporal_resolution": "10 minutes",
        "publication_lag_minutes": 40,
        "projection_source": "Geostationary (Himawari FSD) via GIBS",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["air_mass_rgb"],
        "legend": {"description": "Real air-mass RGB: green warm lows, blue cold highs, red dry stratosphere", "stops": ["warm moist air", "dry intrusion", "cold high"]},
        "time_dependent": True,
    },
    "himawari-visible-red": {
        "name": "Visible Red · Live",
        "satellite": "Himawari-9",
        "sensor": "AHI B3 (0.64 um)",
        "source": "gibs",
        "gibs_layer": "Himawari_AHI_Band3_Red_Visible_1km",
        "native_resolution_km": 1.0,
        "max_native_zoom": 7,
        "temporal_resolution": "10 minutes",
        "publication_lag_minutes": 40,
        "projection_source": "Geostationary (Himawari FSD) via GIBS",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["red_visible_reflectance"],
        "legend": {"description": "Real daytime visible reflectance (black at night)", "stops": ["low reflectance", "cloud / bright surface"]},
        "time_dependent": True,
    },
    # ---- Synthetic Himawari-class generators ----
    "true-color": {
        "name": "True Color",
        "satellite": "Himawari-9",
        "sensor": "AHI bands 1/2/3",
        "native_resolution_km": 1.0,
        "max_native_zoom": 8,
        "temporal_resolution": "10 minutes",
        "projection_source": "Geostationary (Himawari FSD)",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["red", "green", "blue"],
        "legend": {"description": "Sunlight reflectance composite", "stops": ["deep ocean", "shallow water", "vegetation", "bare soil", "cloud tops"]},
        "time_dependent": True,
    },
    "infrared": {
        "name": "Infrared",
        "satellite": "Himawari-9",
        "sensor": "AHI B13 (10.4 um)",
        "native_resolution_km": 2.0,
        "max_native_zoom": 7,
        "temporal_resolution": "10 minutes",
        "projection_source": "Geostationary (Himawari FSD)",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["brightness_temperature"],
        "legend": {"description": "Cloud-top temperature (cold = bright)", "stops": ["warm surface", "mid cloud", "cold tops"]},
        "time_dependent": True,
    },
    "water-vapor": {
        "name": "Water Vapor",
        "satellite": "Himawari-9",
        "sensor": "AHI B08 (6.2 um)",
        "native_resolution_km": 2.0,
        "max_native_zoom": 7,
        "temporal_resolution": "10 minutes",
        "projection_source": "Geostationary (Himawari FSD)",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["upper_tropospheric_humidity"],
        "legend": {"description": "Mid/upper-level moisture (dry = brown, moist = white)", "stops": ["dry", "moist", "saturated"]},
        "time_dependent": True,
    },
    "cloud-temp": {
        "name": "Cloud Temperature",
        "satellite": "Himawari-9",
        "sensor": "AHI B13 derived",
        "native_resolution_km": 2.0,
        "max_native_zoom": 7,
        "temporal_resolution": "10 minutes",
        "projection_source": "Geostationary (Himawari FSD)",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": 85.0, "south": -60.0, "east": 205.0, "north": 60.0},
        "bands": ["cloud_top_temperature"],
        "legend": {"description": "Deep convection (purple/blue = coldest, tallest)", "stops": ["low warm cloud", "tall cold cloud"]},
        "time_dependent": True,
    },
    "elevation": {
        "name": "Elevation",
        "satellite": "SRTM-class DEM",
        "sensor": "Synthetic DEM hillshade",
        "native_resolution_km": 0.03,
        "max_native_zoom": 11,
        "temporal_resolution": "static",
        "projection_source": "EPSG:4326",
        "projection_served": "EPSG:3857 (Web Mercator)",
        "bounds": {"west": -180.0, "south": -85.0, "east": 180.0, "north": 85.0},
        "bands": ["elevation"],
        "legend": {"description": "Hypsometric tint + NW hillshade", "stops": ["lowland", "upland", "peak"]},
        "time_dependent": False,
    },
}


class TileService:
    def __init__(self, cache=None):
        self.cache = cache

    @staticmethod
    def minutes_since_epoch(time_str: str | None) -> int:
        if not time_str:
            return 0
        try:
            dt = datetime.strptime(time_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
            epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return max(0, int((dt - epoch).total_seconds() // 600))
        except ValueError:
            return 0

    async def get_tile(self, product: str, z: int, x: int, y: int, time_str: str | None) -> bytes | None:
        if product not in GENERATORS:
            return None
        key = f"tile:{product}:{time_str or 'static'}:{z}:{x}:{y}"
        if self.cache is not None:
            cached = await self.cache.get(key)
            if cached is not None:
                return cached

        tmin = self.minutes_since_epoch(time_str) if PRODUCTS[product]["time_dependent"] else 0
        rgb, alpha = GENERATORS[product](z, x, y, tmin)
        img = Image.fromarray(np.dstack([rgb, np.full((TILE_SIZE, TILE_SIZE), alpha, dtype=np.uint8)]), "RGBA")

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False)
        data = buf.getvalue()
        if self.cache is not None:
            await self.cache.set(key, data)
        return data

    @staticmethod
    def available_times(product: str, hours: float = 24.0, step_min: int = 10,
                        lag_min: int = 0) -> list[str]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        # Publication lag: newest frames may not exist upstream yet
        # (GIBS Himawari publishes ~20-35 min after scan) — never offer
        # stamps that would render as gaps.
        now -= timedelta(minutes=lag_min)
        if step_min >= 1440:
            # Daily index (MODIS/VIIRS mosaics): date-only stamps,
            # newest published day first.
            count = max(1, int(hours * 60 // step_min))
            base = now.replace(hour=0, minute=0)
            return [(base - i * timedelta(days=1)).strftime("%Y-%m-%d")
                    for i in range(count)]
        now -= timedelta(minutes=now.minute % step_min)
        step = timedelta(minutes=step_min)
        count = int(hours * 60 // step_min)
        return [(now - i * step).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(count)]

    @staticmethod
    def product_metadata(product: str) -> dict | None:
        meta = PRODUCTS.get(product)
        if meta is None:
            return None
        out = dict(meta)
        out["id"] = product
        out["tile_url_template"] = f"/tiles/{product}/{{z}}/{{x}}/{{y}}.png"
        return out
