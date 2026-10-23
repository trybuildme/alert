"""USGS earthquake feed provider (FDSN event service, GeoJSON format).

Real endpoint (no fabrication):
  https://earthquake.usgs.gov/fdsnws/event/1/query
      ?format=geojson&starttime=ISO8601&minmagnitude=M
      [&minlatitude=&maxlatitude=&minlongitude=&maxlongitude=]

Each Feature is normalized into a HazardEvent; malformed features are
counted and skipped, never silently discarded (rejections are reported
by the ingest worker). Downtime returns [] — health handling lives in
the ingest worker.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.hazards.base import HazardEvent, HazardProvider

logger = logging.getLogger("alert.hazards.usgs")

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def parse_usgs_feature(feature: dict) -> tuple[HazardEvent | None, str | None]:
    """Normalize one USGS GeoJSON feature.

    Returns (event, None) on success or (None, reason) when rejected."""
    try:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            return None, "missing coordinates"
        lon, lat = float(coords[0]), float(coords[1])
        depth = float(coords[2]) if len(coords) > 2 else None
        mag_raw = props.get("mag")
        magnitude = float(mag_raw) if mag_raw is not None else None

        raw_time = props.get("time")
        if raw_time is None:
            return None, "missing origin time"
        origin_time = datetime.fromtimestamp(float(raw_time) / 1000.0,
                                             tz=timezone.utc)

        event_id = str(feature.get("id") or "").strip()
        if not event_id:
            return None, "missing event id"

        place = (props.get("place") or "").strip() or None
        # Region bucket: USGS places read like '68 km NE of X, Philippines'
        region = None
        if place and "," in place:
            tail = place.rsplit(",", 1)[1].strip()
            if tail:
                region = tail

        ev = HazardEvent(
            provider="usgs",
            provider_event_id=event_id,
            origin_time=origin_time,
            latitude=lat,
            longitude=lon,
            depth_km=depth,
            magnitude=magnitude,
            magnitude_type=(props.get("magType") or None),
            place=place,
            region=region,
            status=(props.get("status") or None),
            source_url=(props.get("url") or None),
            raw_data=feature,
        )
        problems = ev.validate()
        if problems:
            return None, "; ".join(problems)
        return ev, None
    except (TypeError, ValueError, OverflowError) as exc:
        return None, f"malformed feature: {exc}"


class UsgsProvider(HazardProvider):
    """Polls the USGS FDSN query endpoint within a configured bbox."""

    name = "usgs"

    def __init__(self, client: httpx.AsyncClient | None = None,
                 bbox: tuple[float, float, float, float] | None = None):
        self._client = client
        self.bbox = bbox  # (minlon, minlat, maxlon, maxlat); None = global

    def _client_session(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def fetch_recent(self, lookback_minutes: int,
                           min_magnitude: float) -> list[HazardEvent]:
        starttime = (datetime.now(timezone.utc)
                     - timedelta(minutes=lookback_minutes)).strftime("%Y-%m-%dT%H:%M:%S")
        params = {
            "format": "geojson",
            "starttime": starttime,
            "minmagnitude": f"{min_magnitude:g}",
            "orderby": "time",
        }
        if self.bbox:
            minlon, minlat, maxlon, maxlat = self.bbox
            params.update({
                "minlatitude": f"{minlat}", "maxlatitude": f"{maxlat}",
                "minlongitude": f"{minlon}", "maxlongitude": f"{maxlon}",
            })
        resp = await self._client_session().get(USGS_QUERY_URL, params=params)
        resp.raise_for_status()
        body = resp.json()
        events: list[HazardEvent] = []
        for feature in body.get("features", []):
            ev, rejection = parse_usgs_feature(feature)
            if ev is None:
                logger.warning("usgs event rejected: %s", rejection)
                continue
            events.append(ev)
        return events

    def health(self) -> dict:
        return {"provider": self.name, "status": "configured"}
