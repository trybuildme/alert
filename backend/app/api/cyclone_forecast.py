"""7-day tropical cyclone outlook — naive extrapolation of IBTrACS tracks.

HONESTY FIRST: this is NOT numerical weather prediction. Each storm's
recent motion (least-squares fit over the last <=48 h of best-track
fixes) and intensity trend are projected forward with exponential
damping toward climatology (tau = 72 h). Curvature (recurvature), land
interaction, and vertical shear are ignored. Status names and Wind
Signal numbers follow the PAGASA scale (23 Mar 2022 revision) applied
to whichever agency winds IBTrACS carries. For operational forecasts
consult PAGASA / JTWC bulletins.
"""

import math
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.api.cyclones import (_num, _radius34_nm, _wind_kt,
                              fetch_recent_fixes)

router = APIRouter(prefix="/api")

_PHT = timezone(timedelta(hours=8))  # Asia/Manila; no DST — fixed offset

_STEP_H = 6          # forecast fix interval
_TAU_H = 72.0        # intensity-trend damping time constant
_MAX_WIND_KT = 150   # physical ceiling on projections
_STALE_H = 36        # older last-fix => storm probably dissipated

_TTL_SECONDS = 3600
_cache: dict = {"ts": 0.0, "key": None, "payload": None}

_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday")


def pagasa_status(wind_kt: float | None) -> str | None:
    """PAGASA public classification (10-min basis applied to available
    agency winds): TD <34 kt, TS >=34, STS >=48, TY >=64,
    Super Typhoon >=100 kt (185 km/h)."""
    if wind_kt is None:
        return None
    if wind_kt < 34:
        return "Tropical Depression"
    if wind_kt < 48:
        return "Tropical Storm"
    if wind_kt < 64:
        return "Severe Tropical Storm"
    if wind_kt < 100:
        return "Typhoon"
    return "Super Typhoon"


def signal_number(wind_kt: float | None) -> int | None:
    """PAGASA Wind Signal No. implied by sustained winds (peak signal a
    landfalling system could raise). Bands per TCWS 2022:
    1: 39-61 km/h, 2: 62-88, 3: 89-117, 4: 118-184, 5: >=185 km/h."""
    if wind_kt is None:
        return None
    kmh = wind_kt * 1.852
    if kmh < 39:
        return 0
    if kmh < 62:
        return 1
    if kmh < 89:
        return 2
    if kmh < 118:
        return 3
    if kmh < 185:
        return 4
    return 5


def sshs_category(wind_kt: float | None) -> int | None:
    """Saffir-Simpson number from kt (-1 TD, 0 TS, 1..5 hurricane)."""
    if wind_kt is None:
        return None
    if wind_kt < 34:
        return -1
    if wind_kt < 64:
        return 0
    if wind_kt < 83:
        return 1
    if wind_kt < 96:
        return 2
    if wind_kt < 113:
        return 3
    if wind_kt < 137:
        return 4
    return 5


def _ols_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _fit_motion(fixes: list[dict]) -> tuple[float, float]:
    """(dlat/dh, dlon/dh) deg/hour via least squares over recent fixes."""
    t0 = fixes[0]["_dt"]
    xs = [(f["_dt"] - t0).total_seconds() / 3600 for f in fixes]
    vlat = _ols_slope(xs, [_num(f["LAT"]) for f in fixes])
    vlon = _ols_slope(xs, [_num(f["LON"]) for f in fixes])
    if vlat is None or vlon is None:
        return 0.0, 0.0
    return vlat, vlon


def _compass(bearing_deg: float) -> str:
    idx = round(((bearing_deg % 360) / 22.5)) % 16
    return _COMPASS[idx]


