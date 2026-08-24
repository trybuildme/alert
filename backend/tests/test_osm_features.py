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
