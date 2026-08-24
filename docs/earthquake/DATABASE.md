# Database

SQLite (stdlib, WAL) at `NOAH_EQ_DB` (default `backend/data/earthquakes.db`),
created lazily on first start.

Tables:
- `earthquake_events` — normalized events, UNIQUE(provider, provider_event_id);
  indexes on origin_time, magnitude, depth_km, (latitude, longitude).
- `hazard_alerts` — fired alert decisions (severity, rule, summary, event uid).

Spatial strategy: bounding-box SQL prefilter → exact haversine refinement in
Python. PostGIS migration path: recreate table with
`geometry(Point, 4326)` (+ GiST index), translate bbox/radius queries to
ST_MakeEnvelope / ST_DWithin, swap the four methods in `store.py`. Providers,
pipeline, API shape and frontend need no changes.
