"""Prometheus-style /metrics endpoint.

Text exposition (version 0.0.4). Sources:
  - tile cache hit/miss counters (TileCache.stats)
  - per-provider ingest counters + last latency (IngestWorker.stats)
  - stored event total + live SSE subscribers

Best-effort by design: any subsystem that isn't initialised simply
contributes nothing. Exempt from auth and rate limiting (health-tier).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.hazards.store import scalar_count

router = APIRouter()


def _fmt(name: str, value, labels: str = "", help_text: str | None = None,
         metric_type: str = "gauge") -> str:
    out = []
    if help_text:
        out.append(f"# HELP {name} {help_text}")
    out.append(f"# TYPE {name} {metric_type}")
    if isinstance(value, bool):
        value = int(value)
    out.append(f"{name}{labels} {value}")
    return "\n".join(out)


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


@router.get("/metrics", response_class=PlainTextResponse,
            include_in_schema=False)
async def metrics(request: Request) -> str:
    lines: list[str] = []

    cache = getattr(request.app.state, "cache", None)
    if cache is not None:
        stats = getattr(cache, "stats", {})
        lines.append(_fmt("noah_cache_hits_total",
                          stats.get("hits", 0), metric_type="counter"))
        lines.append(_fmt("noah_cache_misses_total",
                          stats.get("misses", 0), metric_type="counter"))

    eq = getattr(request.app.state, "earthquakes", None)
    if eq:
        worker = eq.get("worker")
        if worker is not None:
            for provider_name, st in getattr(worker, "stats", {}).items():
                label = f'{{provider="{_escape(provider_name)}"}}'
                for key in ("received", "accepted", "duplicates", "rejected"):
                    lines.append(_fmt(f"noah_provider_{key}_total",
                                      st.get(key, 0), label,
                                      metric_type="counter"))
                latency = st.get("last_latency_ms")
                if latency is not None:
                    lines.append(_fmt("noah_provider_last_latency_ms",
                                      latency, label))
                last_success = st.get("last_success")
                if last_success is not None:
                    lines.append(_fmt("noah_provider_last_success_timestamp",
                                      int(last_success), label))
        bus = eq.get("bus")
        if bus is not None:
            lines.append(_fmt("noah_stream_clients", bus.subscriber_count))
        store = eq.get("store")
        if store is not None:
            try:
                lines.append(_fmt("noah_earthquake_events_stored",
                                  scalar_count(store)))
            except Exception:  # noqa: BLE001 — metrics must not fail requests
                pass

    return "\n".join(lines) + "\n"
