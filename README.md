# ALERT

**Atmospheric & Landscape Emergency Response Tracker — Google Maps / Google Earth-style usability
with scientifically honest satellite data reporting.**

The map is the primary interface: a large, continuously zoomable MapLibre GL map with
dashboards and analytics surrounding it.

```
┌────────────────────────────────────────────────────────────────────┐
│  TopBar: search · base-map switcher · satellite products · 2D/3D   │
├──────────┬─────────────────────────────────────────────┬───────────┤
│  LAYERS  │                                             │  INSPECT  │
│  panel   │        MAPLIBRE GL JS (Web Mercator,        │  panel    │
│          │        globe projection for 3D mode)        │           │
│  DRAW &  │   XYZ tiles · GeoJSON · vector · raster     │  TIME     │
│  MEASURE │                                             │  MACHINE  │
└──────────┴─────────────────────────────────────────────┴───────────┘
         FastAPI tile service · Redis/filesystem/memory cache
```

## Quick start

### Docker

```bash
docker compose up --build
# Frontend  http://localhost:3010
# Backend   http://localhost:8002/docs
```

### Local development

```bash
# Backend (Python 3.12+)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8002

# Frontend (Node 20+)
cd frontend
npm install && npm run dev      # http://localhost:3010
```

Redis is optional at dev time — the cache degrades gracefully to filesystem +
in-memory layers. With Docker Compose, Redis runs at `localhost:6380`.

## Architecture

| Tier | Technology | Role |
|------|-----------|------|
| Browser | React 18 + TypeScript + MapLibre GL JS v5 + Zustand | Interactive map, layer control, time machine, drawing |
| Tile service | FastAPI + NumPy + Pillow | `/tiles/{product}/{z}/{x}/{y}.png` — generates only visible tiles |
| Cache | Redis → filesystem → in-memory (write-through, LRU) | User B gets User A's tile instantly |
| Imagery | Synthetic Himawari-class feeds + real Esri/EOX/NASA GIBS XYZ | Multi-resolution satellite layers |

### Data flow (requirement #2)

```
Satellite product (native projection)
   ↓  reprojected to EPSG:3857 tile pyramid
XYZ tile API  /tiles/{product}/{z}/{x}/{y}.png
   ↓  only tiles intersecting the viewport are requested
MapLibre GL JS  (client-side over-zoom beyond native level)
Browser
```

The browser never downloads a full raster — each pan/zoom requests the handful of
256×256 PNGs currently on screen.

## Satellite products & native resolution (#10, #11)

| Product | Satellite / sensor | Native res | Max native zoom | Temporal res |
|---------|--------------------|------------|-----------------|--------------|
| True Color · Live *(real)* | NASA Terra MODIS corrected reflectance (B1/4/3, 250 m) via NASA GIBS | 250 m | z9 | daily |
| Clean Infrared · Live *(real)* | Himawari-9 AHI B13 (10.4 µm) via NASA GIBS | 2 km | z6 | 10 min |
| Air Mass · Live *(real)* | Himawari-9 AHI RGB composite via NASA GIBS | 2 km | z6 | 10 min |
| Visible Red · Live *(real)* | Himawari-9 AHI B3 (0.64 µm) via NASA GIBS | 1 km | z7 | 10 min |
| True Color · Simulated | Himawari-9 AHI B1/2/3 *(synthetic)* | 1 km | z8 | 10 min |
| Infrared | Himawari-9 AHI B13 (10.4 µm) *(synthetic)* | 2 km | z7 | 10 min |
| Water Vapor | Himawari-9 AHI B08 (6.2 µm) *(synthetic)* | 2 km | z7 | 10 min |
| Cloud Temperature | Himawari-9 B13 derived *(synthetic)* | 2 km | z7 | 10 min |
| Elevation | SRTM-class DEM (synthetic) | 30 m class | z11 | static |
| Esri World Imagery *(real)* | Maxar composite | ~1 m | z18 | static mosaic |
| Sentinel-2 Cloudless *(real)* | Copernicus S2 | ~10 m | z13 | annual mosaic |

### Earthquake intelligence module (`docs/earthquake/`)

Real-time earthquake detection & monitoring — the first module of a broader
hazard-intelligence architecture. USGS FDSN feed ingested by a background
worker (configurable bbox/magnitude/interval, exponential backoff, provider
health), normalized + deduplicated into SQLite, pushed to the map over SSE,
and evaluated against configurable alert rules (M≥5/6/7 defaults, plus a
150 km radius around Aurora Province). Map layer is magnitude-scaled and
depth-colored; the **Quakes** panel shows LIVE/STALE provider health, live
statistics, magnitude histogram, filters and event details.

