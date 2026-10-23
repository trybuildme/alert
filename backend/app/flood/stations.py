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

Real-time providers: Open-Meteo + RainViewer radar for enhanced
temporal resolution (5-minute updates).
"""

STATIONS: list[dict] = [
    # --- rainfall (REAL data via Open-Meteo + RainViewer) ----------------
    # Metro Manila cluster
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
    {"id": "rain-ortigas-center",
     "name": "Ortigas Center (Pasig)", "kind": "rainfall",
     "latitude": 14.5856, "longitude": 121.0625,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},
    {"id": "rain-antipolo-rizal",
     "name": "Antipolo (Rizal)", "kind": "rainfall",
     "latitude": 14.5861, "longitude": 121.1747,
     "river_basin": "Pasig-Marikina", "provider": "open-meteo"},

    # Central Luzon
    {"id": "rain-baguio-city",
     "name": "Baguio City Synoptic", "kind": "rainfall",
     "latitude": 16.4164, "longitude": 120.5978,
     "river_basin": "Agno", "provider": "open-meteo"},
    {"id": "rain-dagupan-pangasinan",
     "name": "Dagupan City (Pangasinan)", "kind": "rainfall",
     "latitude": 16.0469, "longitude": 120.3408,
     "river_basin": "Agno", "provider": "open-meteo"},
    {"id": "rain-cabanatuan-nueva-ecija",
     "name": "Cabanatuan (Nueva Ecija)", "kind": "rainfall",
     "latitude": 15.4872, "longitude": 120.9678,
     "river_basin": "Pampanga", "provider": "open-meteo"},
    {"id": "rain-san-fernando-pampanga",
     "name": "San Fernando (Pampanga)", "kind": "rainfall",
     "latitude": 15.0303, "longitude": 120.6886,
     "river_basin": "Pampanga", "provider": "open-meteo"},

    # Bicol Region
    {"id": "rain-legazpi-city",
     "name": "Legazpi City Synoptic", "kind": "rainfall",
     "latitude": 13.1391, "longitude": 123.7439,
     "river_basin": "Bicol", "provider": "open-meteo"},
    {"id": "rain-naga-city",
     "name": "Naga City (Camarines Sur)", "kind": "rainfall",
     "latitude": 13.6217, "longitude": 123.1847,
     "river_basin": "Bicol", "provider": "open-meteo"},

    # Visayas
    {"id": "rain-cebu-city",
     "name": "Mactan (Cebu) Synoptic", "kind": "rainfall",
     "latitude": 10.3167, "longitude": 124.0167,
     "river_basin": "Cebu", "provider": "open-meteo"},
    {"id": "rain-iloilo-city",
     "name": "Iloilo City (Iloilo)", "kind": "rainfall",
     "latitude": 10.7202, "longitude": 122.5621,
     "river_basin": "Panay", "provider": "open-meteo"},
    {"id": "rain-tacloban-city",
     "name": "Tacloban City (Leyte)", "kind": "rainfall",
     "latitude": 11.2422, "longitude": 125.0064,
     "river_basin": "Leyte", "provider": "open-meteo"},

    # Mindanao
    {"id": "rain-davao-city",
     "name": "Davao City Synoptic", "kind": "rainfall",
     "latitude": 7.1907, "longitude": 125.4553,
     "river_basin": "Davao", "provider": "open-meteo"},
    {"id": "rain-cagayan-de-oro",
     "name": "Cagayan de Oro City", "kind": "rainfall",
     "latitude": 8.4547, "longitude": 124.6128,
     "river_basin": "Cagayan", "provider": "open-meteo"},
    {"id": "rain-zamboanga-city",
     "name": "Zamboanga City", "kind": "rainfall",
     "latitude": 6.9214, "longitude": 122.0790,
     "river_basin": "Zamboanga", "provider": "open-meteo"},

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
    {"id": "wl-pasig-river",
     "name": "Pasig River (Rosario)", "kind": "water_level",
     "latitude": 14.5667, "longitude": 121.0833,
     "river_basin": "Pasig-Marikina", "provider": "none"},
    {"id": "wl-paniqui-tarlac",
     "name": "Paniqui River Gauge (Tarlac)", "kind": "water_level",
     "latitude": 15.6647, "longitude": 120.7347,
     "river_basin": "Pampanga", "provider": "none"},
]


def registry() -> list[dict]:
    return STATIONS


def by_kind(kind: str) -> list[dict]:
    return [s for s in STATIONS if s["kind"] == kind]
