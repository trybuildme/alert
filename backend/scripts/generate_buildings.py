#!/usr/bin/env python3
"""Generate buildings_luzon.geojson from Overpass API.

Queries OSM for buildings in Luzon with height/levels tags.
Filters to height > 15m OR area > 500m² OR levels > 5.

Usage:
  cd /home/ofrates/ALERT/backend
  .venv/bin/python scripts/generate_buildings.py
"""

import json
import math
import sys
import os
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX = (13.5, 119.5, 19.0, 123.0)

OVERPASS_QUERY = f"""[out:json][timeout:180];
(
  way["building"]["height"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
  way["building"]["building:levels"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
);
out body;
>;
out skel qt;"""


def spherical_polygon_area(coords):
    """Compute approximate area of a polygon in m²."""
    if len(coords) < 3:
        return 0.0
    R = 6371000.0
    total = 0.0
    for i in range(len(coords)):
        lon1 = math.radians(coords[i][0])
        lat1 = math.radians(coords[i][1])
        lon2 = math.radians(coords[(i + 1) % len(coords)][0])
        lat2 = math.radians(coords[(i + 1) % len(coords)][1])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total * R * R / 2.0)


def build_geometry(way, nodes):
    """Convert OSM way to GeoJSON polygon."""
    coords = []
    for nid in way.get("nodes", []):
        n = nodes.get(nid)
        if n:
            coords.append([n["lon"], n["lat"]])
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def main():
    print("Querying Overpass API for Luzon buildings with height data...")
    resp = httpx.post(
        OVERPASS_URL,
        data={"data": OVERPASS_QUERY},
        timeout=300,
        headers={"User-Agent": "ALERT-GIS/1.0"},
    )
    resp.raise_for_status()
    result = resp.json()

    elements = result.get("elements", [])
    print(f"  Got {len(elements)} elements")

    nodes = {}
    ways = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = {"lat": el["lat"], "lon": el["lon"]}
        elif el["type"] == "way":
            ways[el["id"]] = el

    print(f"  {len(nodes)} nodes, {len(ways)} ways")

    features = []
    skipped = 0
    for wid, way in ways.items():
        tags = way.get("tags", {})
        geom = build_geometry(way, nodes)
        if not geom:
            skipped += 1
            continue

        area = spherical_polygon_area(geom["coordinates"][0])

        height_m = None
        raw_h = tags.get("height", "")
        if raw_h:
            try:
                h = raw_h.replace("m", "").replace(" ", "").strip()
                height_m = float(h)
            except ValueError:
                pass

        levels = None
        raw_l = tags.get("building:levels", "")
        if raw_l:
            try:
                levels = int(raw_l.strip())
                if height_m is None:
                    height_m = levels * 3.0
            except ValueError:
                pass

        if height_m is None and area > 500:
            height_m = 10.0

        if not ((height_m and height_m > 15) or area > 500 or (levels and levels > 5)):
            skipped += 1
            continue

        props = {
            "height": round(height_m, 1) if height_m else 10.0,
            "area_m2": round(area, 1),
            "name": tags.get("name", ""),
            "building_type": tags.get("building", ""),
            "osm_id": wid,
        }
        if levels:
            props["levels"] = levels

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": geom,
        })

    print(f"  Filtered to {len(features)} big buildings (skipped {skipped})")

    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "bbox": list(BBOX),
            "count": len(features),
            "source": "OpenStreetMap via Overpass API",
            "filter": "height > 15m OR area > 500m² OR levels > 5",
        },
        "features": features,
    }

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "data", "buildings_luzon.geojson",
    )
    with open(out, "w") as f:
        json.dump(fc, f)
    size_kb = os.path.getsize(out) // 1024
    print(f"  Written to {out} ({size_kb} KB, {len(features)} features)")


if __name__ == "__main__":
    main()
