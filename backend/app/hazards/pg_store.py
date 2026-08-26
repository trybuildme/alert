"""PostgreSQL / PostGIS backend for normalized hazard events.

This is the migration path documented in docs/earthquake/DATABASE.md:
NOAH's default store is stdlib SQLite (WAL) because one module never
justifies a database container. When NOAH is scaled out (multiple
workers/replicas sharing state), set NOAH_DATABASE_URL to a postgres
DSN and this store takes over — the public interface is identical to
app.hazards.store.EarthquakeStore, so main.py, ingest workers, API
handlers and metrics need no changes.

Design notes:
  * psycopg 3 (`pip install -r requirements-postgres.txt`), lazy
    imported so the dependency stays optional for SQLite deployments.
  * Schema mirrors earthquake_events exactly; UNIQUE(provider,
    provider_event_id) carries over, so upsert semantics are
    unchanged (INSERT ... ON CONFLICT).
  * When the PostGIS extension is present we add a geography(Point)
    column + GiST index and route radius queries through ST_DWithin.
    Without it, we fall back to the same bounding-box prefilter +
    exact haversine refinement SQLite uses — correct either way.
  * One pooled connection guarded by an RLock, matching the SQLite
    store's threading model (write volume is tiny: poll every ~5 min).
"""

from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timedelta, timezone

