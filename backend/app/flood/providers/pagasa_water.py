"""PAGASA water-level provider — PLACEHOLDER awaiting authorized feed.

Honesty contract (project rule 3): PAGASA publishes river gauge
readings on pagasa.dost.gov.ph as HTML pages / map dashboards but has
NO official public machine-readable API. Scraping government
infrastructure without authorization is off-limits for a
decision-support platform.

This stub implements the FloodProvider protocol and reports zero
observations while disabled. When an authorized endpoint exists
(direct feed, DENR-RBDCC partnership, LGU sensor gateway):

    1. set `enabled = True` / wire NOAH_FLOOD_PAGASA_URL env
    2. implement fetch() against the real schema
    3. normalize to {'metric': 'water_level_m', ...} — everything
       downstream (validation, dedup, thresholds, alerts, GIS)
       requires no changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("noah.flood.pagasa")


class PagasaWaterLevelProvider:
    name = "pagasa-water"

    def __init__(self, stations: list[dict], base_url: str | None = None):
        self._stations = [s for s in stations
                          if s["kind"] == "water_level"]
        self._base_url = base_url
        if base_url:
            logger.warning(
                "pagasa water-level base_url configured but the adapter "
                "is not implemented yet — stations will report offline")

    async def poll(self) -> list[dict]:
        # No fabrication: an unimplemented authorized source yields no
        # observations rather than placeholder numbers.
        return []
