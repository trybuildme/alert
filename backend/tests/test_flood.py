"""Flood monitoring module tests.

Covers: risk-engine classification, store dedup/lifecycle, Open-Meteo
parsing, ingest validation + provider failure isolation, alert
generation/resolution, and the /api/flood surface.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.flood.engine import (
    RECOMMENDED_ACTIONS,
    assess_station,
    classify_metric,
    load_thresholds,
)
from app.flood.ingest import FloodIngestWorker
from app.flood.providers.open_meteo_rain import OpenMeteoRainProvider
from datetime import datetime, timedelta, timezone

from app.flood.store import FloodStore


# ---- engine ---------------------------------------------------------------

@pytest.fixture(scope="module")
def thresholds():
    return load_thresholds(None)


class TestClassification:
    def test_normal_below_all_thresholds(self, thresholds):
        assert classify_metric("rainfall_mm_h", 1.0, thresholds)[0] == "NORMAL"

    def test_advisory_watch_warning_critical_matrix(self, thresholds):
        assert classify_metric("rainfall_mm_h", 3.0, thresholds)[0] == "ADVISORY"
        assert classify_metric("rainfall_mm_h", 8.0, thresholds)[0] == "WATCH"
        assert classify_metric("rainfall_mm_h", 16.0, thresholds)[0] == "WARNING"
        assert classify_metric("rainfall_mm_h", 31.0, thresholds)[0] == "CRITICAL"

    def test_unknown_metric_returns_none(self, thresholds):
        assert classify_metric("nope", 5.0, thresholds) is None

    def test_disabled_thresholds_stay_normal(self, thresholds):
        # water_level_m bounds default to None -> never classifies above NORMAL
        assert classify_metric("water_level_m", 99.0, thresholds)[0] == "NORMAL"

    def test_assessment_picks_worst_level(self, thresholds):
        out = assess_station(
            [{"metric": "rainfall_mm_24h", "value": 35.0},
             {"metric": "rainfall_mm_h", "value": 8.0}],
            thresholds, "rainfall")
        assert out["level"] == "WATCH"
        assert len(out["reasons"]) == 2
        assert out["alert"]["threshold"] == 30.0

    def test_assessment_normal_has_no_alert(self, thresholds):
        out = assess_station([], thresholds, "rainfall")
        assert out["level"] == "NORMAL" and out["alert"] is None

    def test_every_level_has_recommended_action(self):
        for lvl in ("NORMAL", "ADVISORY", "WATCH", "WARNING", "CRITICAL"):
            assert RECOMMENDED_ACTIONS[lvl]

    def test_config_override_and_garbage(self, tmp_path, thresholds):
        cfg = tmp_path / "t.json"
        cfg.write_text('{"rainfall_mm_h": {"CRITICAL": 5}}')
        t = load_thresholds(str(cfg))
        assert classify_metric("rainfall_mm_h", 6.0, t)[0] == "CRITICAL"
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        with pytest.raises(ValueError):
            load_thresholds(str(bad))


# ---- store ------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    s = FloodStore(str(tmp_path / "flood.db"))
    s.upsert_stations([
        {"id": "rain-test", "name": "Test Rain", "kind": "rainfall",
         "latitude": 14.5, "longitude": 121.0, "provider": "open-meteo"},
        {"id": "wl-test", "name": "Test Gauge", "kind": "water_level",
         "latitude": 14.6, "longitude": 121.1, "provider": "none"},
    ])
    yield s
    s.close()


class TestStore:
    def test_observation_dedup(self, store):
        assert store.insert_observation("rain-test", "rainfall_mm_h",
                                        5.0, "2026-08-26T00:00:00Z",
                                        "open-meteo") is True
        assert store.insert_observation("rain-test", "rainfall_mm_h",
                                        5.0, "2026-08-26T00:00:00Z",
                                        "open-meteo") is False
        assert store.latest_observation("rain-test", "rainfall_mm_h")[
            "value"] == 5.0

    def test_timeseries_orders_and_windows(self, store):
        from datetime import datetime, timedelta, timezone
        def iso(hours_ago):
            return (datetime.now(timezone.utc)
                    - timedelta(hours=hours_ago)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
        for age, v in ((8, 1.0), (7, 2.0), (2, 3.0)):
            store.insert_observation("rain-test", "rainfall_mm_3h", v,
                                     iso(age), "open-meteo")
        series = store.timeseries("rain-test", "rainfall_mm_3h", hours=5)
        assert [(r["observed_at"], r["value"]) for r in series] == [
            (iso(2), 3.0)]   # only within the 5h window, ascending

    def test_alert_lifecycle(self, store):
        alert = {"id": "flood:wl-test", "station_id": "wl-test",
                 "level": "WATCH", "reason": "test", "measurement": 2.0,
                 "unit": "mm", "threshold": 1.0, "basis": "observed",
                 "source": "alert-flood-engine"}
        assert store.upsert_alert(alert) is True          # new
        assert store.upsert_alert({**alert}) is False      # same level: no-op
        alert2 = {**alert, "level": "WARNING"}
        assert store.upsert_alert(alert2) is False         # escalation updates in place
        levels = [a["level"] for a in store.active_alerts()]
        assert levels == ["WARNING"]
        store.resolve_alert("flood:wl-test")
        assert store.active_alerts() == []
        assert store.latest_alert_level("flood:wl-test") == "WARNING"


# ---- open-meteo provider ------------------------------------------------------

class TestOpenMeteoProvider:
    def test_parse_rejects_malformed(self):
        with pytest.raises(ValueError):
            OpenMeteoRainProvider.parse_payload({"hourly": {}})
        with pytest.raises(ValueError):
            OpenMeteoRainProvider.parse_payload({"hourly": {"time": ["x"],
                                                            "precipitation": []}})

    def test_derive_metrics_sums_windows(self):
        # 24 hourly samples ending NOW, oldest=24mm .. newest=1mm
        now = datetime.now(timezone.utc)
        hourly = {
            (now - timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M"): float(k + 1)
            for k in range(24)
        }
        obs = OpenMeteoRainProvider.derive_metrics(hourly)
        by_metric = {o["metric"]: o["value"] for o in obs}
        assert by_metric["rainfall_mm_h"] == 1.0            # newest hour
        assert by_metric["rainfall_mm_3h"] == 1 + 2 + 3     # rolling sum
        assert by_metric["rainfall_mm_24h"] == sum(range(1, 25))

    def test_null_hours_skipped_not_zero_filled(self):
        now = datetime.now(timezone.utc)
        hourly = {
            (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"): None,
            (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"): 3.0,
            now.strftime("%Y-%m-%dT%H:%M"): None,   # current partial hour
        }
        obs = OpenMeteoRainProvider.derive_metrics(hourly)
        by_metric = {o["metric"]: o["value"] for o in obs}
        assert by_metric["rainfall_mm_h"] == 3.0

    @pytest.mark.asyncio
    async def test_poll_isolates_per_station_failure(self, monkeypatch):
        stations = [
            {"id": "a", "name": "A", "kind": "rainfall", "latitude": 1.0,
             "longitude": 2.0, "provider": "open-meteo"},
            {"id": "b", "name": "B", "kind": "rainfall", "latitude": 3.0,
             "longitude": 4.0, "provider": "open-meteo"},
        ]
        provider = OpenMeteoRainProvider(stations)

        calls = {"n": 0}

        async def flaky_get(url, params=None):
            calls["n"] += 1
            if params["latitude"] == "1.0000":
                raise RuntimeError("network dead")

            class _Resp:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"hourly": {"time": ["2026-08-26T00:00"],
                                       "precipitation": [2.5]}}
            return _Resp()

        provider._client.get = flaky_get
        obs = await provider.poll()
        assert calls["n"] == 2                       # both attempted
        assert {o["station_id"] for o in obs} == {"b"}  # failed one isolated


# ---- ingest -------------------------------------------------------------------

def _worker(store, providers, **kw):
    return FloodIngestWorker(providers, store, **kw)


@pytest.mark.asyncio
async def test_ingest_validates_and_generates_alert(store):
    class GoodProvider:
        name = "good"

        async def poll(self):
            return [
                {"station_id": "rain-test", "metric": "rainfall_mm_h",
                 "value": 40.0, "observed_at": "2026-08-26T00:00:00Z",
                 "source": "good"},                      # -> CRITICAL
                {"station_id": "rain-test", "metric": "bogus",
                 "value": 1.0, "observed_at": "2026-08-26T00:00:00Z",
                 "source": "good"},                      # invalid metric
                {"station_id": "rain-test", "metric": "rainfall_mm_3h",
                 "value": -5.0, "observed_at": "2026-08-26T00:00:00Z",
                 "source": "good"},                      # negative
                {"station_id": "rain-test", "metric": "rainfall_mm_3h",
                 "value": 5.0, "observed_at": "not-a-timestamp",
                 "source": "good"},                      # bad ts
            ]

    fired = []
    worker = _worker(store, [GoodProvider()],
                     on_alert=lambda a: fired.append(a))
    totals = await worker.poll_once()
    stats = worker.stats["good"]
    assert stats["received"] == 4 and stats["invalid"] == 3
    assert totals["accepted"] == 1
    alerts = store.active_alerts()
    assert len(alerts) == 1 and alerts[0]["level"] == "CRITICAL"
    assert fired and fired[0]["level"] == "CRITICAL"
    assert "Evacuate" in fired[0]["recommended_action"]


@pytest.mark.asyncio
async def test_ingest_resolves_alert_when_back_to_normal(store):
    store.insert_observation("rain-test", "rainfall_mm_h", 40.0,
                             "2026-08-26T00:00:00Z", "x")
    store.upsert_alert({"id": "flood:rain-test", "station_id": "rain-test",
                        "level": "CRITICAL", "reason": "earlier",
                        "source": "x"})

    class CalmProvider:
        name = "calm"

        async def poll(self):
            return [{"station_id": "rain-test",
                     "metric": "rainfall_mm_h", "value": 0.0,
                     "observed_at": "2026-08-26T02:00:00Z", "source": "calm"}]

    await _worker(store, [CalmProvider()]).poll_once()
    assert store.active_alerts() == []


@pytest.mark.asyncio
async def test_provider_failure_does_not_block_others(store):
    class DeadProvider:
        name = "dead"

        async def poll(self):
            raise RuntimeError("down")

    class AliveProvider:
        name = "alive"

        async def poll(self):
            return [{"station_id": "rain-test", "metric": "rainfall_mm_h",
                     "value": 1.0, "observed_at":
                     "2026-08-26T03:00:00Z", "source": "alive"}]

    worker = _worker(store, [DeadProvider(), AliveProvider()])
    totals = await worker.poll_once()
    assert totals["accepted"] == 1
    assert worker.stats["dead"]["last_error"].startswith("RuntimeError")
    assert worker.stats["alive"]["last_error"] is None


# ---- API ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_flood_surfaces_real_data(client):
    r = client.get("/api/flood/stations")
    assert r.status_code == 200
    body = r.json()
    kinds = {f["properties"]["kind"] for f in body["features"]}
    assert {"rainfall", "water_level"} <= kinds
    rain_live = [f for f in body["features"]
                 if f["properties"]["data_status"] == "live"]
    # The worker polls on startup against the REAL Open-Meteo feed;
    # at least one rainfall station must have live data.
    assert rain_live, "expected live rainfall stations after startup poll"
    wl = [f for f in body["features"]
          if f["properties"]["kind"] == "water_level"]
    assert all(f["properties"]["data_status"] == "offline-awaiting-feed"
               for f in wl)


def test_api_flood_status_shape(client):
    body = client.get("/api/flood/status").json()
    assert set(body["levels"]) == {"NORMAL", "ADVISORY", "WATCH",
                                   "WARNING", "CRITICAL"}
    assert "basis_note" in body
    assert body["worker_health"]["providers"]["open-meteo"]


def test_api_flood_observations_404(client):
    assert client.get("/api/flood/observations/nope").status_code == 404
