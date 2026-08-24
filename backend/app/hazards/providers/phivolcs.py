"""PHIVOLCS provider stub — REQUIRES CONFIGURATION.

HONESTY FIRST: PHIVOLCS does not publish a stable documented
machine-readable earthquake feed comparable to USGS FDSN. This module
does NOT fabricate an endpoint. When an official source (or a sanctioned
mirror/scrape target) is agreed upon, implement `fetch_recent` below and
set NOAH_EQ_PROVIDERS to include 'phivolcs' with its URL in config.

The class exists so the Philippines-first roadmap has a first-class slot
in the provider layer, and so tests can exercise multi-provider
deduplication without a live feed.
"""

from __future__ import annotations

from app.hazards.base import HazardEvent, HazardProvider


class PhivolcsProvider(HazardProvider):
    name = "phivolcs"

    def __init__(self, feed_url: str | None = None):
        self.feed_url = feed_url

    async def fetch_recent(self, lookback_minutes: int,
                           min_magnitude: float) -> list[HazardEvent]:
        if not self.feed_url:
            # Unconfigured: report nothing, health says so.
            return []
        raise NotImplementedError(
            "PhivolcsProvider.fetch_recent requires an implementation "
            "against the configured official source")

    def health(self) -> dict:
        return {"provider": self.name,
                "status": "requires-configuration" if not self.feed_url
                else "configured-not-implemented"}
