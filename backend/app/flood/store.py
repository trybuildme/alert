"""Flood monitoring persistence — SQLite WAL, PostGIS-shaped schema.

Follows app/hazards/store.py conventions:
  * stdlib sqlite3 + one connection guarded by RLock (write volume is
    tiny: stations poll on the order of minutes)
  * UNIQUE constraints carry dedup semantics
  * lat/lon columns + indexes so the PostGIS migration stays mechanical

Tables:
  flood_stations        curated monitoring points (rain / water_level)
  flood_observations    normalized measurements w/ quality metadata
  flood_alerts          threshold-crossing events (alert engine output)
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flood_stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('rainfall', 'water_level')),
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    river_basin TEXT,
    provider TEXT NOT NULL DEFAULT 'none',
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flood_stations_kind_idx ON flood_stations(kind);

CREATE TABLE IF NOT EXISTS flood_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL REFERENCES flood_stations(id),
    metric TEXT NOT NULL CHECK (metric IN ('rainfall_mm_h', 'rainfall_mm_3h',
                                           'rainfall_mm_24h', 'water_level_m')),
    value REAL NOT NULL,
    observed_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    source TEXT NOT NULL,
    quality TEXT NOT NULL DEFAULT 'ok'
                CHECK (quality IN ('ok', 'estimated', 'stale', 'invalid')),
    collection_method TEXT NOT NULL DEFAULT 'api_poll',
    UNIQUE(station_id, metric, observed_at)
);
CREATE INDEX IF NOT EXISTS flood_obs_station_time_idx
    ON flood_observations(station_id, metric, observed_at DESC);
CREATE INDEX IF NOT EXISTS flood_obs_time_idx ON flood_observations(observed_at);

CREATE TABLE IF NOT EXISTS flood_alerts (
    id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL REFERENCES flood_stations(id),
    level TEXT NOT NULL CHECK (level IN ('NORMAL', 'ADVISORY', 'WATCH',
                                         'WARNING', 'CRITICAL')),
    reason TEXT NOT NULL,
    measurement REAL,
    unit TEXT,
    threshold REAL,
    basis TEXT NOT NULL DEFAULT 'observed',
    source TEXT NOT NULL,
    recommended_action TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS flood_alerts_created_idx ON flood_alerts(created_at DESC);
"""


def _iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FloodStore:
    """Persistence + query facade for the flood module."""

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

    # -- stations -----------------------------------------------------------

    def upsert_stations(self, stations: list[dict]) -> int:
        """Idempotent registry sync from the curated list. Returns count."""
        now = _iso()
        with self._lock, self._conn:
            for s in stations:
                self._conn.execute(
                    "INSERT INTO flood_stations "
                    "(id, name, kind, latitude, longitude, river_basin,"
                    " provider, notes, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(id) DO UPDATE SET"
                    " name=excluded.name, latitude=excluded.latitude,"
                    " longitude=excluded.longitude, river_basin=excluded.river_basin,"
                    " provider=excluded.provider, notes=excluded.notes",
                    (s["id"], s["name"], s["kind"], float(s["latitude"]),
                     float(s["longitude"]), s.get("river_basin"),
                     s.get("provider", "none"), s.get("notes"), now))
        return len(stations)

    def stations(self, kind: str | None = None) -> list[dict]:
        sql = ("SELECT * FROM flood_stations"
               + (" WHERE kind=?" if kind else "") + " ORDER BY name")
        with self._lock:
            rows = self._conn.execute(
                sql, (kind,) if kind else ()).fetchall()
        return [dict(r) for r in rows]

    def get_station(self, station_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM flood_stations WHERE id=?",
                (station_id,)).fetchone()
        return dict(row) if row else None

    # -- observations ---------------------------------------------------------

    def insert_observation(
        self, station_id: str, metric: str, value: float,
        observed_at: str, source: str,
        quality: str = "ok",
        collection_method: str = "api_poll",
    ) -> bool:
        """Insert one normalized observation. Returns True when NEW
        (dedup key: station+metric+observed_at)."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO flood_observations "
                "(station_id, metric, value, observed_at, ingested_at,"
                " source, quality, collection_method)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (station_id, metric, float(value), observed_at, _iso(),
                 source, quality, collection_method))
            return cur.rowcount > 0

    def latest_observation(self, station_id: str, metric: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM flood_observations WHERE station_id=? AND metric=?"
                " ORDER BY observed_at DESC LIMIT 1",
                (station_id, metric)).fetchone()
        return dict(row) if row else None

    def timeseries(self, station_id: str, metric: str,
                   hours: int = 48) -> list[dict]:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(hours=hours))
        with self._lock:
            rows = self._conn.execute(
                "SELECT observed_at, value, quality, source"
                " FROM flood_observations WHERE station_id=? AND metric=?"
                " AND observed_at >= ? ORDER BY observed_at ASC",
                (station_id, metric, cutoff)).fetchall()
        return [dict(r) for r in rows]

    def prune_observations(self, keep_days: int = 90) -> int:
        cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=keep_days))
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM flood_observations WHERE observed_at < ?",
                (cutoff,))
            return cur.rowcount

    # -- alerts ---------------------------------------------------------------

    def upsert_alert(self, alert: dict) -> bool:
        """Insert or update an active alert. Returns True when NEW."""
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT level FROM flood_alerts WHERE id=?",
                (alert["id"],)).fetchone()
            if existing is not None:
                if existing["level"] != alert["level"]:
                    self._conn.execute(
                        "UPDATE flood_alerts SET level=?, reason=?,"
                        " measurement=?, threshold=?, created_at=?,"
                        " resolved_at=NULL WHERE id=?",
                        (alert["level"], alert["reason"],
                         alert.get("measurement"), alert.get("threshold"),
                         _iso(), alert["id"]))
                return False
            self._conn.execute(
                "INSERT INTO flood_alerts (id, station_id, level, reason,"
                " measurement, unit, threshold, basis, source,"
                " recommended_action, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (alert["id"], alert["station_id"], alert["level"],
                 alert["reason"], alert.get("measurement"), alert.get("unit"),
                 alert.get("threshold"), alert.get("basis", "observed"),
                 alert["source"], alert.get("recommended_action"), _iso()))
            return True

    def resolve_alert(self, alert_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE flood_alerts SET resolved_at=? WHERE id=?"
                " AND resolved_at IS NULL",
                (_iso(), alert_id))

    def active_alerts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM flood_alerts WHERE resolved_at IS NULL"
                " ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def latest_alert_level(self, alert_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT level FROM flood_alerts WHERE id=?",
                (alert_id,)).fetchone()
        return row["level"] if row else None

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM flood_alerts ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]

    def prune_alerts(self, older_than_days: int = 30) -> int:
        cutoff = _iso(datetime.now(timezone.utc)
                      - timedelta(days=older_than_days))
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM flood_alerts WHERE created_at < ?"
                " AND resolved_at IS NOT NULL", (cutoff,))
            return cur.rowcount

    # -- backend-agnostic helper (mirrors hazards/store.py) -------------------

    def count_events(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM flood_alerts").fetchone()[0]
