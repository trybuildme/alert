"""
Philippine administrative hierarchy for AURORA-GIS.

Used by: geographic search (#17), admin drill-down workflow (#4),
administrative boundary layers (#6), click-to-inspect context (#7).

Geometry is intentionally simplified: each unit carries a center point
and an approximate bbox rendered as a rectangle polygon. This keeps the
demo fully offline while preserving correct geographic placement.
Swap in GeoJSON from PSA/PHILGIS for production accuracy.
"""

import math

# (name, west, south, east, north)
REGIONS = [
    ("NCR - National Capital Region", 120.90, 14.35, 121.15, 14.77),
    ("CAR - Cordillera Administrative Region", 120.35, 15.65, 121.65, 18.65),
    ("Region I - Ilocos", 119.75, 15.45, 121.30, 18.70),
    ("Region II - Cagayan Valley", 120.55, 15.75, 122.65, 18.85),
    ("Region III - Central Luzon", 119.75, 14.05, 121.60, 16.45),
    ("Region IV-A - CALABARZON", 120.40, 13.55, 122.05, 14.85),
    ("Region IV-B - MIMAROPA", 117.05, 8.25, 123.35, 14.20),
    ("Region V - Bicol", 122.00, 12.45, 124.60, 14.85),
    ("Region VI - Western Visayas", 121.35, 9.45, 123.85, 12.65),
    ("Region VII - Central Visayas", 121.05, 9.25, 125.30, 11.45),
    ("Region VIII - Eastern Visayas", 124.05, 9.95, 126.45, 12.85),
    ("Region IX - Zamboanga Peninsula", 121.80, 5.55, 124.25, 8.70),
    ("Region X - Northern Mindanao", 123.30, 7.35, 125.70, 9.45),
    ("Region XI - Davao", 124.90, 5.45, 127.05, 8.65),
    ("Region XII - SOCCSKSARGEN", 123.35, 5.55, 126.55, 7.75),
    ("Region XIII - Caraga", 125.15, 7.30, 126.85, 10.05),
    ("BARMM - Bangsamoro", 123.35, 5.35, 125.05, 8.05),
]

ISLANDS = [
    ("Luzon", 119.75, 12.00, 124.50, 18.70),
    ("Visayas", 121.00, 9.25, 126.00, 12.90),
    ("Mindanao", 121.80, 5.35, 127.10, 10.05),
]

PROVINCES = {
    "Region I - Ilocos": [
        ("Ilocos Norte", 120.35, 17.85, 121.15, 18.72),
        ("Ilocos Sur", 120.20, 16.85, 120.95, 18.00),
        ("La Union", 120.25, 16.05, 120.70, 17.05),
        ("Pangasinan", 119.70, 15.45, 120.85, 16.50),
    ],
    "NCR - National Capital Region": [
        ("Metro Manila", 120.90, 14.35, 121.15, 14.77),
    ],
}

