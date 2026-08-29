"""``POST /send`` — the approved-reply egress — INTAKE-2 (ADR-F086).

Nothing calls this yet; INTAKE-4 wires api → bridge after a human approves a
drafted reply. Two properties are load-bearing today: it is gated by the shared
bridge token, and it is REPLY-ONLY (no cold send exists to be talked into).
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.normalize import MAX_ATTACHMENT_BYTES
from app.schemas import SendReplyRequest, SendReplyResponse
from tests.conftest import BRIDGE_TOKEN, INBOX


class _RecordingSender:
    def __init__(self) -> None:
        self.requests: list[SendReplyRequest] = []

    async def reply(self, request: SendReplyRequest) -> SendReplyResponse:
        self.requests.append(request)
        return SendReplyResponse(
            provider_message_id="<reply-1@email.amazonses.com>",
            provider_thread_id="2e1c9f73-4e29-424c-8404-c8cd03306c44",
        )


def _client(sender: _RecordingSender) -> TestClient:
    settings = Settings(
        agentmail_api_key="test-agentmail-key",
        agentmail_inbox_address=INBOX,
        lq_ai_backend_url="http://api.test",
        lq_ai_bridge_token=BRIDGE_TOKEN,
    )
    app = create_app(settings, sender=sender, run_subscriber=False)  # type: ignore[arg-type]
    return TestClient(app, raise_server_exceptions=False)


_BODY = {"reply_to_provider_message_id": "<CAF-abc123@mail.gmail.com>", "text": "Noted, thanks."}
_AUTH = {"Authorization": f"Bearer {BRIDGE_TOKEN}"}


def test_missing_token_is_401() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json=_BODY)
    assert res.status_code == 401
    assert sender.requests == []


def test_wrong_token_is_401() -> None:
    sender = _RecordingSender()
    res = _client(sender).post(
        "/send", json=_BODY, headers={"Authorization": "Bearer not-the-token"}
    )
    assert res.status_code == 401
    assert sender.requests == []


def test_wrong_scheme_is_401() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json=_BODY, headers={"Authorization": BRIDGE_TOKEN})
    assert res.status_code == 401


def test_non_ascii_token_is_401_not_500() -> None:
    """``hmac.compare_digest`` raises TypeError on non-ASCII str input.

    Sent as raw bytes because that is how such a header actually arrives —
    Starlette latin-1-decodes it into a str with codepoints above 127, which
    would blow up an un-encoded constant-time compare into a 500.
    """

    sender = _RecordingSender()
    res = _client(sender).post(
        "/send", json=_BODY, headers={"Authorization": b"Bearer t\xc3\xb6k\xc3\xa9n"}
    )
    assert res.status_code == 401


def test_happy_path_returns_provider_ids_only() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json=_BODY, headers=_AUTH)

    assert res.status_code == 200
    assert res.json() == {
        "provider_message_id": "<reply-1@email.amazonses.com>",
        "provider_thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
    }
    assert sender.requests[0].reply_to_provider_message_id == "<CAF-abc123@mail.gmail.com>"
    assert sender.requests[0].text == "Noted, thanks."


def test_attachments_round_trip() -> None:
    sender = _RecordingSender()
    payload = {
        **_BODY,
        "attachments": [
            {
                "filename": "redline.docx",
                "content_type": "application/octet-stream",
                "content_b64": base64.b64encode(b"docx").decode(),
            }
        ],
    }
    res = _client(sender).post("/send", json=payload, headers=_AUTH)

    assert res.status_code == 200
    assert sender.requests[0].attachments[0].filename == "redline.docx"


def test_unknown_field_rejected() -> None:
    """extra="forbid": a caller cannot smuggle recipients past reply-only."""

    sender = _RecordingSender()
    res = _client(sender).post("/send", json={**_BODY, "to": ["victim@example.com"]}, headers=_AUTH)
    assert res.status_code == 422
    assert sender.requests == []


def test_oversize_attachment_rejected() -> None:
    sender = _RecordingSender()
    payload = {
        **_BODY,
        "attachments": [
            {
                "filename": "huge.bin",
                "content_b64": base64.b64encode(b"z" * (MAX_ATTACHMENT_BYTES + 1)).decode(),
            }
        ],
    }
    res = _client(sender).post("/send", json=payload, headers=_AUTH)
    assert res.status_code == 422
    assert sender.requests == []


def test_too_many_attachments_rejected() -> None:
    sender = _RecordingSender()
    one = {"filename": "a.bin", "content_b64": base64.b64encode(b"a").decode()}
    res = _client(sender).post("/send", json={**_BODY, "attachments": [one] * 11}, headers=_AUTH)
    assert res.status_code == 422


def test_invalid_base64_rejected() -> None:
    sender = _RecordingSender()
    res = _client(sender).post(
        "/send",
        json={**_BODY, "attachments": [{"filename": "a.bin", "content_b64": "!!!not-b64!!!"}]},
        headers=_AUTH,
    )
    assert res.status_code == 422


def test_empty_text_rejected() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json={**_BODY, "text": ""}, headers=_AUTH)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# MailSender ↔ SDK contract (no network: the client is a fake).
# ---------------------------------------------------------------------------


class _FakeSendResponse:
    message_id = "<reply-1@email.amazonses.com>"
    thread_id = "2e1c9f73-4e29-424c-8404-c8cd03306c44"


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    async def reply(self, *args: str, **kwargs: object) -> _FakeSendResponse:
        self.calls.append((args, kwargs))
        return _FakeSendResponse()


class _FakeInboxes:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


class _FakeClient:
    def __init__(self) -> None:
        self.inboxes = _FakeInboxes()


async def test_sender_calls_reply_keyed_by_message_id_only() -> None:
    """Reply is keyed by message_id; recipients are deliberately NOT passed."""

    from app.sender import MailSender

    client = _FakeClient()
    sender = MailSender(client=client, inbox_id=INBOX)  # type: ignore[arg-type]

    result = await sender.reply(
        SendReplyRequest(
            reply_to_provider_message_id="<CAF-abc123@mail.gmail.com>",
            text="Noted, thanks.",
            attachments=[
                {  # type: ignore[list-item]
                    "filename": "redline.docx",
                    "content_type": "application/octet-stream",
                    "content_b64": base64.b64encode(b"docx").decode(),
                }
            ],
        )
    )

    args, kwargs = client.inboxes.messages.calls[0]
    assert args == (INBOX, "<CAF-abc123@mail.gmail.com>")
    assert kwargs["text"] == "Noted, thanks."
    assert "to" not in kwargs and "cc" not in kwargs and "bcc" not in kwargs
    attachments = kwargs["attachments"]
    assert isinstance(attachments, list)
    assert attachments[0].filename == "redline.docx"
    assert result.provider_thread_id == "2e1c9f73-4e29-424c-8404-c8cd03306c44"
