# Real-Time Protocol (SSE)

`GET /api/earthquakes/stream` (text/event-stream)

Events:
- `hazard.created` — full GeoJSON feature of a newly detected event
- `hazard.alert` — `{event, severity, rule, summary, event_uid}`
- `provider.status` — `{provider, status:"error", detail}` transitions
Keepalive comments every 15 s. Client: browser EventSource auto-reconnect;
frontend adds a 5 s retry guard. The frontend never re-downloads the full
dataset on update — new features are prepended to the existing source.