MUNICIPALITIES = {
    "Ilocos Norte": [
        ("Laoag City", 18.1978, 120.5936),
        ("Batac City", 18.0565, 120.7440),
        ("San Nicolas", 18.1730, 120.6860),
        ("Paoay", 18.0710, 120.5210),
        ("Currimao", 18.0220, 120.4640),
        ("Badoc", 17.9480, 120.4720),
        ("Pinili", 17.9950, 120.5850),
        ("Vintar", 18.2860, 120.6420),
        ("Bacarra", 18.2400, 120.5920),
        ("Pasuquin", 18.3370, 120.6230),
        ("Burgos", 18.4270, 120.6570),
        ("Bangui", 18.4960, 120.7380),
        ("Pagudpud", 18.5720, 120.8200),
        ("Dingras", 18.1400, 120.7370),
        ("Solsona", 18.1350, 120.7920),
        ("Marcos", 18.0950, 120.8360),
        ("Nueva Era", 18.0500, 120.7900),
        ("Dumalneg", 18.4800, 120.8000),
        ("Adams", 18.4900, 120.8500),
        ("Carasi", 18.2900, 120.7500),
    ],
    # Whole-Luzon coverage: curated representative municipalities per
    # province (approximate real centers, demo accuracy).
    "Ilocos Sur": [
        ("Vigan City", 17.5747, 120.3869),
        ("Candon City", 17.1946, 120.4447),
        ("Bantay", 17.4103, 120.3872),
        ("Santa Maria", 17.3700, 120.4800),
        ("Narvacan", 17.2297, 120.4725),
        ("Tagudin", 16.6067, 120.4647),
    ],
    "La Union": [
        ("San Fernando City", 16.6151, 120.3197),
        ("Agoo", 16.3241, 120.3650),
        ("Bauang", 16.3792, 120.3419),
        ("Bacnotan", 16.4961, 120.3519),
        ("Rosario", 16.2686, 120.4822),
    ],
    "Pangasinan": [
        ("Lingayen", 16.0430, 120.2286),
        ("Dagupan City", 16.0500, 120.3333),
        ("San Carlos City", 15.9236, 120.3475),
        ("Urdaneta City", 15.9761, 120.5711),
        ("Alaminos City", 16.1553, 119.9817),
        ("Calasiao", 16.0147, 120.3686),
    ],
    "Metro Manila": [
        ("Manila", 14.5995, 120.9842),
        ("Quezon City", 14.6760, 121.0437),
        ("Makati", 14.5547, 121.0244),
        ("Pasig", 14.5786, 121.0867),
        ("Caloocan", 14.7600, 120.9800),
        ("Paranaque", 14.4791, 121.0198),
    ],
    "Cavite": [
        ("Imus", 14.4297, 120.9353),
        ("Dasmarinas", 14.3294, 120.9367),
        ("Bacoor", 14.4589, 120.9417),
        ("Tagaytay City", 14.1017, 120.9600),
        ("Trece Martires", 14.2783, 120.8672),
    ],
    "Laguna": [
        ("Santa Cruz", 14.2811, 121.4136),
        ("San Pablo City", 14.0694, 121.3250),
        ("Calamba City", 14.2117, 121.1653),
        ("Los Banos", 14.1700, 121.2400),
        ("Binan", 14.3406, 121.0847),
    ],
    "Batangas": [
        ("Batangas City", 13.7565, 121.0583),
        ("Lipa City", 13.9411, 121.1631),
        ("Tanauan City", 14.0864, 121.1494),
        ("Nasugbu", 14.0697, 120.6272),
        ("Bauan", 13.7917, 121.0083),
    ],
    "Rizal": [
        ("Antipolo City", 14.5878, 121.1760),
        ("Taytay", 14.5644, 121.1328),
        ("Cainta", 14.5686, 121.0822),
        ("Binangonan", 14.4636, 121.1925),
    ],
    "Quezon": [
        ("Lucena City", 13.9314, 121.6172),
        ("Tayabas City", 14.0253, 121.5928),
        ("Lucban", 14.1131, 121.5553),
        ("Infanta", 14.7439, 121.6500),
        ("Gumaca", 13.9211, 122.1006),
    ],
    "Bataan": [
        ("Balanga City", 14.6761, 120.5361),
        ("Mariveles", 14.4333, 120.4833),
        ("Dinalupihan", 14.8000, 120.4667),
    ],
    "Bulacan": [
        ("Malolos City", 14.8443, 120.8139),
        ("San Jose del Monte", 14.8139, 121.0450),
        ("Meycauayan", 14.7361, 120.9608),
        ("Baliwag", 14.9547, 120.9192),
    ],
    "Pampanga": [
        ("San Fernando City", 15.0329, 120.6581),
        ("Angeles City", 15.1439, 120.5919),
        ("Mabalacat", 15.2200, 120.5700),
        ("Guagua", 14.9628, 120.6547),
        ("Arayat", 15.1500, 120.7500),
    ],
    "Tarlac": [
        ("Tarlac City", 15.4800, 120.5900),
        ("Concepcion", 15.3250, 120.6617),
        ("Camiling", 15.6833, 120.4167),
        ("Paniqui", 15.6700, 120.5783),
    ],
    "Zambales": [
        ("Iba", 15.3300, 119.9800),
        ("Olongapo City", 14.8292, 120.2836),
        ("Botolan", 15.2800, 120.0300),
        ("Masinloc", 15.5333, 119.9500),
    ],
    "Nueva Ecija": [
        ("Cabanatuan City", 15.4867, 120.9719),
        ("Gapan City", 15.3064, 120.9464),
        ("Munoz", 15.7286, 120.9050),
        ("San Jose City", 15.8000, 121.0000),
    ],
    "Aurora": [
        ("Baler", 15.7583, 121.5600),
        ("Casiguran", 16.2833, 122.1167),
        ("Dingalan", 15.9000, 121.4000),
    ],
    "Cagayan": [
        ("Tuguegarao City", 17.6131, 121.7270),
        ("Aparri", 18.3569, 121.6406),
        ("Lal-lo", 18.2083, 121.7500),
        ("Sanchez-Mira", 18.5583, 121.2333),
    ],
    "Isabela": [
        ("Ilagan City", 17.1483, 121.8892),
        ("Cauayan City", 16.9300, 121.7733),
        ("Santiago City", 16.6917, 121.5500),
        ("Roxas", 17.1167, 121.6333),
    ],
    "Nueva Vizcaya": [
        ("Bayombong", 16.4833, 121.1500),
        ("Solano", 16.5167, 121.1833),
        ("Bambang", 16.3667, 121.1500),
    ],
    "Quirino": [
        ("Cabarroguis", 16.6000, 121.5333),
        ("Diffun", 16.5833, 121.4667),
    ],
    "Benguet": [
        ("La Trinidad", 16.4553, 120.5878),
        ("Baguio City", 16.4023, 120.5960),
        ("Itogon", 16.3667, 120.6833),
    ],
    "Ifugao": [
        ("Lagawe", 16.8333, 121.1167),
        ("Banaue", 16.9167, 121.0500),
    ],
    "Mountain Province": [
        ("Bontoc", 17.0917, 120.9800),
        ("Sagada", 17.0833, 120.9000),
    ],
    "Abra": [
        ("Bangued", 17.6000, 120.6167),
    ],
    "Kalinga": [
        ("Tabuk City", 17.4667, 121.4667),
    ],
    "Apayao": [
        ("Kabugao", 18.0167, 121.3333),
    ],
    "Batanes": [
        ("Basco", 20.4489, 121.9700),
    ],
    "Marinduque": [
        ("Boac", 13.4367, 121.8383),
    ],
    "Occidental Mindoro": [
        ("Mamburao", 13.2225, 120.5978),
        ("San Jose", 12.5333, 121.0667),
    ],
    "Oriental Mindoro": [
        ("Calapan City", 13.5083, 121.1800),
        ("Pinamalayan", 13.0350, 121.4783),
    ],
}

