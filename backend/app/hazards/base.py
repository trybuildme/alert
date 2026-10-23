"""Core abstractions for the hazard-intelligence architecture.

HazardEvent is the single normalized event model every provider must
produce. HazardProvider is the contract each data source implements.
EventBus is a tiny in-process pub/sub used to push new events and alerts
to SSE subscribers without any broker dependency.

HONESTY: this system reports DETECTED EVENTS from authoritative feeds.
It does not forecast or predict earthquakes, and UI copy must say so.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("alert.hazards")

SEVERITIES = ("INFO", "LOW", "MODERATE", "HIGH", "CRITICAL")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class HazardEvent:
    """Normalized geohazard event (earthquake today)."""

    provider: str                      # 'usgs', 'phivolcs', ...
    provider_event_id: str             # stable upstream identity (dedup key)
    origin_time: datetime              # event occurrence (UTC)
    latitude: float
    longitude: float
    depth_km: float | None = None
    magnitude: float | None = None
    magnitude_type: str | None = None
    place: str | None = None           # human location description
    region: str | None = None          # coarse region bucket (e.g. 'Philippines')
    status: str | None = None          # upstream review status
    source_url: str | None = None
    raw_data: dict = field(default_factory=dict)   # original payload, audit trail
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def uid(self) -> str:
        return f"{self.provider}:{self.provider_event_id}"

    def validate(self) -> list[str]:
        """Return a list of problems; empty list means usable."""
        problems: list[str] = []
        if not self.provider_event_id:
            problems.append("missing provider_event_id")
        try:
            f_lat, f_lon = float(self.latitude), float(self.longitude)
            if not (-90 <= f_lat <= 90 and -180 <= f_lon <= 180):
                problems.append(f"coordinates out of range {f_lat},{f_lon}")
        except (TypeError, ValueError):
            problems.append("non-numeric coordinates")
        if self.origin_time is None:
            problems.append("missing origin_time")
        return problems


class HazardProvider(ABC):
    """One external earthquake/hazard data source."""

    name: str = "abstract"

    @abstractmethod
    async def fetch_recent(self, lookback_minutes: int,
                           min_magnitude: float) -> list[HazardEvent]:
        """Return normalized events observed in the last N minutes.

        Implementations must never raise for provider downtime: return an
        empty list on failure and record health via the ingest worker."""
        raise NotImplementedError

    def health(self) -> dict:
        return {"provider": self.name, "status": "unconfigured"}


class EventBus:
    """In-process broadcast bus. Producers publish dicts with an `event`
    discriminator; SSE handlers subscribe with their own queue."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, message: dict) -> int:
        """Fan out to all subscribers; drops per-subscriber when slow
        (bounded queues keep one stuck client from stalling ingestion).
        Returns number of deliveries attempted."""
        n = 0
        for q in list(self._subscribers):
            try:
                q.put_nowait(message)
                n += 1
            except asyncio.QueueFull:
                logger.warning("event bus subscriber queue full; dropping")
        return n

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
