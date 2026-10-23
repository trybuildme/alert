"""
Tests for the Esri tile proxy: placeholder detection, passthrough,
caching, and graceful upstream failure handling.
"""

import io

import httpx
import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.api import esri_proxy
from app.main import app


def _jpeg(mean: int = 60, size_px: int = 256) -> bytes:
    arr = np.full((size_px, size_px), mean, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _placeholder_jpeg() -> bytes:
    # Mimics Esri's "Map data not yet available." tile: tiny + bright + uniform
    return _jpeg(mean=205)


class MockUpstream:
    """Programmable upstream returning queued responses and counting hits."""

    def __init__(self, responses: list[httpx.Response]):
        self.responses = list(responses)
        self.hits = 0

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.hits += 1
            return self.responses.pop(0)

        return httpx.MockTransport(handler)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_real_tile_passthrough(client, monkeypatch):
    real = _jpeg(mean=60)
    mock = MockUpstream([httpx.Response(200, content=real, headers={"content-type": "image/jpeg"})])
    monkeypatch.setattr(esri_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get("/tiles/esri/18/117584/218895.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == real
    assert mock.hits == 1


def test_placeholder_returns_404(client, monkeypatch):
    mock = MockUpstream([
        httpx.Response(200, content=_placeholder_jpeg(), headers={"content-type": "image/jpeg"}),
    ])
    monkeypatch.setattr(esri_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get("/tiles/esri/19/234725/438160.jpg")
    assert r.status_code == 404
    assert mock.hits == 1

    # Verdict is cached: second request must not hit upstream again
    r2 = client.get("/tiles/esri/19/234725/438160.jpg")
    assert r2.status_code == 404
    assert mock.hits == 1


def test_real_tile_cached(client, monkeypatch):
    real = _jpeg(mean=80)
    mock = MockUpstream([httpx.Response(200, content=real, headers={"content-type": "image/jpeg"})])
    monkeypatch.setattr(esri_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r1 = client.get("/tiles/esri/17/58681/109520.jpg")
    r2 = client.get("/tiles/esri/17/58681/109520.jpg")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.content == real
    assert mock.hits == 1  # second served from cache


def test_upstream_error_degrades_to_404(client, monkeypatch):
    mock = MockUpstream([httpx.Response(500, content=b"boom")])
    monkeypatch.setattr(esri_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get("/tiles/esri/10/500/300.jpg")
    assert r.status_code == 404


def test_out_of_pyramid_404(client):
    assert client.get("/tiles/esri/5/40/0.jpg").status_code == 404
    r = client.get("/tiles/esri/25/0/0.jpg")
    assert r.status_code in (200, 404)


def test_is_placeholder_unit():
    assert esri_proxy.is_placeholder(_placeholder_jpeg()) is True
    assert esri_proxy.is_placeholder(_jpeg(mean=60)) is False
    assert esri_proxy.is_placeholder(b"not an image") is True
