"""Volcano registry + detail endpoint tests."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app

BASE = "http://test"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_registry_lists_phivolcs_sites(client):
    r = client.get("/api/volcanoes")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    names = [f["properties"]["name"] for f in body["features"]]
    for expected in ("Mayon", "Kanlaon", "Taal", "Bulusan"):
        assert expected in names
    # curated snapshot disclosure travels with the data
    assert body["active_status_as_of"]
    assert "NOT live alert levels" in body["disclaimer"]


def test_active_flag_snapshot_matches_registry(client):
    body = client.get("/api/volcanoes").json()
    by_name = {f["properties"]["name"]: f["properties"] for f in body["features"]}
    assert by_name["Kanlaon"]["active_now"] is True
    assert by_name["Pinatubo"]["active_now"] is False


def test_detail_returns_feature_and_seismicity(client):
    r = client.get("/api/volcanoes/mayon")
    assert r.status_code == 200
    body = r.json()
    assert body["properties"]["name"] == "Mayon"
    assert body["properties"]["elevation_m"] == 2463
    assert body["geometry"]["coordinates"] == pytest.approx([123.6856, 13.2579])
    # earthquake module is enabled in the default test settings; the
    # store starts empty so counts exist but are zero.
    assert body["seismicity"]["available"] is True
    assert body["seismicity"]["total_7d"] == 0
    assert body["seismicity"]["count_24h"] == 0
    assert body["seismicity"]["strongest"] is None


def test_detail_uids_use_slug_form(client):
    r = client.get("/api/volcanoes/hibok-hibok")
    assert r.status_code == 200
    assert r.json()["properties"]["name"] == "Hibok-Hibok"


def test_detail_unknown_uid_404(client):
    assert client.get("/api/volcanoes/not-a-volcano").status_code == 404
