"""bridge → api forwarding — INTAKE-2 (ADR-F086).

The bearer must be present (the api mounts the intake router behind
``require_bridge_auth``), a non-2xx must raise (so the webhook path turns it into
a 5xx Svix retries), and no email content may reach a log line.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from app.forwarder import IntakeForwarder

_ENVELOPE: dict[str, Any] = {
    "provider": "agentmail",
    "inbox_id": "intake@bridge.test",
    "thread": {"provider_thread_id": "t-1", "subject": "Project Atlas NDA"},
    "message": {
        "provider_message_id": "<m-1@example.com>",
        "from_addr": "counsel@example.com",
        "to": ["intake@bridge.test"],
        "cc": [],
        "timestamp": "2026-08-29T20:14:39Z",
        "text": "Confidential deal terms follow.",
        "headers": {},
        "auth_state": "pass",
        "attachments": [{"filename": "a.docx", "content_b64": "AAAA"}],
    },
}


def _forwarder(handler: Any) -> tuple[IntakeForwarder, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    async def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return await handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return (
        IntakeForwarder(
            backend_url="http://api.test/", bridge_token="test-bridge-token", http=http
        ),
        seen,
    )


async def test_posts_to_the_intake_endpoint_with_the_bearer() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"duplicate": False, "files_ingested": 1})

    forwarder, seen = _forwarder(handler)
    body = await forwarder.forward(_ENVELOPE)

    assert body == {"duplicate": False, "files_ingested": 1}
    assert str(seen[0].url) == "http://api.test/api/v1/internal/intake/emails"
    assert seen[0].headers["authorization"] == "Bearer test-bridge-token"


async def test_non_2xx_raises_so_the_delivery_is_retried() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "envelope rejected"})

    forwarder, _ = _forwarder(handler)
    with pytest.raises(httpx.HTTPStatusError):
        await forwarder.forward(_ENVELOPE)


async def test_logs_carry_counts_and_ids_but_never_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"duplicate": True, "thread_id": "uuid-1"})

    caplog.set_level(logging.DEBUG)
    forwarder, _ = _forwarder(handler)
    await forwarder.forward(_ENVELOPE)

    rendered = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "Project Atlas NDA" not in rendered
    assert "Confidential deal terms" not in rendered
    assert "counsel@example.com" not in rendered
    assert "test-bridge-token" not in rendered
    assert "uuid-1" in rendered  # IDs and counts ARE the audit surface
