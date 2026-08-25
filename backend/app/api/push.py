"""Web Push subscription management API.

  GET  /api/push/vapid       -> {"public_key": "<b64url>" | null}
  POST /api/push/subscribe   -> {endpoint, keys:{p256dh, auth}}
  POST /api/push/unsubscribe -> {endpoint}

Requires the earthquake module (subscriptions share its SQLite DB).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/api/push")


class SubscriptionBody(BaseModel):
    endpoint: str
    keys: dict


@router.get("/vapid")
async def vapid_public_key() -> dict:
    return {"public_key": settings.VAPID_PUBLIC_KEY or None}


def _store(request: Request):
    eq = getattr(request.app.state, "earthquakes", None)
    if not eq:
        raise HTTPException(503, "hazard module disabled")
    return eq["store"]


@router.post("/subscribe")
async def subscribe(body: SubscriptionBody, request: Request) -> dict:
    p256dh = body.keys.get("p256dh")
    auth = body.keys.get("auth")
    if not body.endpoint or not p256dh or not auth:
        raise HTTPException(422, "subscription requires endpoint + keys")
    # Endpoint is a push-service URL; cap length to bound storage abuse.
    if len(body.endpoint) > 2048 or len(p256dh) > 512 or len(auth) > 512:
        raise HTTPException(422, "subscription fields too long")
    _store(request).save_subscription(body.endpoint, p256dh, auth)
    return {"ok": True}


@router.post("/unsubscribe")
async def unsubscribe(body: SubscriptionBody, request: Request) -> dict:
    removed = _store(request).delete_subscription(body.endpoint)
    return {"ok": True, "removed": removed}
