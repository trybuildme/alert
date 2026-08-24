"""Active tropical cyclone tracks from NOAA IBTrACS (near-real-time).

Source: ibtracs.ACTIVE.list.v04r01.csv — storms with observations in the
last ~7 days, merged across agencies (JTWC, RSMC Tokyo, ...). This is a
best-track archive updated roughly three times per week (Sun/Tue/Thu):
honest about cadence — NOT an operational warning feed. Positions and
intensity are actual analyses; no forecast cone exists in this dataset.
"""

import csv
import io
import math
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter

from app.services.pagasa import (NAMING_DISCLOSURE, assign_pagasa_names,
                                 display_name, par_entry_time, point_in_par,
                                 tc_code)

IBTRACS_ACTIVE_URL = ("https://www.ncei.noaa.gov/data/"
                      "international-best-track-archive-for-climate-"
                      "stewardship-ibtracs/v04r01/access/csv/"
                      "ibtracs.ACTIVE.list.v04r01.csv")

router = APIRouter(prefix="/api")

_client: httpx.AsyncClient | None = None

_TTL_SECONDS = 3600  # upstream refreshes at most daily; re-check hourly
_cache: dict = {"ts": 0.0, "days": None, "payload": None}
_raw_cache: dict = {"ts": 0.0, "rows": None}


def _num(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_iso(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _wind_kt(row: dict) -> float | None:
    """Intensity fallback chain: WMO consensus -> JTWC (USA)."""
    for col in ("WMO_WIND", "USA_WIND"):
        v = _num(row.get(col))
        if v is not None:
            return v
    return None


def _pressure_hpa(row: dict) -> float | None:
    for col in ("WMO_PRES", "USA_PRES", "TOKYO_PRES"):
        v = _num(row.get(col))
        if v is not None:
            return v
    return None


def _sshs_category(row: dict) -> int | None:
    """Saffir-Simpson scale number; -1 = tropical depression,
    0 = tropical storm (per IBTrACS convention)."""
    v = _num(row.get("USA_SSHS"))
    return int(v) if v is not None else None


def _radius34_nm(row: dict) -> float | None:
    """JTWC 34-kt wind radius: max of reported quadrants (nm), else None.
    Max quadrant = conservative single-circle threat extent."""
    quads = [_num(row.get(f"USA_R34_{q}")) for q in ("NE", "SE", "SW", "NW")]
    vals = [v for v in quads if v is not None]
    return max(vals) if vals else None


def _circle_polygon(lon: float, lat: float, radius_km: float,
                    n: int = 48) -> list:
    """Geodesic circle as a GeoJSON Polygon ring (n segments)."""
    r_earth = 6371.0088
    dr = radius_km / r_earth
    latr, lonr = math.radians(lat), math.radians(lon)
    ring = []
    for i in range(n + 1):
        brg = 2 * math.pi * i / n
        lat2 = math.asin(math.sin(latr) * math.cos(dr)
                         + math.cos(latr) * math.sin(dr) * math.cos(brg))
        lon2 = lonr + math.atan2(math.sin(brg) * math.sin(dr) * math.cos(latr),
                                 math.cos(dr) - math.sin(latr) * math.sin(lat2))
        ring.append([round(math.degrees(lon2), 4),
                     round(math.degrees(lat2), 4)])
    return [ring]


async def _fetch_rows() -> list[dict] | None:
    """Download + parse the ACTIVE CSV; None when NOAA NCEI is unreachable."""
    now = time.time()
    if _raw_cache["rows"] is not None and now - _raw_cache["ts"] < _TTL_SECONDS:
        return _raw_cache["rows"]
    global _client
    try:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(timeout=30)
        resp = await _client.get(IBTRACS_ACTIVE_URL)
        resp.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(resp.text)))
    except Exception:
        return None
    _raw_cache.update(ts=now, rows=rows)
    return rows


async def fetch_recent_fixes(days: int = 7) -> dict[str, list[dict]] | None:
    """SID -> time-sorted recent fixes, or None if the upstream feed is
    unavailable. Shared by the track overlay and forecast endpoints."""
    rows = await _fetch_rows()
    if rows is None:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    storms: dict[str, list[dict]] = {}
    for row in rows:
        sid = row.get("SID", "").strip()
        dt = _parse_iso(row.get("ISO_TIME", ""))
        lat = _num(row.get("LAT"))
        lon = _num(row.get("LON"))
        if not sid or dt is None or lat is None or lon is None:
            continue
        if dt < cutoff:
            continue
        storms.setdefault(sid, []).append({**row, "_dt": dt})
    for fixes in storms.values():
        fixes.sort(key=lambda r: r["_dt"])
    return storms


