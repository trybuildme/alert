"""Flood ingestion worker — the pipeline from providers to alerts.

    providers -> poll() -> validate -> dedup(store) -> engine -> alerts

Mirrors hazards/ingest.py: one async loop, per-provider isolation (a
failing feed never blocks others), observations persisted with source
attribution + quality, threshold evaluation after every poll cycle,
alerts deduplicated per station+level and auto-resolved when a station
returns to NORMAL.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.flood.engine import assess_station, load_thresholds
from app.flood.providers.base import FloodProvider
from app.flood.store import FloodStore

logger = logging.getLogger("noah.flood.ingest")

_METRIC_RE = re.compile(r"^(rainfall_mm_h|rainfall_mm_3h|rainfall_mm_24h|"
                        r"water_level_m)$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class FloodIngestWorker:
    def __init__(
        self,
        providers: list[FloodProvider],
        store: FloodStore,
        thresholds_path: str | None = None,
        poll_interval: int = 600,
        alert_enabled: bool = True,
        on_alert=None,           # async fn(alert_dict) -> awaitable | None
    ):
        self._providers = providers
        self._store = store
        self.poll_interval = poll_interval
        self.alert_enabled = alert_enabled
        self._on_alert = on_alert
        self.thresholds = load_thresholds(thresholds_path)
        self.stats: dict[str, dict] = {
            p.name: {"polls": 0, "received": 0, "accepted": 0,
                     "invalid": 0, "last_error": None}
            for p in providers
        }
        self._task: asyncio.Task | None = None

    # -- validation ---------------------------------------------------------

    @staticmethod
    def _validate(obs: dict) -> tuple[bool, str]:
        for key in ("station_id", "metric", "value", "observed_at", "source"):
            if key not in obs or obs[key] is None:
                return False, f"missing {key}"
        if not _METRIC_RE.match(obs["metric"]):
            return False, f"unknown metric {obs['metric']}"
        value = obs["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False, "non-numeric value"
        if value < 0:
            return False, f"negative value {value}"
        # rainfall physically caps far above any real storm; guard junk
        if obs["metric"].startswith("rainfall") and value > 2000:
            return False, f"implausible rainfall {value}"
        if not _ISO_RE.match(obs["observed_at"]):
            return False, f"bad timestamp {obs['observed_at']!r}"
        return True, ""

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.get_event_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — the loop must survive
                logger.error("flood poll cycle failed: %s: %s",
                             type(exc).__name__, exc)
            await asyncio.sleep(self.poll_interval)

    async def poll_once(self) -> dict:
        totals = {"received": 0, "accepted": 0, "alerts": 0}
        for provider in self._providers:
            stats = self.stats.setdefault(
                provider.name,
                {"polls": 0, "received": 0, "accepted": 0,
                 "invalid": 0, "last_error": None})
            try:
                batch = await provider.poll()
                stats["polls"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning("provider %s failed: %s",
                               provider.name, stats["last_error"])
                continue
            stats["last_error"] = None
            accepted_ids: set[str] = set()
            for obs in batch:
                stats["received"] += 1
                ok, why = self._validate(obs)
                if not ok:
                    stats["invalid"] += 1
                    logger.debug("rejected observation (%s): %s", why, obs)
                    continue
                is_new = self._store.insert_observation(
                    station_id=obs["station_id"], metric=obs["metric"],
                    value=obs["value"], observed_at=obs["observed_at"],
                    source=obs["source"],
                    quality=obs.get("quality", "ok"),
                    collection_method=obs.get("collection_method",
                                              "api_poll"))
                if is_new:
                    stats["accepted"] += 1
                    totals["accepted"] += 1
                    accepted_ids.add(obs["station_id"])
            totals["received"] += len(batch)

            # Evaluate thresholds once per affected station per cycle.
            for station_id in accepted_ids:
                station = self._store.get_station(station_id)
                if not station:
                    continue
                metrics = [self._store.latest_observation(station_id, m)
                           for m in ("rainfall_mm_h", "rainfall_mm_3h",
                                     "rainfall_mm_24h", "water_level_m")]
                fresh = [{k: v for k, v in o.items()}
                         for o in metrics if o]
                assessment = assess_station(fresh, self.thresholds,
                                            station["kind"])
                await self._update_alert(station, assessment, totals)
        return totals

    async def _update_alert(self, station: dict, assessment: dict,
                            totals: dict) -> None:
        alert_id = f"flood:{station['id']}"
        level = assessment["level"]
        if level == "NORMAL":
            self._store.resolve_alert(alert_id)
            return
        payload = assessment.get("alert") or {}
        alert = {
            "id": alert_id,
            "station_id": station["id"],
            "level": level,
            "reason": payload.get("reason", ""),
            "measurement": payload.get("measurement"),
            "unit": ("mm" if payload.get("threshold") else None),
            "threshold": payload.get("threshold"),
            "basis": assessment.get("basis", "observed"),
            "source": "noah-flood-engine",
            "recommended_action": assessment["recommended_action"],
        }
        prev_level = self._store.latest_alert_level(alert_id)
        is_new = self._store.upsert_alert(alert)
        if is_new or (prev_level is not None and prev_level != level):
            totals["alerts"] += 1
            logger.info("flood alert %s %s @ %s",
                        level, station["name"], station["id"])
            if self.alert_enabled and self._on_alert:
                result = self._on_alert({**alert,
                                         "station_name": station["name"],
                                         "lat": station["latitude"],
                                         "lon": station["longitude"]})
                if asyncio.iscoroutine(result):
                    await result

    def health(self) -> dict:
        return {
            "providers": {name: dict(s) for name, s in self.stats.items()},
            "poll_interval_s": self.poll_interval,
            "alert_enabled": self.alert_enabled,
        }
