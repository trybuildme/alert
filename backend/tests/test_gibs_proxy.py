"""
Tests for the live NASA GIBS Himawari proxy: passthrough, caching,
honest gap handling, offline synthetic fallback, and catalog exposure.
"""

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import gibs_proxy
from app.main import app

STAMP = "2026-08-21T14:30:00Z"


class MockUpstream:
    """Programmable upstream returning queued responses and counting hits."""

    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.hits = 0
        self.urls = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.hits += 1
            self.urls.append(str(request.url))
            if self.exc is not None:
                raise self.exc
            return self.responses.pop(0)

        return httpx.MockTransport(handler)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _png_bytes() -> bytes:
    return gibs_proxy.TRANSPARENT_PNG[:-1] + b"\x01"  # any bytes; passthrough


def test_live_tile_passthrough(client, monkeypatch):
    real = _png_bytes()
    mock = MockUpstream([httpx.Response(200, content=real)])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get(f"/tiles/himawari-clean-ir/3/5/3.png?time={STAMP}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-aurora-source"] == "live"
    assert r.content == real
    assert mock.hits == 1
    # GIBS WMTS path order is {z}/{y}/{x}
    assert "/Himawari_AHI_Band13_Clean_Infrared/default/" in mock.urls[0]
    assert f"/default/{STAMP}/GoogleMapsCompatible_Level6/3/3/5.png" in mock.urls[0]


def test_live_tile_cached(client, monkeypatch):
    real = _png_bytes()
    mock = MockUpstream([httpx.Response(200, content=real)])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r1 = client.get(f"/tiles/himawari-clean-ir/1/0/0.png?time={STAMP}")
    r2 = client.get(f"/tiles/himawari-clean-ir/1/0/0.png?time={STAMP}")
    assert r1.status_code == 200 and r2.status_code == 200
    assert mock.hits == 1  # second served from cache
    assert r2.headers["x-aurora-source"] == "live"


def test_gap_returns_transparent_and_is_cached(client, monkeypatch):
    mock = MockUpstream([httpx.Response(404, content=b"no frame")])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get(f"/tiles/himawari-air-mass/2/1/1.png?time={STAMP}")
    assert r.status_code == 200
    assert r.headers["x-aurora-source"] == "gap"
    assert r.content == gibs_proxy.TRANSPARENT_PNG

    # Gap verdict cached: upstream must not be asked twice
    r2 = client.get(f"/tiles/himawari-air-mass/2/1/1.png?time={STAMP}")
    assert r2.status_code == 200
    assert r2.headers["x-aurora-source"] == "gap"
    assert mock.hits == 1


def test_unreachable_gibs_falls_back_to_synthetic(client, monkeypatch):
    mock = MockUpstream(exc=httpx.ConnectError("network down"))
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get(f"/tiles/himawari-visible-red/4/8/6.png?time={STAMP}")
    assert r.status_code == 200
    assert r.headers["x-aurora-source"] == "fallback"
    # Synthetic generator output: opaque RGBA, not the transparent gap tile
    assert len(r.content) > 1000
    assert r.content != gibs_proxy.TRANSPARENT_PNG


def test_http_500_also_degrades_to_fallback(client, monkeypatch):
    mock = MockUpstream([httpx.Response(500, content=b"boom")])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get(f"/tiles/himawari-clean-ir/2/2/1.png?time={STAMP}")
    assert r.status_code == 200
    assert r.headers["x-aurora-source"] == "fallback"


def test_beyond_matrix_zoom_never_hits_upstream(client, monkeypatch):
    mock = MockUpstream()
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get(f"/tiles/himawari-clean-ir/9/100/100.png?time={STAMP}")
    assert r.status_code == 200
    assert r.headers["x-aurora-source"] == "gap"
    assert r.content == gibs_proxy.TRANSPARENT_PNG
    assert mock.hits == 0


def test_catalog_lists_live_products(client):
    r = client.get("/api/products")
    by_id = {p["id"]: p for p in r.json()["products"]}
    assert by_id["himawari-air-mass"]["source"] == "gibs"
    assert by_id["himawari-air-mass"]["gibs_layer"] == "Himawari_AHI_Air_Mass"
    assert by_id["himawari-visible-red"]["max_native_zoom"] == 7
    assert by_id["true-color"].get("source") != "gibs"


