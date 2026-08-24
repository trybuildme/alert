"""
Tests for the active cyclone track overlay: IBTrACS parsing, storm
grouping, latest-position properties, day filtering, and honest
degradation when NOAA NCEI is unreachable.
"""

import csv
import io

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import cyclones
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "SID", "SEASON", "NUMBER", "BASIN", "SUBBASIN", "NAME", "ISO_TIME",
        "NATURE", "LAT", "LON", "WMO_WIND", "WMO_PRES", "USA_WIND",
        "USA_PRES", "USA_SSHS", "TOKYO_WIND", "TOKYO_PRES", "DIST2LAND",
        "USA_R34_NE", "USA_R34_SE", "USA_R34_SW", "USA_R34_NW",
    ], extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode()


def _storm(sid: str, name: str, basin: str, fixes: list[tuple[str, str, str, str]],
           wmo_wind=" ", r34: tuple[str, str, str, str] | None = None) -> list[dict]:
    """fixes: (iso_time, lat, lon, usa_wind) tuples, oldest first."""
    out = []
    for iso, lat, lon, wind in fixes:
        sshs = "-1" if float(wind) < 34 else ("0" if float(wind) < 64 else "1")
        ne, se, sw, nw = r34 if r34 else (" ", " ", " ", " ")
        out.append({
            "SID": sid, "SEASON": "2026", "NUMBER": "05", "BASIN": basin,
            "SUBBASIN": "", "NAME": name, "ISO_TIME": iso, "NATURE": "TS",
            "LAT": lat, "LON": lon, "WMO_WIND": wmo_wind, "WMO_PRES": " ",
            "USA_WIND": wind, "USA_PRES": "985", "USA_SSHS": sshs,
            "TOKYO_WIND": " ", "TOKYO_PRES": " ", "DIST2LAND": "120.5",
            "USA_R34_NE": ne, "USA_R34_SE": se, "USA_R34_SW": sw,
            "USA_R34_NW": nw,
        })
    return out


ROWS = (
    _storm("2026123", "SAUDEL", "WP", [
        ("2026-08-18 00:00:00", "7.9", "154.9", "25"),
        ("2026-08-19 06:00:00", "8.5", "154.1", "35"),
        ("2026-08-20 00:00:00", "11.4", "151.6", "55"),
    ])
    + _storm("2026999", "OLDSTORM", "WP", [
        # Entirely outside a 7-day window relative to any test run
        ("2001-01-01 00:00:00", "10.0", "140.0", "30"),
    ])
    + _storm("2026456", "LALA", "EP", [
        ("2026-08-19 12:00:00", "17.2", "-110.5", "70"),
    ])
)


def _mock(monkeypatch, rows=ROWS):
    mock = httpx.MockTransport(
        lambda request: httpx.Response(200, content=_csv_bytes(rows)))
    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=mock))


def _reset_cache():
    cyclones._cache.update(ts=0.0, days=None, payload=None)
    cyclones._raw_cache.update(ts=0.0, rows=None)


@pytest.fixture(autouse=True)
def fresh_cache():
    _reset_cache()
    yield
    _reset_cache()


def test_tracks_and_positions_grouped(client, monkeypatch):
    _mock(monkeypatch)
    r = client.get("/api/cyclones")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "ibtracs-active-v04r01"
    assert "not an operational warning feed" in body["update_cadence"]

    tracks = [f for f in body["features"] if f["properties"]["kind"] == "track"]
    positions = [f for f in body["features"] if f["properties"]["kind"] == "position"]
    names = {f["properties"]["name"] for f in tracks}
    assert names == {"SAUDEL", "LALA"}   # OLDSTORM filtered by recency

    saudel_track = next(f for f in tracks if f["properties"]["name"] == "SAUDEL")
    assert saudel_track["geometry"]["type"] == "LineString"
    assert len(saudel_track["geometry"]["coordinates"]) == 3
    # Oldest -> newest ordering
    assert saudel_track["geometry"]["coordinates"][0] == [154.9, 7.9]
    props = saudel_track["properties"]
    assert props["basin"] == "WP"
    assert props["max_wind_kt"] == 55
    assert props["max_sshs_category"] == 0   # 55kt = tropical storm on SSHS

    pos = next(f for f in positions if f["properties"]["name"] == "SAUDEL")
    pp = pos["properties"]
    assert pos["geometry"]["type"] == "Point"
    assert pos["geometry"]["coordinates"] == [151.6, 11.4]
    assert pp["wind_kt"] == 55              # WMO blank -> USA fallback
    assert pp["pressure_hpa"] == 985.0
    assert pp["dist2land_km"] == 120.5
    assert pp["time"].endswith("Z")


