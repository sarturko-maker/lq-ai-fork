"""Prod ingress — Svix-verified webhook route — INTAKE-2 (ADR-F086).

Signatures are verified over the RAW request body, so every test posts bytes and
signs those exact bytes. The route exists ONLY when a secret is configured: a
dev deployment must not carry an unauthenticated-by-omission ingress.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from svix.webhooks import Webhook

from app.config import Settings
from app.main import create_app
from app.pipeline import MalformedReceivedEvent
from tests.conftest import BRIDGE_TOKEN, INBOX, WEBHOOK_SECRET, make_message_payload


class _RecordingPipeline:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.events: list[Any] = []
        self._raises = raises

    async def process_event(self, event: object) -> dict[str, Any] | None:
        if self._raises is not None:
            raise self._raises
        self.events.append(event)
        return {"duplicate": False}


def _settings(*, secret: str | None) -> Settings:
    return Settings(
        agentmail_api_key="test-agentmail-key",
        agentmail_inbox_address=INBOX,
        agentmail_webhook_secret=secret,
        lq_ai_backend_url="http://api.test",
        lq_ai_bridge_token=BRIDGE_TOKEN,
    )


def _signed_headers(body: bytes) -> dict[str, str]:
    now = datetime.now(tz=UTC)
    signature = Webhook(WEBHOOK_SECRET).sign("msg_test", now, body.decode())
    return {
        "svix-id": "msg_test",
        "svix-timestamp": str(int(now.timestamp())),
        "svix-signature": signature,
        "content-type": "application/json",
    }


def _received_body(**overrides: Any) -> bytes:
    payload = {
        "type": "event",
        "event_type": "message.received",
        "event_id": "b" * 32,
        "message": make_message_payload(),
        "thread": {
            "inbox_id": INBOX,
            "thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
            "labels": ["received"],
            "timestamp": "2026-08-29T20:14:39Z",
            "senders": ["counsel@example.com"],
            "recipients": [INBOX],
            "message_count": 1,
            "size": 12775,
            "updated_at": "2026-08-29T20:14:40Z",
            "created_at": "2026-08-29T20:14:39Z",
        },
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def _client(pipeline: _RecordingPipeline, *, secret: str | None = WEBHOOK_SECRET) -> TestClient:
    app = create_app(
        _settings(secret=secret),
        pipeline=pipeline,  # type: ignore[arg-type]
        run_subscriber=False,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_route_absent_without_a_secret() -> None:
    """No Svix secret ⇒ dev ⇒ websocket-only; the route is never mounted."""

    client = _client(_RecordingPipeline(), secret=None)
    assert client.post("/agentmail/webhook", content=b"{}").status_code == 404


def test_valid_signature_is_accepted_and_forwarded() -> None:
    pipeline = _RecordingPipeline()
    body = _received_body()
    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=_signed_headers(body))

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert len(pipeline.events) == 1
    assert pipeline.events[0].message.message_id == "<CAF-abc123@mail.gmail.com>"


def test_invalid_signature_rejected() -> None:
    pipeline = _RecordingPipeline()
    body = _received_body()
    headers = _signed_headers(body)
    headers["svix-signature"] = "v1,ZGVmaW5pdGVseSBub3QgdGhlIHNpZ25hdHVyZQ=="

    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=headers)

    assert res.status_code == 400
    assert pipeline.events == []


def test_tampered_body_rejected() -> None:
    """Signing the original and posting a mutated body must not verify."""

    pipeline = _RecordingPipeline()
    body = _received_body()
    headers = _signed_headers(body)

    res = _client(pipeline).post(
        "/agentmail/webhook", content=body.replace(b"Draft NDA", b"Wire funds"), headers=headers
    )

    assert res.status_code == 400
    assert pipeline.events == []


def test_missing_signature_headers_rejected() -> None:
    pipeline = _RecordingPipeline()
    body = _received_body()
    res = _client(pipeline).post(
        "/agentmail/webhook", content=body, headers={"content-type": "application/json"}
    )
    assert res.status_code == 400


@pytest.mark.parametrize("event_type", ["message.sent", "message.delivered", "domain.verified"])
def test_non_received_events_are_a_200_noop(event_type: str) -> None:
    """The loop guard on the prod path — acknowledged, never acted on."""

    pipeline = _RecordingPipeline()
    body = json.dumps({"type": "event", "event_type": event_type, "event_id": "c" * 32}).encode()

    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=_signed_headers(body))

    assert res.status_code == 200
    assert res.json() == {"status": "ignored"}
    assert pipeline.events == []


def test_malformed_json_with_a_valid_signature_is_a_400() -> None:
    pipeline = _RecordingPipeline()
    body = b"not json at all"
    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=_signed_headers(body))
    assert res.status_code == 400


def test_forward_failure_is_a_5xx_so_svix_retries() -> None:
    """A swallowed error here would drop a real email on the floor."""

    pipeline = _RecordingPipeline(raises=RuntimeError("api unreachable"))
    body = _received_body()
    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=_signed_headers(body))
    assert res.status_code >= 500


def test_oversize_body_is_refused_unread() -> None:
    """413 BEFORE the body is read — an unauthenticated caller must not be able
    to make the process buffer arbitrary bytes ahead of the signature check."""

    pipeline = _RecordingPipeline()
    huge = b"x" * 16
    res = _client(pipeline).post(
        "/agentmail/webhook",
        content=huge,
        headers={"content-type": "application/json", "content-length": str(4 * 1024 * 1024)},
    )
    assert res.status_code == 413
    assert pipeline.events == []


def test_signed_but_unreadable_message_is_a_5xx_not_a_silent_ok() -> None:
    """A `message.received` we cannot deserialize is our bug, not junk mail.

    Answering 200 would discard a real email permanently; 5xx makes Svix retry
    so the delivery survives long enough for someone to notice.
    """

    pipeline = _RecordingPipeline(raises=MalformedReceivedEvent("no message"))
    body = json.dumps(
        {"type": "event", "event_type": "message.received", "event_id": "f" * 32}
    ).encode()

    res = _client(pipeline).post("/agentmail/webhook", content=body, headers=_signed_headers(body))

    assert res.status_code >= 500


def test_readyz_reports_status_words_not_exception_text() -> None:
    """A readiness probe is the endpoint most likely to be exposed — an httpx
    error string carries the backend host and port."""

    client = _client(_RecordingPipeline())
    res = client.get("/readyz")
    assert res.status_code == 503
    body = res.json()
    assert body["reason"] in {"backend_unreachable", "backend_unhealthy"}
    assert "api.test" not in json.dumps(body)


def test_readyz_exposes_the_subscription_age() -> None:
    """A silently dead subscription is otherwise invisible: process up, port
    answering, no mail arriving."""

    class _FakeSubscriber:
        def health(self) -> dict[str, object]:
            return {
                "connected": True,
                "seconds_since_connect": 12.0,
                "seconds_since_last_frame": 3.0,
            }

    app = create_app(
        _settings(secret=None),
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        subscriber=_FakeSubscriber(),  # type: ignore[arg-type]
        run_subscriber=False,
    )
    res = TestClient(app, raise_server_exceptions=False).get("/readyz")
    assert res.json()["subscription"]["seconds_since_last_frame"] == 3.0


def test_create_app_mutes_third_party_url_logging() -> None:
    """Composition root must close the httpx full-URL logging leak."""

    _client(_RecordingPipeline())
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


def test_healthz() -> None:
    client = _client(_RecordingPipeline())
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
