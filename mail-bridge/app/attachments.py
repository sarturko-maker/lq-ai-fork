"""Attachment fetch — INTAKE-2 (ADR-F086).

The probe settled the question the research doc could not (docs disagreed):
``inboxes.messages.get_attachment`` returns an ``AttachmentResponse`` whose
``download_url`` is a **presigned CloudFront URL, ~1 h TTL, that needs no
Authorization header** — the URL *is* the credential
(``docs/fork/evidence/intake-probe/findings.md`` §Step-4 / verdict (b)). So:

* the URL is fetched server-side and NEVER logged, persisted, returned to a
  caller, or handed to a browser — **including via an exception chain**: httpx's
  own error strings embed the full URL, so provider exceptions are re-raised
  with ``from None`` and only their type name survives;
* the SDK type-lags the API (undeclared server fields survive ``model_dump()``
  but are invisible to typing — same file, §Step-1), so ``download_url`` is read
  defensively, and the "SDK hands back raw bytes" shape the docs also describe
  is handled rather than assumed away.

Bodies are **streamed with a hard abort** at the caps rather than buffered and
then measured: the dev box is a 6.3 GiB no-swap machine (see the OOM-shield
notes in CLAUDE.md's dev rules), and ten declared-24 MB attachments would
otherwise pull 240 MB into memory before a single byte was rejected. Declared
sizes are checked against the running aggregate before any request is made.

Caps mirror the api's own bounds (``api/app/schemas/intake.py``): an oversize
attachment is skipped with a count-only log, never allowed to 422 the whole
envelope and lose the email.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from agentmail import AsyncAgentMail, Attachment

from .normalize import (
    MAX_AGGREGATE_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    MAX_CONTENT_TYPE_CHARS,
    MAX_FILENAME_CHARS,
    strip_nuls,
)

log = logging.getLogger(__name__)

_DEFAULT_CONTENT_TYPE = "application/octet-stream"


class AttachmentFetchError(RuntimeError):
    """Raised when an attachment's bytes could not be obtained at all.

    Distinct from "skipped because it is too large": a fetch failure means the
    provider or the CDN is unhealthy, so the caller must fail the whole delivery
    and let the redelivery (webhook retry / reconnect reconciliation) try again
    rather than land a silently incomplete matter.

    Its message carries an attachment id and an exception TYPE name only —
    never a URL, never a provider error string.
    """


class _AttachmentTooLarge(Exception):
    """Internal: the download crossed a cap and was aborted mid-stream."""


class AttachmentFetcher:
    """Fetches and base64-encodes an inbound message's attachments.

    Both collaborators are injected — the AgentMail SDK client and the httpx
    client used for the presigned GET — so tests substitute fakes at the same
    seam production uses. Neither is constructed here.
    """

    def __init__(self, *, client: AsyncAgentMail, http: httpx.AsyncClient) -> None:
        self._client = client
        self._http = http

    async def fetch_all(
        self,
        attachments: list[Attachment] | None,
        *,
        inbox_id: str,
        message_id: str,
    ) -> list[dict[str, Any]]:
        """Return envelope-shaped attachment dicts, bounded by the api's caps."""

        if not attachments:
            return []

        out: list[dict[str, Any]] = []
        aggregate = 0
        skipped_item_cap = 0
        skipped_aggregate_cap = 0
        skipped_over_count = max(0, len(attachments) - MAX_ATTACHMENTS)

        for attachment in attachments[:MAX_ATTACHMENTS]:
            # How many more bytes this attachment may contribute: the smaller of
            # what one attachment may be and what is left of the envelope's
            # total. Both caps are therefore enforced by one running limit.
            aggregate_headroom = MAX_AGGREGATE_ATTACHMENT_BYTES - aggregate
            limit = min(MAX_ATTACHMENT_BYTES, aggregate_headroom)
            # Which cap is the binding one, for an honest counter.
            hit_aggregate = aggregate_headroom < MAX_ATTACHMENT_BYTES

            declared = getattr(attachment, "size", None)
            if isinstance(declared, int) and declared > limit:
                # Cheap pre-check on the provider's own metadata: never open a
                # connection for bytes we already know we must discard.
                if hit_aggregate:
                    skipped_aggregate_cap += 1
                else:
                    skipped_item_cap += 1
                continue

            try:
                data = await self._download(
                    inbox_id=inbox_id,
                    message_id=message_id,
                    attachment_id=attachment.attachment_id,
                    limit=limit,
                )
            except _AttachmentTooLarge:
                # A lying `size`: the stream was aborted the moment it crossed
                # the cap, so nothing beyond `limit` bytes was ever buffered.
                if hit_aggregate:
                    skipped_aggregate_cap += 1
                else:
                    skipped_item_cap += 1
                continue

            aggregate += len(data)
            out.append(
                {
                    "filename": _filename(attachment),
                    "content_type": _content_type(attachment),
                    "content_b64": base64.b64encode(data).decode("ascii"),
                }
            )

        if skipped_item_cap or skipped_aggregate_cap or skipped_over_count:
            log.info(
                "mail-bridge: attachments bounded",
                extra={
                    "event": "mail_attachments_bounded",
                    "kept": len(out),
                    "skipped_item_cap": skipped_item_cap,
                    "skipped_aggregate_cap": skipped_aggregate_cap,
                    "skipped_over_count_cap": skipped_over_count,
                    "aggregate_bytes": aggregate,
                },
            )
        return out

    async def _download(
        self, *, inbox_id: str, message_id: str, attachment_id: str, limit: int
    ) -> bytes:
        """One attachment's raw bytes, aborting past ``limit``.

        Handles BOTH documented shapes: the verified ``AttachmentResponse``
        carrying a presigned ``download_url`` (two round-trips), and the raw
        ``bytes`` some SDK samples show (one).
        """

        try:
            response = await self._client.inboxes.messages.get_attachment(
                inbox_id, message_id, attachment_id
            )
        except Exception as exc:
            # `from None`, not `from exc`: a provider/httpx error string can
            # carry a full URL, and a chained cause is printed verbatim by every
            # traceback formatter (uvicorn's included).
            raise AttachmentFetchError(
                f"get_attachment failed for attachment {attachment_id} ({type(exc).__name__})"
            ) from None

        if isinstance(response, bytes | bytearray):
            if len(response) > limit:
                raise _AttachmentTooLarge
            return bytes(response)

        download_url = getattr(response, "download_url", None)
        if not isinstance(download_url, str) or not download_url:
            # Defensive: the SDK's model may lag the API, so also look through
            # the dumped payload before giving up.
            dumped = response.model_dump() if hasattr(response, "model_dump") else {}
            candidate = dumped.get("download_url") if isinstance(dumped, dict) else None
            download_url = candidate if isinstance(candidate, str) else None

        if not download_url:
            raise AttachmentFetchError(
                f"attachment {attachment_id} carried neither bytes nor a download_url"
            )

        return await self._stream(download_url, attachment_id=attachment_id, limit=limit)

    async def _stream(self, download_url: str, *, attachment_id: str, limit: int) -> bytes:
        """GET the presigned URL, aborting the moment ``limit`` is crossed.

        The URL is itself the credential, so no Authorization header is sent —
        and neither the URL nor any provider error string reaches a log line or
        an exception chain.
        """

        chunks: list[bytes] = []
        total = 0
        try:
            async with self._http.stream("GET", download_url) as response:
                if response.status_code >= 400:
                    raise AttachmentFetchError(
                        f"presigned download for attachment {attachment_id} "
                        f"returned HTTP {response.status_code}"
                    )
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        # Leaving the `async with` closes the connection, so the
                        # remaining bytes are never pulled off the wire.
                        raise _AttachmentTooLarge
                    chunks.append(chunk)
        except (_AttachmentTooLarge, AttachmentFetchError):
            raise
        except httpx.HTTPError as exc:
            raise AttachmentFetchError(
                f"presigned download failed for attachment {attachment_id} ({type(exc).__name__})"
            ) from None
        return b"".join(chunks)


def _filename(attachment: Attachment) -> str:
    """Never empty — the api requires ``min_length=1``; fall back to the id."""

    raw = strip_nuls(getattr(attachment, "filename", None) or "").strip()
    return (raw or attachment.attachment_id)[:MAX_FILENAME_CHARS]


def _content_type(attachment: Attachment) -> str:
    raw = strip_nuls(getattr(attachment, "content_type", None) or "").strip()
    return (raw or _DEFAULT_CONTENT_TYPE)[:MAX_CONTENT_TYPE_CHARS]
