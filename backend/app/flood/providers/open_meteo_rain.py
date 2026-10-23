"""REAL rainfall provider — Open-Meteo hourly precipitation.

https://api.open-meteo.com/v1/forecast?latitude=&longitude=
    &hourly=precipitation&past_hours=48&forecast_hours=1

Open-Meteo aggregates national weather models + Copernicus ERA5/
GFS; precipitation is genuine model data, not synthesized. Free,
no API key, ~10k calls/day fair-use. We poll each registered rainfall
station's coordinates and derive:

    rainfall_mm_h   latest complete hour
    rainfall_mm_3h  rolling 3-hour sum
    rainfall_mm_24h rolling 24-hour sum

observed_at uses the hour-ending timestamp of the newest sample so the
value is attributed to the interval it represents.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("alert.flood.openmeteo")

UPSTREAM = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoRainProvider:
    name = "open-meteo"

    def __init__(self, stations: list[dict], timeout: float = 15.0):
        # Only stations whose registry entry declares this provider.
        self._stations = [s for s in stations if s.get("provider") == self.name]
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def parse_payload(payload: dict) -> dict[str, float]:
        """hourly.time[] -> hourly.precipitation[] mapping.

        Exposed for tests; raises ValueError on malformed payloads."""
        try:
            times = payload["hourly"]["time"]
            precip = payload["hourly"]["precipitation"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"malformed open-meteo payload: {exc}") from exc
        if len(times) != len(precip):
            raise ValueError("time/precipitation length mismatch")
        out: dict[str, float] = {}
        for ts, mm in zip(times, precip):
            if mm is None:
                continue
            out[ts] = float(mm)
        return out

    @staticmethod
    def derive_metrics(hourly: dict[str, float]) -> list[dict]:
        """Convert the hourly series into normalized observations."""
        # Defensive re-filter: callers may hand us raw payloads with
        # None (partial current hour). Newest COMPLETE hour wins.
        series = [(t, v) for t, v in sorted(hourly.items())
                  if v is not None]
        if not series:
            return []
        stamps = [t for t, _ in series]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        latest_ts = next(
            (t for t in reversed(stamps) if t <= now), stamps[-1])
        idx = stamps.index(latest_ts)

        def window_sum(n: int) -> tuple[float, str]:
            lo = max(0, idx - n + 1)
            vals = [v for t, v in series[lo:idx + 1]]
            total = round(sum(vals), 2)
            start_stamp = series[lo][0]
            return total, start_stamp

        mm_h, _ = window_sum(1)
        mm_3h, _ = window_sum(3)
        mm_24h, _start24 = window_sum(24)

        def iso(stamp: str) -> str:
            dt = datetime.strptime(stamp, "%Y-%m-%dT%H:%M") \
                .replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        obs_time = iso(latest_ts)
        out = [
            {"metric": "rainfall_mm_h", "value": mm_h,
             "observed_at": obs_time},
            {"metric": "rainfall_mm_3h", "value": mm_3h,
             "observed_at": obs_time},
            {"metric": "rainfall_mm_24h", "value": mm_24h,
             "observed_at": obs_time},
        ]
        return out

    async def poll(self) -> list[dict]:
        observations: list[dict] = []
        for station in self._stations:
            try:
                resp = await self._client.get(UPSTREAM, params={
                    "latitude": f"{station['latitude']:.4f}",
                    "longitude": f"{station['longitude']:.4f}",
                    "hourly": "precipitation",
                    "past_hours": 48,
                    "forecast_hours": 1,
                })
                resp.raise_for_status()
                hourly = self.parse_payload(resp.json())
                for obs in self.derive_metrics(hourly):
                    observations.append({
                        "station_id": station["id"],
                        "source": self.name,
                        **obs,
                    })
            except Exception as exc:  # noqa: BLE001 — per-station isolation
                logger.warning("open-meteo poll failed for %s: %s: %s",
                               station["id"], type(exc).__name__,
                               exc or "(no message)")
                continue
        return observations