def forecast_daily(fixes: list[dict], horizon_days: int = 7) -> dict | None:
    """Project one storm forward; returns summary + daily entries.

    Daily buckets use Philippine (PHT) calendar dates so each row reads
    like a morning bulletin: date, weekday name, day-max status and the
    peak Wind Signal implied."""
    last = fixes[-1]
    now = datetime.now(timezone.utc)
    age_h = (now - last["_dt"]).total_seconds() / 3600
    lat0, lon0 = _num(last["LAT"]), _num(last["LON"])
    w0 = _wind_kt(last)
    r34_nm = _radius34_nm(last)

    window = [f for f in fixes if f["_dt"] >= last["_dt"] - timedelta(hours=48)][-6:]
    vlat, vlon = _fit_motion(window)
    speed_kmh = ((vlat ** 2 + vlon ** 2) ** 0.5) * 111.32
    bearing_deg = (90.0 - math.degrees(math.atan2(vlat, vlon))) % 360 \
        if (vlat or vlon) else 0.0

    wwindow = [(f["_dt"] - window[0]["_dt"]).total_seconds() / 3600
               for f in window if _wind_kt(f) is not None]
    wvals = [_wind_kt(f) for f in window if _wind_kt(f) is not None]
    slope_h = _ols_slope(wwindow, wvals) if len(wwindow) >= 3 else None
    slope_h = max(-2.0, min(2.0, slope_h)) if slope_h is not None else 0.0

    steps = []
    t_last = last["_dt"]
    # Extend the horizon to compensate for stale best-track fixes so the
    # outlook always spans 7 FUTURE PHT calendar days where possible.
    n_steps = horizon_days * (24 // _STEP_H) + int(math.ceil(max(age_h, 0.0) / _STEP_H))
    for i in range(1, n_steps + 1):
        dt_h = i * _STEP_H
        damp = _TAU_H * (1.0 - math.exp(-dt_h / _TAU_H))
        wind = None
        if w0 is not None:
            wind = max(15.0, min(_MAX_WIND_KT, w0 + slope_h * damp))
        steps.append({
            "_t": t_last + timedelta(hours=dt_h),
            "lat": lat0 + vlat * dt_h,
            "lon": lon0 + vlon * dt_h,
            "wind_kt": wind,
        })

    buckets: dict[str, list] = {}
    for s in steps:
        local = s["_t"].astimezone(_PHT)
        buckets.setdefault(local.strftime("%Y-%m-%d"), []).append((local, s))

    today_pht = datetime.now(_PHT).strftime("%Y-%m-%d")
    daily = []
    for date_key in sorted(buckets):
        if date_key < today_pht:
            continue                      # skip days already behind us
        items = buckets[date_key]
        local, rep = items[-1]
        wind_max = max((s["wind_kt"] for _, s in items), default=None)
        daily.append({
            "valid_utc": rep["_t"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date": date_key,
            "day": _DAY_NAMES[local.weekday()],
            "lat": round(rep["lat"], 3),
            "lon": round(rep["lon"], 3),
            "wind_kt": round(wind_max) if wind_max is not None else None,
            "wind_kmh": round(wind_max * 1.852) if wind_max is not None else None,
            "status": pagasa_status(wind_max),
            "signal_no": signal_number(wind_max),
            "sshs_category": sshs_category(wind_max),
        })
        if len(daily) >= horizon_days:
            break

    return {
        "last_fix": t_last.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "age_hours": round(age_h, 1),
        "stale": age_h > _STALE_H,
        "current": {
            "lat": lat0, "lon": lon0, "wind_kt": w0,
            "wind_kmh": round(w0 * 1.852) if w0 is not None else None,
            "status": pagasa_status(w0),
            "signal_no": signal_number(w0),
            "sshs_category": sshs_category(w0),
            "wind_radius_nm": r34_nm,
            "wind_radius_km": round(r34_nm * 1.852) if r34_nm else None,
        },
        "motion": {
            "bearing_deg": round(bearing_deg, 1),
            "bearing_compass": _compass(bearing_deg),
            "speed_kmh": round(speed_kmh, 1),
        },
        "intensity_trend_kt_per_day": round(slope_h * 24, 1),
        "daily": daily,
    }


async def build_forecast(days: int = 7, horizon_days: int = 7) -> dict:
    storms = await fetch_recent_fixes(days)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = {
        "generated_at": generated_at,
        "horizon_days": horizon_days,
        "methodology": "naive persistence extrapolation of IBTrACS "
                       "best-track motion/intensity with 72-h damping — "
                       "not an official PAGASA/JTWC forecast",
        "storms": [],
    }
    if storms is None:
        return {"source": "unavailable", **base}
    out = []
    for sid, fixes in storms.items():
        fc = forecast_daily(fixes, horizon_days)
        if fc is None:
            continue
        out.append({
            "sid": sid,
            "name": fixes[-1].get("NAME", "").strip() or "UNNAMED",
            "basin": fixes[-1].get("BASIN", "").strip(),
            "n_obs": len(fixes),
            **fc,
        })
    out.sort(key=lambda s: s["name"])
    return {"source": "ibtracs-active-v04r01 + linear-extrapolation",
            **base, "storms": out}


@router.get("/cyclones/forecast")
async def cyclone_forecast(days: int = 7, horizon_days: int = 7) -> dict:
    if not 1 <= days <= 30:
        days = 7
    if not 1 <= horizon_days <= 7:
        horizon_days = 7
    key = (days, horizon_days)
    now = time.time()
    if (_cache["payload"] is not None and _cache["key"] == key
            and now - _cache["ts"] < _TTL_SECONDS):
        return _cache["payload"]
    payload = await build_forecast(days=days, horizon_days=horizon_days)
    _cache.update(ts=now, key=key, payload=payload)
    return payload
