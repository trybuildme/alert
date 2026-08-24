"""
Tests for the 7-day cyclone outlook: naive extrapolation sanity,
PAGASA status / Wind Signal classification, PHT date + weekday naming,
and honest degradation when NOAA NCEI is unreachable.
"""

import csv
import io
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from starlette.testclient import TestClient

from app.api import cyclones, cyclone_forecast
from app.api.cyclone_forecast import pagasa_status, signal_number, sshs_category
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
    ], extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode()


def _hours_ago(h: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=h)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# Storm heading due west at ~16 km/h, intensifying 55 -> 75 kt.
WESTERN = [
    {"SID": "2026123", "SEASON": "2026", "NUMBER": "05", "BASIN": "WP",
     "SUBBASIN": "", "NAME": "SAUDEL", "ISO_TIME": _hours_ago(30),
     "NATURE": "TS", "LAT": "10.0", "LON": "150.0", "WMO_WIND": " ",
     "WMO_PRES": " ", "USA_WIND": "55", "USA_PRES": "985",
     "USA_SSHS": "0", "TOKYO_WIND": " ", "TOKYO_PRES": " ",
     "DIST2LAND": "900"},
    {"SID": "2026123", "SEASON": "2026", "NUMBER": "05", "BASIN": "WP",
     "SUBBASIN": "", "NAME": "SAUDEL", "ISO_TIME": _hours_ago(18),
     "NATURE": "TS", "LAT": "10.0", "LON": "148.0", "WMO_WIND": " ",
     "WMO_PRES": " ", "USA_WIND": "65", "USA_PRES": "975",
     "USA_SSHS": "1", "TOKYO_WIND": " ", "TOKYO_PRES": " ",
     "DIST2LAND": "700"},
    {"SID": "2026123", "SEASON": "2026", "NUMBER": "05", "BASIN": "WP",
     "SUBBASIN": "", "NAME": "SAUDEL", "ISO_TIME": _hours_ago(6),
     "NATURE": "TS", "LAT": "10.0", "LON": "146.0", "WMO_WIND": " ",
     "WMO_PRES": " ", "USA_WIND": "75", "USA_PRES": "965",
     "USA_SSHS": "1", "TOKYO_WIND": " ", "TOKYO_PRES": " ",
     "DIST2LAND": "500"},
]


def _mock(monkeypatch, rows):
    mock = httpx.MockTransport(
        lambda request: httpx.Response(200, content=_csv_bytes(rows)))
    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=mock))


def _reset():
    cyclones._cache.update(ts=0.0, days=None, payload=None)
    cyclones._raw_cache.update(ts=0.0, rows=None)
    cyclone_forecast._cache.update(ts=0.0, key=None, payload=None)


@pytest.fixture(autouse=True)
def fresh_caches():
    _reset()
    yield
    _reset()


# ---------- pure classifier units ----------

def test_pagasa_status_boundaries():
    assert pagasa_status(None) is None
    assert pagasa_status(25) == "Tropical Depression"
    assert pagasa_status(34) == "Tropical Storm"
    assert pagasa_status(48) == "Severe Tropical Storm"
    assert pagasa_status(64) == "Typhoon"
    assert pagasa_status(99) == "Typhoon"
    assert pagasa_status(100) == "Super Typhoon"
    assert pagasa_status(140) == "Super Typhoon"


def test_signal_number_bands_match_tcws_2022():
    # km/h bands: none <39 | 1:39-61 | 2:62-88 | 3:89-117 | 4:118-184 | 5:>=185
    # (kt boundaries: sig3 begins at 89 km/h = 48.05 kt; sig5 at 99.9 kt)
    cases = {15: 0, 20: 0, 21.5: 1, 33: 1, 34: 2, 47: 2, 48: 2,
             48.1: 3, 63: 3, 64: 4, 99: 4, 100: 5, 160: 5}
    for kt, sig in cases.items():
        assert signal_number(kt) == sig, f"{kt} kt -> signal {sig}"
    assert signal_number(None) is None


def test_sshs_category_from_wind():
    assert sshs_category(30) == -1
    assert sshs_category(50) == 0
    assert sshs_category(70) == 1
    assert sshs_category(90) == 2
    assert sshs_category(112) == 3
    assert sshs_category(113) == 4
    assert sshs_category(120) == 4
    assert sshs_category(137) == 5
    assert sshs_category(None) is None


# ---------- endpoint behaviour ----------

def test_forecast_shape_days_dates_signals(client, monkeypatch):
    _mock(monkeypatch, WESTERN)
    r = client.get("/api/cyclones/forecast")
    body = r.json()
    assert r.status_code == 200
    assert body["source"].startswith("ibtracs-active-v04r01")
    assert "not an official PAGASA/JTWC forecast" in body["methodology"]
    assert body["horizon_days"] == 7

    storms = body["storms"]
    assert len(storms) == 1
    st = storms[0]
    assert st["name"] == "SAUDEL"
    # Fixture reports no R34 quadrants -> radius honestly absent
    assert st["current"]["wind_radius_nm"] is None
    assert st["current"]["wind_radius_km"] is None
    # Westward persistence: compass bearing due W, lon strictly decreasing
    assert st["motion"]["bearing_compass"] == "W"
    lons = [d["lon"] for d in st["daily"]]
    assert lons == sorted(lons, reverse=True)
    assert lons[-1] < 146.0                    # moved west of last fix

    daily = st["daily"]
    assert len(daily) == 7                     # one row per upcoming PHT day

    today_pht = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    seen_days = set()
    prev_date = ""
    for d in daily:
        # Weekday name must match the PHT calendar date it accompanies
        expected = datetime.strptime(d["date"], "%Y-%m-%d").strftime("%A")
        assert d["day"] == expected
        assert d["date"] >= today_pht          # outlook starts in the future
        assert d["date"] > prev_date           # strictly chronological
        prev_date = d["date"]
        seen_days.add(d["day"])
        assert d["signal_no"] is None or 0 <= d["signal_no"] <= 5
        # Internal consistency: STY implies signal 5; TD implies no high signal
        if d["status"] == "Super Typhoon":
            assert d["signal_no"] == 5
        if d["status"] == "Tropical Depression":
            assert d["signal_no"] in (0, 1)
    assert len(seen_days) >= 6                 # genuinely distinct weekdays

    # Intensifying trend survives damping but respects the physical ceiling
    winds = [d["wind_kt"] for d in daily]
    assert winds[-1] > 75                      # still strengthening
    assert all(w <= 150 for w in winds)


def test_forecast_upstream_failure_degrades_honestly(client, monkeypatch):
    broken = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=broken))
    r = client.get("/api/cyclones/forecast")
    body = r.json()
    assert r.status_code == 200
    assert body["source"] == "unavailable"
    assert body["storms"] == []


def test_forecast_response_is_cached_across_calls(client, monkeypatch):
    hits = {"n": 0}

    def handler(request):
        hits["n"] += 1
        return httpx.Response(200, content=_csv_bytes(WESTERN))

    monkeypatch.setattr(cyclones, "_client",
                        httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    client.get("/api/cyclones/forecast")
    client.get("/api/cyclones/forecast")
    assert hits["n"] == 1
