"""Security hardening tests: CORS restriction, rate limiting,
security headers, and input-validation caps."""

import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.ratelimit import RateLimitState, match_bucket
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---- CORS ------------------------------------------------------------------

def test_cors_allows_configured_origin(client):
    origin = settings.CORS_ORIGINS[0]
    r = client.get("/api/products", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin


def test_cors_rejects_unknown_origin(client):
    r = client.get("/api/products", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_not_wildcard_by_default():
    assert "*" not in settings.CORS_ORIGINS


# ---- Security headers --------------------------------------------------------

def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


# ---- Rate limiting ------------------------------------------------------------

def test_match_bucket_prefixes():
    assert match_bucket("/tiles/himawari-clean-ir/4/1/1.png")[0] == "tiles"
    assert match_bucket("/api/places?bbox=1,2,3,4")[0] == "osm"
    assert match_bucket("/api/earthquakes/statistics")[0] == "eq"
    # health/docs exempt from bucket matching entirely
    assert match_bucket("/health") is None


def test_rate_limiter_blocks_after_window_exhausted():
    state = RateLimitState()
    allowed_counts = 0
    for _ in range(5):
        ok, _ = state.check("1.2.3.4", "test", 3, 60)
        allowed_counts += ok
    assert allowed_counts == 3          # first 3 pass, rest blocked
    blocked_ok, retry_after = state.check("1.2.3.4", "test", 3, 60)
    assert not blocked_ok and retry_after >= 1


def test_rate_limiter_isolates_ips_and_buckets():
    state = RateLimitState()
    for _ in range(3):
        state.check("1.1.1.1", "b", 3, 60)
    ok, _ = state.check("1.1.1.1", "b", 3, 60)
    assert not ok                        # same ip+bucket exhausted
    ok, _ = state.check("2.2.2.2", "b", 3, 60)
    assert ok                            # other IP unaffected
    ok, _ = state.check("1.1.1.1", "other", 3, 60)
    assert ok                            # other bucket unaffected


def test_middleware_returns_429_with_retry_after(client, monkeypatch):
    from app.core import ratelimit
    monkeypatch.setattr(ratelimit, "BUCKETS", [
        ("/api/cyclones", "cyclone-test", 2, 60)])
    monkeypatch.setattr(ratelimit, "_state", ratelimit.RateLimitState())

    codes = [client.get("/api/cyclones").status_code for _ in range(4)]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429
    r = client.get("/api/cyclones")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "rate limit" in r.json()["detail"]


def test_rate_limit_enabled_by_default():
    # NOAH_RATE_LIMIT_ENABLED=0 must be the explicit opt-out
    assert settings.RATE_LIMIT_ENABLED is True


# ---- Input validation -------------------------------------------------------

def test_search_query_length_capped(client):
    r = client.get("/api/search?q=" + "x" * 200)
    assert r.status_code == 422          # FastAPI rejects >120 chars


# ---- Trusted proxy X-Forwarded-For resolution ---------------------------------

@pytest.fixture()
def ip_app():
    from fastapi import FastAPI, Request

    from app.core.ratelimit import parse_networks, resolve_client_ip

    probe = FastAPI()

    @probe.get("/ip")
    def ip(request: Request):
        return {"ip": resolve_client_ip(request,
                                        parse_networks(["10.0.0.1",
                                                        "10.0.0.0/8"]))}

    return probe


def test_xff_ignored_without_trusted_proxies(ip_app):
    from app.core.ratelimit import parse_networks, resolve_client_ip
    c = TestClient(ip_app)
    r = c.get("/ip", headers={"X-Forwarded-For": "9.9.9.9"})
    assert r.json()["ip"] != "9.9.9.9"   # direct peer wins when unconfigured
    assert resolve_client_ip  # noqa: B018 (import sanity)


def test_resolve_client_ip_chain_logic():
    from app.core import ratelimit

    class FakeClient:
        def __init__(self, host):
            self.host = host

    class FakeRequest:
        def __init__(self, host, xff=None):
            self.client = FakeClient(host)
            self.headers = {"x-forwarded-for": xff} if xff else {}

    trusted = ratelimit.parse_networks(["10.0.0.0/8"])
    # Direct connection from a non-proxy client: XFF ignored entirely
    assert ratelimit.resolve_client_ip(
        FakeRequest("8.8.8.8", "1.2.3.4"), trusted) == "8.8.8.8"
    # Trusted proxy forwards one hop
    assert ratelimit.resolve_client_ip(
        FakeRequest("10.0.0.5", "1.2.3.4"), trusted) == "1.2.3.4"
    # Chain: proxy -> proxy -> client; rightmost non-trusted wins
    assert ratelimit.resolve_client_ip(
        FakeRequest("10.0.0.5", "10.0.0.6, 1.2.3.4"), trusted) == "1.2.3.4"
    # Spoofing client header through direct connection does nothing
    assert ratelimit.resolve_client_ip(FakeRequest("8.8.8.8"), trusted) \
        == "8.8.8.8"
    # Malformed XFF entries skipped
    assert ratelimit.resolve_client_ip(
        FakeRequest("10.0.0.5", "garbage, 1.2.3.4"), trusted) == "1.2.3.4"
    # All-trusted chain falls back to direct peer
    assert ratelimit.resolve_client_ip(
        FakeRequest("10.0.0.5", "10.0.0.6"), trusted) == "10.0.0.5"


# ---- Auth ---------------------------------------------------------------------

@pytest.fixture()
def auth_app():
    from fastapi import FastAPI

    from app.core.auth import AuthMiddleware

    secured = FastAPI()

    @secured.get("/api/ping")
    def ping():
        return {"ok": True}

    @secured.get("/health")
    def health():
        return {"ok": True}

    secured.add_middleware(AuthMiddleware, token="s3cret")
    return TestClient(secured)


def test_auth_disabled_when_token_empty():
    from fastapi import FastAPI

    from app.core.auth import AuthMiddleware

    open_app = FastAPI()

    @open_app.get("/api/ping")
    def ping():
        return {"ok": True}

    open_app.add_middleware(AuthMiddleware, token="")
    c = TestClient(open_app)
    assert c.get("/api/ping").status_code == 200


def test_auth_rejects_missing_and_wrong_token(auth_app):
    assert auth_app.get("/api/ping").status_code == 401
    assert auth_app.get(
        "/api/ping", headers={"Authorization": "Bearer wrong"}).status_code \
        == 401
    assert auth_app.get("/api/ping?access_token=nope").status_code == 401


def test_auth_accepts_bearer_header_and_query_param(auth_app):
    assert auth_app.get(
        "/api/ping", headers={"Authorization": "Bearer s3cret"}).status_code \
        == 200
    assert auth_app.get("/api/ping?access_token=s3cret").status_code == 200


def test_auth_exempts_health(auth_app):
    assert auth_app.get("/health").status_code == 200


def test_auth_www_authenticate_header(auth_app):
    r = auth_app.get("/api/ping")
    assert r.headers["www-authenticate"] == "Bearer"
