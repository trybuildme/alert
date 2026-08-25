# Deployment & Configuration

Env vars (all optional):
```
EARTHQUAKE_ENABLED=1            EARTHQUAKE_POLL_INTERVAL=300
EARTHQUAKE_MIN_MAGNITUDE=2.5    EARTHQUAKE_LOOKBACK_MINUTES=180
EARTHQUAKE_HISTORY_DAYS=30      EARTHQUAKE_MAX_DEPTH_KM=800
EARTHQUAKE_BBOX=115,4,127,21    NOAH_EQ_DB=backend/data/earthquakes.db
EARTHQUAKE_ALERT_ENABLED=1      NOAH_EQ_ALERT_RULES=/path/rules.json
EARTHQUAKE_WS_ENABLED=1         NOAH_EQ_REF_LAT/LON/RADIUS_KM=15.78/121.55/150
```
Docker: add a volume for `/app/data` so history survives rebuilds.
nginx: SSE needs `proxy_buffering off` for `/api/earthquakes/stream`.

## Public exposure hardening

```
NOAH_AUTH_TOKEN=<secret>         # empty = auth disabled (default)
NOAH_TRUSTED_PROXIES=127.0.0.1,10.0.0.0/8   # XFF trusted from these only
NOAH_ALERT_RETENTION_DAYS=90
```

Auth: when `NOAH_AUTH_TOKEN` is set, every path except `/health`, docs and
`/metrics` requires `Authorization: Bearer <token>` or `?access_token=`(SSE).
Rate limiting resolves the real client IP by walking `X-Forwarded-For`
right-to-left past trusted proxies only — untrusted senders' XFF is ignored.

Config is pydantic-settings (`app/core/config.py`); all historical env
names keep working.

Observability: Prometheus text metrics at `/metrics` (cache hits/misses,
per-provider ingest counters + latency, stored events, SSE clients).
