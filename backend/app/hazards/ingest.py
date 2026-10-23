"""Background ingestion worker: poll providers → validate → normalize →
dedup → persist → publish → alert.

Runs as a single asyncio task owned by the FastAPI lifespan. Provider
failures never crash the loop; they flip provider health to 'error' and
back off exponentially (30 s → 8 min cap) until success. Health is
surfaced by /api/earthquakes/health — the UI's LIVE/STALE badge derives
from this, not from mere frontend connectivity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.hazards.base import EventBus, HazardProvider
from app.hazards.store import EarthquakeStore

logger = logging.getLogger("alert.hazards.ingest")

_BACKOFF_CAP_S = 480


class IngestWorker:
    def __init__(self, providers: list[HazardProvider], store: EarthquakeStore,
                 bus: EventBus, *, poll_interval: int = 300,
                 lookback_minutes: int = 180, min_magnitude: float = 2.5,
                 max_depth_km: float | None = None,
                 reference_point: tuple[float, float] | None = None,
                 rules: list[dict] | None = None,
                 alert_enabled: bool = True,
                 backfill_days: int = 0,
                 on_alert=None):
        self.providers = providers
        self.store = store
        self.bus = bus
        self.poll_interval = max(30, poll_interval)
        self.lookback_minutes = lookback_minutes
        self.min_magnitude = min_magnitude
        self.max_depth_km = max_depth_km
        self.reference_point = reference_point
        self.rules = rules or []
        self.alert_enabled = alert_enabled
        self.backfill_days = max(0, backfill_days)
        # on_alert: async callback(decision, event) provided by API layer
        self.on_alert = on_alert
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._backoff_s = 0
        self.stats: dict[str, dict] = {}
        for p in providers:
            self.stats[p.name] = {"received": 0, "accepted": 0, "duplicates": 0,
                                  "rejected": 0, "last_success": None,
                                  "last_error": None, "last_latency_ms": None}

    # -- health -------------------------------------------------------------

    def health(self) -> dict:
        now = time.time()
        out = {"overall": "stale"}
        freshest = None
        for p in self.providers:
            st = dict(self.stats.get(p.name, {}))
            ph = p.health()
            st.update(ph)
            last = self.stats[p.name]["last_success"]
            if last:
                age_s = now - last
                st["age_seconds"] = int(age_s)
                if age_s < max(self.poll_interval * 2.5, 900):
                    st["state"] = "live"
                else:
                    st["state"] = "stale"
            else:
                st.setdefault("state", "error" if self.stats[p.name]["last_error"] else "starting")
            if st["state"] == "live":
                out["overall"] = "live"
            freshest = max(freshest or 0, last or 0)
        out["last_success_epoch"] = freshest or None
        out["poll_interval"] = self.poll_interval
        return out

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="eq-ingest")
        if self.backfill_days > 0:
            asyncio.create_task(self._backfill_once(), name="eq-backfill")

    async def _backfill_once(self) -> None:
        """One-time historical backfill so the map has context on first
        paint. Silent: no SSE flood, no alert evaluation on history."""
        try:
            totals = await self.poll_once(
                lookback_minutes=self.backfill_days * 1440, publish=False)
            logger.info("earthquake backfill (%sd): %s new, %s updated,"
                        " %s rejected",
                        self.backfill_days, totals["new"], totals["updated"],
                        totals["rejected"])
        except Exception as exc:  # noqa: BLE001 — never block the worker
            logger.error("earthquake backfill failed: %s", exc)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _run(self) -> None:
        logger.info("earthquake ingest worker started (every %ss)",
                    self.poll_interval)
        while not self._stop.is_set():
            try:
                await self.poll_once()
                self._backoff_s = 0
            except Exception as exc:  # noqa: BLE001 — worker must survive
                logger.exception("ingest cycle failed: %s", exc)
            await asyncio.wait_for(self._stop.wait(),
                                   timeout=self.poll_interval + self._backoff_s)

    async def poll_once(self, lookback_minutes: int | None = None,
                        publish: bool = True) -> dict:
        totals = {"new": 0, "updated": 0, "rejected": 0}
        window = lookback_minutes if lookback_minutes is not None \
            else self.lookback_minutes
        for provider in self.providers:
            stats = self.stats[provider.name]
            t0 = time.monotonic()
            try:
                events = await provider.fetch_recent(
                    window, self.min_magnitude)
            except Exception as exc:  # noqa: BLE001
                stats["last_error"] = f"{type(exc).__name__}: {exc}"
                self._backoff_s = min(max(self._backoff_s * 2, 60), _BACKOFF_CAP_S)
                logger.warning("provider %s failed (%s); backoff %ss",
                               provider.name, exc, self._backoff_s)
                self.bus.publish({
                    "event": "provider.status",
                    "provider": provider.name,
                    "status": "error",
                    "detail": str(exc)[:200],
                    "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                continue

            stats["last_latency_ms"] = int((time.monotonic() - t0) * 1000)
            stats["last_success"] = time.time()
            stats["last_error"] = None
            new_events: list = []
            for ev in events:
                stats["received"] += 1
                problems = ev.validate()
                if problems:
                    stats["rejected"] += 1
                    totals["rejected"] += 1
                    logger.warning("rejected %s event: %s", provider.name, problems)
                    continue
                if self.max_depth_km is not None and (
                        ev.depth_km is not None and ev.depth_km > self.max_depth_km):
                    continue
                created = self.store.upsert_event(ev)
                if created:
                    stats["accepted"] += 1
                    totals["new"] += 1
                    new_events.append(ev)
                else:
                    stats["duplicates"] += 1
                    totals["updated"] += 1

            # Publish new events + evaluate alerts (skipped during backfill:
            # history must not flood live subscribers or fire stale alerts)
            for ev in new_events:
                distance_km = None
                if self.reference_point:
                    distance_km = self.store.haversine_km(
                        self.reference_point[0], self.reference_point[1],
                        ev.latitude, ev.longitude)
                if not publish:
                    continue
                payload = {
                    "event": "hazard.created",
                    "hazard": "earthquake",
                    **self._feature(ev, distance_km),
                }
                self.bus.publish(payload)

                if self.alert_enabled and self.rules:
                    from app.hazards.alerts import evaluate_event
                    decisions = evaluate_event(
                        ev, self.rules, self.reference_point,
                        distance_km=distance_km)
                    for d in decisions:
                        self.store.record_alert(d.severity, d.rule_name,
                                                d.summary, d.event_uid)
                        if self.on_alert:
                            try:
                                await self.on_alert(d, ev)
                            except Exception as exc:  # noqa: BLE001
                                logger.error("alert dispatch failed: %s", exc)
        return totals

    @staticmethod
    def _feature(ev, distance_km: float | None = None) -> dict:
        props = {
            "uid": ev.uid,
            "provider": ev.provider,
            "provider_event_id": ev.provider_event_id,
            "origin_time": ev.origin_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "magnitude": ev.magnitude,
            "magnitude_type": ev.magnitude_type,
            "depth_km": ev.depth_km,
            "place": ev.place,
            "region": ev.region,
            "source_url": ev.source_url,
        }
        if distance_km is not None:
            props["distance_km"] = round(distance_km, 1)
        return {
            "properties": props,
            "geometry": {"type": "Point",
                         "coordinates": [ev.longitude, ev.latitude]},
        }
