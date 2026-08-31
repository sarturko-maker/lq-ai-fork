"""``POST /send`` — the approved-reply egress — INTAKE-2 (ADR-F086) / 4b (F087).

INTAKE-4b wires api → bridge after a human approves a drafted reply. Four
properties are load-bearing: it is gated by the shared bridge token; it is
REPLY-ONLY (no cold send exists to be talked into); a repeated
``idempotency_key`` is refused rather than delivered twice; and the Reply-To
plus-address is composed HERE from the bridge's own inbox, so the caller can
send a matter TAG but never an address.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import _MAX_SEND_BODY, create_app
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


_BODY = {
    "reply_to_provider_message_id": "<CAF-abc123@mail.gmail.com>",
    "text": "Noted, thanks.",
    "idempotency_key": "0f3b8b1e-0000-4000-8000-000000000001",
}
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


def test_unknown_field_rejected() -> None:
    """extra="forbid": a caller cannot smuggle recipients past reply-only."""

    sender = _RecordingSender()
    res = _client(sender).post("/send", json={**_BODY, "to": ["victim@example.com"]}, headers=_AUTH)
    assert res.status_code == 422
    assert sender.requests == []


def test_attachments_field_removed() -> None:
    """F6a: attachments were dead surface — the field is gone and now forbidden."""

    sender = _RecordingSender()
    payload = {
        **_BODY,
        "attachments": [{"filename": "redline.docx", "content_b64": "ZG9jeA=="}],
    }
    res = _client(sender).post("/send", json=payload, headers=_AUTH)
    assert res.status_code == 422
    assert sender.requests == []


def test_oversize_send_body_refused() -> None:
    """F6b: a body over the send cap is refused 413 without being handled."""

    sender = _RecordingSender()
    payload = {**_BODY, "text": "z" * (_MAX_SEND_BODY + 1)}
    res = _client(sender).post("/send", json=payload, headers=_AUTH)
    assert res.status_code == 413
    assert sender.requests == []


def test_empty_text_rejected() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json={**_BODY, "text": ""}, headers=_AUTH)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# INTAKE-4b (ADR-F087): idempotency key + the Reply-To matter tag.
# ---------------------------------------------------------------------------


def test_missing_idempotency_key_rejected() -> None:
    """An unkeyed send cannot be told apart from a repeat, so it is refused."""

    sender = _RecordingSender()
    body = {k: v for k, v in _BODY.items() if k != "idempotency_key"}
    res = _client(sender).post("/send", json=body, headers=_AUTH)
    assert res.status_code == 422
    assert sender.requests == []


def test_oversize_idempotency_key_rejected() -> None:
    sender = _RecordingSender()
    res = _client(sender).post("/send", json={**_BODY, "idempotency_key": "k" * 65}, headers=_AUTH)
    assert res.status_code == 422


def test_reply_to_tag_must_match_the_reference_pattern() -> None:
    """A tag is a matter reference, never a free string — and never an address:
    the plus-address is composed from the bridge's own inbox."""

    sender = _RecordingSender()
    for bad in ("nwt-com-0001", "victim@example.com", "NWT-COM-1", "NWT-COM-0001 x", ""):
        res = _client(sender).post("/send", json={**_BODY, "reply_to_tag": bad}, headers=_AUTH)
        assert res.status_code == 422, bad
    assert sender.requests == []


def test_valid_reply_to_tag_reaches_the_sender() -> None:
    sender = _RecordingSender()
    res = _client(sender).post(
        "/send", json={**_BODY, "reply_to_tag": "NWT-COM-0042"}, headers=_AUTH
    )
    assert res.status_code == 200
    assert sender.requests[0].reply_to_tag == "NWT-COM-0042"


def test_repeated_idempotency_key_is_409_and_sends_once() -> None:
    """The real MailSender over a fake SDK client: the second POST never reaches
    the provider (ADR-F087 — a repeat is refused, never delivered twice)."""

    from app.sender import MailSender

    client = _FakeClient()
    settings = Settings(
        agentmail_api_key="test-agentmail-key",
        agentmail_inbox_address=INBOX,
        lq_ai_backend_url="http://api.test",
        lq_ai_bridge_token=BRIDGE_TOKEN,
    )
    app = create_app(
        settings,
        sender=MailSender(client=client, inbox_id=INBOX),  # type: ignore[arg-type]
        run_subscriber=False,
    )
    with TestClient(app, raise_server_exceptions=False) as http:
        first = http.post("/send", json=_BODY, headers=_AUTH)
        second = http.post("/send", json=_BODY, headers=_AUTH)

    assert first.status_code == 200
    assert second.status_code == 409
    assert len(client.inboxes.messages.calls) == 1


def test_a_different_idempotency_key_still_sends() -> None:
    from app.sender import MailSender

    client = _FakeClient()
    sender = MailSender(client=client, inbox_id=INBOX)  # type: ignore[arg-type]
    settings = Settings(
        agentmail_api_key="test-agentmail-key",
        agentmail_inbox_address=INBOX,
        lq_ai_backend_url="http://api.test",
        lq_ai_bridge_token=BRIDGE_TOKEN,
    )
    app = create_app(settings, sender=sender, run_subscriber=False)
    with TestClient(app, raise_server_exceptions=False) as http:
        assert http.post("/send", json=_BODY, headers=_AUTH).status_code == 200
        assert (
            http.post(
                "/send", json={**_BODY, "idempotency_key": "second-key"}, headers=_AUTH
            ).status_code
            == 200
        )
    assert len(client.inboxes.messages.calls) == 2


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
            idempotency_key="row-1",
        )
    )

    args, kwargs = client.inboxes.messages.calls[0]
    assert args == (INBOX, "<CAF-abc123@mail.gmail.com>")
    assert kwargs["text"] == "Noted, thanks."
    assert "to" not in kwargs and "cc" not in kwargs and "bcc" not in kwargs
    # F6a: the send is text-only — no attachments kwarg is passed at all.
    assert "attachments" not in kwargs
    assert result.provider_thread_id == "2e1c9f73-4e29-424c-8404-c8cd03306c44"
    # The caller's key is handed to the provider's own idempotency guard too.
    assert kwargs["idempotency_key"] == "row-1"
    # No tag ⇒ the kwarg is OMITTED, not sent as an explicit null.
    assert "reply_to" not in kwargs


async def test_sender_composes_the_reply_to_plus_address_from_its_own_inbox() -> None:
    """ADR-F087/F088: the api sends a TAG; the address is ours to build."""

    from app.sender import MailSender, compose_reply_to

    client = _FakeClient()
    sender = MailSender(client=client, inbox_id=INBOX)  # type: ignore[arg-type]
    await sender.reply(
        SendReplyRequest(
            reply_to_provider_message_id="<CAF-abc123@mail.gmail.com>",
            text="Noted.",
            idempotency_key="row-2",
            reply_to_tag="NWT-COM-0042",
        )
    )
    _, kwargs = client.inboxes.messages.calls[0]
    local, _, domain = INBOX.partition("@")
    assert kwargs["reply_to"] == f"{local}+NWT-COM-0042@{domain}"
    assert compose_reply_to("no-at-sign", "NWT-COM-0042") is None
    assert compose_reply_to("@domain.test", "NWT-COM-0042") is None