def test_wind_radius_and_extent_polygon(client, monkeypatch):
    """JTWC R34 quadrants -> radius props + honest geodesic extent polygon;
    storms without reported radii get no extent (no fabricated circles)."""
    rows = (
        _storm("2026310", "LALA", "EP", [
            ("2026-08-19 12:00:00", "17.2", "-110.5", "100"),
        ], r34=("120", "100", "60", "110"))
        + _storm("2026311", "NANGKA", "WP", [
            ("2026-08-19 18:00:00", "27.6", "163.0", "20"),
        ])
    )
    _mock(monkeypatch, rows)
    body = client.get("/api/cyclones").json()
    features = body["features"]

    pos = next(f for f in features
               if f["properties"]["kind"] == "position"
               and f["properties"]["name"] == "LALA")
    assert pos["properties"]["wind_radius_nm"] == 120      # max quadrant
    assert pos["properties"]["wind_radius_km"] == 222      # 120 nm * 1.852

    extents = [f for f in features if f["properties"]["kind"] == "extent"]
    assert len(extents) == 1                               # only LALA
    ext = extents[0]
    assert ext["properties"]["name"] == "LALA"
    ring = ext["geometry"]["coordinates"][0]
    assert ext["geometry"]["type"] == "Polygon"
    assert len(ring) == 49                                 # closed 48-gon
    assert ring[0] == ring[-1]
    # Ring stays within ~radius of the center: max quadrant 120 nm = 222 km,
    # so every vertex is inside a 3-deg box around (-110.5, 17.2)
    for lon, lat in ring:
        assert abs(lon - -110.5) <= 3.0
        assert abs(lat - 17.2) <= 3.0

    nangka = next(f for f in features
                  if f["properties"]["kind"] == "position"
                  and f["properties"]["name"] == "NANGKA")
    assert nangka["properties"]["wind_radius_nm"] is None
    assert nangka["properties"]["wind_radius_km"] is None


def test_days_parameter_filters_recent_only(client, monkeypatch):
    rows = _storm("2026777", "RECENT", "WP", [
        ("2020-01-01 00:00:00", "5.0", "150.0", "30"),
        ("2099-01-01 00:00:00", "6.0", "151.0", "40"),
    ])
    _mock(monkeypatch, rows)
    r = client.get("/api/cyclones?days=7")
    tracks = [f for f in r.json()["features"]]
    assert len(tracks) == 2                 # track + position both present
    line = next(f for f in tracks if f["properties"]["kind"] == "track")
    assert line["properties"]["n_points"] == 1   # only the future fix kept


def test_upstream_failure_degrades_honestly(client, monkeypatch):
    broken = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=broken))
    r = client.get("/api/cyclones")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "unavailable"
    assert body["features"] == []


def test_response_is_cached_across_calls(client, monkeypatch):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, content=_csv_bytes(ROWS))

    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client.get("/api/cyclones")
    client.get("/api/cyclones")
    assert hits["n"] == 1


def test_pagasa_names_assigned_on_par_entry(client, monkeypatch):
    """Storms entering the PAR get PAGASA names in chronological entry
    order (2026 = Set II: ADA, BASYANG, ...); storms outside stay
    international-only."""
    rows = (
        _storm("2026001", "MYSURG", "WP", [
            ("2026-08-18 00:00:00", "12.0", "141.0", "35"),
            ("2026-08-19 00:00:00", "14.0", "133.0", "45"),   # enters PAR
            ("2026-08-20 00:00:00", "16.0", "128.0", "55"),
        ])
        + _storm("2026002", "SECOND", "WP", [
            ("2026-08-19 00:00:00", "10.0", "139.0", "30"),
            ("2026-08-20 06:00:00", "11.0", "131.0", "40"),   # enters later
        ])
        + _storm("2026003", "NEVERPAR", "WP", [
            ("2026-08-19 00:00:00", "8.0", "150.0", "30"),
        ])
    )
    _mock(monkeypatch, rows)
    body = client.get("/api/cyclones").json()
    assert body["naming"] == cyclones.NAMING_DISCLOSURE

    props = {f["properties"]["name"]: f["properties"]
             for f in body["features"] if f["properties"]["kind"] == "position"}

    assert props["MYSURG"]["pagasa_name"] == "ADA"
    assert props["MYSURG"]["in_par"] is True
    assert props["MYSURG"]["display_name"] == "ADA (MYSURG)"
    # PAGASA classification codes (panahon.gov.ph scheme)
    assert props["MYSURG"]["pagasa_code"] == "STS"        # 55 kt
    assert props["MYSURG"]["pagasa_code_peak"] == "STS"
    assert props["NEVERPAR"]["pagasa_code"] == "TD"       # 30 kt
    assert props["NEVERPAR"]["pagasa_code_peak"] == "TD"

    # Chronological PAR-entry order: SECOND entered after MYSURG
    assert props["SECOND"]["pagasa_name"] == "BASYANG"
    assert props["SECOND"]["in_par"] is True
    assert props["SECOND"]["pagasa_code"] == "TS"         # 40 kt

    assert props["NEVERPAR"]["pagasa_name"] is None
    assert props["NEVERPAR"]["in_par"] is False
    assert props["NEVERPAR"]["display_name"] == "NEVERPAR"
