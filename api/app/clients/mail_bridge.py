"""api → mail-bridge ``POST /send`` client — INTAKE-4b (ADR-F087).

The ONE outbound leg email intake adds to ``api/``. It carries the bridge token
the api already holds for the other direction and nothing else: **no AgentMail
credential ever exists in this process** (ADR-F086 — the gateway key-holder
pattern applied to email), and no recipient address is ever sent. The bridge
derives recipients from the message being answered, so a compromised or
mis-prompted agent cannot use this path to mail a third party.

Design notes:

* **No retries, anywhere.** A retry loop around an email send is how a
  counterparty receives the same letter three times. One attempt; a failure is
  reported honestly to the caller, which records it and stops (ADR-F087).
* **Idempotency key = the ASK, not the attempt.** The caller derives it from the
  human-approved call's checkpointed tool-call id (``intake_tools._send_key``), so
  a re-execution of the same ask presents the same key. The bridge rejects a repeat
  with 409, which surfaces here as :class:`BridgeSendError` with reason
  ``duplicate`` — never as a second send.
* **Errors carry a CLASS, never a body.** ``reason`` is one of a closed set of
  short tokens (``http_502``, ``timeout``, ``transport``, ``duplicate``,
  ``unexpected``); a provider error string can quote the message, the address or
  the subject, and those must not reach a log line, an audit row or a DB column.
* One reply per run at most, so a pooled client buys nothing: each call opens
  and closes its own ``httpx.AsyncClient`` unless one is injected. Nothing is
  left open in a worker that may be cancelled mid-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

#: A send is one small JSON POST; the provider call behind it is the slow part.
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class SentReply:
    """What the bridge gives back — provider identifiers only, never content."""

    provider_message_id: str
    provider_thread_id: str


class BridgeSendError(Exception):
    """A send that did not happen. ``reason`` is an error CLASS, never a body."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BridgeClient(Protocol):
    """The seam the intake tool depends on (tests substitute a fake)."""

    async def send_reply(
        self,
        *,
        reply_to_provider_message_id: str,
        idempotency_key: str,
        text: str,
        reply_to_tag: str | None = None,
    ) -> SentReply:
        """Send one human-approved reply, or raise :class:`BridgeSendError`."""
        ...  # pragma: no cover - protocol


class MailBridgeClient:
    """HTTP implementation of :class:`BridgeClient`."""

    def __init__(
        self,
        base_url: str,
        bridge_token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bridge_token = bridge_token
        self._timeout = timeout
        self._http = http

    async def send_reply(
        self,
        *,
        reply_to_provider_message_id: str,
        idempotency_key: str,
        text: str,
        reply_to_tag: str | None = None,
    ) -> SentReply:
        payload: dict[str, object] = {
            "reply_to_provider_message_id": reply_to_provider_message_id,
            "idempotency_key": idempotency_key,
            "text": text,
        }
        if reply_to_tag is not None:
            # The TAG only — the bridge composes the plus-address from its own
            # inbox address. Neither the api nor the agent may choose a Reply-To.
            payload["reply_to_tag"] = reply_to_tag
        headers = {"Authorization": f"Bearer {self._bridge_token}"}
        try:
            if self._http is not None:
                response = await self._http.post(
                    f"{self._base_url}/send", json=payload, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/send", json=payload, headers=headers
                    )
        except httpx.TimeoutException as exc:
            raise BridgeSendError("timeout") from exc
        except (httpx.HTTPError, OSError) as exc:
            # The exception text can carry the bridge host/port — the CLASS only.
            raise BridgeSendError("transport") from exc

        if response.status_code == 409:
            raise BridgeSendError("duplicate")
        if response.status_code >= 400:
            raise BridgeSendError(f"http_{response.status_code}")
        try:
            body = response.json()
            return SentReply(
                provider_message_id=str(body["provider_message_id"]),
                provider_thread_id=str(body["provider_thread_id"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            # A 2xx we cannot read means the mail may well have gone out — we
            # simply do not know its id. Report it as a failure (the human sees
            # "not sent"), never as a success with a made-up id.
            raise BridgeSendError("unexpected") from exc


def build_mail_bridge_client() -> BridgeClient | None:
    """Provider-callable default for the composition point (tests inject a fake).

    ``None`` when the deployment has not configured the bridge (no URL or no
    token): the tool then records the draft with ``send_error='not_configured'``
    and says plainly that nothing was delivered. Failing honestly beats an
    unauthenticated POST into the void.
    """
    from app.config import get_settings

    settings = get_settings()
    base_url = settings.lq_ai_mail_bridge_url.strip()
    token = settings.lq_ai_bridge_token.strip()
    if not base_url or not token:
        logger.warning(
            "mail-bridge send is not configured; approved replies cannot be delivered",
            extra={"event": "mail_bridge_not_configured", "has_url": bool(base_url)},
        )
        return None
    return MailBridgeClient(base_url, token)


__all__ = [
    "BridgeClient",
    "BridgeSendError",
    "MailBridgeClient",
    "SentReply",
    "build_mail_bridge_client",
]