BARANGAYS = {
    "Laoag City": [
        ("San Lorenzo", 18.2130, 120.5880),
        ("Barit", 18.2450, 120.5560),
        ("Santa Angela", 18.1900, 120.5450),
        ("Caaoacan", 18.1600, 120.6180),
        ("Bacsil", 18.1500, 120.5500),
        ("Bengcag", 18.2050, 120.6010),
        ("Dibua South", 18.2300, 120.6100),
        ("San Mateo", 18.1750, 120.5980),
    ],
}

# Curated landmarks: instant offline answers, ranked with admin units.
# (name, lat, lon, zoom, parent)
LANDMARKS = [
    ("Bangui Windmills", 18.5320, 120.7112, 15, "Bangui, Ilocos Norte"),
    ("Paoay Church", 18.0638, 120.5220, 16, "Paoay, Ilocos Norte"),
    ("Kapurpurawan Rock Formation", 18.5050, 120.6570, 15, "Burgos, Ilocos Norte"),
    ("Cape Bojeador Lighthouse", 18.5120, 120.6480, 16, "Burgos, Ilocos Norte"),
    ("Calle Crisologo, Vigan", 17.5740, 120.3870, 16, "Vigan, Ilocos Sur"),
    ("Banaue Rice Terraces", 16.9328, 121.0560, 13, "Ifugao, CAR"),
    ("Mayon Volcano", 13.2543, 123.6867, 12, "Albay, Bicol"),
    ("Taal Volcano", 14.0020, 120.9930, 14, "Batangas, CALABARZON"),
    ("Chocolate Hills", 9.7917, 124.1500, 13, "Bohol, Central Visayas"),
    ("Rizal Park", 14.5820, 120.9770, 16, "Manila, NCR"),
    ("Intramuros", 14.5930, 120.9730, 15, "Manila, NCR"),
    ("Magellan's Cross", 10.2920, 123.9020, 17, "Cebu City, Central Visayas"),
    ("San Juanico Bridge", 11.0800, 125.0200, 14, "Leyte, Eastern Visayas"),
]


