# Database

## Default: SQLite (stdlib, WAL)

`NOAH_EQ_DB` (default `backend/data/earthquakes.db`), created lazily on
first start.

Tables:
- `earthquake_events` — normalized events, UNIQUE(provider, provider_event_id);
  indexes on origin_time, magnitude, depth_km, (latitude, longitude).
- `hazard_alerts` — fired alert decisions (severity, rule, summary, event uid).
- `push_subscriptions` — web-push endpoints for the notification bell.

Spatial strategy: bounding-box SQL prefilter → exact haversine refinement in
Python.

## Optional: PostgreSQL / PostGIS

For multi-worker or multi-replica deployments (the in-process SQLite
store cannot be shared across processes), set:

```bash
NOAH_DATABASE_URL=postgresql://noah:noah@postgis:5432/noah   # postgres:// also accepted
```

`app/hazards/db.open_store()` then swaps every consumer (API, ingest
worker, alerts, push, `/metrics`) to `app.hazards.pg_store.PgHazardStore`
— same interface, no other code changes. The dependency is optional:
`pip install -r requirements-postgres.txt` (psycopg 3).

Behavior notes:
* Schema mirrors SQLite exactly; UNIQUE(provider, provider_event_id)
  keeps upsert/dedup semantics identical.
* With the PostGIS extension present, a generated `geography(Point,
  4326)` column + GiST index are added automatically and radius queries
  (`nearby()`) route through `ST_DWithin`/`ST_Distance`. Without it,
  the store falls back to the same bbox-prefilter + haversine path as
  SQLite. Results are equivalent either way.

Docker (opt-in):

```bash
docker compose --profile postgis up -d postgis      # postgis/postgis:16-3.5 on :5433
```

Migrating existing rows:

```bash
cd backend && pip install -r requirements-postgres.txt
export NOAH_DATABASE_URL=postgresql://noah:noah@localhost:5433/noah
python scripts/migrate_sqlite_to_pg.py              # idempotent per event
```

Tests for the dialect/factory logic (no live database required):
`backend/tests/test_pg_store.py`.
