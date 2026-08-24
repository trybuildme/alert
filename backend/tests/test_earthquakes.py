"""Earthquake intelligence module tests: provider normalization,
dedup/persistence, spatial queries, REST API, SSE bus, alert engine."""

import asyncio
import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.hazards.alerts import evaluate_event, load_rules
from app.hazards.base import EventBus, HazardEvent
from app.hazards.ingest import IngestWorker
from app.hazards.providers.usgs import parse_usgs_feature
from app.hazards.store import EarthquakeStore
from app.main import app


# ---- fixtures -------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    s = EarthquakeStore(str(tmp_path / "eq.db"))
    yield s
    s.close()


def _usgs_feature(fid="us2000abc1", mag=5.4, lon=121.5, lat=15.2, depth=42.0,
                  place="52 km NE of Baler, Philippines", time_ms=1_760_000_000_000):
    return {
        "id": fid,
        "properties": {"mag": mag, "magType": "mb", "place": place,
                       "time": time_ms, "status": "reviewed",
                       "url": "https://earthquake.usgs.gov/x"},
        "geometry": {"coordinates": [lon, lat, depth]},
    }


def _event(provider="usgs", pid="p1", mag=5.0, lat=15.8, lon=121.6,
           depth=30.0) -> HazardEvent:
    from datetime import datetime, timezone
    return HazardEvent(
        provider=provider, provider_event_id=pid,
        origin_time=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        latitude=lat, longitude=lon, depth_km=depth, magnitude=mag,
        magnitude_type="mb", place="near Aurora", region="Philippines",
        status="reviewed", raw_data={})


# ---- provider normalization ----------------------------------------------

def test_parse_valid_usgs_feature():
    ev, err = parse_usgs_feature(_usgs_feature())
    assert err is None and ev is not None
    assert ev.provider == "usgs"
    assert ev.magnitude == 5.4
    assert ev.depth_km == 42.0
    assert ev.region == "Philippines"
    problems = ev.validate()
    assert problems == []


@pytest.mark.parametrize("mutate,why", [
    (lambda f: f["geometry"].update(coordinates=[]), "missing coordinates"),
    (lambda f: f["properties"].update(time=None), "missing origin time"),
    (lambda f: f.update(id=""), "missing event id"),
    (lambda f: f["properties"].update(mag=None), None),   # mag optional
])
def test_parse_malformed_features(mutate, why):
    feat = _usgs_feature()
    mutate(feat)
    ev, err = parse_usgs_feature(feat)
    if why is None:
        assert ev is not None          # missing magnitude is tolerated
    else:
        assert ev is None and why in (err or "")


def test_parse_rejects_out_of_range_coordinates():
    ev, err = parse_usgs_feature(_usgs_feature(lat=999.0))
    assert ev is None and "out of range" in err


def test_duplicate_detection_same_id(store):
    ev = _event()
    assert store.upsert_event(ev) is True       # new
    assert store.upsert_event(ev) is False      # duplicate
    body = store.query(days=3650)
    assert body["total"] == 1


def test_magnitude_revision_updates_existing_row(store):
    store.upsert_event(_event(mag=4.8))
    store.upsert_event(_event(mag=5.1))
    row = store.get_by_provider_id("usgs", "p1")
    assert row["properties"]["magnitude"] == 5.1


# ---- spatial queries -------------------------------------------------------

def test_radius_query_and_distance(store):
    near = _event(pid="near", lat=15.78, lon=121.55)     # ~Aurora province
    far = _event(pid="far", lat=35.68, lon=139.77)       # Tokyo
    store.upsert_event(near)
    store.upsert_event(far)
    res = store.nearby(15.78, 121.55, radius_km=300, days=3650)
    names = [f["properties"]["uid"] for f in res["features"]]
    assert names == ["usgs:near"]
    assert res["features"][0]["properties"]["distance_km"] < 50


def test_bbox_filtering(store):
    store.upsert_event(_event(pid="ph", lon=121.6, lat=15.2))
    store.upsert_event(_event(pid="cl", lon=-72.0, lat=-33.4))  # Chile
    body = store.query(days=3650, bbox=(115, 4, 127, 21))
    uids = [f["properties"]["uid"] for f in body["features"]]
    assert uids == ["usgs:ph"]


def test_statistics_from_real_rows(store):
    for i, mag in enumerate((3.1, 4.2, 5.9, 6.7)):
        store.upsert_event(_event(pid=f"s{i}", mag=mag))
    stats = store.statistics(reference_point=(15.78, 121.55),
                             reference_radius_km=150)
    assert stats["today"] >= 4
    assert stats["strongest_24h"]["magnitude"] == 6.7
    assert sum(b["count"] for b in stats["magnitude_histogram_7d"]) == 4
    assert stats["total_stored"] == 4


# ---- alert engine ----------------------------------------------------------

def test_alert_thresholds_and_severity():
    rules = load_rules(None)  # defaults: M>=5 MODERATE, >=6 HIGH, >=7 CRITICAL
    big = _event(mag=7.2)
    fired = evaluate_event(big, rules)
    severities = {d.severity for d in fired}
    assert fired and severities == {"MODERATE", "HIGH", "CRITICAL"}

    small = _event(mag=4.0)
    assert evaluate_event(small, rules) == []


