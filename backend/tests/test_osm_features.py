"""
Tests for the Overpass-backed OSM roads/waterways endpoints: bbox
parsing/clamping/snapping, tier validation, GeoJSON conversion, disk
caching, and honest degradation when Overpass is unreachable.
"""

import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import osm_features
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(osm_features, "_CACHE_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def _overpass_payload() -> dict:
    return {
        "version": 0.6,
        "elements": [
            {
                "type": "way", "id": 1001,
                "tags": {"highway": "primary", "name": "EDSA"},
                "geometry": [{"lat": 14.58, "lon": 121.0},
                             {"lat": 14.59, "lon": 121.01},
                             {"lat": 14.60, "lon": 121.02}],
            },
            {
                "type": "way", "id": 2002,
                "tags": {"highway": "track"},   # unnamed farm track
                "geometry": [{"lat": 10.0, "lon": 123.0},
                             {"lat": 10.01, "lon": 123.0}],
            },
            {
                # Degenerate single-point way must be dropped
                "type": "way", "id": 3003,
                "tags": {"highway": "motorway"},
                "geometry": [{"lat": 12.0, "lon": 124.0}],
            },
        ],
    }


def test_roads_converted_and_filtered_by_tier(client, monkeypatch):
    seen = {}

    def handler(request):
        seen["query"] = request.content.decode()
        return httpx.Response(200, json=_overpass_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = client.get("/api/roads?bbox=120.9,14.5,121.1,14.7&tier=major")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "osm-overpass"
    assert len(body["features"]) == 2          # degenerate way dropped
    f = body["features"][0]
    assert f["properties"]["class"] == "primary"
    assert f["properties"]["name"] == "EDSA"
    assert f["geometry"]["coordinates"][0] == [121.0, 14.58]
    # Overpass QL bbox order is (south,west,north,east); viewport is
    # grid-snapped, so compare numerically
    import re
    m = re.search(r"\]\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)", seen["query"])
    s_, w_, n_, e_ = (float(v) for v in m.groups())
    assert abs(s_ - 14.5) < 0.06 and abs(n_ - 14.7) < 0.06
    assert abs(w_ - 120.9) < 0.06 and abs(e_ - 121.1) < 0.06
    assert "motorway|trunk|primary|secondary" in seen["query"]

    r2 = client.get("/api/roads?bbox=120.9,14.5,121.1,14.7&tier=minor")
    assert "tertiary|unclassified|track" in seen["query"]
    assert r2.status_code == 200


def test_invalid_bbox_and_tier_rejected_without_upstream(client, monkeypatch):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json=_overpass_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert client.get("/api/roads").json()["error"] == "missing-or-invalid-bbox"
    assert client.get("/api/roads?bbox=121,14.7,120.9,14.5").json()["error"] == "missing-or-invalid-bbox"
    assert client.get("/api/roads?bbox=120.9,14.5,121.1,14.7&tier=huge").json()["error"] == "unknown-tier"
    assert hits["n"] == 0                       # nothing reached Overpass


def test_snapped_bboxes_share_cache(client, monkeypatch):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, json=_overpass_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client.get("/api/roads?bbox=120.901,14.502,121.099,14.698")
    client.get("/api/roads?bbox=120.911,14.512,121.089,14.688")
    assert hits["n"] == 1                       # snapped to same grid cell


def test_overpass_down_degrades_honestly(client, monkeypatch):
    broken = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=broken))
    r = client.get("/api/waterways?bbox=123.0,9.0,123.3,9.3")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "unavailable"
    assert body["features"] == []


def test_disk_cache_file_valid_geojson(client, monkeypatch):
    def handler(request):
        return httpx.Response(200, json=_overpass_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client.get("/api/waterways?bbox=123.0,9.0,123.3,9.3")
    files = list(osm_features._CACHE_DIR.glob("waterways_*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())
    assert stored["type"] == "FeatureCollection"


# ---- Place labels (OSM settlement nodes) ----

def _places_payload() -> dict:
    return {
        "version": 0.6,
        "elements": [
            {"type": "node", "id": 10, "lat": 14.599, "lon": 120.984,
             "tags": {"place": "city", "name": "Manila",
                      "population": "1846513", "capital": "yes"}},
            {"type": "node", "id": 11, "lat": 14.6042, "lon": 120.9822,
             "tags": {"place": "town", "name": "Pandacan"}},
            {"type": "node", "id": 12, "lat": 16.0, "lon": 121.0,
             "tags": {"place": "village", "name": ""}},   # unnamed: dropped
            {"type": "node", "id": 13, "lat": 17.0, "lon": 122.0,
             "tags": {"amenity": "school", "name": "No place tag"}},
        ],
    }


def test_places_converted_with_population_and_capital(client, monkeypatch):
    seen = {}

    def handler(request):
        seen["query"] = request.content.decode()
        return httpx.Response(200, json=_places_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = client.get("/api/places?bbox=120.8,14.4,121.2,14.8")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "osm-overpass"
    # Unnamed village and non-place node dropped
    by_name = {f["properties"]["name"]: f["properties"] for f in body["features"]}
    assert set(by_name) == {"Manila", "Pandacan"}

    manila = by_name["Manila"]
    assert manila["class"] == "city"
    assert manila["population"] == 1846513
    assert manila["capital"] is True
    assert body["features"][0]["geometry"]["coordinates"] == [120.984, 14.599]

    assert by_name["Pandacan"]["capital"] is False
    assert by_name["Pandacan"]["population"] is None

    # Query targets place nodes only
    assert '"place"~"^(city|town|village|borough|suburb|quarter|neighbourhood)$"' in seen["query"]


def test_places_invalid_bbox_rejected(client):
    body = client.get("/api/places").json()
    assert body["error"] == "missing-or-invalid-bbox"
    assert body["features"] == []


def test_overpass_429_backoff_then_recovers(client, monkeypatch):
    """A burst of viewport fetches can trip Overpass's rate limiter;
    the proxy must wait and retry rather than serve an empty map."""
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json=_places_payload())

    monkeypatch.setattr(osm_features, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    r = client.get("/api/places?bbox=120.8,14.4,121.2,14.8")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "osm-overpass"
    assert len(body["features"]) >= 2
    assert hits["n"] == 2
