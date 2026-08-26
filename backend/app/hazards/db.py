"""Hazard-store factory: SQLite (default) or PostgreSQL via NOAH_DATABASE_URL.

The SQLite store remains the default — see the rationale in
app/hazards/store.py. Setting NOAH_DATABASE_URL to a postgres:// or
postgresql:// DSN switches every consumer (API, ingest worker, alerts,
push, metrics) to app.hazards.pg_store.PgHazardStore with no other
code changes. Migrate existing rows with
backend/scripts/migrate_sqlite_to_pg.py.
"""

from __future__ import annotations

import os

from app.hazards.store import EarthquakeStore


def is_postgres_dsn(url: str) -> bool:
    return url.strip().lower().startswith(("postgres://", "postgresql://"))


def open_store(sqlite_path: str) -> EarthquakeStore:
    """Return the configured hazard store for this deployment."""
    dsn = os.environ.get("NOAH_DATABASE_URL", "").strip()
    if dsn:
        from app.hazards.pg_store import PgHazardStore
        return PgHazardStore(dsn)  # type: ignore[return-value]
    return EarthquakeStore(sqlite_path)
