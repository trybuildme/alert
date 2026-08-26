"""SQLite persistence for normalized hazard events (earthquakes today).

Deliberate choices:
  * stdlib sqlite3 — NOAH has no database layer; adding a Postgres
    container for one module violates the no-unnecessary-infrastructure
    rule. The schema below is deliberately PostGIS-shaped so a future
    migration is mechanical (see docs/earthquake/DATABASE.md).
  * WAL mode + one connection guarded by an RLock: the ingest worker and
    API handlers interleave, but write volume is tiny (poll every ~5 min).
  * Deduplication via UNIQUE(provider, provider_event_id) with
    INSERT OR IGNORE + UPDATE-on-magnitude-change semantics.
Spatial queries: bounding-box SQL prefilter on lat/lon indexes, then an
exact haversine refinement in Python for radius queries.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.hazards.base import HazardEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS earthquake_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    origin_time TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    depth_km REAL,
    magnitude REAL,
    magnitude_type TEXT,
    place TEXT,
    region TEXT,
    status TEXT,
    source_url TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, provider_event_id)
);
CREATE INDEX IF NOT EXISTS eq_origin_time_idx ON earthquake_events(origin_time);
CREATE INDEX IF NOT EXISTS eq_magnitude_idx ON earthquake_events(magnitude);
CREATE INDEX IF NOT EXISTS eq_depth_idx ON earthquake_events(depth_km);
CREATE INDEX IF NOT EXISTS eq_latlon_idx ON earthquake_events(latitude, longitude);
CREATE TABLE IF NOT EXISTS hazard_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class EarthquakeStore:
    """Persistence + query facade over earthquake_events."""

    def __init__(self, db_path: str):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- writes ------------------------------------------------------------

    def upsert_event(self, ev: HazardEvent) -> bool:
        """Insert or refresh an event. Returns True when the row is NEW.

        Known rows get their magnitude/status/place refreshed (USGS
        revises magnitudes), but updated_at only moves on real change."""
        now = _iso(datetime.now(timezone.utc))
        with self._lock:
            cur = self._conn.execute(
                "SELECT magnitude, status, place FROM earthquake_events "
                "WHERE provider=? AND provider_event_id=?",
                (ev.provider, ev.provider_event_id))
            existing = cur.fetchone()
            if existing is None:
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO earthquake_events "
                        "(provider, provider_event_id, origin_time, latitude,"
                        " longitude, depth_km, magnitude, magnitude_type,"
                        " place, region, status, source_url, raw_json,"
                        " created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                with self._conn:
                    self._conn.execute(
                        "UPDATE earthquake_events SET magnitude=?, status=?,"
                        " place=?, updated_at=? WHERE provider=? AND provider_event_id=?",
                        (ev.magnitude, ev.status, ev.place, now,
                         ev.provider, ev.provider_event_id))
            return False

    def record_alert(self, severity: str, rule_name: str, summary: str,
                     event_uid: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO hazard_alerts (created_at, severity, rule_name,"
                " summary, event_uid) VALUES (?,?,?,?,?)",
                (_iso(datetime.now(timezone.utc)), severity, rule_name,
                 summary, event_uid))

    def prune_alerts(self, older_than_days: int) -> int:
        """Delete hazard_alerts older than the retention window.
        Returns the number of rows removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM hazard_alerts WHERE created_at < ?",
                (_iso(cutoff),))
            return cur.rowcount

    # -- web push subscriptions ---------------------------------------------

    def save_subscription(self, endpoint: str, p256dh: str, auth: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO push_subscriptions (endpoint, p256dh, auth,"
                " created_at) VALUES (?,?,?,?)"
                " ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh,"
                " auth=excluded.auth",
                (endpoint, p256dh, auth, _iso(datetime.now(timezone.utc))))

    def delete_subscription(self, endpoint: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ?",
                (endpoint,))
            return cur.rowcount > 0

    def list_subscriptions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions"
            ).fetchall()
        return [{"endpoint": r["endpoint"], "p256dh": r["p256dh"],
                 "auth": r["auth"]} for r in rows]

    # -- reads -------------------------------------------------------------

    @staticmethod
    def _row_to_feature(row: sqlite3.Row) -> dict:
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
        """Server-side filtered, paginated GeoJSON FeatureCollection."""
        where, args = [], []
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=days))
        where.append("origin_time >= ?")
        args.append(cutoff)
        if min_magnitude is not None:
            where.append("magnitude >= ?")
            args.append(min_magnitude)
        if max_magnitude is not None:
            where.append("magnitude < ?")
            args.append(max_magnitude)
        if min_depth is not None:
            where.append("depth_km >= ?")
            args.append(min_depth)
        if max_depth is not None:
            where.append("depth_km <= ?")
            args.append(max_depth)
        if provider:
            where.append("provider = ?")
            args.append(provider)
        if bbox:
            w, s, e, n = bbox
            where.append("longitude >= ? AND longitude <= ?"
                         " AND latitude >= ? AND latitude <= ?")
            args.extend([w, e, s, n])
        cond = " AND ".join(where)
        with self._lock:
            total = self._conn.execute(
                f"SELECT COUNT(*) FROM earthquake_events WHERE {cond}",
                args).fetchone()[0]
            rows = self._conn.execute(
                f"SELECT * FROM earthquake_events WHERE {cond}"
                f" ORDER BY origin_time DESC LIMIT ? OFFSET ?",
                [*args, limit, offset]).fetchall()
        features = [self._row_to_feature(r) for r in rows]
        # Radius refinement helper piggybacks on query results client-side;
        # dedicated nearby() covers distance filtering.
        return {
            "type": "FeatureCollection",
            "features": features,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_by_provider_id(self, provider: str,
                           provider_event_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM earthquake_events WHERE provider=? AND"
                " provider_event_id=?",
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
        """Events within radius_km of a point (bbox prefilter + exact
        haversine), nearest first."""
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
        """Live dashboard numbers, computed in SQL from real rows."""
        now = datetime.now(timezone.utc)
        out: dict = {}
        with self._lock:
            def scalar(sql: str, args: tuple = ()) -> object:
                return self._conn.execute(sql, args).fetchone()[0]

            out["last_hour"] = scalar(
                "SELECT COUNT(*) FROM earthquake_events WHERE origin_time >= ?",
                (_iso(now - timedelta(hours=1)),))
            out["today"] = scalar(
                "SELECT COUNT(*) FROM earthquake_events WHERE origin_time >= ?",
                (_iso(now - timedelta(days=1)),))
            strongest = self._conn.execute(
                "SELECT provider, provider_event_id, magnitude, place,"
                " origin_time FROM earthquake_events WHERE origin_time >= ?"
                " ORDER BY magnitude DESC LIMIT 1",
                (_iso(now - timedelta(days=1)),)).fetchone()
            deepest = self._conn.execute(
                "SELECT depth_km, place, magnitude, origin_time FROM"
                " earthquake_events WHERE origin_time >= ? AND depth_km IS NOT NULL"
                " ORDER BY depth_km DESC LIMIT 1",
                (_iso(now - timedelta(days=1)),)).fetchone()

        def row_props(row: sqlite3.Row | None) -> dict | None:
            if row is None:
                return None
            return dict(row)

        out["strongest_24h"] = row_props(strongest)
        out["deepest_24h"] = row_props(deepest)

        # Magnitude histogram (real data, fixed M0.5-wide bins up to M9)
        hist = [0] * 18
        with self._lock:
            rows = self._conn.execute(
                "SELECT magnitude FROM earthquake_events WHERE origin_time >= ?"
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

        out["total_stored"] = scalar_count(self)
        return out


    # -- backend-agnostic helpers --------------------------------------------
    # PgHazardStore exposes the same methods so callers (e.g. /metrics)
    # never need to know which engine is underneath.

    def count_events(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM earthquake_events").fetchone()[0]

    def latest_updated_at(self) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(updated_at) FROM earthquake_events").fetchone()
        return row[0] if row else None


def scalar_count(store: EarthquakeStore) -> int:
    if hasattr(store, "count_events"):
        return store.count_events()
    with store._lock:
        return store._conn.execute(
            "SELECT COUNT(*) FROM earthquake_events").fetchone()[0]


def latest_updated_at(store: EarthquakeStore) -> str | None:
    if hasattr(store, "latest_updated_at"):
        return store.latest_updated_at()
    with store._lock:
        row = store._conn.execute(
            "SELECT MAX(updated_at) FROM earthquake_events").fetchone()
    return row[0] if row else None
