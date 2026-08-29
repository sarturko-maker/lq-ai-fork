"""Attachment fetch + caps — INTAKE-2 (ADR-F086).

Covers both provider shapes the docs describe (the probe-verified presigned
``download_url``, and the raw-``bytes`` return some SDK samples show), the api's
per-item and aggregate caps, and the security invariant that matters most here:
**a presigned download URL is a credential and must never reach a log line.**
"""

from __future__ import annotations

import base64
import logging
import traceback
from typing import Any

import httpx
import pytest

from app.attachments import AttachmentFetcher, AttachmentFetchError
from app.normalize import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS
from app.observability import mute_url_logging
from tests.conftest import INBOX, make_attachment

SECRET_URL = "https://cdn.agentmail.to/attachments/abc?Signature=SUPERSECRETSIG"
MESSAGE_ID = "<CAF-abc123@mail.gmail.com>"


class _FakeAttachmentResponse:
    def __init__(self, download_url: str) -> None:
        self.download_url = download_url

    def model_dump(self) -> dict[str, Any]:
        return {"download_url": self.download_url}


class _FakeMessagesClient:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[tuple[str, str, str]] = []

    async def get_attachment(self, inbox_id: str, message_id: str, attachment_id: str) -> Any:
        self.calls.append((inbox_id, message_id, attachment_id))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeInboxes:
    def __init__(self, messages: _FakeMessagesClient) -> None:
        self.messages = messages


class _FakeClient:
    def __init__(self, response: Any) -> None:
        self.inboxes = _FakeInboxes(_FakeMessagesClient(response))


def _fetcher(response: Any, *, payload: bytes = b"PK\x03\x04docx-bytes") -> AttachmentFetcher:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in {k.lower() for k in request.headers}
        return httpx.Response(200, content=payload)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AttachmentFetcher(client=_FakeClient(response), http=http)  # type: ignore[arg-type]


async def test_download_url_path() -> None:
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    out = await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)
    assert len(out) == 1
    assert base64.b64decode(out[0]["content_b64"]) == b"PK\x03\x04docx-bytes"
    assert out[0]["filename"] == "SecureScan-MSA.docx"


async def test_raw_bytes_fallback_path() -> None:
    """Some SDK samples show ``get_attachment`` handing back bytes directly."""

    fetcher = _fetcher(b"raw-bytes-straight-from-the-sdk")
    out = await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)
    assert base64.b64decode(out[0]["content_b64"]) == b"raw-bytes-straight-from-the-sdk"


async def test_download_url_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """The presigned URL is a credential — it must not reach ANY log line.

    Including ``httpx``'s own ``HTTP Request: GET <full url>`` at INFO, which is
    exactly how this leaked before ``mute_url_logging`` existed. The bridge
    calls it at the composition root; this test asserts the same guarantee.
    """

    mute_url_logging()
    caplog.set_level(logging.DEBUG)
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    await fetcher.fetch_all(
        [make_attachment(), make_attachment(size=MAX_ATTACHMENT_BYTES + 1)],
        inbox_id=INBOX,
        message_id=MESSAGE_ID,
    )
    # Both the formatted message AND every structured `extra` field.
    rendered = "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert SECRET_URL not in rendered
    assert "SUPERSECRETSIG" not in rendered
    assert "cdn.agentmail.to" not in rendered


async def test_filename_falls_back_to_attachment_id() -> None:
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    attachment = make_attachment(filename=None)
    out = await fetcher.fetch_all([attachment], inbox_id=INBOX, message_id=MESSAGE_ID)
    assert out[0]["filename"] == attachment.attachment_id
    assert out[0]["content_type"].endswith("wordprocessingml.document")


async def test_missing_content_type_defaults() -> None:
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    out = await fetcher.fetch_all(
        [make_attachment(content_type=None)], inbox_id=INBOX, message_id=MESSAGE_ID
    )
    assert out[0]["content_type"] == "application/octet-stream"


