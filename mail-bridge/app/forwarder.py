"""bridge → api envelope forwarding — INTAKE-2 (ADR-F086).

One call: ``POST {LQ_AI_BACKEND_URL}/api/v1/internal/intake/emails`` behind the
shared ``LQ_AI_BRIDGE_TOKEN`` bearer (``require_bridge_auth`` on the api side —
the same bearer the slack-/teams-bridge present). The api owns idempotency: a
redelivery of a message it has already claimed returns ``duplicate: true`` and
uploads nothing, which is exactly what makes this bridge safe to keep
STATELESS — it never has to remember what it has seen.

Log discipline (ADR-F086 security posture; CLAUDE.md audit contract): status,
counts and provider IDs only. No subject, no body, no sender, no attachment
bytes, and never the AgentMail key or a presigned URL.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_INTAKE_PATH = "/api/v1/internal/intake/emails"


class IntakeForwarder:
    """POSTs one normalized envelope to the LQ.AI api."""

    def __init__(self, *, backend_url: str, bridge_token: str, http: httpx.AsyncClient) -> None:
        self._url = backend_url.rstrip("/") + _INTAKE_PATH
        self._token = bridge_token
        self._http = http

    async def forward(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Send the envelope; raise on any non-2xx.

        Raising is load-bearing on the webhook path: a failed forward must
        surface as a 5xx so Svix retries the delivery rather than dropping a
        real email on the floor.
        """

        response = await self._http.post(
            self._url,
            json=envelope,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        message = envelope.get("message", {})
        attachments = message.get("attachments", []) if isinstance(message, dict) else []
        response.raise_for_status()
        body = response.json()
        log.info(
            "mail-bridge: envelope forwarded",
            extra={
                "event": "mail_envelope_forwarded",
                "status": response.status_code,
                "attachments": len(attachments),
                "duplicate": bool(body.get("duplicate")) if isinstance(body, dict) else None,
                "thread_id": body.get("thread_id") if isinstance(body, dict) else None,
                "files_ingested": body.get("files_ingested") if isinstance(body, dict) else None,
            },
        )
        return body if isinstance(body, dict) else {}