from app.hazards.base import HazardEvent
from app.hazards.store import _iso

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS earthquake_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    origin_time TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    depth_km DOUBLE PRECISION,
    magnitude DOUBLE PRECISION,
    magnitude_type TEXT,
    place TEXT,
    region TEXT,
    status TEXT,
    source_url TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT earthquake_events_provider_uid UNIQUE (provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS eq_origin_time_idx ON earthquake_events(origin_time);
CREATE INDEX IF NOT EXISTS eq_magnitude_idx ON earthquake_events(magnitude);
CREATE INDEX IF NOT EXISTS eq_depth_idx ON earthquake_events(depth_km);
CREATE TABLE IF NOT EXISTS hazard_alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TEXT NOT NULL,
    severity TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    event_uid TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint TEXT PRIMARY KEY,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_POSTGIS_DDL = """
ALTER TABLE earthquake_events ADD COLUMN IF NOT EXISTS
    geom geography(Point, 4326)
    GENERATED ALWAYS AS
        (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED;
CREATE INDEX IF NOT EXISTS eq_geom_idx ON earthquake_events USING GIST(geom);
"""


class PgHazardStore:
    """Drop-in PostgreSQL replacement for EarthquakeStore."""

    def __init__(self, dsn: str):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - guard rail
            raise RuntimeError(
                "NOAH_DATABASE_URL is set but psycopg is not installed. "
                "Run: pip install -r requirements-postgres.txt") from exc
        self._dsn = dsn
        self._lock = threading.RLock()
        self._conn = psycopg.connect(dsn, row_factory=psycopg.rows.dict_row)
        # Autocommit is essential: psycopg3 opens an implicit transaction
        # for any bare execute() and leaves it open. With the default
        # autocommit=False, our later `with conn.transaction()` write
        # blocks degenerate into SAVEPOINTs inside that never-ending
        # implicit transaction — nothing would ever COMMIT and other
        # sessions (and /metrics, replicas) see zero rows.
        self._conn.autocommit = True
        with self._lock, self._conn.transaction():
            self._conn.execute(_PG_SCHEMA)
        self.has_postgis = self._detect_postgis()
        if self.has_postgis:
            with self._lock, self._conn.transaction():
                self._conn.execute(_POSTGIS_DDL)

    def _detect_postgis(self) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis')"
            ).fetchone()
        return bool(row["exists"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- writes -------------------------------------------------------------

    def upsert_event(self, ev: HazardEvent) -> bool:
        """Insert or refresh an event; returns True when the row is NEW."""
        now = _iso(datetime.now(timezone.utc))
        with self._lock, self._conn.transaction():
            cur = self._conn.execute(
                "SELECT magnitude, status, place FROM earthquake_events "
                "WHERE provider=%s AND provider_event_id=%s",
                (ev.provider, ev.provider_event_id))
            existing = cur.fetchone()
            if existing is None:
                self._conn.execute(
                    "INSERT INTO earthquake_events "
                    "(provider, provider_event_id, origin_time, latitude,"
                    " longitude, depth_km, magnitude, magnitude_type,"
                    " place, region, status, source_url, raw_json,"
                    " created_at, updated_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (ev.provider, ev.provider_event_id, _iso(ev.origin_time),
                     float(ev.latitude), float(ev.longitude), ev.depth_km,
                     ev.magnitude, ev.magnitude_type, ev.place, ev.region,
                     ev.status, ev.source_url,
                     json.dumps(ev.raw_data)[:64_000], now, now))
                return True
            changed = (existing["magnitude"] != ev.magnitude
                       or existing["status"] != ev.status
                       or existing["place"] != ev.place)
            if changed:
                self._conn.execute(
                    "UPDATE earthquake_events SET magnitude=%s, status=%s,"
                    " place=%s, updated_at=%s WHERE provider=%s AND provider_event_id=%s",
                    (ev.magnitude, ev.status, ev.place, now,
                     ev.provider, ev.provider_event_id))
            return False

    def record_alert(self, severity: str, rule_name: str, summary: str,
                     event_uid: str) -> None:
        with self._lock, self._conn.transaction():
            self._conn.execute(
                "INSERT INTO hazard_alerts (created_at, severity, rule_name,"
                " summary, event_uid) VALUES (%s,%s,%s,%s,%s)",
                (_iso(datetime.now(timezone.utc)), severity, rule_name,
                 summary, event_uid))

    def prune_alerts(self, older_than_days: int) -> int:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=older_than_days))
        with self._lock, self._conn.transaction():
            cur = self._conn.execute(
                "DELETE FROM hazard_alerts WHERE created_at < %s", (cutoff,))
            return cur.rowcount

    # -- web push subscriptions ----------------------------------------------

    def save_subscription(self, endpoint: str, p256dh: str, auth: str) -> None:
        with self._lock, self._conn.transaction():
            self._conn.execute(
                "INSERT INTO push_subscriptions (endpoint, p256dh, auth,"
                " created_at) VALUES (%s,%s,%s,%s)"
                " ON CONFLICT(endpoint) DO UPDATE SET"
                " p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth",
                (endpoint, p256dh, auth, _iso(datetime.now(timezone.utc))))

    def delete_subscription(self, endpoint: str) -> bool:
        with self._lock, self._conn.transaction():
            cur = self._conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint=%s", (endpoint,))
            return cur.rowcount > 0

    def list_subscriptions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions").fetchall()
        return [{"endpoint": r["endpoint"], "p256dh": r["p256dh"],
                 "auth": r["auth"]} for r in rows]

    # -- reads ---------------------------------------------------------------

    @staticmethod
    def _row_to_feature(row: dict) -> dict:
        return {
            "type": "Feature",
            "id": f"{row['provider']}:{row['provider_event_id']}",
            "properties": {
                "uid": f"{row['provider']}:{row['provider_event_id']}",
                "provider": row["provider"],
                "provider_event_id": row["provider_event_id"],
                "origin_time": row["origin_time"],
                "magnitude": row["magnitude"],
                "magnitude_type": row["magnitude_type"],
                "depth_km": row["depth_km"],
                "place": row["place"],
                "region": row["region"],
                "status": row["status"],
                "source_url": row["source_url"],
                "detected_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
            "geometry": {"type": "Point",
                         "coordinates": [row["longitude"], row["latitude"]]},
        }

    def query(self, days: int = 30, min_magnitude: float | None = None,
              max_magnitude: float | None = None, min_depth: float | None = None,
              max_depth: float | None = None, provider: str | None = None,
              bbox: tuple[float, float, float, float] | None = None,
              limit: int = 2000, offset: int = 0) -> dict:
        where: list[str] = ["origin_time >= %s"]
        args: list = [_iso(datetime.now(timezone.utc) - timedelta(days=days))]
        if min_magnitude is not None:
            where.append("magnitude >= %s")
            args.append(min_magnitude)
        if max_magnitude is not None:
            where.append("magnitude < %s")
            args.append(max_magnitude)
        if min_depth is not None:
            where.append("depth_km >= %s")
            args.append(min_depth)
        if max_depth is not None:
            where.append("depth_km <= %s")
            args.append(max_depth)
        if provider:
            where.append("provider = %s")
            args.append(provider)
        if bbox:
            w, s, e, n = bbox
            where.append("longitude >= %s AND longitude <= %s"
                         " AND latitude >= %s AND latitude <= %s")
            args.extend([w, e, s, n])
        cond = " AND ".join(where)
        cols = ("provider, provider_event_id, origin_time, latitude,"
                " longitude, depth_km, magnitude, magnitude_type, place,"
                " region, status, source_url, created_at, updated_at")
        with self._lock:
            total = self._conn.execute(
                f"SELECT COUNT(*) AS n FROM earthquake_events WHERE {cond}",
                args).fetchone()["n"]
            rows = self._conn.execute(
                f"SELECT {cols} FROM earthquake_events WHERE {cond}"
                f" ORDER BY origin_time DESC LIMIT %s OFFSET %s",
                [*args, limit, offset]).fetchall()
        return {
            "type": "FeatureCollection",
            "features": [self._row_to_feature(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_by_provider_id(self, provider: str,
                           provider_event_id: str) -> dict | None:
        cols = "*"
        with self._lock:
            row = self._conn.execute(
                f"SELECT {cols} FROM earthquake_events WHERE provider=%s"
                " AND provider_event_id=%s",
                (provider, provider_event_id)).fetchone()
        return self._row_to_feature(row) if row else None

    def haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = p2 - p1
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    def nearby(self, latitude: float, longitude: float, radius_km: float,
               days: int = 30, min_magnitude: float | None = None,
               limit: int = 100) -> dict:
        """Events within radius_km of a point, nearest first.

        With PostGIS: single ST_DWithin query against the geography
        index (true great-circle distance). Without: the SQLite path's
        bbox prefilter + exact haversine refinement."""
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        if self.has_postgis:
            sql = (
                "SELECT provider, provider_event_id, origin_time, latitude,"
                " longitude, depth_km, magnitude, magnitude_type, place,"
                " region, status, source_url, created_at, updated_at,"
                " ST_Distance(geom,"
                " ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)/1000 AS distance_km"
                " FROM earthquake_events WHERE origin_time >= %s"
                " AND ST_DWithin(geom,"
                " ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)")
            args: list = [longitude, latitude, cutoff,
                          longitude, latitude, radius_km * 1000]
            if min_magnitude is not None:
                sql += " AND magnitude >= %s"
                args.append(min_magnitude)
            sql += " ORDER BY distance_km LIMIT %s"
            args.append(limit)
            with self._lock:
                rows = self._conn.execute(sql, args).fetchall()
            hits = []
            for r in rows:
                feat = self._row_to_feature(r)
                feat["properties"]["distance_km"] = round(r["distance_km"], 1)
                hits.append(feat)
            return {"type": "FeatureCollection", "features": hits,
                    "total": len(hits)}

        # No PostGIS: identical semantics to the SQLite store.
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * max(math.cos(math.radians(latitude)), 0.01))
        pre = self.query(days=days, min_magnitude=min_magnitude,
                         bbox=(longitude - dlon, latitude - dlat,
                               longitude + dlon, latitude + dlat),
                         limit=5000)
        hits = []
        for feat in pre["features"]:
            lon, lat = feat["geometry"]["coordinates"]
            dist = self.haversine_km(latitude, longitude, lat, lon)
            if dist <= radius_km:
                feat["properties"]["distance_km"] = round(dist, 1)
                hits.append(feat)
        hits.sort(key=lambda f: f["properties"]["distance_km"])
        return {"type": "FeatureCollection", "features": hits[:limit],
                "total": len(hits)}

    def statistics(self, reference_point: tuple[float, float] | None = None,
                   reference_radius_km: float = 150.0) -> dict:
        now = datetime.now(timezone.utc)
        out: dict = {}
        with self._lock:
            def scalar(sql: str, args: tuple = ()):
                return self._conn.execute(sql, args).fetchone()["n"]

            out["last_hour"] = scalar(
                "SELECT COUNT(*) AS n FROM earthquake_events WHERE origin_time >= %s",
                (_iso(now - timedelta(hours=1)),))
            out["today"] = scalar(
                "SELECT COUNT(*) AS n FROM earthquake_events WHERE origin_time >= %s",
                (_iso(now - timedelta(days=1)),))
            strongest = self._conn.execute(
                "SELECT provider, provider_event_id, magnitude, place,"
                " origin_time FROM earthquake_events WHERE origin_time >= %s"
                " ORDER BY magnitude DESC NULLS LAST LIMIT 1",
                (_iso(now - timedelta(days=1)),)).fetchone()
            deepest = self._conn.execute(
                "SELECT depth_km, place, magnitude, origin_time FROM"
                " earthquake_events WHERE origin_time >= %s AND depth_km IS NOT NULL"
                " ORDER BY depth_km DESC NULLS LAST LIMIT 1",
                (_iso(now - timedelta(days=1)),)).fetchone()

        out["strongest_24h"] = dict(strongest) if strongest else None
        out["deepest_24h"] = dict(deepest) if deepest else None

        hist = [0] * 18
        with self._lock:
            rows = self._conn.execute(
                "SELECT magnitude FROM earthquake_events WHERE origin_time >= %s"
                " AND magnitude IS NOT NULL",
                (_iso(now - timedelta(days=7)),)).fetchall()
        for r in rows:
            idx = int(min(max((r["magnitude"] - 0) / 0.5, 0), 17))
            hist[idx] += 1
        out["magnitude_histogram_7d"] = [
            {"bin_low": round(i * 0.5, 1),
             "bin_high": round(i * 0.5 + 0.5, 1), "count": c}
            for i, c in enumerate(hist)]

        if reference_point:
            near = self.nearby(reference_point[0], reference_point[1],
                               reference_radius_km, days=7, limit=1)
            out["nearest_reference"] = (
                near["features"][0]["properties"] if near["features"] else None)
            within = self.nearby(reference_point[0], reference_point[1],
                                 reference_radius_km, days=1)
            out["reference_region_last_24h"] = len(within["features"])

        out["total_stored"] = self.count_events()
        return out

    def count_events(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) AS n FROM earthquake_events").fetchone()["n"]

    def latest_updated_at(self) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(updated_at) AS m FROM earthquake_events").fetchone()
        return row["m"]