async def test_declared_oversize_is_skipped_without_downloading() -> None:
    """Skip on the provider's own size metadata — never pull 100 MB to bin it."""

    client_holder = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    out = await client_holder.fetch_all(
        [make_attachment(size=MAX_ATTACHMENT_BYTES + 1), make_attachment()],
        inbox_id=INBOX,
        message_id=MESSAGE_ID,
    )
    # The oversize one is skipped; the whole envelope still lands.
    assert len(out) == 1


async def test_actual_oversize_bytes_are_skipped_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lying ``size`` must not get past the streaming cap.

    The caps are shrunk rather than allocating 25 MB of fixture bytes; what is
    under test is the check, not the constant.
    """

    monkeypatch.setattr("app.attachments.MAX_ATTACHMENT_BYTES", 8)
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL), payload=b"x" * 9)
    out = await fetcher.fetch_all([make_attachment(size=1)], inbox_id=INBOX, message_id=MESSAGE_ID)
    assert out == []


async def test_aggregate_cap_stops_accumulating(monkeypatch: pytest.MonkeyPatch) -> None:
    """Several individually-legal attachments must not add up past the cap."""

    monkeypatch.setattr("app.attachments.MAX_ATTACHMENT_BYTES", 100)
    monkeypatch.setattr("app.attachments.MAX_AGGREGATE_ATTACHMENT_BYTES", 15)
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL), payload=b"y" * 10)

    out = await fetcher.fetch_all(
        [make_attachment(size=10), make_attachment(size=10), make_attachment(size=10)],
        inbox_id=INBOX,
        message_id=MESSAGE_ID,
    )

    # First one fits (10 ≤ 15); the rest would push the total past the cap and
    # are skipped — the envelope still lands rather than 422-ing as a whole.
    assert len(out) == 1


async def test_attachment_count_cap() -> None:
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    out = await fetcher.fetch_all(
        [make_attachment() for _ in range(MAX_ATTACHMENTS + 5)],
        inbox_id=INBOX,
        message_id=MESSAGE_ID,
    )
    assert len(out) == MAX_ATTACHMENTS


async def test_no_attachments_makes_no_calls() -> None:
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL))
    assert await fetcher.fetch_all(None, inbox_id=INBOX, message_id=MESSAGE_ID) == []


async def test_sdk_failure_raises_so_the_delivery_is_retried() -> None:
    fetcher = _fetcher(RuntimeError("provider down"))
    with pytest.raises(AttachmentFetchError):
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)


async def test_response_without_a_url_raises() -> None:
    class _Empty:
        pass

    fetcher = _fetcher(_Empty())
    with pytest.raises(AttachmentFetchError):
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)


async def test_cdn_error_raises() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"expired")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = AttachmentFetcher(
        client=_FakeClient(_FakeAttachmentResponse(SECRET_URL)),  # type: ignore[arg-type]
        http=http,
    )
    with pytest.raises(AttachmentFetchError):
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)


async def test_stream_aborts_instead_of_buffering_past_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The body is abandoned mid-stream, not buffered and then measured.

    On a 6.3 GiB no-swap dev box, ten declared-24 MB attachments buffered before
    the check is 240 MB of resident bytes for nothing.
    """

    monkeypatch.setattr("app.attachments.MAX_ATTACHMENT_BYTES", 10)
    pulled = 0

    async def chunks() -> Any:
        nonlocal pulled
        for _ in range(100):
            pulled += 1
            yield b"z" * 5

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = AttachmentFetcher(
        client=_FakeClient(_FakeAttachmentResponse(SECRET_URL)),  # type: ignore[arg-type]
        http=http,
    )

    out = await fetcher.fetch_all([make_attachment(size=1)], inbox_id=INBOX, message_id=MESSAGE_ID)

    assert out == []
    # 3 chunks = 15 bytes > the 10-byte cap; the other 97 were never pulled.
    assert pulled <= 4


