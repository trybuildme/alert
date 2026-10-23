# ALERT · Earthquake Intelligence Module — Architecture Assessment

**Status:** implemented as described here · **Date:** 2026-08-24
**Scope:** first module of a broader real-time geospatial hazard-intelligence
architecture (`app/hazards/`), designed so floods, typhoons, landslides,
volcanic activity, etc. can plug into the same provider → pipeline → API →
map skeleton.

---

## 1. Existing architecture (inspected 2026-08-24)

| Aspect | Finding |
|---|---|
| Frontend | React 18 + TypeScript + MapLibre GL JS v5 + Zustand; Vite build |
| Backend | FastAPI monolith (`app/main.py` lifespan), routers under `app/api/` |
| Services | httpx-based async providers (GIBS/Esri tile proxies, IBTrACS cyclones, Overpass OSM) |
| Database | **None.** No ORM, no Postgres, no migrations exist anywhere in the repo |
| Cache | Redis → filesystem → memory write-through tiers (`app/cache/redis_cache.py`) |
| Real-time | **None.** No WebSocket/SSE endpoints; frontend polls REST endpoints |
| Auth | None (single-user local deployment) |
| Workers | None; long-running behavior lives in FastAPI `lifespan` |
| Map layers | Registry pattern: `stores/index.ts INITIAL_LAYERS` + `LAYER_IDS` visibility groups + lazy GeoJSON sources (`useLayerVisibility.ts`) |
| Panels | Right-docked panels pattern (`CycloneForecastPanel`, `InspectPanel`) fed by Zustand UI state |
| Deployment | docker-compose (backend, nginx-frontend, redis) or bare uvicorn+Vite |
| Config | Hand-rolled `Settings` class reading `os.getenv` (`app/core/config.py`) |
| Tests | pytest, 77 passing; TestClient + `httpx.MockTransport` mocking convention |

## 2. Reusable components (no duplication)

* **Provider/poller pattern** — mirrors `cyclones.py` (`fetch_recent_fixes`,
  TTL caches, honest degradation) and `osm_features.py` (retry/backoff,
  disk cache).
* **GeoJSON FeatureCollection conventions** — properties-first design used by
  `/api/cyclones`.
* **Map layer registry** — new layer = entry in `INITIAL_LAYERS` +
  `LAYER_IDS` group + sources/layers in `useMap.ts`. No engine changes.
* **Panel pattern** — `EarthquakePanel` follows `CycloneForecastPanel`
  structure/styling.
* **Settings class** — earthquake env vars join `app/core/config.py`.

## 3. Key architectural decisions

1. **Storage: SQLite via stdlib `sqlite3`** — ALERT has *no* database;
   introducing PostgreSQL+PostGIS solely for this module would violate
   "no unnecessary second database / smallest coherent increment". SQLite WAL
   mode, single writer connection guarded by a lock, indexes on origin_time,
   magnitude, depth, provider_event_id. Spatial queries use bounding-box SQL
   prefilter + exact haversine refinement in Python. PostGIS upgrade path:
   `docs/earthquake/DATABASE.md` (schema is deliberately PostGIS-shaped).
2. **Real-time: SSE** (`GET /api/earthquakes/stream`) over WebSocket —
   one-way push fits the use case, works through the existing nginx config,
   auto-reconnects natively in browsers (`EventSource`). An in-process
   asyncio broadcast bus (`hazards/bus.py`) decouples producers (ingest,
   alerts) from consumers.
3. **Ingestion: asyncio task started in `lifespan`** — same lifecycle the app
   already uses for Redis warm-up. Interval/backoff/lookback configurable.
   No Celery/APScheduler.
4. **Providers: abstract base `HazardProvider`** returning normalized
   `HazardEvent` models. USGS implemented against the real FDSN GeoJSON feed;
   PHIVOLCS ships as a documented stub requiring configuration (no fabricated
   endpoints).
5. **Alerts:** rule list loaded from JSON env/path, evaluated after each
   ingestion batch; severities INFO→CRITICAL; results published on the bus
   and persisted. No siren coupling — notifications go through a
   `NotificationDispatcher` abstraction whose first channel is the dashboard
   itself.
6. **Honesty:** the system reports *detected events*, never forecasts or
   predictions; UI copy states this.

## 4. Integration points — files modified

| File | Change |
|---|---|
| `backend/app/main.py` | wire router + start/stop ingestion worker in lifespan |
| `backend/app/core/config.py` | `EARTHQUAKE_*` settings block |
| `frontend/src/stores/index.ts` | `earthquakes` layer registry entry + UI state for panel/filters |
| `frontend/src/hooks/useMap.ts` | `earthquakes` source + magnitude/depth-styled circle layers |
| `frontend/src/hooks/useLayerVisibility.ts` | visibility group mapping |

## 5. Files created

```
backend/app/hazards/__init__.py     package marker
backend/app/hazards/base.py         HazardEvent model, HazardProvider ABC, EventBus
backend/app/hazards/store.py        SQLite persistence + queries + stats
backend/app/hazards/providers/usgs.py
backend/app/hazards/providers/phivolcs.py   stub, requires configuration
backend/app/hazards/ingest.py       polling worker, dedup, health tracking
backend/app/hazards/alerts.py       rule engine + dispatcher abstraction
backend/app/api/earthquakes.py      REST + SSE router
backend/tests/test_earthquakes.py   provider/store/API/alert coverage
docs/earthquake/*.md                documentation set
frontend/src/hooks/useEarthquakes.ts  EventSource client + initial fetch + incremental merge
frontend/src/components/panels/EarthquakePanel.tsx
```

## 6. Dependencies required

None beyond current requirements.txt (stdlib `sqlite3`, `asyncio`, `json`;
httpx already present). Deliberately: no Kafka, no Celery, no PostGIS
container, no chart library (dashboard uses CSS bars).

## 7. Risks

| Risk | Mitigation |
|---|---|
| SQLite write contention under burst ingest | single connection + lock; writes batched per poll cycle |
| Overpass-style upstream rate limits | backoff + jitter, cached responses, health surfaced as STALE |
| SSE behind nginx buffering | `X-Accel-Buffering: no` header set; dev server unaffected |
| Thousands of historical features hurting the map | default map window bounded (last N days ≥ min mag); older data queryable via API only |
| No auth on alerting APIs | documented risk; local-trusted deployment assumption, same as every existing endpoint |
| PHIVOLCS has no stable public machine-readable API | provider stub requires explicit URL configuration; never fabricated |

## 8. Migration strategy

1. Ship additive-only changes; existing endpoints/layers untouched.
2. Earthquake subsystem lazily creates its SQLite file on first use.
3. Future PostGIS move: replay `store.py` schema into Postgres, swap the
   four store methods — provider/pipeline/API/frontend unchanged.
4. Future hazard modules reuse `base.HazardEvent/HazardProvider/EventBus`,
   `store.py` table-per-hazard pattern, `alerts.py` rules, and the SSE bus.

## 9. Out of scope for this increment (designed-for, not built)

3D globe (backend already serves clean GeoJSON; CesiumJS can consume it
later), historical replay UI (API time-window queries fully support it),
email/SMS dispatchers (abstraction + dashboard channel shipped), Web Push.
