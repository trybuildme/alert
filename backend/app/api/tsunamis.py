"""Tsunami bulletin intelligence from tsunami.gov (NOAA/NWS).

Source: the Pacific Tsunami Warning Center CAP Atom feed
(https://www.tsunami.gov/events/xml/PAAQAtom.xml) — real bulletins only,
never synthesized. Entries are alert products (warnings/watch/advisory)
with georss:point coordinates.

Honesty contract: this reports ISSUED PRODUCTS from an authoritative
source. It is not a forecast and does not imply any wave has occurred.

GET /api/tsunamis -> GeoJSON FeatureCollection of recent bulletins.
Cached 120 s; upstream downtime degrades to an empty collection with
source=unavailable rather than stale fabrication.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("noah.tsunamis")

FEED_URL = "https://www.tsunami.gov/events/xml/PAAQAtom.xml"
CACHE_TTL_S = 120
MAX_AGE_DAYS = 3          # drop bulletins older than this from the layer

router = APIRouter(prefix="/api/tsunamis")

_client = httpx.AsyncClient(timeout=15)
_cache: dict = {"ts": 0.0, "features": None}
# Exponential backoff when upstream fails: without negative caching,
# every dashboard poll would re-hit a flapping feed at full rate
# (tsunami.gov has been observed to 503 transiently through proxies).
_backoff: dict = {"failures": 0, "next_try": 0.0}
MAX_BACKOFF_S = 900

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "georss": "http://www.georss.org/georss",
}


def parse_atom_feed(xml_text: str) -> list[dict]:
    """Defensive Atom -> feature dicts; malformed entries are skipped."""
    features: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("tsunami feed unparsable: %s", exc)
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    for entry in root.findall("atom:entry", NS):
        try:
            entry_id = (entry.findtext("atom:id", default="", namespaces=NS)
                        ).rsplit("/", 1)[-1].strip()
            title = entry.findtext("atom:title", default="", namespaces=NS).strip()
            updated_raw = entry.findtext("atom:updated", default="", namespaces=NS)
            point_raw = entry.findtext("georss:point", default="", namespaces=NS)
            link_el = entry.find("atom:link", NS)
            link = link_el.get("href") if link_el is not None else None
            summary = (entry.findtext("atom:summary", default="", namespaces=NS)
                       or "").strip()
            if not entry_id:
                continue
            parts = point_raw.split()
            if len(parts) != 2:
                continue
            lat, lon = float(parts[0]), float(parts[1])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            updated = _parse_iso(updated_raw) or datetime.now(timezone.utc)
            if updated < cutoff:
                continue
            features.append({
                "type": "Feature",
                "id": f"tsunami.gov:{entry_id}",
                "properties": {
                    "uid": f"tsunami.gov:{entry_id}",
                    "title": title,
                    "summary": summary[:500],
                    "updated": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "provider": "tsunami.gov",
                    "source_url": link,
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            })
        except (ValueError, TypeError):
            continue
    return features


def _parse_iso(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch_bulletins() -> list[dict] | None:
    """Cached fetch; None signals upstream unavailability."""
    now = time.monotonic()
    if (_cache["features"] is not None
            and now - _cache["ts"] < CACHE_TTL_S):
        return _cache["features"]
    if now < _backoff["next_try"]:
        return None   # still backing off from recent failures
    try:
        response = await _client.get(FEED_URL)
        response.raise_for_status()
        features = parse_atom_feed(response.text)
        _cache.update(ts=time.monotonic(), features=features)
        _backoff["failures"] = 0
        return features
    except Exception as exc:  # noqa: BLE001 — degrade honestly
        failures = _backoff["failures"] + 1
        delay = min(CACHE_TTL_S * 2 ** min(failures - 1, 5), MAX_BACKOFF_S)
        _backoff.update(failures=failures, next_try=time.monotonic() + delay)
        # exc may carry an empty message through some proxy stacks —
        # always log the exception class alongside it.
        logger.warning("tsunami feed unavailable (attempt %d, backing off %ds): %s: %s",
                       failures, delay, type(exc).__name__, exc or "(no message)")
        return None


@router.get("")
async def tsunamis() -> JSONResponse:
    features = await fetch_bulletins()
    body = {
        "type": "FeatureCollection",
        "features": features or [],
        "source": "tsunami.gov-paaq-atom" if features is not None else "unavailable",
        "disclaimer": ("Issued tsunami products from NOAA/NWS tsunami.gov "
                       "— not forecasts; absence of entries means no "
                       "recent bulletins, not safety."),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    status = 200 if features is not None else 503
    return JSONResponse(body, status_code=status)
