"""In-process per-IP rate limiting (no external dependency).

Fixed-window counters keyed by (client IP, bucket). Chosen over token
buckets for zero-dependency simplicity and O(1) memory per active IP;
windows are small so the granularity is fine for protective purposes.

Buckets are matched by path prefix. Tile rendering is deliberately
generous (a single pan fires dozens of tile requests); proxies that fan
out to upstream services (Overpass, NASA, Esri) and alerting endpoints
are tighter.

Trust model: client IP is request.client.host — DIRECT connection only.
Behind a reverse proxy, configure NOAH_TRUSTED_PROXIES with the proxy
IPs/CIDRs; the limiter then walks X-Forwarded-For right-to-left and
takes the first non-trusted address (standard proxy-chain semantics).
Untrusted senders' XFF headers are ignored.

Set NOAH_RATE_LIMIT_ENABLED=0 to disable entirely (e.g., load tests).
"""

from __future__ import annotations

import ipaddress
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# path prefix -> (bucket name, max requests, window seconds)
BUCKETS: list[tuple[str, str, int, int]] = [
    ("/tiles", "tiles", 600, 60),
    ("/api/places", "osm", 60, 60),
    ("/api/roads", "osm", 60, 60),
    ("/api/waterways", "osm", 60, 60),
    ("/api/earthquakes", "eq", 120, 60),
    ("/api/search", "search", 60, 60),
    ("/api/cyclones", "api", 240, 60),
    ("/api/", "api", 240, 60),
]

# Paths never limited (health probes, docs)
EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


class RateLimitState:
    """Fixed-window counters: {(ip, bucket): (window_start, count)}."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, str], tuple[float, int]] = {}

    def check(self, ip: str, bucket: str, max_requests: int,
              window_s: int) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        key = (ip, bucket)
        with self._lock:
            start, count = self._counters.get(key, (now, 0))
            if now - start >= window_s:
                start, count = now, 0
            count += 1
            # Opportunistic cleanup so idle IPs don't accumulate forever
            if len(self._counters) > 10_000:
                self._counters = {
                    k: v for k, v in self._counters.items()
                    if now - v[0] < 300}
            self._counters[key] = (start, count)
            if count > max_requests:
                retry_after = max(1, int(window_s - (now - start)))
                return False, retry_after
            return True, 0


_state = RateLimitState()


def match_bucket(path: str) -> tuple[str, int, int] | None:
    for prefix, name, max_req, window in BUCKETS:
        if path.startswith(prefix):
            return name, max_req, window
    return None


def parse_networks(raw: list[str]) -> list:
    """'1.2.3.4', '10.0.0.0/8', ... -> ipaddress network objects."""
    nets = []
    for item in raw or []:
        try:
            nets.append(ipaddress.ip_network(item.strip(), strict=False))
        except ValueError:
            continue
    return nets


def resolve_client_ip(request: Request, trusted: list) -> str:
    """Real client IP: walk X-Forwarded-For right-to-left, skipping
    trusted proxies. Falls back to the direct peer when no proxy chain
    is configured or the chain is exhausted/untrusted."""
    direct = request.client.host if request.client else "unknown"
    if not trusted:
        return direct
    try:
        peer = ipaddress.ip_address(direct)
    except ValueError:
        return direct
    if not any(peer in net for net in trusted):
        return direct
    xff = request.headers.get("x-forwarded-for", "")
    candidates = [c.strip() for c in xff.split(",") if c.strip()]
    for candidate in reversed(candidates):
        try:
            addr = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(addr in net for net in trusted):
            return str(addr)
    return direct


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True,
                 trusted_proxies: list[str] | None = None):
        super().__init__(app)
        self.enabled = enabled
        self.trusted = parse_networks(trusted_proxies or [])

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)
        bucket = match_bucket(path)
        if bucket is None:
            return await call_next(request)
        name, max_req, window = bucket
        ip = resolve_client_ip(request, self.trusted)
        allowed, retry_after = _state.check(ip, name, max_req, window)
        if not allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)})
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Conservative default headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy",
                                    "strict-origin-when-cross-origin")
        return response
