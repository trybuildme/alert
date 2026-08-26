"""Flood data provider protocol.

Every external feed plugs in behind this interface so the ingest
worker, store, engine and UI never change when providers are added.
A provider returns NORMALIZED observations or raises; validation and
dedup live downstream (ingest.py), never inside providers.
"""

from __future__ import annotations

from typing import Protocol

# Normalized observation: one measurement at one instant.
#   station_id      curated registry id (stations.py)
#   metric          'rainfall_mm_h' | 'rainfall_mm_3h'
#                 | 'rainfall_mm_24h' | 'water_level_m'
#   value           float, already in the metric's unit
#   observed_at     ISO-8601 UTC ('...Z')
#   source          provider identifier for attribution


class FloodProvider(Protocol):
    """name: stable id used for source attribution + health stats."""

    name: str

    async def poll(self) -> list[dict]:
        """Return normalized observations. Raises on upstream failure."""
        ...
