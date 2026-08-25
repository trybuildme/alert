"""Optional shared-token auth for public exposure.

Disabled by default (NOAH_AUTH_TOKEN empty). When set, every request
outside EXEMPT_PREFIXES must present the token via:

  - "Authorization: Bearer <token>" header, or
  - "?access_token=<token>" query parameter (EventSource/SSE cannot set
    custom headers).

Comparison is constant-time. The middleware sits innermost so 401
responses still traverse CORS and security-headers middleware.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/metrics")


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("access_token")


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str = ""):
        super().__init__(app)
        self.token = token.encode() if token else b""

    async def dispatch(self, request: Request, call_next):
        if not self.token:
            return await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return await call_next(request)
        presented = _extract_token(request)
        if presented is None or not hmac.compare_digest(
                presented.encode(), self.token):
            return JSONResponse(
                {"detail": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"})
        return await call_next(request)
