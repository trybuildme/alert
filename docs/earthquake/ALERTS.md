# Alert Engine

Rules JSON at `NOAH_EQ_ALERT_RULES` (defaults inline). Rule:
```json
{"name": "aurora-close", "severity": "HIGH",
 "all_of": [{"field":"magnitude","op":">=","value":4.5}],
 "any_of": [{"field":"depth_km","op":"<=","value":100}],
 "within_reference_km": 150}
```
Fields: `magnitude`, `depth_km`, `distance_km` (from reference point),
`region`. Ops: `>= <= > < ==`. Severities: INFO LOW MODERATE HIGH CRITICAL.
Reference point: `NOAH_EQ_REF_LAT/LON/RADIUS_KM` (default Aurora Province).

Flow: Event → rules → decision(s) → persisted → NotificationDispatcher →
channels.

## Delivery channels

| Channel | Enable with | Behaviour |
|---|---|---|
| dashboard | always on | rides the SSE event bus |
| email | `NOAH_SMTP_HOST` + `NOAH_SMTP_TO` (optional `NOAH_SMTP_PORT/USER/PASSWORD/FROM`) | SMTP STARTTLS, sent off the event loop |
| webhook | `NOAH_WEBHOOK_URL` | POSTs the alert JSON to any relay |

Channel failures are logged and never break ingestion (`app/hazards/channels.py`).

## Retention

`hazard_alerts` rows older than `NOAH_ALERT_RETENTION_DAYS` (default 90)
are pruned daily by a lifespan task (`EarthquakeStore.prune_alerts`).