async def fetch_active_storms(days: int = 7) -> dict:
    """GeoJSON FeatureCollection of active storms: one LineString track
    plus one latest-position Point per storm."""
    now = time.time()
    if (_cache["payload"] is not None and _cache["days"] == days
            and now - _cache["ts"] < _TTL_SECONDS):
        return _cache["payload"]

    empty = {"type": "FeatureCollection", "features": [],
             "source": "unavailable"}
    storms = await fetch_recent_fixes(days)
    if storms is None:
        return dict(empty)

    features = []
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # PAGASA local naming: storms that entered PAR get the next free
    # name of the entry year's rotating set, in chronological order.
    par_entries = [(sid, t) for sid, obs0 in storms.items()
                   if (t := par_entry_time(obs0)) is not None]
    pagasa_names = assign_pagasa_names(par_entries)

    for sid, obs in storms.items():
        obs.sort(key=lambda r: r["_dt"])
        name = obs[-1].get("NAME", "").strip() or "UNNAMED"
        basin = obs[-1].get("BASIN", "").strip()
        coords = [[_num(r["LON"]), _num(r["LAT"])] for r in obs]
        winds = [w for w in (_wind_kt(r) for r in obs) if w is not None]
        cats = [c for c in (_sshs_category(r) for r in obs) if c is not None]
        last = obs[-1]
        r34_nm = _radius34_nm(last)
        pagasa = pagasa_names.get(sid)
        # PAGASA classification codes (panahon.gov.ph scheme): current
        # fix for positions/extents, peak in window for the track line.
        code_now = tc_code(_wind_kt(last))
        winds_with_idx = [(w, r) for w, r in zip((_wind_kt(r) for r in obs), obs)
                          if w is not None]
        code_peak = tc_code(max((w for w, _ in winds_with_idx),
                                default=None)) if winds_with_idx else None

        common = {
            "sid": sid,
            "name": name,
            "basin": basin,
            "n_points": len(obs),
            "first_fix": obs[0]["_dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_fix": last["_dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "max_wind_kt": max(winds) if winds else None,
            "max_sshs_category": max(cats) if cats else None,
            "in_par": point_in_par(coords[-1][0], coords[-1][1]),
            "pagasa_name": pagasa,
            "display_name": display_name(name, pagasa),
            "pagasa_code_peak": code_peak,
        }
        features.append({
            "type": "Feature",
            "properties": {**common, "kind": "track"},
            "geometry": {"type": "LineString", "coordinates": coords},
        })
        features.append({
            "type": "Feature",
            "properties": {
                **common,
                "kind": "position",
                "time": common["last_fix"],
                "lat": _num(last["LAT"]),
                "lon": _num(last["LON"]),
                "wind_kt": _wind_kt(last),
                "pagasa_code": code_now,
                "pressure_hpa": _pressure_hpa(last),
                "sshs_category": _sshs_category(last),
                "dist2land_km": _num(last.get("DIST2LAND")),
                "wind_radius_nm": r34_nm,
                "wind_radius_km": round(r34_nm * 1.852) if r34_nm else None,
            },
            "geometry": {"type": "Point",
                         "coordinates": [coords[-1][0], coords[-1][1]]},
        })
        # 34-kt wind extent: honest circle only when JTWC reports quadrants
        if r34_nm:
            features.append({
                "type": "Feature",
                "properties": {
                    **common,
                    "kind": "extent",
                    "wind_radius_nm": r34_nm,
                    "wind_radius_km": round(r34_nm * 1.852),
                    "radius_basis": "max USA_R34 quadrant",
                },
                "geometry": {"type": "Polygon", "coordinates": _circle_polygon(
                    coords[-1][0], coords[-1][1], r34_nm * 1.852)},
            })

    payload = {
        "type": "FeatureCollection",
        "features": features,
        "source": "ibtracs-active-v04r01",
        "fetched_at": fetched_at,
        # Honest cadence note surfaced by the UI legend
        "update_cadence": "best-track archive, refreshed ~3x weekly "
                          "(not an operational warning feed)",
        "naming": NAMING_DISCLOSURE,
    }
    _cache.update(ts=now, days=days, payload=payload)
    return payload


@router.get("/cyclones")
async def active_cyclones(days: int = 7) -> dict:
    if not 1 <= days <= 30:
        days = 7
    return await fetch_active_storms(days=days)
