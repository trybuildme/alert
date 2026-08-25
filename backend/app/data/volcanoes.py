"""Curated static dataset: Philippine volcanoes monitored by PHIVOLCS.

Coordinates/elevations are public reference values; eruption years are
the last known events from published records. `active_now` is a MANUAL
snapshot of current eruptive/unrest status curated from public PHIVOLCS
reporting (see ACTIVE_AS_OF) — it is not a live feed. UI copy must not
imply real-time status; current alert levels only via official channels.
"""

ACTIVE_AS_OF = "2026-08"

# name, latitude, longitude, elevation_m, last_known_eruption_year,
# active_now, notes
VOLCANOES = [
    ("Mayon", 13.2579, 123.6856, 2463, 2018, False, "Albay — persistently restless"),
    ("Kanlaon", 10.4119, 123.1320, 2435, 2024, True, "Negros Island — intermittent eruptions since June 2024"),
    ("Taal", 14.0021, 120.9934, 311, 2022, True, "Batangas — ongoing caldera unrest, phreatic episodes"),
    ("Bulusan", 12.7669, 124.0528, 1562, 2022, True, "Sorsogon — recurrent phreatic activity"),
    ("Pinatubo", 15.1299, 120.3566, 1486, 1992, False, "Zambales/Tarlac/Pampanga — 1991 climactic eruption"),
    ("Hibok-Hibok", 9.2048, 124.6747, 1338, 1952, False, "Camiguin Island"),
    ("Parker", 6.1130, 124.8920, 1824, None, False, "South Cotabato — caldera"),
    ("Matutum", 6.3620, 125.1070, 2286, None, False, "South Cotabato"),
    ("Musuan", 7.8726, 125.0695, 646, None, False, "Bukidnon"),
    ("Smith", 19.5260, 121.9090, 688, None, False, "Babuyan Island"),
    ("Babuyan Claro", 19.5264, 121.9542, 1081, None, False, "Babuyanes"),
    ("Camiguin de Babuyan", 18.8290, 121.7310, 712, None, False, "Babuyanes"),
    ("Didicas", 19.0790, 122.1960, 244, None, False, "Submarine/emergent volcanic island"),
]


def volcano_features() -> list[dict]:
    features = []
    for name, lat, lon, elev, last_year, active_now, note in VOLCANOES:
        properties = {
            "uid": f"phivolcs-site:{name.lower().replace(' ', '-')}",
            "name": name,
            "elevation_m": elev,
            "active_now": active_now,
            "note": note,
            "provider": "phivolcs-registry",
        }
        if last_year is not None:
            properties["last_known_eruption"] = f"{last_year}"
        features.append({
            "type": "Feature",
            "id": properties["uid"],
            "properties": properties,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })
    return features
