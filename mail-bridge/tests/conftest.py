"""Test fixtures for the LQ.AI Mail Bridge — INTAKE-2.

``app/main.py`` constructs the FastAPI ``app`` object at module import time
(``app = create_app()``), which calls ``Settings()`` and fails if the operator
hasn't set the required provider/LQ.AI env vars. Tests must not depend on a real
AgentMail account, so this conftest seeds the process environment with safe
fixture values BEFORE pytest collects any test that imports from ``app.main``.

Individual tests build their own app via ``create_app(settings=…, pipeline=…)``
to inject fakes; the env seeding here only keeps the module-level line from
crashing on import.

**No fixture value is a real credential** — the AgentMail key exists only in the
running service's environment (ADR-F086), never in this repo.
"""

from __future__ import annotations

import base64
import os
from typing import Any

_TEST_DEFAULTS = {
    "AGENTMAIL_API_KEY": "test-agentmail-key",
    "AGENTMAIL_INBOX_ADDRESS": "intake@bridge.test",
    "LQ_AI_BACKEND_URL": "http://api.test",
    "LQ_AI_BRIDGE_TOKEN": "test-bridge-token",
}

for key, value in _TEST_DEFAULTS.items():
    os.environ.setdefault(key, value)

# The webhook route must be absent unless a test asks for it — never inherit a
# secret from the developer's shell.
os.environ.pop("AGENTMAIL_WEBHOOK_SECRET", None)

import pytest  # noqa: E402
from agentmail import Attachment, Message, MessageReceivedEvent  # noqa: E402
from agentmail.core.unchecked_base_model import construct_type  # noqa: E402

from app.config import Settings  # noqa: E402

INBOX = "intake@bridge.test"
BRIDGE_TOKEN = "test-bridge-token"

#: A base64 secret in the shape Svix hands out. Fixture-only, not a credential.
WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"lq-ai-mail-bridge-test-secret!!!").decode()


def make_message_payload(**overrides: Any) -> dict[str, Any]:
    """The wire shape of one inbound AgentMail message (probe-derived)."""

    payload: dict[str, Any] = {
        "inbox_id": INBOX,
        "thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
        "message_id": "<CAF-abc123@mail.gmail.com>",
        "labels": ["received", "unread"],
        "timestamp": "2026-08-29T20:14:39.514000Z",
        "from": "Counterparty <counsel@example.com>",
        "to": [INBOX],
        "subject": "Draft NDA for review",
        "text": "Please review the attached NDA.",
        "size": 12775,
        "updated_at": "2026-08-29T20:14:40Z",
        "created_at": "2026-08-29T20:14:39Z",
    }
    payload.update(overrides)
    return payload


def make_message(**overrides: Any) -> Message:
    """A typed ``Message``, built the way the SDK builds one off the wire."""

    message = construct_type(type_=Message, object_=make_message_payload(**overrides))
    assert isinstance(message, Message)
    return message


def make_attachment(**overrides: Any) -> Attachment:
    payload: dict[str, Any] = {
        "attachment_id": "ea77d0f0-1111-2222-3333-444455556666",
        "filename": "SecureScan-MSA.docx",
        "size": 37998,
        "content_type": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "content_disposition": "attachment",
    }
    payload.update(overrides)
    attachment = construct_type(type_=Attachment, object_=payload)
    assert isinstance(attachment, Attachment)
    return attachment


def make_received_event(**message_overrides: Any) -> MessageReceivedEvent:
    payload = {
        "type": "event",
        "event_type": "message.received",
        "event_id": "9f0c1b2a3d4e5f60718293a4b5c6d7e8",
        "message": make_message_payload(**message_overrides),
        "thread": {
            "inbox_id": INBOX,
            "thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
            "labels": ["received", "unread"],
            "timestamp": "2026-08-29T20:14:39.514000Z",
            "senders": ["counsel@example.com"],
            "recipients": [INBOX],
            "subject": "Draft NDA for review",
            "message_count": 1,
            "size": 12775,
            "updated_at": "2026-08-29T20:14:40Z",
            "created_at": "2026-08-29T20:14:39Z",
        },
    }
    event = construct_type(type_=MessageReceivedEvent, object_=payload)
    assert isinstance(event, MessageReceivedEvent)
    return event


@pytest.fixture
def settings() -> Settings:
    return Settings(
        agentmail_api_key="test-agentmail-key",
        agentmail_inbox_address=INBOX,
        agentmail_webhook_secret=None,
        lq_ai_backend_url="http://api.test",
        lq_ai_bridge_token=BRIDGE_TOKEN,
    )
