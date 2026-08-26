"""
Layer registry (#6) and click-to-inspect analytics (#7, #19).
"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.data.ph_admin import (BARANGAYS, FLOOD_ZONES, MUNICIPALITIES,
                               MUNICIPAL_FLOOD_ZONES, PROVINCIAL_FLOOD_ZONES)
from app.services.tile_service import PRODUCTS

router = APIRouter(prefix="/api")

LAYER_REGISTRY = [
    {"id": "satellite", "name": "Satellite Imagery", "group": "satellite", "default_on": True,
     "type": "raster", "description": "Active satellite product overlay"},
    {"id": "admin-boundaries", "name": "Administrative Boundaries", "group": "gis", "default_on": True,
     "type": "geojson", "description": "Region / province / municipality / barangay hierarchy"},
    {"id": "roads", "name": "Roads", "group": "gis", "default_on": False,
     "type": "vector", "description": "OSM major roads and farm tracks"},
    {"id": "rivers", "name": "Rivers", "group": "gis", "default_on": False,
     "type": "vector", "description": "OSM waterways"},
    {"id": "elevation", "name": "Elevation", "group": "terrain", "default_on": False,
     "type": "raster", "description": "Hypsometric DEM hillshade (30 m class)"},
    {"id": "agricultural-areas", "name": "Agricultural Areas", "group": "analysis", "default_on": False,
     "type": "geojson", "description": "Monitored farm polygons"},
    {"id": "flood-risk", "name": "Flood Risk", "group": "analysis", "default_on": False,
     "type": "geojson", "description": "Zoom-linked flood risk: province squares refine to municipalities across Luzon"},
    {"id": "weather-stations", "name": "Weather Stations", "group": "weather", "default_on": False,
     "type": "geojson", "description": "Synoptic station network"},
    {"id": "rainfall", "name": "Rainfall", "group": "weather", "default_on": False,
     "type": "geojson", "description": "3-hour accumulated rainfall estimate"},
    {"id": "alerts", "name": "Alerts", "group": "analysis", "default_on": False,
     "type": "geojson", "description": "Active weather and crop alerts"},
]

WEATHER_STATIONS = [
    {"name": "Laoag Synoptic Station", "lat": 18.1800, "lon": 120.5300},
    {"name": "Vigan Station", "lat": 17.5700, "lon": 120.3900},
    {"name": "Baguio Station", "lat": 16.4100, "lon": 120.6000},
    {"name": "Tuguegarao Station", "lat": 17.6100, "lon": 121.7300},
    {"name": "Manila Science Garden", "lat": 14.6300, "lon": 121.0400},
]

FARMS = [
    {"name": "AURORA Demo Farm - Paoay", "lat": 18.0700, "lon": 120.5260,
     "polygon": [[[120.515, 18.062], [120.538, 18.062], [120.538, 18.081], [120.515, 18.081], [120.515, 18.062]]],
     "crop": "Rice", "area_hectares": 42.6},
    {"name": "Bacarra Agri Plot", "lat": 18.2410, "lon": 120.5940,
     "polygon": [[[120.586, 18.234], [120.602, 18.234], [120.602, 18.248], [120.586, 18.248], [120.586, 18.234]]],
     "crop": "Corn", "area_hectares": 12.8},
]


@router.get("/layers")
async def layers():
    return {"layers": LAYER_REGISTRY}


def _pseudo(lat: float, lon: float, salt: int) -> float:
    """Deterministic pseudo-random value in [0,1) from coordinates."""
    v = math.sin(lat * 12.9898 + lon * 78.233 + salt * 3.7) * 43758.5453
    return v - math.floor(v)


def _containing_units(lat: float, lon: float):
    found = []
    for prov, munis in MUNICIPALITIES.items():
        for name, mlat, mlon in munis:
            if abs(lat - mlat) < 0.05 and abs(lon - mlon) < 0.05:
                found.append(("municipality", name))
                for bname, blat, blon in BARANGAYS.get(name, []):
                    if abs(lat - blat) < 0.02 and abs(lon - blon) < 0.02:
                        found.append(("barangay", bname))
                return found
    return found


@router.get("/inspect")
async def inspect(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    product: str = Query("true-color"),
    time: str | None = Query(None),
):
    meta = PRODUCTS.get(product, PRODUCTS["true-color"])

    observation_time = time or (PRODUCTS[product].get("temporal_resolution") == "static"
                                and "static" or None)
    data_age_min = None
    latest = None
    if meta["time_dependent"]:
        now = datetime.now(timezone.utc)
        latest = now.replace(second=0, microsecond=0)
        latest = latest.replace(minute=(latest.minute // 10) * 10)
        obs_dt = None
        if time:
            try:
                obs_dt = datetime.strptime(time.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                obs_dt = None
        obs_dt = obs_dt or latest
        data_age_min = max(0, int((now - obs_dt).total_seconds() // 60))

    admin = _containing_units(lat, lon)
    def _hit(z):
        return z["bbox"][0] <= lon <= z["bbox"][2] and z["bbox"][1] <= lat <= z["bbox"][3]
    flood = (next((z for z in MUNICIPAL_FLOOD_ZONES if _hit(z)), None)
             or next((z for z in PROVINCIAL_FLOOD_ZONES if _hit(z)), None)
             or next((z for z in FLOOD_ZONES if _hit(z)), None))

    ndvi = round(0.35 + 0.55 * _pseudo(lat, lon, 1), 3)
    ndvi_trend = round((_pseudo(lat, lon, 2) - 0.5) * 0.2, 3)
    soil_moisture = round(0.15 + 0.7 * _pseudo(lat, lon, 3), 3)
    rainfall_3h_mm = round(24 * _pseudo(lat, lon, 4), 1)
    temperature_c = round(24 + 8 * _pseudo(lat, lon, 5), 1)
    humidity_pct = round(55 + 40 * _pseudo(lat, lon, 6), 0)
    wind_kph = round(5 + 45 * _pseudo(lat, lon, 7), 0)

    nearest_station = min(WEATHER_STATIONS,
                          key=lambda s: (s["lat"] - lat) ** 2 + (s["lon"] - lon) ** 2)
    dist_km = math.hypot((nearest_station["lat"] - lat) * 111,
                         (nearest_station["lon"] - lon) * 105)

    return {
        "location": {"latitude": round(lat, 6), "longitude": round(lon, 6)},
        "administrative_context": [{"level": lvl, "name": nm} for lvl, nm in admin],
        "satellite": {
            "satellite": meta["satellite"],
            "product": meta["name"],
            "product_id": product,
            "native_resolution_km": meta["native_resolution_km"],
            "resolution_label": (f"{meta['native_resolution_km']:g} km"
                                 if meta["native_resolution_km"] >= 1
                                 else f"{int(meta['native_resolution_km'] * 1000)} m"),
            "latest_observation": latest.strftime("%Y-%m-%d %H:%M UTC") if latest else None,
            "observation_time": observation_time,
            "data_age_minutes": data_age_min,
            "data_source": ("NASA GIBS live Himawari-9 AHI (gibs.earthdata.nasa.gov)"
                            if meta.get("source") == "gibs" else
                            "NOAH tile service (synthetic Himawari-class feed)"),
        },
        "agriculture": {
            "data_quality": "synthetic",
            "note": ("Placeholder values from a deterministic noise model "
                     "— no live satellite/gauge source is wired yet. Not "
                     "operational."),
            "ndvi_estimate": ndvi,
            "ndvi_30d_trend": ndvi_trend,
            "soil_moisture_index": soil_moisture,
            "interpretation": ("healthy vegetation" if ndvi > 0.6 else
                               "moderate vegetation stress" if ndvi > 0.45 else "low vegetation activity"),
        },
        "weather": {
            "data_quality": "synthetic",
            "note": ("Simulated readings — no live station/gauge feed is "
                     "wired yet. Station name/location is real; values "
                     "are not."),
            "rainfall_3h_mm": rainfall_3h_mm,
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "wind_kph": wind_kph,
            "nearest_station": nearest_station["name"],
            "station_distance_km": round(dist_km, 1),
        },
        "flood_risk": flood,
        "farms_nearby": [
            {k: f[k] for k in ("name", "crop", "area_hectares")}
            for f in FARMS if abs(f["lat"] - lat) < 0.25 and abs(f["lon"] - lon) < 0.25
        ],
    }


@router.get("/farms")
async def farms():
    """Demo registry: hand-placed illustrative farm polygons, not a live
    cadastral/agricultural feed."""
    return {
        "type": "FeatureCollection",
        "source": "demo-registry",
        "disclaimer": ("Illustrative demo farms — no live agricultural "
                       "census or cadastral feed is wired yet."),
        "features": [
            {"type": "Feature",
             "properties": {"name": f["name"], "crop": f["crop"], "area_hectares": f["area_hectares"],
                            "center_lat": f["lat"], "center_lon": f["lon"], "zoom": 15},
             "geometry": {"type": "Polygon", "coordinates": f["polygon"]}}
            for f in FARMS
        ],
    }


@router.get("/weather-stations")
async def weather_stations():
    """Station names/locations are real PAGASA synoptic sites; the
    readings next to them are simulated placeholders."""
    return {
        "type": "FeatureCollection",
        "source": "static-station-list-simulated-readings",
        "disclaimer": ("Real station locations; temperature/rainfall "
                       "values are SIMULATED placeholders (no live "
                       "observation feed yet)."),
        "features": [
            {"type": "Feature",
             "properties": {"name": s["name"],
                            "simulated": True,
                            "temperature_c": round(24 + 8 * _pseudo(s["lat"], s["lon"], 5), 1),
                            "rainfall_3h_mm": round(24 * _pseudo(s["lat"], s["lon"], 4), 1)},
             "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}}
            for s in WEATHER_STATIONS
        ],
    }


@router.get("/flood-zones")
async def flood_zones():
    """Zoom-linked hierarchy: ~33 km province squares guide at country
    zoom, municipal squares refine from z~9; coarse regional basins
    remain as legacy fallback."""
    features = []
    for z in [*PROVINCIAL_FLOOD_ZONES, *MUNICIPAL_FLOOD_ZONES, *FLOOD_ZONES]:
        w, s, e, n = z["bbox"]
        features.append({
            "type": "Feature",
            "properties": {"risk_level": z["risk_level"], "name": z["name"],
                           "simulated": True,
                           "description": z["description"],
                           "granularity": z.get("granularity", "regional"),
                           **({"municipality": z["municipality"], "province": z["province"]}
                              if "municipality" in z else {})},
            "geometry": {"type": "Polygon", "coordinates": [[
                [w, s], [e, s], [e, n], [w, n], [w, s],
            ]]},
        })
    return {"type": "FeatureCollection", "features": features,
            "source": "demo-risk-model",
            "disclaimer": ("Illustrative flood-risk model — NOT an "
                           "operational hazard map. Official flood "
                           "advisories via PAGASA / MGB.")}


@router.get("/rainfall")
async def rainfall():
    return {
        "type": "FeatureCollection",
        "source": "simulated-estimates",
        "disclaimer": ("Simulated rainfall values at real station "
                       "locations — no live gauge feed yet."),
        "features": [
            {"type": "Feature",
             "properties": {"mm": round(30 * _pseudo(s["lat"], s["lon"], 4), 1),
                            "station": s["name"], "simulated": True},
             "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]}}
            for s in WEATHER_STATIONS
        ],
    }


@router.get("/alerts")
async def alerts():
    """NO live weather-warning source is wired yet (PAGASA publishes no
    open machine-readable feed). An honest empty collection is served —
    a fabricated alert zone used to live here and was removed: showing
    invented hazard warnings on a hazard platform is dangerous."""
    return {
        "type": "FeatureCollection",
        "features": [],
        "source": "no-live-source",
        "disclaimer": ("No operational weather-warning feed is connected "
                       "yet. Absence of features means NO DATA, not "
                       "'all clear'. Official warnings via PAGASA."),
    }
