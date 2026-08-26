"""Curated flood-monitoring station registry.

RAINFALL stations: real PAGASA synoptic/agromet station locations
(public reference coordinates). Rainfall observations for these points
come from the REAL Open-Meteo provider (app/flood/providers/open_meteo_rain.py)
— no fabricated values.

WATER_LEVEL stations: real river monitoring points used by PAGASA in
public flood bulletins (e.g., Marikina River, Sto. Niño, Tumana,
Bambang, San Jose, Nangka on the Marikina River system). There is NO
official machine-readable feed — the pagasa_water provider stays
disabled and these stations report 'offline / awaiting authorized
feed' until one exists (see docs/flood/FLOOD.md). We do NOT fabricate
readings.
"""

STATIONS: list[dict] = [
    # --- rainfall (REAL data via Open-Meteo) -----------------------------
    {"id": "rain-pagasa-synoptic-manila",
     "name": "Port Area (Manila) Synoptic", "kind": "rainfall",
     "latitude": 14.5826, "longitude": 120.9767,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},
    {"id": "rain-pagasa-quezon-city",
     "name": "Quezon City Synoptic", "kind": "rainfall",
     "latitude": 14.6333, "longitude": 121.0333,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},
    {"id": "rain-tanay-rizal",
     "name": "Tanay (Rizal)", "kind": "rainfall",
     "latitude": 14.5081, "longitude": 121.2842,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},
    {"id": "rain-sciences-garden-diliman",
     "name": "Science Garden (Diliman)", "kind": "rainfall",
     "latitude": 14.6507, "longitude": 121.0489,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},
    {"id": "rain-baguio-city",
     "name": "Baguio City Synoptic", "kind": "rainfall",
     "latitude": 16.4164, "longitude": 120.5978,
     "river_basin": "Agno", "provider": "open-meteo"},
    {"id": "rain-legazpi-city",
     "name": "Legazpi City Synoptic", "kind": "rainfall",
     "latitude": 13.1391, "longitude": 123.7439,
     "river_basin": "Bicol", "provider": "open-meteo"},
    {"id": "rain-cebu-city",
     "name": "Mactan (Cebu) Synoptic", "kind": "rainfall",
     "latitude": 10.3167, "longitude": 124.0167,
     "river_basin": "Cebu", "provider": "open-meteo"},
    {"id": "rain-davao-city",
     "name": "Davao City Synoptic", "kind": "rainfall",
     "latitude": 7.1907, "longitude": 125.4553,
     "river_basin": "Davao", "provider": "open-meteo"},

    # --- water_level (PLACEHOLDER: awaiting authorized feed) -------------
    {"id": "wl-marikina-sto-nino",
     "name": "Marikina River · Sto. Niño", "kind": "water_level",
     "latitude": 14.6342, "longitude": 121.0981,
     "river_basin": "Marikina", "provider": "none",
     "notes": "PAGASA primary flood-monitoring gauge; 15 m alarm / 16 m critical references"},
    {"id": "wl-marikina-tumana",
     "name": "Marikina River · Tumana", "kind": "water_level",
     "latitude": 14.6589, "longitude": 121.1025,
     "river_basin": "Marikina", "provider": "none"},
    {"id": "wl-marikina-bambang",
     "name": "Marikina River · Bambang", "kind": "water_level",
     "latitude": 14.6636, "longitude": 121.1189,
     "river_basin": "Marikina", "provider": "none"},
    {"id": "wl-san-juan-river-nangka",
     "name": "San Juan River · Nangka", "kind": "water_level",
     "latitude": 14.6736, "longitude": 121.0889,
     "river_basin": "Marikina", "provider": "none"},
]


def registry() -> list[dict]:
    return STATIONS


def by_kind(kind: str) -> list[dict]:
    return [s for s in STATIONS if s["kind"] == kind]
