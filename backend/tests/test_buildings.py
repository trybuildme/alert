"""3D buildings GeoJSON endpoint tests."""

from __future__ import annotations

import json
import os

import pytest
from starlette.testclient import TestClient

from app.api import buildings as buildings_mod
from app.main import app

BUNDLED = os.path.join(
    os.path.dirname(os.path.dirname(buildings_mod.__file__)),
    "data", "buildings_luzon.geojson",
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_served_payload_and_cache_header(client, tmp_path, monkeypatch):
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"height": 30.0, "name": "Test Tower"},
            "geometry": {"type": "Polygon", "coordinates": [[[121.0, 14.0]]]},
        }],
    }
    path = tmp_path / "buildings.geojson"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(buildings_mod, "_DATA_PATH", str(path))

    r = client.get("/api/buildings")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert r.json() == payload


def test_missing_file_returns_honest_empty_layer(client, tmp_path, monkeypatch):
    monkeypatch.setattr(buildings_mod, "_DATA_PATH",
                        str(tmp_path / "absent.geojson"))

    r = client.get("/api/buildings")

    assert r.status_code == 200
    assert r.json() == {"type": "FeatureCollection", "features": []}
    assert r.headers["cache-control"] == "public, max-age=3600"


def test_bundled_dataset_is_present_and_parseable():
    assert os.path.exists(BUNDLED), "buildings_luzon.geojson must ship with the repo"
    with open(BUNDLED, "rb") as f:
        data = json.load(f)
    assert data["type"] == "FeatureCollection"
    assert data["features"], "dataset must contain at least one footprint"
    assert data["metadata"]["count"] == len(data["features"])