def test_times_endpoint_serves_live_product(client):
    r = client.get("/api/products/himawari-visible-red/times")
    body = r.json()
    assert body["product"] == "himawari-visible-red"
    assert len(body["timestamps"]) > 0
    assert body["timestamps"][0].endswith("Z")


# ---- Windy-style enhanced IR ----

def _gray_png(level: int) -> bytes:
    import io
    import numpy as np
    from PIL import Image
    arr = np.full((256, 256), level, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_enhanced_ir_lut_extremes():
    lut = gibs_proxy.enhanced_ir_lut()
    warm = lut[20]      # warm surface -> near-black navy
    assert warm.max() < 60 and warm[2] >= warm[1] >= warm[0]
    deck = lut[205]     # bright deck -> white-ish
    assert deck.min() > 200
    cold = lut[255]     # coldest tops -> violet
    r, g, b = cold
    assert b > r > g


def test_enhanced_route_recolors_and_separates_cache(client, monkeypatch):
    gray = _gray_png(230)
    mock = MockUpstream([httpx.Response(200, content=gray),
                         httpx.Response(200, content=gray)])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    plain = client.get(f"/tiles/himawari-clean-ir/3/6/3.png?time={STAMP}")
    windy = client.get(f"/tiles/himawari-clean-ir/3/6/3.png?time={STAMP}&palette=windy")
    assert plain.status_code == windy.status_code == 200
    assert plain.headers["x-aurora-source"] == "live"
    assert windy.headers["x-aurora-source"] == "live"
    # Recolored body differs from the grayscale original and actually
    # maps intensity 230 through the LUT (bright deck -> white)
    import io as _io
    import numpy as _np
    from PIL import Image as _Image
    px = _np.asarray(_Image.open(_io.BytesIO(windy.content)).convert("RGB"))
    expected = gibs_proxy.enhanced_ir_lut()[230]
    assert (px[0, 0] == expected).all()
    assert not windy.content.startswith(plain.content[:50]) or windy.content != plain.content
    # Two distinct upstream hits: palettes cached separately
    assert mock.hits == 2

    # Both variants now cached
    client.get(f"/tiles/himawari-clean-ir/3/6/3.png?time={STAMP}")
    client.get(f"/tiles/himawari-clean-ir/3/6/3.png?time={STAMP}&palette=windy")
    assert mock.hits == 2


def test_palette_ignored_for_other_gibs_products(client, monkeypatch):
    # Distinct coords: must not collide with the gap-verdict cached by
    # test_gap_returns_transparent_and_is_cached (session-wide FS cache).
    png = _gray_png(90)
    mock = MockUpstream([httpx.Response(200, content=png)])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r1 = client.get(f"/tiles/himawari-air-mass/3/4/4.png?time={STAMP}&palette=windy")
    r2 = client.get(f"/tiles/himawari-air-mass/3/4/4.png?time={STAMP}")
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content   # no enhancement applied
    assert mock.hits == 1             # shared cache entry


# ---- MODIS true color (daily JPEG feed) ----

def _jpeg_bytes() -> bytes:
    import io
    import numpy as np
    from PIL import Image
    arr = np.random.RandomState(7).randint(0, 255, (8, 8, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return buf.getvalue()


def test_modis_times_are_daily(client):
    r = client.get("/api/products/modis-true-color/times")
    body = r.json()
    assert body["product"] == "modis-true-color"
    assert body["step_minutes"] == 1440
    stamps = body["timestamps"]
    assert len(stamps) >= 8   # daily feed widens the default window
    import re
    for s in stamps:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)


def test_modis_jpeg_upstream_served_as_png(client, monkeypatch):
    jpeg = _jpeg_bytes()
    mock = MockUpstream([httpx.Response(200, content=jpeg)])
    monkeypatch.setattr(gibs_proxy, "_client", httpx.AsyncClient(transport=mock.transport()))

    r = client.get("/tiles/modis-true-color/5/9/5.png?time=2026-08-20")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-aurora-source"] == "live"
    # Body is a genuine PNG despite JPEG upstream
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Upstream hit used the Level9 matrix with {z}/{y}/{x} order and .jpg
    assert "/MODIS_Terra_CorrectedReflectance_TrueColor/default/" in mock.urls[0]
    assert "/GoogleMapsCompatible_Level9/5/5/9.jpg" in mock.urls[0]

    # Cached: second request does not re-hit upstream
    client.get("/tiles/modis-true-color/5/9/5.png?time=2026-08-20")
    assert mock.hits == 1