These are **detected events only** — the system does not forecast or predict
earthquakes. PHIVOLCS ships as a provider stub awaiting an official
machine-readable source; see `docs/earthquake/DATA-SOURCES.md`.

### Active cyclone tracks
`GET /api/cyclones` returns a GeoJSON FeatureCollection of storms active
in the last N days (default 7): one LineString of past positions plus a
latest-position Point per storm (wind kt, SSHS category, pressure,
distance to land). Data comes from NOAA's IBTrACS near-real-time
`ACTIVE` subset, cached server-side for 1 h and degraded honestly to an
empty set when NOAA NCEI is unreachable. Cadence disclosure: IBTrACS is
a best-track archive refreshed roughly three times weekly — it shows
where storms *have been* with agency-merged intensity, not operational
forecast cones. Toggle via **Layers → Cyclone Tracks**.

**PAGASA naming**: storms that enter the Philippine Area of Responsibility
carry the official PAGASA local name of their entry year's rotating set
(`year mod 4`, 25 regular + 10 auxiliary names, list as revised Jan 2022 /
Jan 2025). Assignment is chronological by PAR-entry order; because
IBTrACS exposes only the recent window, the sequence is an *estimate* —
the payload's `naming` field says so. Map labels lead with the PAGASA
name (`BASYANG (INTERNATIONAL)`) once assigned.

### Cyclone outlook, clouds & PAR

- **7-Day Outlook** (`GET /api/cyclones/forecast`): naive persistence
  extrapolation of best-track motion (OLS velocity over recent fixes,
  intensity slope clamped to ±2 kt/h with exponential damping) stepped
  every 6 h for `horizon_days`. Buckets are grouped by Philippine
  Standard Time date with PAGASA status (incl. Super Typhoon ≥100 kt)
  and Wind Signal No. per the 2022 TCWS revision. This is explicitly
  *not* an official PAGASA/JTWC forecast; panel and API say so.
- **Pulse & wind radius**: active storms breathe (two-phase ring,
  radius scaled by SSHS category) and carry a geodesic 48-gon extent
  polygon at max R34 when quadrant data exists.
- **Cyclone Clouds · Himawari-9 IR** (**Layers → under Cyclone
  Forecast**): live GIBS Clean IR canopy, latest published frame,
  refreshed on a 5-min cycle while visible; rendered above satellite
  rasters but below all vector overlays.
- **Philippine Area of Responsibility**: solid yellow boundary from
  PAGASA's official definition (5°N 115°E → 15°N 115°E → 21°N 120°E →
  25°N 120°E → 25°N 135°E → 5°N 135°E), toggleable via
  **Layers → Philippine Area of Responsibility**.

### Live GIBS proxy

The four `· Live` products are proxied through
`/tiles/{product}/{z}/{x}/{y}.png` from
`gibs.earthdata.nasa.gov` WMTS (EPSG:3857, 10-minute time dimension,
rolling ~23-day window). Every tile carries an `X-Alert-Source` header:

| Source | Meaning |
|--------|---------|
| `live` | Real GIBS bytes, cached 72 h (past frames are immutable) |
| `gap`  | Frame absent upstream (scan housekeeping window / outside disk) → transparent PNG, never synthetic filler |
| `fallback` | GIBS unreachable → synthetic generator output so the app keeps working offline |

The `/api/products/{id}/times` index applies a 40-minute publication lag
so the Time Machine never offers stamps that haven't been published yet.

Clean Infrared additionally accepts `&palette=windy` — a Windy-style
enhanced-IR recolor (near-black surface, white decks, cold tops flaring
yellow → orange → red → violet) computed server-side with a robust
per-tile contrast stretch. Qualitative by design: GIBS pre-renders its
own normalization, so exact Kelvin values are not recoverable; palettes
are cached separately from plain tiles.

Max-native-zoom follows the NASA GIBS convention (`log2(156543 m/px ÷ native res)`).
Beyond that level MapLibre over-zooms client-side and the **Resolution Indicator**
(bottom right) shows:

> *Viewing beyond native satellite resolution — imagery is over-zoomed, not new data.*

No artificial detail is implied by digital zoom.

### Esri placeholder handling & deep-zoom fallback

Esri World Imagery answers HTTP 200 with a baked-in placeholder JPEG
("Map data not yet available.") wherever coverage ends — typically z17–18 in rural
areas. ALERT proxies Esri tiles through `/tiles/esri/{z}/{x}/{y}.jpg`:

