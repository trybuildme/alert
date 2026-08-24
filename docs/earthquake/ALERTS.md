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
channels (today: dashboard via SSE; sirens/email/SMS subscribe later).
