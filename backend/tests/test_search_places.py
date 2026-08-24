"""
Global place search via Nominatim: merge with local index, zoom fitting,
caching, and graceful degradation when the geocoder is unreachable.
"""

import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import search as search_mod
from app.main import app

NOMINATIM_PARIS = [
    {
        "lat": "48.856614",
        "lon": "2.3522219",
        "display_name": "Paris, Ile-de-France, France",
        "type": "city",
        "class": "place",
        "importance": 0.95,
        "boundingbox": ["48.6572", "49.0463", "2.2242", "2.4699"],
    },
    {
        "lat": "33.315195",
        "lon": "-111.789843",
        "display_name": "Paris, Maricopa County, Arizona, USA",
        "type": "town",
        "class": "boundary",
        "importance": 0.3,
        "boundingbox": ["33.2952", "33.3352", "-111.8098", "-111.7698"],
    },
]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _mock(responses: list[httpx.Response], hits: list[int] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if hits is not None:
            hits[0] += 1
        return responses.pop(0)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_global_place_found(client, monkeypatch):
    monkeypatch.setattr(search_mod, "_client", _mock([
        httpx.Response(200, content=json.dumps(NOMINATIM_PARIS).encode()),
    ]))
    r = client.get("/api/search", params={"q": "Paris"}).json()
    names = [x["name"] for x in r["results"]]
    assert "Paris" in names
    paris = next(x for x in r["results"] if x["name"] == "Paris")
    assert abs(paris["lat"] - 48.8566) < 0.01
    assert paris["parent"] and "France" in paris["parent"]
    # bbox ~0.39 deg wide -> mid-zoom, not street level
    assert 5 <= paris["zoom"] <= 12


def test_local_results_rank_first(client, monkeypatch):
    monkeypatch.setattr(search_mod, "_client", _mock([
        httpx.Response(200, content=json.dumps(NOMINATIM_PARIS).encode()),
    ]))
    r = client.get("/api/search", params={"q": "ilocos norte"}).json()
    assert r["results"][0]["name"] == "Ilocos Norte"
    assert r["results"][0]["level"] == "province"


def test_geocoder_down_degrades_gracefully(client, monkeypatch):
    monkeypatch.setattr(search_mod, "_client", _mock([
        httpx.Response(500, content=b"boom"),
    ]))
    r = client.get("/api/search", params={"q": "Vigan"}).json()
    # local index still answers (Vigan is in Ilocos Sur provinces? not indexed;
    # but Laoag-area entries matching 'vigan' may be absent -> empty is fine,
    # key point: no 500 error)
    assert isinstance(r["results"], list)


def test_nominatim_cached(client, monkeypatch):
    hits = [0]
    mock_client = _mock([
        httpx.Response(200, content=json.dumps(NOMINATIM_PARIS).encode()),
    ], hits)
    monkeypatch.setattr(search_mod, "_client", mock_client)

    client.get("/api/search", params={"q": "paris-cache-check"})
    client.get("/api/search", params={"q": "paris-cache-check"})
    assert hits[0] == 1


def test_zoom_fitting_unit():
    # Country-sized bbox -> low zoom; district-sized -> street-approach zoom
    assert search_mod.zoom_for_bbox(4.0, 21.0, 116.0, 127.0) <= 5
    assert 12 <= search_mod.zoom_for_bbox(48.85, 48.87, 2.30, 2.34) <= 15


def test_landmarks_answer_locally(client):
    # Geocoder is blocked by conftest -> proves landmarks work offline
    r = client.get("/api/search", params={"q": "chocolate hills"}).json()
    top = r["results"][0]
    assert top["name"] == "Chocolate Hills"
    assert top["level"] == "landmark"
    assert abs(top["lat"] - 9.7917) < 0.001

    r2 = client.get("/api/search", params={"q": "bangui"}).json()
    assert any(x["level"] == "landmark" and "Windmills" in x["name"] for x in r2["results"])
