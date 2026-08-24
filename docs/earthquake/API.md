# Earthquake REST + Stream API

| Endpoint | Purpose |
|---|---|
| `GET /api/earthquakes` | Filtered, paginated FeatureCollection. Params: days(1-3650), min/max_magnitude, min/max_depth, provider, bbox=w,s,e,n, limit(≤5000), offset |
| `GET /api/earthquakes/recent?hours=24` | Convenience recent window |
| `GET /api/earthquakes/{provider:event_id}` | Full detail; optional latitude/longitude → distance_from_reference_km |
| `GET /api/earthquakes/nearby?latitude&longitude&radius_km&days` | Exact haversine radius query (bbox prefilter), nearest first |
| `GET /api/earthquakes/region?...` | Historical regional counts by magnitude band |
| `GET /api/earthquakes/statistics` | Live dashboard numbers + 7-day magnitude histogram from real rows |
| `GET /api/earthquakes/alerts?limit=` | Persisted alert decisions |
| `GET /api/earthquakes/health` | Provider health: overall live/stale, per-provider state, stream client count |
| `GET /api/earthquakes/stream` | SSE: `hazard.created`, `hazard.alert`, `provider.status`, 15 s keepalives |

All responses are DETECTED EVENTS only — no forecasts/predictions.
