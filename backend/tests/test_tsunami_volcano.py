"""Tsunami feed parsing + volcano registry tests."""

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import tsunamis as tsunamis_mod
from app.main import app

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:georss="http://www.georss.org/georss">
  <title>PAAQ</title>
  <entry>
    <id>urn:uuid:11111111-1111-1111-1111-111111111111</id>
    <title>Test tsunami bulletin for PH coast</title>
    <updated>{now}</updated>
    <link href="https://www.tsunami.gov/events/xml/PAAQ/2026/08/25/xyz/1/announcement.html"/>
    <summary type="html">... TESTING ONLY ...</summary>
    <georss:point>13.0 121.5</georss:point>
  </entry>
  <entry>
    <id>urn:uuid:22222222-2222-2222-2222-222222222222</id>
    <title>Bad entry - no point</title>
    <updated>{now}</updated>
  </entry>
  <entry>
    <id>urn:uuid:33333333-3333-3333-3333-333333333333</id>
    <title>Ancient entry - outside age window</title>
    <updated>2001-01-01T00:00:00Z</updated>
    <georss:point>0.0 0.0</georss:point>
  </entry>
</feed>
"""


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_parse_atom_feed_skips_malformed_and_stale():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    features = tsunamis_mod.parse_atom_feed(ATOM.format(now=now))
    assert len(features) == 1
    f = features[0]
    assert f["properties"]["provider"] == "tsunami.gov"
    assert f["geometry"]["coordinates"] == [121.5, 13.0]
    assert "TESTING ONLY" in f["properties"]["summary"]
    assert f["properties"]["source_url"].endswith(".html")


def test_parse_atom_feed_rejects_garbage():
    assert tsunamis_mod.parse_atom_feed("not xml at all") == []
    # bad coordinates skipped, no crash
    features = tsunamis_mod.parse_atom_feed(
        ATOM.replace("13.0 121.5", "999.0 999.0"))
    assert features == []


def test_tsunamis_endpoint_unavailable_is_honest(client, monkeypatch):
    async def fail():
        return None

    monkeypatch.setattr(tsunamis_mod, "fetch_bulletins", fail)
    r = client.get("/api/tsunamis")
    assert r.status_code == 503
    assert r.json()["source"] == "unavailable"
    assert r.json()["features"] == []


def test_tsunamis_endpoint_serves_cached_features(client, monkeypatch):
    async def cached():
        return [{
            "type": "Feature", "id": "tsunami.gov:t",
            "properties": {"uid": "tsunami.gov:t", "title": "T"},
            "geometry": {"type": "Point", "coordinates": [120.0, 14.0]},
        }]

    tsunamis_mod._cache.update(ts=0.0, features=None)
    monkeypatch.setattr(tsunamis_mod, "fetch_bulletins", cached)
    r = client.get("/api/tsunamis")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "tsunami.gov-paaq-atom"
    assert len(body["features"]) == 1


# ---- volcanoes -----------------------------------------------------------------

def test_volcanoes_registry(client):
    r = client.get("/api/volcanoes")
    assert r.status_code == 200
    body = r.json()
    names = {f["properties"]["name"] for f in body["features"]}
    assert {"Mayon", "Kanlaon", "Taal", "Bulusan", "Pinatubo"} <= names
    mayon = next(f for f in body["features"]
                 if f["properties"]["name"] == "Mayon")
    assert mayon["geometry"]["coordinates"][0] == pytest.approx(123.686, abs=0.01)
    assert mayon["properties"]["last_known_eruption"] == "2018"
    assert mayon["properties"]["active_now"] is False
    # active snapshot flag present on all sites; Kanlaon/Taal/Bulusan
    # curated as currently active as of the dataset date
    assert "active_status_as_of" in body
    actives = {f["properties"]["name"] for f in body["features"]
               if f["properties"]["active_now"]}
    assert {"Kanlaon", "Taal", "Bulusan"} <= actives
    assert len(actives) == 3
    assert "NOT live alert levels" in body["disclaimer"]
