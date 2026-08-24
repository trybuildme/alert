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
No new Python dependencies.
