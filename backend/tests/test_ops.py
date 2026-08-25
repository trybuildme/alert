"""Ops-surface tests: /metrics exposition, hazard_alerts retention,
and notification delivery channels."""

import json

import httpx
import pytest
from starlette.testclient import TestClient

from app.hazards.channels import EmailChannel, WebhookChannel
from app.hazards.store import EarthquakeStore
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---- /metrics -----------------------------------------------------------------

def test_metrics_endpoint_prometheus_format(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    lines = r.text.strip().splitlines()
    # every non-comment line is name value
    samples = [ln for ln in lines if ln and not ln.startswith("#")]
    assert samples, "expected at least one metric sample"
    for ln in samples:
        parts = ln.rsplit(" ", 1)
        assert len(parts) == 2, f"malformed sample: {ln}"
        float(parts[1])


def test_metrics_exposes_cache_counters(client):
    r = client.get("/metrics")
    assert "noah_cache_hits_total" in r.text
    assert "noah_cache_misses_total" in r.text


def test_metrics_exposes_ingest_and_store_when_eq_enabled(client):
    r = client.get("/metrics")
    if 'provider=' in r.text:
        # Worker has not polled in tests (network blocked), so counters
        # exist but latency/success gauges may not have fired yet.
        assert "# TYPE noah_provider_received_total counter" in r.text
    assert "noah_earthquake_events_stored" in r.text
    assert "noah_stream_clients" in r.text


# ---- alert retention ------------------------------------------------------------

@pytest.fixture()
def tmp_store(tmp_path):
    return EarthquakeStore(str(tmp_path / "eq.db"))


def test_prune_alerts_removes_only_old_rows(tmp_store):
    store = tmp_store
    store.record_alert("HIGH", "rule-a", "summary", "uid-1")
    store.record_alert("INFO", "rule-b", "summary", "uid-2")
    # Backdate the first row beyond any sane retention window
    with store._lock, store._conn:
        store._conn.execute(
            "UPDATE hazard_alerts SET created_at = ? WHERE event_uid = ?",
            ("2000-01-01T00:00:00Z", "uid-1"))

    removed = store.prune_alerts(older_than_days=90)
    assert removed == 1
    with store._lock:
        remaining = store._conn.execute(
            "SELECT event_uid FROM hazard_alerts").fetchall()
    assert [r["event_uid"] for r in remaining] == ["uid-2"]
    store.close()


def test_prune_alerts_noop_when_young(tmp_store):
    store = tmp_store
    store.record_alert("MODERATE", "rule", "summary", "uid-1")
    assert store.prune_alerts(older_than_days=90) == 0
    store.close()


# ---- channels ---------------------------------------------------------------------

def test_webhook_channel_posts_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = WebhookChannel("https://relay.example/hook", client=client)

    payload = {"event": "hazard.alert", "severity": "HIGH",
               "summary": "M6.1 — somewhere"}
    run(coro_send(channel, payload))

    assert seen["url"] == "https://relay.example/hook"
    assert seen["body"]["severity"] == "HIGH"


def coro_send(channel, payload):
    return channel(payload)


def run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def test_email_channel_builds_message():
    channel = EmailChannel("smtp.example", 587, "noah@example",
                           "secret", "alerts@example",
                           ["a@example", "b@example"])
    msg = channel._build_message({
        "event": "hazard.alert", "severity": "CRITICAL",
        "rule": "major-quake-global", "summary": "M7.2 — Eastern Visayas",
    })
    assert msg["From"] == "alerts@example"
    assert msg["To"] == "a@example, b@example"
    assert "CRITICAL" in msg["Subject"]
    body = msg.get_content().strip()
    assert "summary: M7.2 — Eastern Visayas" in body