def _bbox_polygon(w, s, e, n):
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]


def _center_square(lat, lon, half_deg):
    return [[[lon - half_deg, lat - half_deg], [lon + half_deg, lat - half_deg],
             [lon + half_deg, lat + half_deg], [lon - half_deg, lat + half_deg],
             [lon - half_deg, lat - half_deg]]]


def regions_geojson() -> dict:
    features = []
    for name, w, s, e, n in REGIONS:
        features.append({
            "type": "Feature",
            "properties": {"level": "region", "name": name,
                           "center_lat": round((s + n) / 2, 5), "center_lon": round((w + e) / 2, 5)},
            "geometry": {"type": "Polygon", "coordinates": _bbox_polygon(w, s, e, n)},
        })
    return {"type": "FeatureCollection", "features": features}


def islands_geojson() -> dict:
    features = []
    for name, w, s, e, n in ISLANDS:
        features.append({
            "type": "Feature",
            "properties": {"level": "island", "name": name,
                           "center_lat": round((s + n) / 2, 5), "center_lon": round((w + e) / 2, 5)},
            "geometry": {"type": "Polygon", "coordinates": _bbox_polygon(w, s, e, n)},
        })
    return {"type": "FeatureCollection", "features": features}


def provinces_geojson(region: str | None = None) -> dict:
    features = []
    for reg, provs in PROVINCES.items():
        if region and reg != region:
            continue
        for name, w, s, e, n in provs:
            features.append({
                "type": "Feature",
                "properties": {"level": "province", "name": name, "region": reg,
                               "center_lat": round((s + n) / 2, 5), "center_lon": round((w + e) / 2, 5)},
                "geometry": {"type": "Polygon", "coordinates": _bbox_polygon(w, s, e, n)},
            })
    return {"type": "FeatureCollection", "features": features}


def municipalities_geojson(province: str | None = None) -> dict:
    features = []
    for prov, munis in MUNICIPALITIES.items():
        if province and prov != province:
            continue
        for name, lat, lon in munis:
            features.append({
                "type": "Feature",
                "properties": {"level": "municipality", "name": name, "province": prov,
                               "center_lat": lat, "center_lon": lon},
                "geometry": {"type": "Polygon", "coordinates": _center_square(lat, lon, 0.035)},
            })
    return {"type": "FeatureCollection", "features": features}


def barangays_geojson(municipality: str | None = None) -> dict:
    features = []
    for muni, brgys in BARANGAYS.items():
        if municipality and muni != municipality:
            continue
        for name, lat, lon in brgys:
            features.append({
                "type": "Feature",
                "properties": {"level": "barangay", "name": name, "municipality": muni,
                               "center_lat": lat, "center_lon": lon},
                "geometry": {"type": "Polygon", "coordinates": _center_square(lat, lon, 0.010)},
            })
    return {"type": "FeatureCollection", "features": features}


def search_index() -> list[dict]:
    """Flattened place index for geographic search."""
    entries = []
    for name, w, s, e, n in ISLANDS:
        entries.append({"name": name, "level": "island", "parent": "Philippines",
                        "lat": round((s + n) / 2, 5), "lon": round((w + e) / 2, 5), "zoom": 6})
    for name, w, s, e, n in REGIONS:
        entries.append({"name": name, "level": "region", "parent": "Philippines",
                        "lat": round((s + n) / 2, 5), "lon": round((w + e) / 2, 5), "zoom": 7})
    for reg, provs in PROVINCES.items():
        for name, w, s, e, n in provs:
            entries.append({"name": name, "level": "province", "parent": reg,
                            "lat": round((s + n) / 2, 5), "lon": round((w + e) / 2, 5), "zoom": 9})
    for prov, munis in MUNICIPALITIES.items():
        for name, lat, lon in munis:
            entries.append({"name": name, "level": "municipality", "parent": prov,
                            "lat": lat, "lon": lon, "zoom": 12})
    for muni, brgys in BARANGAYS.items():
        for name, lat, lon in brgys:
            entries.append({"name": name, "level": "barangay", "parent": muni,
                            "lat": lat, "lon": lon, "zoom": 15})
    for name, lat, lon, zoom, parent in LANDMARKS:
        entries.append({"name": name, "level": "landmark", "parent": parent,
                        "lat": lat, "lon": lon, "zoom": zoom})
    return entries


