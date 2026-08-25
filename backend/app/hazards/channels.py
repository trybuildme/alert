"""Notification delivery channels beyond the dashboard SSE bus.

Each channel is an async callable taking the alert payload dict;
failures are logged by the dispatcher and never break ingestion.

  - EmailChannel: SMTP with STARTTLS; blocking smtplib calls are pushed
    to a worker thread so the event loop never stalls. Enabled when
    NOAH_SMTP_HOST and NOAH_SMTP_TO are both set.
  - WebhookChannel: POSTs the JSON payload to a generic relay URL
    (Discord/Slack-compatible adapters or any receiver). Enabled when
    NOAH_WEBHOOK_URL is set.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

logger = logging.getLogger("noah.hazards.channels")


class EmailChannel:
    def __init__(self, host: str, port: int, user: str, password: str,
                 from_addr: str, to_addrs: list[str]):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr or user
        self._to = to_addrs

    def _build_message(self, payload: dict) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = f"[NOAH {payload.get('severity', 'INFO')}] {payload.get('summary', 'hazard alert')}"
        msg["From"] = self._from
        msg["To"] = ", ".join(self._to)
        body = "\n".join(
            f"{key}: {value}" for key, value in sorted(payload.items()))
        msg.set_content(body + "\n\n— NOAH hazard monitor\n")
        return msg

    def _send_sync(self, payload: dict) -> None:
        msg = self._build_message(payload)
        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except smtplib.SMTPNotSupportedError:
                logger.warning("SMTP server did not offer STARTTLS; "
                               "continuing in plaintext")
            if self._user and self._password:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)

    async def __call__(self, payload: dict) -> None:
        await asyncio.to_thread(self._send_sync, payload)


class WebhookChannel:
    def __init__(self, url: str, client: httpx.AsyncClient | None = None):
        self._url = url
        self._client = client

    async def __call__(self, payload: dict) -> None:
        if self._client is not None:
            response = await self._client.post(self._url, json=payload)
            response.raise_for_status()
            return
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self._url, json=payload)
            response.raise_for_status()
