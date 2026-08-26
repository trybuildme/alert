# NOAH Flood Monitoring Module

Real-time flood monitoring and mapping as a first-class NOAH capability,
built on the existing hazards-module architecture.

## Data honesty ledger

| Component | Status | Source |
|---|---|---|
| Rainfall observations | **REAL** | Open-Meteo hourly precipitation at real PAGASA synoptic-station coordinates (`app/flood/providers/open_meteo_rain.py`) |
| Water-level gauges | **PLACEHOLDER** | Registry holds real gauge locations (Marikina system). PAGASA/DENR publish no open machine-readable feed; `pagasa_water.py` is a disabled adapter — stations report `offline-awaiting-feed`, never fabricated values |
| Satellite flood extent | **NOT WIRED** | No suitable public WMTS product identified; layer hooks exist. Awaiting provider decision |
| Flood hazard zones | **LEGACY DEMO** | The pre-existing `flood-risk` map layer is simulated (labeled in-UI). Authoritative PAGASA/MGB hazard GIS files can be ingested when obtained |
| Risk levels | **DERIVED (observed)** | NOAH's classification of observed rainfall — explicitly NOT official PAGASA warnings |
| Alerts | **REAL processing** | Threshold engine on real observations, persisted, dispatched through existing channels |

## Architecture / data flow

```
Open-Meteo (real)          future: PAGASA/DENR feeds, IoT sensors
        ↓                          ↓
   FloodProvider.poll()   (app/flood/providers/base.py protocol)
        ↓
  FloodIngestWorker.poll_once()            (app/flood/ingest.py)
    validate → normalize → dedup insert (UNIQUE station+metric+ts)
        ↓
   FloodStore (SQLite WAL, PostGIS-shaped)  (app/flood/store.py)
        ↓
   risk engine classify()                   (app/flood/engine.py)
        ↓
   flood_alerts table + NotificationDispatcher + bell/map layers
        ↓
   /api/flood/*  →  dashboard layers, popups, notifications
```

Worker runs every `FLOOD_POLL_INTERVAL` seconds inside the backend
lifespan; per-provider isolation means one dead feed never blocks others.
Retention: observations 90 d, resolved alerts 30 d (daily sweep).

## Database schema (backend/data/flood.db)

- `flood_stations(id PK, name, kind[rainfall|water_level], lat, lon,
  river_basin, provider, notes, created_at)`
- `flood_observations(id PK, station_id FK, metric[rainfall_mm_h|
  rainfall_mm_3h|rainfall_mm_24h|water_level_m], value, observed_at,
  ingested_at, source, quality[ok|estimated|stale|invalid],
  collection_method, UNIQUE(station_id, metric, observed_at))`
- `flood_alerts(id PK 'flood:<station_id>', station_id FK, level,
  reason, measurement, unit, threshold, basis, source,
  recommended_action, created_at, resolved_at)`

Indexes on kind, (station,metric,time desc), time, created_at.
PostGIS path identical to the earthquake module (`NOAH_DATABASE_URL`).

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/flood/stations?kind=` | GeoJSON stations with live status, latest mm/h (`mmh`,`mmhLabel` for styling), data_status (`live`/`offline-awaiting-feed`) |
| `GET /api/flood/observations/{id}?metric=&hours=` | Time-series per station (default 48 h) |
| `GET /api/flood/status` | Level counts, per-station level, active alerts, worker health |
| `GET /api/flood/alerts?limit=` | Recent alerts incl. active/resolved |

All reads are health-tier public (consistent with other NOAH surfaces);
there is no write endpoint — ingestion is server-side only, which closes
unauthorized sensor submissions by construction.

## Flood-risk logic & thresholds

Per-station worst-of across metrics; defaults (JSON-overridable via
`NOAH_FLOOD_THRESHOLDS_PATH`):

- mm/h: ADVISORY ≥2.5 · WATCH ≥7.5 · WARNING ≥15 · CRITICAL ≥30
- 3 h: 5 / 10 / 20 / 45
- 24 h: 15 / 30 / 60 / 100

Water-level thresholds intentionally `null` until real gauge datum
thresholds arrive per station. Every assessment carries `basis:
'observed'` and per-level recommended actions. Engine outputs are NOAH's
automated synthesis — not official PAGASA Alert Levels.

Alerts dedupe as one row per station (`flood:<station_id>`); level
escalations update in place and fire notifications; return to NORMAL
auto-resolves. Dispatch reuses the earthquake module's channels
(email/webhook/web-push when configured).

## Configuration / env vars

| Var | Default | Meaning |
|---|---|---|
| `FLOOD_ENABLED` | true | Module master switch |
| `NOAH_FLOOD_DB` | backend/data/flood.db | SQLite path |
| `FLOOD_POLL_INTERVAL` | 600 s | Provider poll cadence |
| `FLOOD_ALERT_ENABLED` | true | Notification dispatch |
| `NOAH_FLOOD_THRESHOLDS_PATH` | "" | JSON threshold overrides |
| `NOAH_FLOOD_PAGASA_URL` | "" | Reserved for authorized feed |

## GIS layers (all independently switchable)

- **Rain Stations · Live** (default ON): circles colored by mm/h vs
  thresholds, labels show latest rate
- **Water-Level Gauges**: gray markers, honestly offline
- **Flood Alerts · Live**: halo+marker per active alert, colored by level
- Click any marker → popup: readings w/ trend arrows, timestamp,
  source, quality, basin/provider attribution

Bell notifications: new/escalated flood alerts land unread (kind 💧),
24 h expiry applies.

## Deployment / monitoring / troubleshooting

- Runs inside the standard uvicorn/gunicorn container; no extra services
- Health: `/api/flood/status` → `worker_health.providers.<name>`
  (`last_error`, poll counts); Grafana alert rule candidates mirror the
  earthquake ones
- "Station shows offline": expected until an authorized water-level feed
  exists, or Open-Meteo unreachable — check worker `last_error`
- Stale timestamps: worker polls every 10 min; Open-Meteo hourly series
  lag up to ~1 h by nature of the source
