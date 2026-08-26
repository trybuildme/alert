"""Elevation profile endpoint tests (Open-Meteo Copernicus DEM proxy)."""

from __future__ import annotations

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import elevation as elevation_mod
from app.main import app

BASE = "http://test"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mock_upstream(monkeypatch):
    """Deterministic upstream: elevation = 10 * latitude."""
    captured: dict = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            lats = [float(x) for x in captured["params"]["latitude"].split(",")]
            return {"elevation": [lat * 10 for lat in lats]}

    class _Client:
        @staticmethod
        async def get(url, params=None):
            captured["url"] = url
            captured["params"] = params or {}
            return _Resp()

    monkeypatch.setattr(elevation_mod, "_client", _Client())
    return captured


def test_profile_returns_real_shaped_payload(client, mock_upstream):
    r = client.get("/api/elevation/profile",
                   params={"coords": "15.0,121.0|15.5,121.5|16.0,122.0"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["elevations_m"] == pytest.approx([150.0, 155.0, 160.0])
    assert body["source"] == "open-meteo-copernicus-dem-glo-90"
    assert body["resolution_m"] == 90
    assert len(body["points"]) == 3


def test_profile_caches_repeat_calls(client, mock_upstream):
    coords = {"coords": "14.1,120.9|14.2,121.0"}
    assert client.get("/api/elevation/profile", params=coords).json()[
        "cached"] is False
    second = client.get("/api/elevation/profile", params=coords).json()
    assert second["cached"] is True


def test_profile_validates_input(client, mock_upstream):
    # single point -> rejected
    assert client.get("/api/elevation/profile",
                      params={"coords": "15.0,121.0"}).status_code == 400
    # out-of-range lat
    assert client.get("/api/elevation/profile",
                      params={"coords": "95.0,121.0|15.0,121.0"}).status_code == 400
    # malformed pair
    assert client.get("/api/elevation/profile",
                      params={"coords": "15.0|15.5,121.0"}).status_code == 400
    # >100 points
    many = "|".join(f"15.{i % 10:04d}2,121.{i % 10:04d}3" for i in range(101))
    assert client.get("/api/elevation/profile",
                      params={"coords": many}).status_code == 400


def test_profile_degrades_honestly_when_upstream_down(client, monkeypatch):
    class _Client:
        @staticmethod
        async def get(url, params=None):
            raise httpx.ConnectError("upstream unreachable")

    monkeypatch.setattr(elevation_mod, "_client", _Client())
    r = client.get("/api/elevation/profile",
                   params={"coords": "15.0,121.0|15.5,121.5"})
    assert r.status_code == 502
    assert "unavailable" in r.json()["detail"]