def test_alert_region_rule_with_distance():
    rules = [{"name": "aurora-close", "severity": "HIGH",
              "any_of": [{"field": "magnitude", "op": ">=", "value": 4.5}],
              "within_reference_km": 100}]
    close = _event(mag=4.8, lat=15.78, lon=121.55)
    far_ev = _event(mag=4.8, lat=18.0, lon=122.5)
    assert len(evaluate_event(close, rules, distance_km=20)) == 1
    assert evaluate_event(far_ev, rules, distance_km=280) == []


def test_custom_rules_file(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps({"rules": [
        {"name": "deep-only", "severity": "LOW",
         "all_of": [{"field": "depth_km", "op": ">", "value": 300},
                    {"field": "magnitude", "op": ">=", "value": 4.0}]}]}))
    rules = load_rules(str(p))
    deep = _event(mag=4.5, depth=450)
    shallow = _event(mag=4.5, depth=40)
    assert len(evaluate_event(deep, rules)) == 1
    assert evaluate_event(shallow, rules) == []


# ---- ingest worker + bus ---------------------------------------------------

class FakeProvider:
    name = "fake"

    def __init__(self, events):
        self.events = events

    async def fetch_recent(self, lookback_minutes, min_magnitude):
        return self.events

    def health(self):
        return {"provider": self.name, "status": "configured"}


async def _drain(coro_factory):
    return await coro_factory


def test_worker_dedups_publishes_and_alerts(store, tmp_path):
    async def scenario():
        bus = EventBus()
        q = bus.subscribe()
        alerts = []
        worker = IngestWorker(
            [FakeProvider([_event(pid="x1", mag=6.2)])], store, bus,
            poll_interval=3600, rules=load_rules(None),
            on_alert=lambda d, e: alerts.append(d))
        totals = await worker.poll_once()
        assert totals["new"] == 1
        # duplicate cycle -> no new publication of hazard.created
        totals2 = await worker.poll_once()
        assert totals2["new"] == 0

        msgs = []
        while not q.empty():
            msgs.append(q.get_nowait())
        kinds = [m["event"] for m in msgs]
        assert "hazard.created" in kinds
        created = next(m for m in msgs if m["event"] == "hazard.created")
        assert created["properties"]["magnitude"] == 6.2
        assert any(d.severity == "HIGH" for d in alerts)

    asyncio.run(scenario())


def test_worker_survives_provider_failure(store):
    class BrokenProvider(FakeProvider):
        async def fetch_recent(self, lookback_minutes, min_magnitude):
            raise RuntimeError("feed down")

    async def scenario():
        bus = EventBus()
        worker = IngestWorker([BrokenProvider([])], store, bus,
                              poll_interval=3600)
        h = worker.health()
        assert h["overall"] == "stale"           # never succeeded yet
        await worker.poll_once()                 # must not raise
        st = worker.stats["fake"]
        assert "RuntimeError" in (st["last_error"] or "")

    asyncio.run(scenario())


# ---- REST API --------------------------------------------------------------

@pytest.fixture()
def client(store, monkeypatch):
    from app.core.config import settings
    # Keep the real ingestion worker out of these API-level tests
    monkeypatch.setattr(settings, "EARTHQUAKE_ENABLED", False)
    bus = EventBus()

    class FakeProvider:
        name = "fake"

        async def fetch_recent(self, a, b):
            return []

        def health(self):
            return {"provider": "fake", "status": "configured"}

    worker = IngestWorker([FakeProvider()], store, bus, poll_interval=3600)
    app.state.earthquakes = {"store": store, "bus": bus, "worker": worker,
                             "reference_point": (15.78, 121.55),
                             "reference_radius_km": 150, "enabled": True}
    with TestClient(app) as c:
        yield c


def test_api_list_filter_pagination(client, store):
    for i in range(12):
        store.upsert_event(_event(pid=f"api{i}", mag=3.0 + i * 0.2))
    r = client.get("/api/earthquakes?min_magnitude=5&limit=3&offset=0")
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 2          # mags 3.0..5.2 -> two at/above M5
    assert len(body["features"]) == 2
    mags = [f["properties"]["magnitude"] for f in body["features"]]
    assert mags == sorted(mags, reverse=True)     # newest-first ordering by time; same ts -> stable
    assert client.get("/api/earthquakes?bbox=999,0,1000,1").status_code == 400


def test_api_detail_and_404(client, store):
    store.upsert_event(_event(pid="det"))
    uid = "usgs:det"
    r = client.get(f"/api/earthquakes/{uid}?latitude=15.78&longitude=121.55")
    assert r.status_code == 200
    props = r.json()["properties"]
    assert "distance_from_reference_km" in props
    assert client.get("/api/earthquakes/usgs:nope").status_code == 404


def test_api_nearby_region_statistics_health(client, store):
    store.upsert_event(_event(pid="nb", lat=15.78, lon=121.55, mag=4.4))
    assert client.get(
        "/api/earthquakes/nearby?latitude=15.78&longitude=121.55&radius_km=200"
    ).json()["total"] == 1
    reg = client.get(
        "/api/earthquakes/region?latitude=15.78&longitude=121.55&radius_km=200").json()
    assert reg["total"] == 1 and reg["magnitude_bands"]["moderate"] == 1
    stats = client.get("/api/earthquakes/statistics").json()
    assert "not forecasts" in stats["disclaimer"]
    health = client.get("/api/earthquakes/health").json()
    assert health["overall"] in ("live", "stale")
    assert "requires-configuration" in json.dumps(health["providers_configured"]) or \
        health["enabled"] is True
