"""Real-time rainfall provider — Open-Meteo with enhanced frequency.

This provider fetches precipitation data from Open-Meteo with shorter
intervals for near-real-time monitoring. It uses the "nowcast" endpoint
for the most recent precipitation data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("alert.flood.openmeteo_realtime")

# Open-Meteo nowcast endpoint for near-real-time precipitation
NOWCAST_API = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoRealtimeProvider:
    """Enhanced Open-Meteo provider with real-time precipitation data."""

    name = "open-meteo-rt"

    def __init__(self, stations: list[dict], timeout: float = 15.0):
        self._stations = [s for s in stations if s.get("kind") == "rainfall"]
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def poll(self) -> list[dict]:
        """Poll real-time precipitation data for all stations."""
        observations: list[dict] = []

        for station in self._stations:
            try:
                # Fetch current precipitation with nowcast
                resp = await self._client.get(NOWCAST_API, params={
                    "latitude": f"{station['latitude']:.4f}",
                    "longitude": f"{station['longitude']:.4f}",
                    "current": "precipitation,rain,showers",
                    "past_hours": 3,
                    "forecast_hours": 0,
                })
                resp.raise_for_status()
                data = resp.json()

                current = data.get("current", {})
                if not current:
                    continue

                # Extract current precipitation values
                precipitation = current.get("precipitation", 0.0)
                rain = current.get("rain", 0.0)
                showers = current.get("showers", 0.0)

                # Total current precipitation rate
                total_mmh = precipitation or (rain + showers)

                # Get current time
                current_time = current.get("time", "")
                if current_time:
                    # Convert to ISO format
                    obs_time = datetime.strptime(
                        current_time, "%Y-%m-%dT%H:%M"
                    ).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    obs_time = datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )

                observations.append({
                    "station_id": station["id"],
                    "metric": "rainfall_mm_h",
                    "value": float(total_mmh),
                    "observed_at": obs_time,
                    "source": self.name,
                    "quality": "ok",
                    "collection_method": "api_poll",
                })

                # Also fetch hourly data for 3h and 24h aggregates
                hourly = data.get("hourly", {})
                if hourly:
                    times = hourly.get("time", [])
                    precip = hourly.get("precipitation", [])

                    if times and precip and len(times) == len(precip):
                        # Calculate 3h sum
                        now = datetime.now(timezone.utc)
                        three_hours_ago = now.strftime("%Y-%m-%dT%H:%M")
                        mm_3h = sum(
                            p for t, p in zip(times, precip)
                            if p is not None and t >= three_hours_ago
                        )

                        # Calculate 24h sum
                        twenty_four_hours_ago = (
                            now.timestamp() - 86400
                        )
                        mm_24h = sum(
                            p for t, p in zip(times, precip)
                            if p is not None
                            and datetime.strptime(
                                t, "%Y-%m-%dT%H:%M"
                            ).timestamp() >= twenty_four_hours_ago
                        )

                        if mm_3h > 0:
                            observations.append({
                                "station_id": station["id"],
                                "metric": "rainfall_mm_3h",
                                "value": round(mm_3h, 2),
                                "observed_at": obs_time,
                                "source": self.name,
                                "quality": "ok",
                                "collection_method": "api_poll",
                            })

                        if mm_24h > 0:
                            observations.append({
                                "station_id": station["id"],
                                "metric": "rainfall_mm_24h",
                                "value": round(mm_24h, 2),
                                "observed_at": obs_time,
                                "source": self.name,
                                "quality": "ok",
                                "collection_method": "api_poll",
                            })

            except Exception as exc:
                logger.warning("openmeteo-rt poll failed for %s: %s",
                               station["id"], exc)
                continue

        return observations