async def test_declared_size_is_checked_against_the_running_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ten legal-sized attachments must not be downloaded to bust the total."""

    monkeypatch.setattr("app.attachments.MAX_ATTACHMENT_BYTES", 100)
    monkeypatch.setattr("app.attachments.MAX_AGGREGATE_ATTACHMENT_BYTES", 12)
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL), payload=b"y" * 10)
    client = fetcher._client.inboxes.messages  # type: ignore[attr-defined]

    out = await fetcher.fetch_all(
        [make_attachment(size=10) for _ in range(5)], inbox_id=INBOX, message_id=MESSAGE_ID
    )

    assert len(out) == 1
    # Only the first attachment was ever requested; the rest failed the
    # declared-size pre-check against the remaining headroom.
    assert len(client.calls) == 1


async def test_counters_split_item_and_aggregate_skips(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("app.attachments.MAX_ATTACHMENT_BYTES", 10)
    monkeypatch.setattr("app.attachments.MAX_AGGREGATE_ATTACHMENT_BYTES", 12)
    caplog.set_level(logging.INFO)
    fetcher = _fetcher(_FakeAttachmentResponse(SECRET_URL), payload=b"y" * 10)

    await fetcher.fetch_all(
        [make_attachment(size=99), make_attachment(size=10), make_attachment(size=10)],
        inbox_id=INBOX,
        message_id=MESSAGE_ID,
    )

    bounded = [r for r in caplog.records if getattr(r, "event", None) == "mail_attachments_bounded"]
    assert bounded[0].skipped_item_cap == 1  # type: ignore[attr-defined]
    assert bounded[0].skipped_aggregate_cap == 1  # type: ignore[attr-defined]


async def test_provider_error_never_leaks_the_url_through_the_exception_chain(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """B2: `raise ... from exc` put the presigned URL in every traceback.

    httpx error strings embed the full request URL, and an unhandled webhook
    error is printed by uvicorn WITH its ``__cause__``/``__context__`` — so the
    signature reached the logs even though no log call of ours mentioned it.
    """

    mute_url_logging()
    caplog.set_level(logging.DEBUG)

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused for {request.url}")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = AttachmentFetcher(
        client=_FakeClient(_FakeAttachmentResponse(SECRET_URL)),  # type: ignore[arg-type]
        http=http,
    )

    with pytest.raises(AttachmentFetchError) as exc_info:
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)

    # Exactly what uvicorn would print for an unhandled error on the webhook.
    rendered = "".join(
        traceback.format_exception(
            type(exc_info.value), exc_info.value, exc_info.value.__traceback__
        )
    )
    rendered += "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)

    assert "SUPERSECRETSIG" not in rendered
    assert "cdn.agentmail.to" not in rendered
    # The type name survives, which is what an operator actually needs.
    assert "ConnectError" in str(exc_info.value)


async def test_http_error_status_never_leaks_the_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"expired")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = AttachmentFetcher(
        client=_FakeClient(_FakeAttachmentResponse(SECRET_URL)),  # type: ignore[arg-type]
        http=http,
    )

    with pytest.raises(AttachmentFetchError) as exc_info:
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)

    rendered = "".join(
        traceback.format_exception(
            type(exc_info.value), exc_info.value, exc_info.value.__traceback__
        )
    )
    assert "SUPERSECRETSIG" not in rendered
    assert "403" in str(exc_info.value)


async def test_sdk_error_never_leaks_through_the_chain() -> None:
    fetcher = _fetcher(RuntimeError(f"boom while calling {SECRET_URL}"))

    with pytest.raises(AttachmentFetchError) as exc_info:
        await fetcher.fetch_all([make_attachment()], inbox_id=INBOX, message_id=MESSAGE_ID)

    rendered = "".join(
        traceback.format_exception(
            type(exc_info.value), exc_info.value, exc_info.value.__traceback__
        )
    )
    assert "SUPERSECRETSIG" not in rendered
