"""Terrain tile proxy tests (AWS Terrarium upstream, mocked)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.api import terrain_proxy as terrain_mod
from app.main import app

BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"
PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class _Resp:
    def __init__(self, status_code=200, content=PNG):
        self.status_code = status_code
        self.content = content


class _Upstream:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.urls: list[str] = []

    async def get(self, url):
        self.urls.append(url)
        return _Resp(self.status_code)


@pytest.fixture()
def upstream(monkeypatch):
    fake = _Upstream()
    monkeypatch.setattr(terrain_mod, "_client", fake)
    return fake


def test_native_tile_is_proxied(client, upstream):
    r = client.get("/tiles/terrain/5/26/13.png")

    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert upstream.urls == [f"{BASE}/5/26/13.png"]


def test_overzoom_clamps_to_native_parent(client, upstream):
    r = client.get("/tiles/terrain/16/106/52.png")

    assert r.status_code == 200
    assert upstream.urls == [f"{BASE}/14/26/13.png"]


def test_tile_outside_pyramid_is_404(client, upstream):
    r = client.get("/tiles/terrain/2/4/0.png")

    assert r.status_code == 404
    assert upstream.urls == []


def test_zoom_beyond_limit_is_400(client, upstream):
    r = client.get("/tiles/terrain/23/0/0.png")

    assert r.status_code == 400
    assert upstream.urls == []


@pytest.mark.parametrize("upstream_status,expected", [(404, 404), (500, 502)])
def test_upstream_failure_is_not_masked(client, monkeypatch,
                                        upstream_status, expected):
    upstream = _Upstream(status_code=upstream_status)
    monkeypatch.setattr(terrain_mod, "_client", upstream)

    r = client.get("/tiles/terrain/5/26/13.png")

    assert r.status_code == expected


def test_cors_header_is_not_duplicated(client, upstream):
    r = client.get("/tiles/terrain/5/26/13.png",
                   headers={"Origin": "http://localhost:3010"})

    assert r.status_code == 200
    assert len(r.headers.get_list("access-control-allow-origin")) == 1