1. Each tile is fetched once, analyzed (tiny + near-uniform bright pixels = placeholder),
   and cached — real imagery **and** "empty" verdicts alike.
2. Placeholders are re-served as `404`, so MapLibre drops them.
3. While Esri is the active product, **Sentinel-2 Cloudless (~10 m)** renders beneath it;
   dropped tiles reveal over-zoomed Sentinel-2 instead of gray text.

Deep zoom therefore degrades to soft-but-real imagery, never fake detail.

## Zoom pyramid (#10)

| Zoom | Coverage | Example |
|------|----------|---------|
| 0–1 | Global | Earth disc (globe mode) |
| 2–5 | Country / archipelago | Philippines |
| 6–7 | Island group | Luzon |
| 7–9 | Region | Ilocos Region |
| 9–11 | Province | Ilocos Norte |
| 11–14 | Municipality | Laoag City |
| 14–19 | Barangay / farm | San Lorenzo, Paoay fields |

Administrative labels and boundaries fade in/out per zoom band so the map stays legible
at every level.

## Reprojection & georeferencing (#12, #13)

* The browser map is **EPSG:3857 (Web Mercator)**; all readouts convert to WGS84 lat/lon.
* Tiles are generated directly in Web Mercator tile space from a global lattice-noise
  field keyed by world-pixel coordinates, so every feature is anchored to the same
  geographic location at all zoom levels — imagery is never "stretched over the map".
* A production Himawari feed arrives in its native **geostationary projection**
  (CFAC/line-column or NSPERECT). The documented pipeline is:
  1. Acquire full-disk segment (HSD/HIMAWARI8 netCDF).
  2. Calibrate to reflectance/brightness temperature.
  3. Reproject geostationary → EPSG:4326 with GDAL (`gdalwarp -t_srs EPSG:4326`,
     using the satellite height/longitude projection parameters).
  4. Write **Cloud Optimized GeoTIFF**, then serve via TiTiler
     (`/tiles/{z}/{x}/{y}.png?url=...`) or `rio xyz` — drop-in replacements for this
     repo's synthetic generator.
* Dateline handling: XYZ x-indices wrap modulo `2^z`; the globe projection renders the
  antimeridian correctly in 3D mode.

## Feature map (spec → implementation)

| # | Requirement | Where |
|---|-------------|-------|
| 1 | Wheel zoom, drag pan, pinch, double-click, controls, scale bar, north, fullscreen | MapLibre controls + custom north indicator (`MapControls.tsx`) |
| 2 | Multi-resolution tiled imagery | `tile_service.py`, XYZ endpoint |
| 3 | Raster/vector/GeoJSON/WMS-ready stack | MapLibre sources in `useMap.ts` |
| 4 | PH drill-down workflow | Admin hierarchy + label zoom bands |
| 5 | Base-map switcher + independent satellite overlay | `TopBar.tsx`, `mapConfig.ts` |
| 6 | Layer panel: toggle, opacity, ordering, metadata, legend; last layer sequence (order/visibility/opacity) restored across reloads via localStorage (`noah.layers.v1`) | `LayerPanel.tsx`, `stores/index.ts` |
| 7 | Click-to-inspect | `InspectPanel.tsx` + `/api/inspect` |
| 8 | Time machine preserving extent during animation | `TimeMachine.tsx` |
| 9 | Preload + cache + crossfade animation | Image() preloading, `raster-fade-duration`, server cache |
| 10 | Deep zoom pyramid + honest max-native warning | Resolution indicator |
| 11 | Native resolution / scale / zoom display | `ResolutionIndicator.tsx` |
| 12–13 | Georeferencing & reprojection docs | This README |
| 14 | High-performance tile service | FastAPI + NumPy (~60 ms/tile) |
| 15 | Redis + FS + memory caching | `cache/redis_cache.py` |
| 16 | 3D Earth button (globe projection now, CesiumJS-compatible later) | `TopBar` 2D/3D toggle |
| 17 | Geographic search incl. coordinates | `SearchBox` + `/api/search` |
| 18 | Drawing tools with area/perimeter/center | `MeasurementPanel.tsx`, spherical-excess math |
| 19 | Farm workflow (fly-to, NDVI, weather, flood) | Farm click handler + inspect API |
| 20 | Map-first UX | App layout |

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests -q   # 65 tests
cd frontend && npx tsc && npm run build             # typecheck + production build
```

## Ports

| Service | Host port |
|---------|-----------|
| Frontend (dev) | 3010 |
| Backend | 8002 |
| Redis | 6380 |
