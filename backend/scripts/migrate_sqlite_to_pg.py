#!/usr/bin/env python3
"""One-shot migration: SQLite hazard store -> PostgreSQL/PostGIS.

Usage (from backend/):
    pip install -r requirements-postgres.txt
    export NOAH_DATABASE_URL=postgresql://noah:noah@localhost:5433/noah
    python scripts/migrate_sqlite_to_pg.py [--db data/earthquakes.db]

Copies earthquake_events, hazard_alerts and push_subscriptions into the
PostGIS schema created by PgHazardStore, then verifies row counts.
Idempotent per event: re-running upserts (no duplicates).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.hazards.db import is_postgres_dsn  # noqa: E402
from app.hazards.pg_store import PgHazardStore  # noqa: E402


def migrate(db_path: str, dsn: str) -> None:
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = PgHazardStore(dsn)

    events = src.execute(
        "SELECT provider, provider_event_id, origin_time, latitude, longitude,"
        " depth_km, magnitude, magnitude_type, place, region, status,"
        " source_url, raw_json, created_at, updated_at"
        " FROM earthquake_events").fetchall()
    for i in range(0, len(events), 500):
        with dst._lock, dst._conn.transaction():
            for r in events[i:i + 500]:
                exists = dst._conn.execute(
                    "SELECT 1 FROM earthquake_events WHERE provider=%s"
                    " AND provider_event_id=%s",
                    (r["provider"], r["provider_event_id"])).fetchone()
                if exists:
                    continue
                cols = ", ".join(r.keys())
                marks = ", ".join(["%s"] * len(r))
                dst._conn.execute(
                    f"INSERT INTO earthquake_events ({cols}) VALUES ({marks})",
                    tuple(r))
    print(f"earthquake_events: {len(events)} rows processed")

    alerts = src.execute(
        "SELECT created_at, severity, rule_name, summary, event_uid"
        " FROM hazard_alerts").fetchall()
    with dst._lock, dst._conn.transaction():
        for r in alerts:
            dst._conn.execute(
                "INSERT INTO hazard_alerts (created_at, severity, rule_name,"
                " summary, event_uid) VALUES (%s,%s,%s,%s,%s)", tuple(r))
    print(f"hazard_alerts: {len(alerts)} rows copied")

    subs = src.execute(
        "SELECT endpoint, p256dh, auth, created_at"
        " FROM push_subscriptions").fetchall()
    for r in subs:
        dst.save_subscription(r["endpoint"], r["p256dh"], r["auth"])
    print(f"push_subscriptions: {len(subs)} rows copied")

    stored = dst.count_events()
    print(f"verify: pg now holds {stored} events")
    assert stored >= len(events), "row-count mismatch after migration"

    dst.close()
    src.close()
    print("migration complete")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/earthquakes.db",
                    help="path to the SQLite store (default: %(default)s)")
    args = ap.parse_args()
    import os
    dsn = os.environ.get("NOAH_DATABASE_URL", "")
    if not is_postgres_dsn(dsn):
        ap.error("NOAH_DATABASE_URL must be a postgres:// or postgresql:// DSN")
    migrate(args.db, dsn.strip())


if __name__ == "__main__":
    main()
