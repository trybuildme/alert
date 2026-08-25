"""Web Push delivery channel (browser notifications).

Subscriptions live in push_subscriptions (same SQLite DB as events).
Delivery uses pywebpush (VAPID). Endpoints that answer 404/410 (gone or
expired) are pruned so the list never rots. All network work happens off
the event loop; failures are logged, never raised — ingestion must not
depend on notification success.

Enable with NOAH_VAPID_PRIVATE_KEY + NOAH_VAPID_PUBLIC_KEY (base64url
raw EC keys, generate via py_vapid) and NOAH_VAPID_SUBJECT.
"""

from __future__ import annotations

import asyncio
import json
import logging

from pywebpush import WebPushException, webpush

logger = logging.getLogger("noah.hazards.push")


def send_to_subscription(sub: dict, payload: dict, private_key: str,
                         public_key: str, subject: str) -> bool:
    """Blocking single-target push. Returns False when the endpoint is
    gone and should be pruned. Raises other errors to the caller."""
    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": subject},
        )
        return True
    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        if status in (404, 410):
            return False
        raise


class WebPushChannel:
    def __init__(self, store, private_key: str, public_key: str,
                 subject: str):
        self._store = store
        self._private = private_key
        self._public = public_key
        self._subject = subject

    async def __call__(self, payload: dict) -> int:
        subs = await asyncio.to_thread(self._store.list_subscriptions)
        delivered = 0
        for sub in subs:
            try:
                ok = await asyncio.to_thread(
                    send_to_subscription, sub, payload,
                    self._private, self._public, self._subject)
            except Exception as exc:  # noqa: BLE001 — one bad target ≠ all
                logger.warning("push to %s… failed: %s",
                               sub["endpoint"][:48], exc)
                continue
            if ok:
                delivered += 1
            else:
                logger.info("pruning dead push endpoint %s…",
                            sub["endpoint"][:48])
                await asyncio.to_thread(
                    self._store.delete_subscription, sub["endpoint"])
        return delivered
