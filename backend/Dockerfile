FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root runtime; /app/data holds the SQLite DB (mounted volume)
RUN useradd --system --create-home alert \
    && mkdir -p /app/data \
    && chown -R alert:alert /app
USER alert

EXPOSE 8002

# Single worker by DEFAULT and for good reason: the event bus, ingest
# loop, rate limiter and SSE fan-out are in-process. Multiple workers
# would split SSE subscribers across processes that can't see each
# other's events. Raise ALERT_WEB_WORKERS only with that understood.
CMD ["sh", "-c", "exec python -m gunicorn -k uvicorn.workers.UvicornWorker \
    -w ${ALERT_WEB_WORKERS:-1} --graceful-timeout 30 --timeout 120 \
    --max-requests 10000 --max-requests-jitter 1000 \
    -b 0.0.0.0:8002 app.main:app"]
