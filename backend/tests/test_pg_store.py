"""Tests for the PostgreSQL/PostGIS migration path.

No live database required: we exercise the factory selection, DSN
detection, SQL-dialect statements against a fake connection, and the
backend-agnostic store helpers used by /metrics.
"""

from __future__ import annotations

import os
import sys
import threading
import types
from datetime import datetime, timezone
from unittest import mock

import pytest

from app.hazards.base import HazardEvent
from app.hazards.db import is_postgres_dsn, open_store
from app.hazards.pg_store import PgHazardStore, _PG_SCHEMA
from app.hazards.store import EarthquakeStore


# --- factory ------------------------------------------------------------

def test_is_postgres_dsn():
    assert is_postgres_dsn("postgresql://u:p@h:5432/alert")
    assert is_postgres_dsn("postgres://u:p@h/alert")
    assert is_postgres_dsn("  POSTGRESQL://u:p@h  ")
    assert not is_postgres_dsn("mysql://x/y")
    assert not is_postgres_dsn("")
    assert not is_postgres_dsn("/plain/path.db")


def test_open_store_defaults_to_sqlite(tmp_path):
    store = open_store(str(tmp_path / "eq.db"))
    assert isinstance(store, EarthquakeStore)
    with pytest.raises(AttributeError):
        _ = store.has_postgis  # sqlite store has no pg-specific flag
    store.close()


class _FakeCursor:
    def __init__(self):
        self.fetchone_value = None
        self.fetchall_value: list = []

    def fetchone(self):
        return self.fetchone_value

    def fetchall(self):
        return self.fetchall_value


class _FakePgConn:
    """Minimal psycopg connection double for schema-path tests."""

    def __init__(self):
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, args=()):
        cur = _FakeCursor()
        if "pg_extension" in sql:
            cur.fetchone_value = {"exists": False}
        elif "COUNT(*)" in sql:
            cur.fetchone_value = {"n": 0}
        if "SELECT" in sql and "ORDER BY origin_time DESC" in sql:
            cur.fetchall_value = []
        self.executed.append((sql, args))
        return cur

    def transaction(self):
        return mock.MagicMock()

    def close(self):
        pass


@pytest.fixture()
def fake_psycopg(monkeypatch):
    conn = _FakePgConn()
    module = types.ModuleType("psycopg")
    module.connect = lambda *a, **k: conn
    module.rows = types.SimpleNamespace(dict_row=object())
    monkeypatch.setitem(sys.modules, "psycopg", module)
    return conn


def test_open_store_switches_on_env(tmp_path, fake_psycopg):
    with mock.patch.dict(os.environ,
                         {"NOAH_DATABASE_URL": "postgresql://x/y"}):
        store = open_store(str(tmp_path / "ignored.db"))
    assert isinstance(store, PgHazardStore)
    assert store.has_postgis is False  # extension absent -> haversine fallback
    # Schema was applied on init.
    assert any("earthquake_events" in sql for sql, _ in fake_psycopg.executed)
    store.close()


def test_pg_upsert_and_nearby_contract(tmp_path, fake_psycopg, monkeypatch):
    """Without PostGIS, nearby() falls back to query()+haversine and
    upsert_event follows the same new/refresh contract as SQLite."""
    ev = HazardEvent(
        provider="usgs", provider_event_id="pg-test-2",
        origin_time=datetime.now(timezone.utc),
        latitude=15.2, longitude=122.5)
    store = PgHazardStore.__new__(PgHazardStore)  # skip real connect
    store._dsn = "postgresql://x"
    store._lock = threading.RLock()
    store._conn = fake_psycopg
    store.has_postgis = False
    assert store.upsert_event(ev) is True  # SELECT -> None -> INSERT branch
    nearby = store.nearby(15.2, 122.5, radius_km=100)
    assert nearby["type"] == "FeatureCollection"
    assert isinstance(store.count_events(), int)


# --- schema / dialect ----------------------------------------------------

def test_schema_uses_pg_identity_and_conflict():
    assert "GENERATED ALWAYS AS IDENTITY" in _PG_SCHEMA
    assert "UNIQUE (provider, provider_event_id)" in _PG_SCHEMA


def test_upsert_sql_is_paramstyle_and_idempotent(tmp_path):
    """The SQLite twin must produce identical rows for identical events;
    the PG upsert mirrors its WHERE/ON CONFLICT semantics by contract."""
    ev = HazardEvent(
        provider="usgs", provider_event_id="pg-test-1",
        origin_time=datetime.now(timezone.utc),
        latitude=15.2, longitude=122.5,
        depth_km=33.0, magnitude=5.1, magnitude_type="mww",
        place="Test", region="PH", status="reviewed",
        source_url="https://example.gov", raw_data={})
    # Contract check on the SQLite reference implementation.
    store = EarthquakeStore(str(tmp_path / "ref.db"))
    try:
        assert store.upsert_event(ev) is True
        assert store.upsert_event(ev) is False  # dedup on (provider, uid)
    finally:
        store.close()