FLOOD_ZONES = [
    {"risk_level": "high", "name": "Pampanga Delta", "granularity": "regional", "description": "Low-lying alluvial plain, seasonal Pampanga River flooding",
     "bbox": [120.60, 14.85, 120.85, 15.10]},
    {"risk_level": "high", "name": "Agno River Basin", "granularity": "regional", "description": "Pangasinan flood plain, typhoon-season flooding",
     "bbox": [120.30, 15.90, 120.60, 16.20]},
    {"risk_level": "medium", "name": "Cagayan Valley", "granularity": "regional", "description": "Cagayan River floodplain",
     "bbox": [121.50, 17.20, 122.20, 18.00]},
    {"risk_level": "medium", "name": "Laguna de Bay Basin", "granularity": "regional", "description": "Lakeshore communities, seasonal overflow",
     "bbox": [121.00, 14.15, 121.45, 14.45]},
    {"risk_level": "low", "name": "Ilocos Coastal Plain", "granularity": "regional", "description": "Narrow coastal strip, storm-surge exposure",
     "bbox": [120.40, 17.90, 121.10, 18.70]},
]

# Municipal-resolution flood susceptibility: one zone per mapped
# municipality, same footprint as its admin polygon so the layers align.
# Risk is a deterministic pseudo-random estimate (stable across restarts),
# NOT an official hazard map — swap in DENR/MGB susceptibility data for
# production accuracy.
_FLOOD_BANDS = (
    ("high", "High flood susceptibility - low-lying terrain and drainage congestion"),
    ("medium", "Moderate susceptibility - riverine and flash-flood exposure in the wet season"),
    ("low", "Low susceptibility - elevated or well-drained terrain"),
)

MUNICIPAL_FLOOD_ZONES = []
for _prov, _munis in MUNICIPALITIES.items():
    for _name, _lat, _lon in _munis:
        _v = math.sin(_lat * 12.9898 + _lon * 78.233) * 43758.5453
        _v -= math.floor(_v)
        _level, _desc = _FLOOD_BANDS[0 if _v < 0.25 else (1 if _v < 0.60 else 2)]
        MUNICIPAL_FLOOD_ZONES.append({
            "risk_level": _level,
            "name": _name,
            "description": f"{_desc} ({_prov})",
            "municipality": _name,
            "province": _prov,
            "granularity": "municipal",
            "bbox": [_lon - 0.035, _lat - 0.035, _lon + 0.035, _lat + 0.035],
        })

# Province-resolution tier: one ~33 km square per province (centroid of
# its mapped municipalities). The zoom-linked hierarchy — province
# squares guide at country zoom, municipal squares refine from z~9.
PROVINCIAL_FLOOD_ZONES = []
for _prov, _munis in MUNICIPALITIES.items():
    _clat = sum(m[1] for m in _munis) / len(_munis)
    _clon = sum(m[2] for m in _munis) / len(_munis)
    _v = math.sin(_clat * 12.9898 + _clon * 78.233) * 43758.5453
    _v -= math.floor(_v)
    _level, _desc = _FLOOD_BANDS[0 if _v < 0.25 else (1 if _v < 0.60 else 2)]
    PROVINCIAL_FLOOD_ZONES.append({
        "risk_level": _level,
        "name": _prov,
        "description": f"Province-level {_desc.lower()}",
        "province": _prov,
        "granularity": "province",
        "bbox": [_clon - 0.15, _clat - 0.15, _clon + 0.15, _clat + 0.15],
    })
