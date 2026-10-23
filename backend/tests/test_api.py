import io

import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.main import app

BASE = "http://test"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- health

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "cache" in body


# ---------------------------------------------------------------- tiles

@pytest.mark.parametrize("product", ["true-color", "infrared", "water-vapor", "cloud-temp", "elevation"])
def test_tile_png_per_product(client, product):
    r = client.get(f"/tiles/{product}/3/4/3.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (256, 256)


def test_tile_unknown_product_404(client):
    assert client.get("/tiles/nope/0/0/0.png").status_code == 404


def test_tile_overzoom_serves_parent(client):
    r = client.get("/tiles/true-color/30/0/0.png")
    assert r.status_code == 200


def test_tile_outside_pyramid_404(client):
    assert client.get("/tiles/true-color/2/5/0.png").status_code == 404


def test_tile_deterministic(client):
    a = client.get("/tiles/true-color/5/12/9.png").content
    b = client.get("/tiles/true-color/5/12/9.png").content
    assert a == b


def test_tile_time_dependent_changes_pixels(client):
    a = client.get("/tiles/true-color/4/10/6.png?time=2026-08-21T00:00:00Z").content
    b = client.get("/tiles/true-color/4/10/6.png?time=2026-08-21T06:00:00Z").content
    assert a != b


def test_tile_cache_hit(client):
    client.get("/tiles/infrared/3/2/3.png")  # prime cache
    r = client.get("/tiles/infrared/3/2/3.png")
    assert r.status_code == 200
    stats = client.get("/health").json()["cache"]
    assert stats["total_hits"] >= 1


# ---------------------------------------------------------------- products

def test_products_catalog(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    products = {p["id"]: p for p in r.json()["products"]}
    assert "true-color" in products
    tc = products["true-color"]
    assert tc["native_resolution_km"] == 1.0
    assert tc["max_native_zoom"] == 8
    assert tc["satellite"] == "Himawari-9"
    ir = products["infrared"]
    assert ir["max_native_zoom"] == 7


def test_product_times(client):
    r = client.get("/api/products/true-color/times")
    ts = r.json()["timestamps"]
    assert len(ts) > 100
    assert all(t.endswith("Z") for t in ts)
    # descending order, 10-minute steps
    from datetime import datetime
    parsed = [datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") for t in ts[:2]]
    assert (parsed[0] - parsed[1]).total_seconds() == 600


# ---------------------------------------------------------------- search

def test_search_place_name(client):
    r = client.get("/api/search", params={"q": "Ilocos Norte"})
    names = [x["name"] for x in r.json()["results"]]
    assert "Ilocos Norte" in names


def test_search_partial(client):
    r = client.get("/api/search", params={"q": "laoag"})
    results = r.json()["results"]
    assert results and results[0]["level"] == "municipality"
    assert abs(results[0]["lat"] - 18.1978) < 0.01


def test_search_coordinates(client):
    r = client.get("/api/search", params={"q": "18.1978, 120.5936"})
    res = r.json()["results"][0]
    assert res["level"] == "coordinates"
    assert res["zoom"] == 14


def test_search_empty(client):
    r = client.get("/api/search", params={"q": "Atlantis"})
    assert r.json()["results"] == []


# ---------------------------------------------------------------- admin

def test_admin_hierarchy(client):
    regions = client.get("/api/admin/regions").json()
    assert any(f["properties"]["name"].startswith("Region I") for f in regions["features"])

    provs = client.get("/api/admin/provinces", params={"region": "Region I - Ilocos"}).json()
    names = [f["properties"]["name"] for f in provs["features"]]
    assert "Ilocos Norte" in names

    munis = client.get("/api/admin/municipalities", params={"province": "Ilocos Norte"}).json()
    mnames = [f["properties"]["name"] for f in munis["features"]]
    assert "Laoag City" in mnames and len(mnames) >= 20

    brgys = client.get("/api/admin/barangays", params={"municipality": "Laoag City"}).json()
    assert len(brgys["features"]) >= 8


# ---------------------------------------------------------------- layers & inspect

def test_layers_registry(client):
    r = client.get("/api/layers").json()["layers"]
    ids = {l["id"] for l in r}
    assert {"satellite", "admin-boundaries", "roads", "rivers", "elevation",
            "agricultural-areas", "flood-risk", "weather-stations", "rainfall",
            "alerts"} <= ids


def test_inspect_payload(client):
    r = client.get("/api/inspect", params={
        "lat": 18.20, "lon": 120.59, "product": "true-color",
        "time": "2026-08-21T02:30:00Z",
    })
    body = r.json()
    assert body["location"]["latitude"] == 18.2
    sat = body["satellite"]
    assert sat["satellite"] == "Himawari-9"
    assert sat["resolution_label"] == "1 km"
    assert sat["data_age_minutes"] is not None
    assert "ndvi_estimate" in body["agriculture"]
    assert body["weather"]["nearest_station"]


def test_inspect_flood_zone(client):
    r = client.get("/api/inspect", params={"lat": 14.95, "lon": 120.70})
    flood = r.json()["flood_risk"]
    assert flood is not None and flood["risk_level"] == "high"


def test_inspect_municipality_context(client):
    r = client.get("/api/inspect", params={"lat": 18.1978, "lon": 120.5936})
    ctx = {c["name"] for c in r.json()["administrative_context"]}
    assert "Laoag City" in ctx


def test_farms_geojson(client):
    r = client.get("/api/farms").json()
    assert r["type"] == "FeatureCollection"
    assert len(r["features"]) >= 2
